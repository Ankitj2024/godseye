"""Local -> Modal transport.

This is the entire boundary between the control plane and the compute plane:

* files move through a Modal Volume (``godseye-jobs`` by default)
* stages are invoked as deployed Modal Functions, looked up by name
* every worker returns the same ``RemoteStageResult`` dict shape

Because artifacts live on the Volume, a downstream worker can consume an
upstream worker's output without a local round-trip.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from godseye.config import ModalSettings
from godseye.errors import RemoteStageError, RemoteTransportError
from godseye.schemas.remote import RemoteStageResult
from godseye.utils.fs import ensure_dir, human_bytes, iter_files
from godseye.utils.logging import get_logger

logger = get_logger("remote")

_DEPLOY_HINT = (
    "Deploy the compute plane first:  modal deploy modal_app/app.py\n"
    "Then verify it with:             python run_pipeline.py doctor"
)


def _format_elapsed(seconds: float) -> str:
    """Format an elapsed duration as a compact human-readable string."""
    if seconds >= 60:
        m = int(seconds // 60)
        s = seconds % 60
        return f"{m}m {s:.1f}s"
    return f"{seconds:.1f}s"



@dataclass
class TransferReport:
    file_count: int
    total_bytes: int

    @property
    def human_total(self) -> str:
        return human_bytes(self.total_bytes)


def _import_modal() -> Any:
    try:
        import modal  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RemoteTransportError(
            "The `modal` package is required for remote stages. "
            "Install it with `pip install -r requirements.txt`."
        ) from exc
    return modal


class ModalTransport:
    """Volume-backed file staging plus deployed-function invocation."""

    def __init__(self, settings: ModalSettings, job_id: str) -> None:
        self.settings = settings
        self.job_id = job_id
        self._volume: Any = None
        self._functions: dict[str, Any] = {}

    # -- remote path helpers ----------------------------------------------

    @property
    def job_prefix(self) -> str:
        return f"/{self.settings.jobs_prefix.strip('/')}/{self.job_id}"

    def remote_path(self, *parts: str) -> str:
        tail = "/".join(part.strip("/") for part in parts if part)
        return f"{self.job_prefix}/{tail}" if tail else self.job_prefix

    # -- volume ------------------------------------------------------------

    @property
    def volume(self) -> Any:
        if self._volume is None:
            modal = _import_modal()
            try:
                self._volume = modal.Volume.from_name(
                    self.settings.volume_name,
                    environment_name=self.settings.environment,
                    create_if_missing=True,
                )
            except Exception as exc:  # noqa: BLE001
                raise RemoteTransportError(
                    f"Could not open Modal Volume '{self.settings.volume_name}': {exc}\n"
                    "Check that you are authenticated (`modal token new`)."
                ) from exc
        return self._volume

    def upload_dir(self, local_dir: Path, remote_dir: str) -> TransferReport:
        """Upload every file under ``local_dir`` to ``remote_dir``."""
        if not local_dir.exists():
            raise RemoteTransportError(f"Nothing to upload, missing directory: {local_dir}")

        files = list(iter_files(local_dir))
        if not files:
            raise RemoteTransportError(f"Nothing to upload, directory is empty: {local_dir}")

        total_bytes = sum(f.stat().st_size for f in files)
        logger.info(
            "Uploading %d files (%s) -> volume:%s",
            len(files),
            human_bytes(total_bytes),
            remote_dir,
        )
        try:
            with self.volume.batch_upload(force=True) as batch:
                batch.put_directory(str(local_dir), remote_dir)
        except Exception as exc:  # noqa: BLE001
            raise RemoteTransportError(
                f"Upload to volume path '{remote_dir}' failed: {exc}"
            ) from exc

        return TransferReport(file_count=len(files), total_bytes=total_bytes)

    def upload_file(self, local_file: Path, remote_file: str) -> TransferReport:
        if not local_file.is_file():
            raise RemoteTransportError(f"Nothing to upload, missing file: {local_file}")
        size = local_file.stat().st_size
        logger.info("Uploading %s (%s) -> volume:%s", local_file.name, human_bytes(size), remote_file)
        try:
            with self.volume.batch_upload(force=True) as batch:
                batch.put_file(str(local_file), remote_file)
        except Exception as exc:  # noqa: BLE001
            raise RemoteTransportError(f"Upload of '{local_file}' failed: {exc}") from exc
        return TransferReport(file_count=1, total_bytes=size)

    def download_prefix(self, remote_dir: str, local_dir: Path) -> TransferReport:
        """Mirror a volume prefix into ``local_dir``, preserving structure."""
        modal = _import_modal()
        from modal.volume import FileEntryType  # noqa: PLC0415

        ensure_dir(local_dir)
        normalized = remote_dir.rstrip("/")

        try:
            entries = self.volume.listdir(normalized, recursive=True)
        except modal.exception.NotFoundError as exc:
            raise RemoteTransportError(
                f"Volume path '{normalized}' does not exist. The worker reported success "
                "but produced no output directory."
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise RemoteTransportError(f"Could not list volume path '{normalized}': {exc}") from exc

        file_entries = [e for e in entries if e.type == FileEntryType.FILE]
        if not file_entries:
            raise RemoteTransportError(
                f"Volume path '{normalized}' contains no files to download."
            )

        total_bytes = 0
        for entry in file_entries:
            relative = entry.path[len(normalized) :].lstrip("/")
            destination = local_dir / relative
            ensure_dir(destination.parent)
            try:
                with destination.open("wb") as handle:
                    for chunk in self.volume.read_file(entry.path):
                        handle.write(chunk)
            except Exception as exc:  # noqa: BLE001
                raise RemoteTransportError(
                    f"Download of '{entry.path}' failed: {exc}"
                ) from exc
            total_bytes += destination.stat().st_size

        logger.info(
            "Downloaded %d files (%s) from volume:%s",
            len(file_entries),
            human_bytes(total_bytes),
            normalized,
        )
        return TransferReport(file_count=len(file_entries), total_bytes=total_bytes)

    def remove_prefix(self, remote_dir: str) -> None:
        """Best-effort cleanup of a volume prefix, used before forced reruns."""
        modal = _import_modal()
        try:
            self.volume.remove_file(remote_dir.rstrip("/"), recursive=True)
        except modal.exception.NotFoundError:
            return
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not remove volume prefix %s: %s", remote_dir, exc)

    # -- function invocation ----------------------------------------------

    def _lookup(self, function_name: str) -> Any:
        if function_name in self._functions:
            return self._functions[function_name]

        modal = _import_modal()
        try:
            handle = modal.Function.from_name(
                self.settings.app_name,
                function_name,
                environment_name=self.settings.environment,
            )
            # from_name() is lazy; hydrate here so a missing deployment fails with
            # an actionable message instead of surfacing mid-invocation.
            handle.hydrate()
        except modal.exception.NotFoundError as exc:
            raise RemoteTransportError(
                f"Modal function '{function_name}' not found in app "
                f"'{self.settings.app_name}'.\n{_DEPLOY_HINT}\n\nUnderlying error: {exc}"
            ) from exc
        except modal.exception.AuthError as exc:
            raise RemoteTransportError(
                f"Modal authentication failed: {exc}\nRun `modal token new`."
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise RemoteTransportError(
                f"Could not resolve Modal function '{function_name}': {exc}\n{_DEPLOY_HINT}"
            ) from exc

        self._functions[function_name] = handle
        return handle

    def ensure_function(self, function_name: str) -> None:
        """Resolve a worker up front.

        Called before staging inputs so a missing deployment does not cost a
        multi-hundred-megabyte upload first.
        """
        self._lookup(function_name)

    def call(self, function_name: str, payload: dict[str, Any]) -> RemoteStageResult:
        """Invoke a deployed worker and validate its result envelope.

        Uses ``spawn`` plus polling rather than a blocking ``remote`` call.
        Reconstruction can run for hours, and a blocking call ties the job's
        survival to an uninterrupted client connection: when the client-side
        deadline expires, Modal cancels the input and the work is thrown away.
        """
        call_id = self.spawn(function_name, payload)
        return self.poll(function_name, call_id)

    def spawn(self, function_name: str, payload: dict[str, Any]) -> str:
        """Start a worker and return its function-call id."""
        modal = _import_modal()
        handle = self._lookup(function_name)
        logger.info("Spawning Modal function '%s'", function_name)

        try:
            call = handle.spawn(payload)
        except Exception as exc:  # noqa: BLE001
            raise RemoteTransportError(
                f"Could not start Modal function '{function_name}': {exc}"
            ) from exc

        logger.info("Modal call id: %s", call.object_id)
        del modal
        return call.object_id

    def poll(
        self,
        function_name: str,
        call_id: str,
        poll_interval: float = 20.0,
    ) -> RemoteStageResult:
        """Wait for a spawned call, logging progress, and validate the result."""
        modal = _import_modal()

        try:
            call = modal.FunctionCall.from_id(call_id)
        except Exception as exc:  # noqa: BLE001
            raise RemoteTransportError(
                f"Could not reattach to Modal call '{call_id}': {exc}"
            ) from exc

        deadline = self.settings.call_timeout_seconds
        started = time.monotonic()
        raw: Any = None

        while True:
            elapsed = time.monotonic() - started
            if elapsed > deadline:
                raise RemoteStageError(
                    f"Modal function '{function_name}' exceeded the local wait budget of "
                    f"{deadline}s. The remote call {call_id} may still be running; "
                    "reattach with `python run_pipeline.py resume <job_id>`.",
                    exception_type="LocalWaitTimeout",
                )
            try:
                raw = call.get(timeout=poll_interval)
                break
            except modal.exception.OutputExpiredError as exc:
                raise RemoteStageError(
                    f"Result for Modal call '{call_id}' has expired and cannot be "
                    "retrieved. Rerun the stage with --force-stage.",
                    exception_type="OutputExpiredError",
                ) from exc
            except (modal.exception.TimeoutError, TimeoutError, ConnectionError):
                logger.info(
                    "Still running '%s' (%s elapsed, call %s)",
                    function_name,
                    _format_elapsed(elapsed + poll_interval),
                    call_id,
                )
                continue
            except modal.exception.FunctionTimeoutError as exc:
                raise RemoteStageError(
                    f"Modal function '{function_name}' hit its own timeout: {exc}",
                    exception_type="FunctionTimeoutError",
                ) from exc
            except modal.exception.RemoteError as exc:
                raise RemoteStageError(
                    f"Modal function '{function_name}' failed remotely: {exc}",
                    exception_type="RemoteError",
                ) from exc
            except Exception as exc:  # noqa: BLE001
                raise RemoteTransportError(
                    f"Waiting on Modal function '{function_name}' failed: "
                    f"{type(exc).__name__}: {exc!r}"
                ) from exc

        if not isinstance(raw, dict):
            raise RemoteStageError(
                f"Worker '{function_name}' returned {type(raw).__name__}, expected a dict "
                "matching the RemoteStageResult contract.",
                exception_type="ContractViolation",
            )

        try:
            result = RemoteStageResult.model_validate(raw)
        except Exception as exc:  # noqa: BLE001
            raise RemoteStageError(
                f"Worker '{function_name}' returned a malformed result: {exc}",
                exception_type="ContractViolation",
            ) from exc

        if not result.ok:
            error = result.error
            raise RemoteStageError(
                error.message if error else f"Worker '{function_name}' reported failure.",
                exception_type=error.exception_type if error else "RemoteStageError",
                traceback_text=error.traceback if error else None,
                failed_command=error.failed_command if error else None,
                log_tail=error.log_tail if error else [],
                remote_logs=result.logs,
            )

        logger.info(
            "Modal function '%s' completed in %s",
            function_name,
            _format_elapsed(time.monotonic() - started),
        )
        return result

    def ping(self) -> dict[str, Any]:
        """Round-trip check used by ``godseye doctor``."""
        result = self.call(self.settings.ping_function, {"job_id": self.job_id})
        return {"worker": result.worker, "metrics": result.metrics, "notes": result.notes}

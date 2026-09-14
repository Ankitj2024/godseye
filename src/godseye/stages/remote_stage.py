"""Shared behaviour for stages that execute on Modal.

Every remote stage follows the same shape: stage inputs onto the Volume, invoke
a deployed worker, mirror the worker's output prefix back into the job folder,
and register what came back. Centralising that here keeps individual remote
stages small and keeps the local/remote contract in exactly one place.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from godseye.pipeline.context import StageContext
from godseye.pipeline.stage import Stage, StageOutcome
from godseye.remote.transport import ModalTransport
from godseye.schemas.enums import ArtifactKind, ExecutionTarget, Provenance
from godseye.schemas.remote import RemoteStageResult
from godseye.utils.fs import reset_dir


def artifact_kind_from_string(value: str) -> ArtifactKind:
    """Map a worker-declared kind onto the local enum, defaulting to metadata."""
    try:
        return ArtifactKind(value)
    except ValueError:
        return ArtifactKind.METADATA


class RemoteStage(Stage):
    """Base class for Modal-backed stages."""

    target: ClassVar[ExecutionTarget] = ExecutionTarget.MODAL

    #: Attribute on ``ModalSettings`` holding this stage's function name.
    function_setting: ClassVar[str]

    #: Name of this stage's directory inside the volume job prefix.
    remote_output_name: ClassVar[str]

    #: Provenance applied to artifacts this stage brings back.
    provenance: ClassVar[Provenance] = Provenance.OBSERVED

    # -- subclass hooks ----------------------------------------------------

    def stage_inputs(self, ctx: StageContext, transport: ModalTransport) -> dict[str, Any]:
        """Upload whatever the worker needs. Returns metrics about the transfer."""
        return {}

    def build_payload(self, ctx: StageContext, transport: ModalTransport) -> dict[str, Any]:
        raise NotImplementedError

    def local_output_dir(self, ctx: StageContext) -> Path:
        return ctx.paths.stage_dir(self.name)

    def enrich(
        self,
        ctx: StageContext,
        result: RemoteStageResult,
        outcome: StageOutcome,
        local_dir: Path,
    ) -> None:
        """Optional post-download hook for stage-specific bookkeeping."""

    # -- execution ---------------------------------------------------------

    def function_name(self, ctx: StageContext) -> str:
        return getattr(ctx.config.modal, self.function_setting)

    def run(self, ctx: StageContext) -> StageOutcome:
        log = ctx.logger(self.name)
        transport = ctx.remote
        function_name = self.function_name(ctx)

        # Fail fast on a missing/unreachable deployment before uploading anything.
        transport.ensure_function(function_name)

        upload_metrics = self.stage_inputs(ctx, transport)
        payload = self.build_payload(ctx, transport)

        log.info("Dispatching '%s' to Modal function '%s'", self.name.value, function_name)
        result = transport.call(function_name, payload)

        output_prefix = result.output_prefix or transport.remote_path(self.remote_output_name)
        local_dir = reset_dir(self.local_output_dir(ctx))
        transfer = transport.download_prefix(output_prefix, local_dir)

        metrics: dict[str, Any] = {
            **upload_metrics,
            **result.metrics,
            "downloaded_files": transfer.file_count,
            "downloaded_bytes": transfer.total_bytes,
            "remote_output_prefix": output_prefix,
        }
        if result.worker:
            metrics["worker"] = result.worker

        outcome = StageOutcome(metrics=metrics, notes=list(result.notes))
        self._register_remote_artifacts(ctx, result, outcome, local_dir, output_prefix)
        self.enrich(ctx, result, outcome, local_dir)
        return outcome

    def _register_remote_artifacts(
        self,
        ctx: StageContext,
        result: RemoteStageResult,
        outcome: StageOutcome,
        local_dir: Path,
        output_prefix: str,
    ) -> None:
        registered: set[str] = set()

        for artifact in result.artifacts:
            relative = artifact.relative_path.lstrip("/")
            local_path = local_dir / relative
            if not local_path.exists():
                continue
            registered.add(relative)
            outcome.add_artifact(
                local_path,
                artifact_kind_from_string(artifact.kind),
                provenance=self.provenance,
                artifact_id=f"{self.name.value}:{relative}",
                metadata={
                    "remote_path": artifact.remote_path,
                    "remote_sha256": artifact.sha256,
                    **artifact.metadata,
                },
            )

        for remote_log in result.logs:
            relative = remote_log[len(output_prefix) :].lstrip("/") if remote_log.startswith(
                output_prefix
            ) else Path(remote_log).name
            local_path = local_dir / relative
            if local_path.exists() and relative not in registered:
                registered.add(relative)
                outcome.add_artifact(
                    local_path,
                    ArtifactKind.LOG,
                    artifact_id=f"{self.name.value}:{relative}",
                    compute_hash=False,
                )

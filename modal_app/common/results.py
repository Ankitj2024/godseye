"""Result envelope construction.

Every worker returns the same dict shape so the local transport can validate one
contract instead of one per stage. See ``godseye.schemas.remote``.
"""

from __future__ import annotations

import hashlib
import platform
import socket
import subprocess
import traceback
from pathlib import Path
from typing import Any

from modal_app.common.shell import CommandError
from modal_app.common.volumes import to_volume_path

_HASH_LIMIT_BYTES = 512 * 1024 * 1024


def sha256_file(path: Path, limit: int = _HASH_LIMIT_BYTES) -> str | None:
    """Hash a file unless it is large enough that hashing costs real time."""
    if path.stat().st_size > limit:
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def worker_info(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    info: dict[str, Any] = {
        "hostname": socket.gethostname(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "gpu": _gpu_name(),
    }
    if extra:
        info.update(extra)
    return info


def _gpu_name() -> str | None:
    try:
        output = subprocess.run(  # noqa: S603
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    name = output.stdout.strip().splitlines()
    return name[0].strip() if name else None


def artifact(
    file_path: Path,
    output_root: Path,
    kind: str,
    metadata: dict[str, Any] | None = None,
    compute_hash: bool = True,
) -> dict[str, Any]:
    """Describe one produced file relative to the stage output root."""
    relative = file_path.relative_to(output_root).as_posix()
    return {
        "remote_path": to_volume_path(file_path),
        "relative_path": relative,
        "kind": kind,
        "size_bytes": file_path.stat().st_size,
        "sha256": sha256_file(file_path) if compute_hash else None,
        "metadata": metadata or {},
    }


def collect_logs(log_dir: Path) -> list[str]:
    if not log_dir.exists():
        return []
    return [to_volume_path(p) for p in sorted(log_dir.glob("*.log"))]


def success(
    stage: str,
    output_prefix: str,
    metrics: dict[str, Any],
    artifacts: list[dict[str, Any]],
    logs: list[str] | None = None,
    notes: list[str] | None = None,
    worker: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "status": "completed",
        "worker": worker or worker_info(),
        "metrics": metrics,
        "artifacts": artifacts,
        "output_prefix": output_prefix,
        "logs": logs or [],
        "notes": notes or [],
        "error": None,
    }


def failure(
    stage: str,
    exc: BaseException,
    output_prefix: str | None = None,
    logs: list[str] | None = None,
    metrics: dict[str, Any] | None = None,
    worker: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Report failure as data, not as a raised exception.

    Returning a structured failure lets the local side record which command
    broke and where its log lives, instead of just seeing a stack trace.
    """
    failed_command = exc.command if isinstance(exc, CommandError) else None
    log_tail = exc.tail if isinstance(exc, CommandError) else []

    return {
        "stage": stage,
        "status": "failed",
        "worker": worker or worker_info(),
        "metrics": metrics or {},
        "artifacts": [],
        "output_prefix": output_prefix,
        "logs": logs or [],
        "notes": [],
        "error": {
            "exception_type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
            "failed_command": failed_command,
            "log_tail": log_tail[-25:],
        },
    }

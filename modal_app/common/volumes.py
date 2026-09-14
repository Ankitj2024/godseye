"""Shared Volume definition and container path translation.

The local client addresses files by *volume* path (``/jobs/<id>/frames``).
Inside a container the same file lives under the mount point
(``/vol/jobs/<id>/frames``). Everything crossing that boundary goes through
these helpers rather than string concatenation at the call site.
"""

from __future__ import annotations

from pathlib import Path

import modal

from modal_app.common.config import VOLUME_MOUNT, VOLUME_NAME

jobs_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

MOUNT_ROOT = Path(VOLUME_MOUNT)


def to_container_path(volume_path: str) -> Path:
    """``/jobs/x/frames`` -> ``/vol/jobs/x/frames``"""
    return MOUNT_ROOT / volume_path.lstrip("/")


def to_volume_path(container_path: Path) -> str:
    """``/vol/jobs/x/frames`` -> ``/jobs/x/frames``"""
    resolved = Path(container_path)
    try:
        return "/" + resolved.relative_to(MOUNT_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()

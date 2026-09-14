"""Connectivity diagnostics worker.

A deliberately trivial function on a tiny image. ``godseye doctor`` calls it to
prove the whole remote path works - auth, app lookup, Volume mount, result
contract - before anyone waits on a multi-hour COLMAP job.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import modal

from modal_app.common.app import app
from modal_app.common.config import VOLUME_MOUNT, WORKER_PYTHON_VERSION
from modal_app.common.results import success, worker_info
from modal_app.common.volumes import jobs_volume

STAGE = "diagnostics"

diagnostics_image = (
    modal.Image.debian_slim(python_version=WORKER_PYTHON_VERSION)
    .env({"PYTHONUNBUFFERED": "1"})
    .add_local_python_source("modal_app")
)


@app.function(
    image=diagnostics_image,
    timeout=120,
    volumes={VOLUME_MOUNT: jobs_volume},
)
def ping(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Confirm the worker runs and the jobs Volume is mounted and writable."""
    payload = payload or {}
    mount = Path(VOLUME_MOUNT)

    probe_file = mount / ".godseye_healthcheck"
    writable = True
    try:
        probe_file.write_text("ok\n", encoding="utf-8")
        probe_file.unlink(missing_ok=True)
    except OSError:
        writable = False

    return success(
        stage=STAGE,
        output_prefix=None,
        metrics={
            "volume_mounted": mount.exists(),
            "volume_writable": writable,
            "job_id": payload.get("job_id"),
        },
        artifacts=[],
        notes=["Remote round-trip succeeded."],
        worker=worker_info(),
    )

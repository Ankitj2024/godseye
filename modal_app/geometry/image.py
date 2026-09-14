"""Geometry post-processing worker image.

Open3D and trimesh are pinned here rather than in the local requirements for a
concrete reason: Open3D publishes no Python 3.13 wheels, so a controlled 3.11
worker image is the only reproducible way to run it.
"""

from __future__ import annotations

import modal

from modal_app.common.config import OPEN3D_VERSION, TRIMESH_VERSION, WORKER_PYTHON_VERSION

geometry_image = (
    modal.Image.debian_slim(python_version=WORKER_PYTHON_VERSION)
    # Open3D links against GL/OpenMP even for headless point-cloud work.
    .apt_install("libgl1", "libgomp1", "libusb-1.0-0", "libx11-6")
    .pip_install(
        "numpy>=2.0,<3.0",
        f"open3d=={OPEN3D_VERSION}",
        f"trimesh=={TRIMESH_VERSION}",
        "pygltflib>=1.16,<2.0",
    )
    .env({"PYTHONUNBUFFERED": "1"})
    .add_local_python_source("modal_app")
)

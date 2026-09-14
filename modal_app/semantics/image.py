"""Semantic detection worker image."""

from __future__ import annotations

import modal

from modal_app.common.config import OPEN3D_VERSION, WORKER_PYTHON_VERSION

semantic_image = (
    modal.Image.debian_slim(python_version=WORKER_PYTHON_VERSION)
    .apt_install("libgl1", "libgomp1", "libusb-1.0-0", "libx11-6")
    .pip_install(
        "numpy>=2.0,<3.0",
        "pillow>=10.0,<11.0",
        "scipy>=1.11,<2.0",
        f"open3d=={OPEN3D_VERSION}",
        "torch>=2.2,<3.0",
        "torchvision>=0.17,<1.0",
        "transformers>=4.38,<5.0",
    )
    .env({"PYTHONUNBUFFERED": "1"})
    .add_local_python_source("modal_app")
)

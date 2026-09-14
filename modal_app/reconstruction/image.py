"""COLMAP worker image.

Built from the official COLMAP CUDA image rather than compiling from source:

* the published image is reproducible and pinned by tag
* it is built with CUDA support, which dense stereo requires
* it avoids a ~30 minute source build on every image cache miss

The image ships no usable Python, so a standalone interpreter is added. To swap
in a source build later, replace only this module: nothing else in the pipeline
depends on how the image was produced.
"""

from __future__ import annotations

import modal

from modal_app.common.config import COLMAP_IMAGE_TAG, WORKER_PYTHON_VERSION

colmap_image = (
    modal.Image.from_registry(
        f"colmap/colmap:{COLMAP_IMAGE_TAG}",
        add_python=WORKER_PYTHON_VERSION,
    )
    .env(
        {
            # COLMAP links Qt; without this it tries to reach a display server
            # and aborts in a headless container.
            "QT_QPA_PLATFORM": "offscreen",
            "PYTHONUNBUFFERED": "1",
        }
    )
    .add_local_python_source("modal_app")
)

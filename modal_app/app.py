"""Deploy entrypoint for the God's Eye compute plane.

    modal deploy modal_app/app.py

Importing the worker modules here is what registers their functions on the App.
The App itself lives in ``modal_app.common.app`` so workers can import it without
a circular dependency on this module.
"""

from __future__ import annotations

from modal_app.common.app import app
from modal_app.completion.worker import complete_generative_scene
from modal_app.depth.worker import enhance_depth
from modal_app.diagnostics import ping
from modal_app.geometry.worker import postprocess_geometry
from modal_app.reconstruction.worker import reconstruct_exact
from modal_app.semantics.worker import detect_semantics

__all__ = [
    "app",
    "complete_generative_scene",
    "detect_semantics",
    "enhance_depth",
    "ping",
    "postprocess_geometry",
    "reconstruct_exact",
]


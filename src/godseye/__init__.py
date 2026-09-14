"""God's Eye: drone video to 3D scene pipeline.

The local package is the control plane. It validates input, prepares job
directories, selects keyframes, dispatches compute-heavy stages to Modal, and
packages final deliverables into ``outputs/<job_id>/``.
"""

__version__ = "0.1.0"

MANIFEST_SCHEMA_VERSION = 1

__all__ = ["__version__", "MANIFEST_SCHEMA_VERSION"]

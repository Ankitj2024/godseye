"""Worker-side configuration.

Kept independent of the local ``godseye`` package so worker images never need to
install or version-match the control plane. Overridable via environment
variables at deploy time.
"""

from __future__ import annotations

import os

APP_NAME = os.environ.get("GODSEYE_MODAL_APP_NAME", "godseye")
VOLUME_NAME = os.environ.get("GODSEYE_MODAL_VOLUME_NAME", "godseye-jobs")

#: Where the jobs Volume is mounted inside every container.
VOLUME_MOUNT = "/vol"

#: Pinned COLMAP image. Tags are date-based builds published by the COLMAP team;
#: `latest` is deliberately avoided so a redeploy cannot silently change the
#: reconstruction toolchain.
COLMAP_IMAGE_TAG = os.environ.get("GODSEYE_COLMAP_TAG", "20260729.7651")

#: Python added on top of the COLMAP CUDA image, which ships no usable Python.
WORKER_PYTHON_VERSION = os.environ.get("GODSEYE_WORKER_PYTHON", "3.11")

COLMAP_GPU = os.environ.get("GODSEYE_COLMAP_GPU", "A10G")
COLMAP_CPU = float(os.environ.get("GODSEYE_COLMAP_CPU", "8.0"))
COLMAP_MEMORY_MB = int(os.environ.get("GODSEYE_COLMAP_MEMORY_MB", "32768"))
COLMAP_TIMEOUT_SECONDS = int(os.environ.get("GODSEYE_COLMAP_TIMEOUT", str(6 * 60 * 60)))

GEOMETRY_CPU = float(os.environ.get("GODSEYE_GEOMETRY_CPU", "8.0"))
GEOMETRY_MEMORY_MB = int(os.environ.get("GODSEYE_GEOMETRY_MEMORY_MB", "32768"))
GEOMETRY_TIMEOUT_SECONDS = int(os.environ.get("GODSEYE_GEOMETRY_TIMEOUT", str(2 * 60 * 60)))

OPEN3D_VERSION = os.environ.get("GODSEYE_OPEN3D_VERSION", "0.19.0")
TRIMESH_VERSION = os.environ.get("GODSEYE_TRIMESH_VERSION", "4.7.4")

DEPTH_GPU = os.environ.get("GODSEYE_DEPTH_GPU", "A10G")
DEPTH_CPU = float(os.environ.get("GODSEYE_DEPTH_CPU", "4.0"))
DEPTH_MEMORY_MB = int(os.environ.get("GODSEYE_DEPTH_MEMORY_MB", "16384"))
DEPTH_TIMEOUT_SECONDS = int(os.environ.get("GODSEYE_DEPTH_TIMEOUT", str(2 * 60 * 60)))

SEMANTIC_GPU = os.environ.get("GODSEYE_SEMANTIC_GPU", "A10G")
SEMANTIC_CPU = float(os.environ.get("GODSEYE_SEMANTIC_CPU", "4.0"))
SEMANTIC_MEMORY_MB = int(os.environ.get("GODSEYE_SEMANTIC_MEMORY_MB", "16384"))
SEMANTIC_TIMEOUT_SECONDS = int(os.environ.get("GODSEYE_SEMANTIC_TIMEOUT", str(2 * 60 * 60)))

COMPLETION_CPU = float(os.environ.get("GODSEYE_COMPLETION_CPU", "4.0"))
COMPLETION_MEMORY_MB = int(os.environ.get("GODSEYE_COMPLETION_MEMORY_MB", "16384"))
COMPLETION_TIMEOUT_SECONDS = int(os.environ.get("GODSEYE_COMPLETION_TIMEOUT", str(2 * 60 * 60)))


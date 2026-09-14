"""Canonical enums for the God's Eye pipeline.

These values are part of the on-disk contract: they appear in ``manifest.json``,
in stage directory names, and in the remote worker payloads. Treat renames as
breaking changes and bump ``MANIFEST_SCHEMA_VERSION``.
"""

from __future__ import annotations

from enum import Enum


class PipelineMode(str, Enum):
    """Reconstruction mode requested by the user."""

    EXACT = "exact"
    GENERATIVE = "generative"


class StageName(str, Enum):
    """Every stage the pipeline knows about, implemented or planned.

    The string value doubles as the per-stage working directory name where a
    stage owns its own folder.
    """

    JOB_SETUP = "job_setup"
    FRAME_EXTRACTION = "frame_extraction"
    KEYFRAME_SELECTION = "keyframe_selection"
    RECONSTRUCTION_EXACT = "reconstruction_exact"
    GEOMETRY_POSTPROCESS = "geometry_postprocess"
    DEPTH_ENHANCEMENT = "depth_enhancement"
    SEMANTIC_DETECTION = "semantic_detection"
    SCENE_GRAPH = "scene_graph"
    GENERATIVE_COMPLETION = "generative_completion"
    OUTPUT_PACKAGING = "output_packaging"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class JobStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class ExecutionTarget(str, Enum):
    """Where a stage actually executes."""

    LOCAL = "local"
    MODAL = "modal"


class FailureOrigin(str, Enum):
    """Whether a failure happened on the control plane or the compute plane."""

    LOCAL = "local"
    MODAL = "modal"


class Provenance(str, Enum):
    """How a piece of geometry or metadata came to exist."""

    OBSERVED = "observed"
    DEPTH_ASSISTED = "depth_assisted"
    INFERRED = "inferred"


class ConfidenceTier(str, Enum):
    HIGH_OBSERVED = "high_observed"
    MEDIUM_ENHANCED = "medium_enhanced"
    LOW_INFERRED = "low_inferred"


class ArtifactKind(str, Enum):
    """Coarse artifact classification used for packaging decisions."""

    VIDEO = "video"
    FRAME_SET = "frame_set"
    KEYFRAME_SET = "keyframe_set"
    CAMERA_POSES = "camera_poses"
    SPARSE_POINTCLOUD = "sparse_pointcloud"
    DENSE_POINTCLOUD = "dense_pointcloud"
    MESH = "mesh"
    SCENE_EXPORT = "scene_export"
    DEPTH_MAP = "depth_map"
    METADATA = "metadata"
    SUMMARY = "summary"
    LOG = "log"
    PREVIEW = "preview"


PROVENANCE_TO_CONFIDENCE: dict[Provenance, ConfidenceTier] = {
    Provenance.OBSERVED: ConfidenceTier.HIGH_OBSERVED,
    Provenance.DEPTH_ASSISTED: ConfidenceTier.MEDIUM_ENHANCED,
    Provenance.INFERRED: ConfidenceTier.LOW_INFERRED,
}

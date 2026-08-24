"""Enums for the God's Eye pipeline."""

from enum import Enum


class ReconstructionMode(str, Enum):
    """The two reconstruction modes the user can choose."""
    EXACT = "exact"
    GENERATIVE = "generative"


class StageStatus(str, Enum):
    """Status of an individual pipeline stage."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class JobStatus(str, Enum):
    """Top-level status of a job."""
    CREATED = "created"
    INGESTING = "ingesting"
    SELECTING_FRAMES = "selecting_frames"
    RECONSTRUCTING = "reconstructing"
    ENHANCING_DEPTH = "enhancing_depth"
    DETECTING_SEMANTICS = "detecting_semantics"
    BUILDING_SCENE_GRAPH = "building_scene_graph"
    COMPLETING_SCENE = "completing_scene"
    PACKAGING = "packaging"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL_SUCCESS = "partial_success"


# Ordered list of pipeline stages for progress tracking
PIPELINE_STAGES = [
    "ingest",
    "frame_analysis",
    "keyframe_selection",
    "reconstruction",
    "depth_enhancement",
    "semantic_detection",
    "scene_graph",
    "generative_completion",
    "packaging",
]

STAGE_DISPLAY_NAMES = {
    "ingest": "Video Ingest",
    "frame_analysis": "Frame Analysis",
    "keyframe_selection": "Keyframe Selection",
    "reconstruction": "3D Reconstruction",
    "depth_enhancement": "Depth Enhancement",
    "semantic_detection": "Semantic Detection",
    "scene_graph": "Scene Graph Construction",
    "generative_completion": "Generative Completion",
    "packaging": "Output Packaging",
}

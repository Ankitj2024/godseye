"""Pipeline core: stage contract, execution context, and composition."""

from godseye.pipeline.context import StageContext
from godseye.pipeline.registry import all_stages, build_pipeline, planned_stage_targets
from godseye.pipeline.stage import (
    ArtifactSpec,
    NotImplementedStage,
    SkipStage,
    Stage,
    StageOutcome,
)

__all__ = [
    "ArtifactSpec",
    "NotImplementedStage",
    "SkipStage",
    "Stage",
    "StageContext",
    "StageOutcome",
    "all_stages",
    "build_pipeline",
    "planned_stage_targets",
]

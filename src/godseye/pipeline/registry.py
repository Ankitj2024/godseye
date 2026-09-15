"""Pipeline composition.

The stage order here is the dependency graph from the architecture document.
Planned-but-unbuilt stages are registered as ``NotImplementedStage`` on purpose:
they show up in ``godseye stages`` and in every manifest as explicitly skipped,
so a partial system never masquerades as a complete one.
"""

from __future__ import annotations

from godseye.pipeline.stage import Stage
from godseye.schemas.enums import ExecutionTarget, PipelineMode, StageName
from godseye.stages import (
    DepthEnhancementStage,
    ExactReconstructionStage,
    FrameExtractionStage,
    GenerativeCompletionStage,
    GeometryPostprocessStage,
    KeyframeSelectionStage,
    OutputPackagingStage,
    SceneGraphStage,
    SemanticDetectionStage,
    SemanticMaskingStage,
)


def all_stages() -> list[Stage]:
    """Every stage in canonical execution order, regardless of mode."""
    return [
        FrameExtractionStage(),
        KeyframeSelectionStage(),
        SemanticMaskingStage(),
        ExactReconstructionStage(),
        GeometryPostprocessStage(),
        DepthEnhancementStage(),
        SemanticDetectionStage(),
        SceneGraphStage(),
        GenerativeCompletionStage(),
        OutputPackagingStage(),
    ]



def build_pipeline(mode: PipelineMode) -> list[Stage]:
    """Stages that participate in the requested mode."""
    return [stage for stage in all_stages() if stage.applies_to(mode)]


def planned_stage_targets(mode: PipelineMode) -> list[tuple[StageName, ExecutionTarget]]:
    """(stage, target) pairs used to pre-populate a fresh manifest."""
    return [(stage.name, stage.target) for stage in build_pipeline(mode)]

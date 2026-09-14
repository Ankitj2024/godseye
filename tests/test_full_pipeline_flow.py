"""Full mock pipeline flow tests (Phases 7–10).

Verifies that the complete stage registry (depth, semantics, scene graph,
generative completion) participates correctly in both EXACT and GENERATIVE
pipeline builds, and that output packaging picks up all new deliverables.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar
from unittest.mock import MagicMock

import pytest

from godseye.config import PipelineConfig
from godseye.orchestrator.job import JobPaths, new_job_id
from godseye.orchestrator.manifest_store import ManifestStore
from godseye.pipeline.registry import all_stages, build_pipeline
from godseye.pipeline.stage import Stage, StageOutcome
from godseye.schemas.enums import (
    ArtifactKind,
    ExecutionTarget,
    JobStatus,
    PipelineMode,
    StageName,
)
from godseye.schemas.scene import ObjectsDocument, SceneGraphDocument


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stage_names(pipeline: list[Stage]) -> list[StageName]:
    return [s.name for s in pipeline]


# ---------------------------------------------------------------------------
# Registry / ordering tests
# ---------------------------------------------------------------------------


def test_all_stages_returns_concrete_instances():
    """No placeholder NotImplementedStage should exist in the full registry."""
    from godseye.pipeline.stage import NotImplementedStage

    stages = all_stages()
    for stage in stages:
        assert not isinstance(stage, NotImplementedStage), (
            f"{stage.name} is still a NotImplementedStage placeholder"
        )


def test_exact_pipeline_stage_order():
    exact = _stage_names(build_pipeline(PipelineMode.EXACT))

    # Core ordering requirements.
    assert exact.index(StageName.FRAME_EXTRACTION) < exact.index(StageName.KEYFRAME_SELECTION)
    assert exact.index(StageName.KEYFRAME_SELECTION) < exact.index(StageName.RECONSTRUCTION_EXACT)
    assert exact.index(StageName.RECONSTRUCTION_EXACT) < exact.index(StageName.GEOMETRY_POSTPROCESS)
    assert exact.index(StageName.GEOMETRY_POSTPROCESS) < exact.index(StageName.DEPTH_ENHANCEMENT)
    assert exact.index(StageName.DEPTH_ENHANCEMENT) < exact.index(StageName.SEMANTIC_DETECTION)
    assert exact.index(StageName.SEMANTIC_DETECTION) < exact.index(StageName.SCENE_GRAPH)
    assert exact.index(StageName.SCENE_GRAPH) < exact.index(StageName.OUTPUT_PACKAGING)

    # Generative completion must NOT appear in exact mode.
    assert StageName.GENERATIVE_COMPLETION not in exact

    # Packaging is always last.
    assert exact[-1] == StageName.OUTPUT_PACKAGING


def test_generative_pipeline_stage_order():
    gen = _stage_names(build_pipeline(PipelineMode.GENERATIVE))

    assert StageName.GENERATIVE_COMPLETION in gen
    assert gen.index(StageName.SCENE_GRAPH) < gen.index(StageName.GENERATIVE_COMPLETION)
    assert gen.index(StageName.GENERATIVE_COMPLETION) < gen.index(StageName.OUTPUT_PACKAGING)
    assert gen[-1] == StageName.OUTPUT_PACKAGING


def test_new_stages_present_in_both_modes():
    """All Phase 7–10 stages (except generative completion) run in both modes."""
    for mode in PipelineMode:
        names = _stage_names(build_pipeline(mode))
        assert StageName.DEPTH_ENHANCEMENT in names, f"Missing DEPTH_ENHANCEMENT in {mode}"
        assert StageName.SEMANTIC_DETECTION in names, f"Missing SEMANTIC_DETECTION in {mode}"
        assert StageName.SCENE_GRAPH in names, f"Missing SCENE_GRAPH in {mode}"


# ---------------------------------------------------------------------------
# Output packaging integration tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def config(tmp_path: Path) -> PipelineConfig:
    cfg = PipelineConfig(root=tmp_path)
    cfg.work_root.mkdir(parents=True, exist_ok=True)
    cfg.outputs_root.mkdir(parents=True, exist_ok=True)
    return cfg


@pytest.fixture()
def job_paths(config: PipelineConfig) -> JobPaths:
    paths = JobPaths(
        job_id=new_job_id(),
        work_root=config.work_root,
        outputs_root=config.outputs_root,
    )
    paths.create()
    return paths


def test_output_packaging_picks_up_depth_pointcloud(
    config: PipelineConfig, job_paths: JobPaths
):
    """When depth_pointcloud.ply exists packaging copies it and adds to exports."""
    # Simulate a minimal exact_scene.glb so the 'no deliverables' guard passes.
    glb = job_paths.geometry_dir / "exact_scene.glb"
    glb.write_bytes(b"glTF")

    # Simulate depth enhancement output.
    ply = job_paths.depth_dir / "depth_pointcloud.ply"
    ply.write_bytes(b"ply\n")

    from godseye.orchestrator.manifest_store import ManifestStore
    from godseye.schemas.manifest import ArtifactRecord

    store = ManifestStore.create(job_paths, PipelineMode.EXACT, {})
    store.manifest.artifacts["scene"] = ArtifactRecord(
        artifact_id="scene",
        stage=StageName.GEOMETRY_POSTPROCESS,
        kind=ArtifactKind.SCENE_EXPORT,
        relative_path="geometry/exact_scene.glb",
        size_bytes=4,
    )
    store.save()

    from godseye.pipeline.context import StageContext
    from godseye.stages.output_packaging import OutputPackagingStage

    ctx = MagicMock(spec=StageContext)
    ctx.manifest = store.manifest
    ctx.paths = job_paths
    ctx.job_id = job_paths.job_id
    import logging
    ctx.logger.return_value = logging.getLogger("test_pkg")
    ctx.config = config

    stage = OutputPackagingStage()
    outcome = stage.run(ctx)

    exports = outcome.metrics["exports"]
    assert "depth_pointcloud_ply" in exports
    assert (job_paths.output_dir / "depth_pointcloud.ply").exists()


def test_output_packaging_picks_up_generative_scene(
    config: PipelineConfig, job_paths: JobPaths
):
    """When generative_scene.glb exists (generative mode) packaging copies it."""
    glb = job_paths.geometry_dir / "exact_scene.glb"
    glb.write_bytes(b"glTF")

    gen_glb = job_paths.completion_dir / "generative_scene.glb"
    gen_glb.write_bytes(b"glTF-gen")

    from godseye.orchestrator.manifest_store import ManifestStore
    from godseye.schemas.manifest import ArtifactRecord

    store = ManifestStore.create(job_paths, PipelineMode.GENERATIVE, {})
    store.manifest.artifacts["scene"] = ArtifactRecord(
        artifact_id="scene",
        stage=StageName.GEOMETRY_POSTPROCESS,
        kind=ArtifactKind.SCENE_EXPORT,
        relative_path="geometry/exact_scene.glb",
        size_bytes=4,
    )
    store.save()

    from godseye.pipeline.context import StageContext
    from godseye.stages.output_packaging import OutputPackagingStage

    ctx = MagicMock(spec=StageContext)
    ctx.manifest = store.manifest
    ctx.paths = job_paths
    ctx.job_id = job_paths.job_id
    import logging
    ctx.logger.return_value = logging.getLogger("test_pkg")
    ctx.config = config

    stage = OutputPackagingStage()
    outcome = stage.run(ctx)

    exports = outcome.metrics["exports"]
    assert "generative_scene_glb" in exports
    assert (job_paths.output_dir / "generative_scene.glb").exists()


def test_output_packaging_writes_populated_objects_json_from_semantics(
    config: PipelineConfig, job_paths: JobPaths
):
    """objects.json produced by packaging must load the semantics stage output."""
    glb = job_paths.geometry_dir / "exact_scene.glb"
    glb.write_bytes(b"glTF")

    from godseye.schemas.scene import SceneObject, Transform, Vec3
    from godseye.schemas.enums import Provenance

    obj = SceneObject(
        object_id="obj_001",
        object_class="vehicle",
        transform=Transform(translation=Vec3(x=0.0, y=0.0, z=0.0)),
        dimensions=Vec3(x=4.0, y=2.0, z=1.5),
        confidence=0.90,
        provenance=Provenance.OBSERVED,
    )
    doc = ObjectsDocument(
        job_id=job_paths.job_id,
        generated=True,
        object_count=1,
        objects=[obj],
    )
    (job_paths.semantics_dir / "objects.json").write_text(
        doc.model_dump_json(indent=2), encoding="utf-8"
    )

    from godseye.orchestrator.manifest_store import ManifestStore
    from godseye.schemas.manifest import ArtifactRecord

    store = ManifestStore.create(job_paths, PipelineMode.EXACT, {})
    store.manifest.artifacts["scene"] = ArtifactRecord(
        artifact_id="scene",
        stage=StageName.GEOMETRY_POSTPROCESS,
        kind=ArtifactKind.SCENE_EXPORT,
        relative_path="geometry/exact_scene.glb",
        size_bytes=4,
    )
    store.save()

    from godseye.pipeline.context import StageContext
    from godseye.stages.output_packaging import OutputPackagingStage

    ctx = MagicMock(spec=StageContext)
    ctx.manifest = store.manifest
    ctx.paths = job_paths
    ctx.job_id = job_paths.job_id
    import logging
    ctx.logger.return_value = logging.getLogger("test_pkg")
    ctx.config = config

    stage = OutputPackagingStage()
    stage.run(ctx)

    out_objects = json.loads((job_paths.output_dir / "objects.json").read_text())
    assert out_objects["generated"] is True
    assert out_objects["object_count"] == 1
    assert out_objects["objects"][0]["object_class"] == "vehicle"


def test_confidence_document_reflects_depth_tier_when_stage_ran(
    config: PipelineConfig, job_paths: JobPaths
):
    """confidence.json must include MEDIUM_ENHANCED tier when depth stage ran."""
    from godseye.orchestrator.manifest_store import ManifestStore
    from godseye.schemas.manifest import ArtifactRecord, StageRecord
    from godseye.schemas.enums import ConfidenceTier

    glb = job_paths.geometry_dir / "exact_scene.glb"
    glb.write_bytes(b"glTF")

    store = ManifestStore.create(job_paths, PipelineMode.EXACT, {})
    store.manifest.artifacts["scene"] = ArtifactRecord(
        artifact_id="scene",
        stage=StageName.GEOMETRY_POSTPROCESS,
        kind=ArtifactKind.SCENE_EXPORT,
        relative_path="geometry/exact_scene.glb",
        size_bytes=4,
    )
    store.manifest.stages[StageName.RECONSTRUCTION_EXACT] = StageRecord(
        name=StageName.RECONSTRUCTION_EXACT,
        target=ExecutionTarget.MODAL,
        metrics={"dense_point_count": 500_000, "registered_images": 40, "input_images": 42},
    )
    store.manifest.stages[StageName.DEPTH_ENHANCEMENT] = StageRecord(
        name=StageName.DEPTH_ENHANCEMENT,
        target=ExecutionTarget.MODAL,
        metrics={"point_count": 120_000},
    )
    store.save()

    from godseye.pipeline.context import StageContext
    from godseye.stages.output_packaging import OutputPackagingStage

    ctx = MagicMock(spec=StageContext)
    ctx.manifest = store.manifest
    ctx.paths = job_paths
    ctx.job_id = job_paths.job_id
    import logging
    ctx.logger.return_value = logging.getLogger("test_pkg")
    ctx.config = config

    stage = OutputPackagingStage()
    stage.run(ctx)

    conf = json.loads((job_paths.output_dir / "confidence.json").read_text())
    assert conf["tier_summary"][ConfidenceTier.MEDIUM_ENHANCED.value] == 120_000

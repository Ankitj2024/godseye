"""Job identity, paths, and manifest persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from godseye.config import PipelineConfig
from godseye.orchestrator.job import JobPaths, is_valid_job_id, new_job_id
from godseye.orchestrator.manifest_store import ManifestError, ManifestStore
from godseye.schemas.enums import (
    ArtifactKind,
    ExecutionTarget,
    JobStatus,
    PipelineMode,
    StageName,
    StageStatus,
)
from godseye.schemas.manifest import StageError
from godseye.schemas.enums import FailureOrigin


def _paths(config: PipelineConfig) -> JobPaths:
    return JobPaths(
        job_id=new_job_id(),
        work_root=config.work_root,
        outputs_root=config.outputs_root,
    ).create()


def test_job_id_format_is_sortable_and_validated():
    job_id = new_job_id()
    assert is_valid_job_id(job_id)
    assert not is_valid_job_id("not-a-job")
    assert not is_valid_job_id("20260826-120000-TOOLONGHASH")


def test_job_paths_create_all_directories(config: PipelineConfig):
    paths = _paths(config)
    for directory in paths.all_dirs():
        assert directory.is_dir()
    assert paths.manifest_path.parent == paths.job_dir


def test_stage_dir_covers_every_stage(config: PipelineConfig):
    paths = _paths(config)
    for stage in StageName:
        assert isinstance(paths.stage_dir(stage), Path)


def test_relative_and_resolve_round_trip(config: PipelineConfig):
    paths = _paths(config)
    target = paths.reconstruction_dir / "sparse_points.ply"
    relative = paths.relative(target)
    assert relative == "reconstruction/sparse_points.ply"
    assert paths.resolve(relative) == target


def test_manifest_round_trip_preserves_state(config: PipelineConfig):
    paths = _paths(config)
    store = ManifestStore.create(
        paths=paths,
        mode=PipelineMode.EXACT,
        config_snapshot={"root": str(config.root)},
        planned_stages=[(StageName.FRAME_EXTRACTION, ExecutionTarget.LOCAL)],
    )
    store.start_stage(StageName.FRAME_EXTRACTION, ExecutionTarget.LOCAL)
    store.complete_stage(StageName.FRAME_EXTRACTION, metrics={"candidate_count": 42})

    reloaded = ManifestStore.load(paths).manifest
    record = reloaded.stages[StageName.FRAME_EXTRACTION]
    assert record.status == StageStatus.COMPLETED
    assert record.metrics["candidate_count"] == 42
    assert record.duration_seconds is not None
    assert reloaded.mode == PipelineMode.EXACT
    # job_setup is recorded first so manifest order reads as execution order.
    assert next(iter(reloaded.stages)) == StageName.JOB_SETUP


def test_manifest_load_missing_raises(config: PipelineConfig):
    paths = JobPaths(
        job_id="20260826-120000-abcdef",
        work_root=config.work_root,
        outputs_root=config.outputs_root,
    )
    with pytest.raises(ManifestError):
        ManifestStore.load(paths)


def test_artifact_registration_records_hash_and_relative_path(config: PipelineConfig):
    paths = _paths(config)
    store = ManifestStore.create(paths, PipelineMode.EXACT, {})

    target = paths.reconstruction_dir / "sparse_points.ply"
    target.write_bytes(b"ply\nformat ascii 1.0\nelement vertex 3\nend_header\n")

    record = store.register_artifact(
        stage=StageName.RECONSTRUCTION_EXACT,
        path=target,
        kind=ArtifactKind.SPARSE_POINTCLOUD,
    )
    assert record is not None
    assert record.relative_path == "reconstruction/sparse_points.ply"
    assert record.sha256 and len(record.sha256) == 64
    assert store.artifact_path(record.artifact_id) == target
    assert record.artifact_id in store.manifest.stage(
        StageName.RECONSTRUCTION_EXACT
    ).artifact_ids


def test_register_artifact_returns_none_for_missing_file(config: PipelineConfig):
    paths = _paths(config)
    store = ManifestStore.create(paths, PipelineMode.EXACT, {})
    result = store.register_artifact(
        stage=StageName.RECONSTRUCTION_EXACT,
        path=paths.reconstruction_dir / "absent.ply",
        kind=ArtifactKind.MESH,
    )
    assert result is None


def test_reset_stage_drops_artifacts_and_state(config: PipelineConfig):
    paths = _paths(config)
    store = ManifestStore.create(paths, PipelineMode.EXACT, {})
    target = paths.geometry_dir / "mesh.ply"
    target.write_text("mesh")

    store.start_stage(StageName.GEOMETRY_POSTPROCESS, ExecutionTarget.MODAL)
    store.register_artifact(
        stage=StageName.GEOMETRY_POSTPROCESS, path=target, kind=ArtifactKind.MESH
    )
    store.complete_stage(StageName.GEOMETRY_POSTPROCESS, metrics={"a": 1})
    assert store.manifest.artifacts

    store.reset_stage(StageName.GEOMETRY_POSTPROCESS)
    record = store.manifest.stage(StageName.GEOMETRY_POSTPROCESS)
    assert record.status == StageStatus.PENDING
    assert record.artifact_ids == []
    assert record.metrics == {}
    assert store.manifest.artifacts == {}


def test_fail_stage_records_origin(config: PipelineConfig):
    paths = _paths(config)
    store = ManifestStore.create(paths, PipelineMode.EXACT, {})
    store.start_stage(StageName.RECONSTRUCTION_EXACT, ExecutionTarget.MODAL)
    store.fail_stage(
        StageName.RECONSTRUCTION_EXACT,
        StageError(
            origin=FailureOrigin.MODAL,
            exception_type="CommandError",
            message="colmap mapper exited 1",
            failed_command="colmap mapper",
            log_tail=["boom"],
        ),
    )
    record = ManifestStore.load(paths).manifest.stages[StageName.RECONSTRUCTION_EXACT]
    assert record.status == StageStatus.FAILED
    assert record.error is not None
    assert record.error.origin == FailureOrigin.MODAL
    assert record.error.failed_command == "colmap mapper"


def test_set_job_status_persists(config: PipelineConfig):
    paths = _paths(config)
    store = ManifestStore.create(paths, PipelineMode.GENERATIVE, {})
    store.set_job_status(JobStatus.PARTIAL)
    assert ManifestStore.load(paths).manifest.status == JobStatus.PARTIAL

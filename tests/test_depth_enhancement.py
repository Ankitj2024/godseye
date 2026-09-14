"""Tests for the depth enhancement stage (Phase 9).

Covers payload construction and the packaging selector for the depth-enhanced
point cloud. The Modal remote call itself is not exercised here — that requires
live GPU credits.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from godseye.artifacts import packaging
from godseye.config import PipelineConfig
from godseye.orchestrator.job import JobPaths, new_job_id
from godseye.schemas.enums import ArtifactKind, ExecutionTarget, PipelineMode, Provenance
from godseye.schemas.manifest import ArtifactRecord, JobManifest
from godseye.schemas.remote import DepthRequest
from godseye.stages.depth_enhancement import DepthEnhancementStage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def job_paths(tmp_path: Path) -> JobPaths:
    job_id = new_job_id()
    paths = JobPaths(job_id=job_id, work_root=tmp_path / "work", outputs_root=tmp_path / "out")
    paths.create()
    return paths


@pytest.fixture()
def manifest(job_paths: JobPaths) -> JobManifest:
    return JobManifest(job_id=job_paths.job_id, mode=PipelineMode.EXACT)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_stage_identity():
    stage = DepthEnhancementStage()
    assert stage.name.value == "depth_enhancement"
    assert stage.target == ExecutionTarget.MODAL
    assert stage.provenance == Provenance.DEPTH_ASSISTED


def test_stage_applies_to_both_modes():
    stage = DepthEnhancementStage()
    assert stage.applies_to(PipelineMode.EXACT) is True
    assert stage.applies_to(PipelineMode.GENERATIVE) is True


def test_depth_request_schema_roundtrip():
    """DepthRequest must survive JSON serialisation without loss."""
    req = DepthRequest(
        job_id="20260101-000000-aabbcc",
        frames_prefix="/vol/jobs/x/frames",
        reconstruction_prefix="/vol/jobs/x/reconstruction",
        output_prefix="/vol/jobs/x/depth",
        model_name="depth_anything_v2",
        max_depth=80.0,
        densify=True,
        use_gpu=True,
    )
    reloaded = DepthRequest.model_validate_json(req.model_dump_json())
    assert reloaded.model_name == "depth_anything_v2"
    assert reloaded.densify is True
    assert reloaded.max_depth == pytest.approx(80.0)


def test_select_depth_pointcloud_finds_file_in_depth_dir(
    manifest: JobManifest, job_paths: JobPaths
):
    """Selector returns the canonical path when depth_pointcloud.ply exists."""
    ply_file = job_paths.depth_dir / "depth_pointcloud.ply"
    ply_file.write_bytes(b"ply\n")  # minimal sentinel content

    result = packaging.select_depth_pointcloud(manifest, job_paths)
    assert result == ply_file


def test_select_depth_pointcloud_returns_none_when_absent(
    manifest: JobManifest, job_paths: JobPaths
):
    result = packaging.select_depth_pointcloud(manifest, job_paths)
    assert result is None


def test_select_depth_pointcloud_falls_back_to_manifest_artifact(
    manifest: JobManifest, job_paths: JobPaths
):
    """If canonical path is absent but a manifest artifact exists, use it."""
    from godseye.schemas.enums import StageName

    alt_file = job_paths.depth_dir / "enhanced_cloud.ply"
    alt_file.write_bytes(b"ply\n")
    manifest.artifacts["depth_pc"] = ArtifactRecord(
        artifact_id="depth_pc",
        stage=StageName.DEPTH_ENHANCEMENT,
        kind=ArtifactKind.DENSE_POINTCLOUD,
        relative_path="depth/enhanced_cloud.ply",
        size_bytes=4,
    )
    result = packaging.select_depth_pointcloud(manifest, job_paths)
    assert result == alt_file

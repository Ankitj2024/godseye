"""Tests for the generative completion stage (Phase 10).

Validates payload schema round-trips, mode-gating (GENERATIVE-only),
and the packaging selectors for generative_scene.glb.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from godseye.artifacts import packaging
from godseye.orchestrator.job import JobPaths, new_job_id
from godseye.schemas.enums import ArtifactKind, ExecutionTarget, PipelineMode, Provenance, StageName
from godseye.schemas.manifest import ArtifactRecord, JobManifest
from godseye.schemas.remote import GenerativeRequest
from godseye.stages.generative_completion import GenerativeCompletionStage


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
    return JobManifest(job_id=job_paths.job_id, mode=PipelineMode.GENERATIVE)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_stage_identity():
    stage = GenerativeCompletionStage()
    assert stage.name.value == "generative_completion"
    assert stage.target == ExecutionTarget.MODAL
    assert stage.provenance == Provenance.INFERRED


def test_stage_applies_only_to_generative_mode():
    stage = GenerativeCompletionStage()
    assert stage.applies_to(PipelineMode.GENERATIVE) is True
    assert stage.applies_to(PipelineMode.EXACT) is False


def test_generative_request_schema_roundtrip():
    req = GenerativeRequest(
        job_id="20260101-000000-aabbcc",
        geometry_prefix="/vol/jobs/x/geometry",
        semantics_prefix="/vol/jobs/x/semantics",
        output_prefix="/vol/jobs/x/completion",
        asset_library_prefix="/vol/jobs/x/assets",
        fill_missing=True,
        max_proxy_insertions=25,
    )
    reloaded = GenerativeRequest.model_validate_json(req.model_dump_json())
    assert reloaded.fill_missing is True
    assert reloaded.max_proxy_insertions == 25


def test_select_generative_scene_finds_canonical_path(
    manifest: JobManifest, job_paths: JobPaths
):
    """Selector returns completion_dir/generative_scene.glb when it exists."""
    glb_file = job_paths.completion_dir / "generative_scene.glb"
    glb_file.write_bytes(b"glTF")  # minimal sentinel

    result = packaging.select_generative_scene(manifest, job_paths)
    assert result == glb_file


def test_select_generative_scene_returns_none_when_absent(
    manifest: JobManifest, job_paths: JobPaths
):
    result = packaging.select_generative_scene(manifest, job_paths)
    assert result is None


def test_select_generative_scene_falls_back_to_manifest_artifact(
    manifest: JobManifest, job_paths: JobPaths
):
    """When the canonical file is absent but a manifest artifact points to one, use it."""
    alt_file = job_paths.completion_dir / "generative_custom.glb"
    alt_file.write_bytes(b"glTF")

    manifest.artifacts["gen_scene"] = ArtifactRecord(
        artifact_id="gen_scene",
        stage=StageName.GENERATIVE_COMPLETION,
        kind=ArtifactKind.SCENE_EXPORT,
        relative_path="completion/generative_custom.glb",
        size_bytes=4,
    )
    result = packaging.select_generative_scene(manifest, job_paths)
    assert result == alt_file


def test_generative_scene_not_in_exact_pipeline():
    """EXACT mode must exclude the generative completion stage entirely."""
    from godseye.pipeline.registry import build_pipeline

    exact_stages = [s.name for s in build_pipeline(PipelineMode.EXACT)]
    assert StageName.GENERATIVE_COMPLETION not in exact_stages


def test_generative_scene_in_generative_pipeline():
    from godseye.pipeline.registry import build_pipeline

    gen_stages = [s.name for s in build_pipeline(PipelineMode.GENERATIVE)]
    assert StageName.GENERATIVE_COMPLETION in gen_stages
    # Must come before output packaging.
    assert gen_stages.index(StageName.GENERATIVE_COMPLETION) < gen_stages.index(
        StageName.OUTPUT_PACKAGING
    )

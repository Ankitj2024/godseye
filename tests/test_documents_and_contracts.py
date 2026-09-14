"""Output documents, the remote contract, and CLI wiring."""

from __future__ import annotations

import json

import pytest

from godseye.artifacts.documents import (
    build_confidence_document,
    build_objects_document,
    build_scene_document,
    build_scene_graph_document,
)
from godseye.errors import RemoteStageError, RemoteTransportError
from godseye.pipeline.registry import build_pipeline
from godseye.schemas.enums import (
    ArtifactKind,
    ConfidenceTier,
    ExecutionTarget,
    PipelineMode,
    StageName,
)
from godseye.schemas.manifest import ArtifactRecord, JobManifest, StageRecord
from godseye.schemas.remote import RemoteStageResult


def _manifest_with_metrics() -> JobManifest:
    manifest = JobManifest(job_id="20260826-120000-abcdef", mode=PipelineMode.EXACT)
    manifest.stages[StageName.RECONSTRUCTION_EXACT] = StageRecord(
        name=StageName.RECONSTRUCTION_EXACT,
        target=ExecutionTarget.MODAL,
        metrics={
            "registered_images": 42,
            "input_images": 50,
            "sparse_point_count": 12000,
            "dense_point_count": 900000,
        },
    )
    manifest.stages[StageName.GEOMETRY_POSTPROCESS] = StageRecord(
        name=StageName.GEOMETRY_POSTPROCESS,
        target=ExecutionTarget.MODAL,
        metrics={
            "output_point_count": 850000,
            "mesh_vertex_count": 120000,
            "mesh_triangle_count": 240000,
            "bounds": {"min": [-1.0, -2.0, -3.0], "max": [1.0, 2.0, 3.0]},
        },
    )
    manifest.stages[StageName.KEYFRAME_SELECTION] = StageRecord(
        name=StageName.KEYFRAME_SELECTION,
        target=ExecutionTarget.LOCAL,
        metrics={"keyframe_count": 50},
    )
    return manifest


def test_scene_document_reports_geometry_and_scale_honestly():
    manifest = _manifest_with_metrics()
    manifest.artifacts["a"] = ArtifactRecord(
        artifact_id="a",
        stage=StageName.GEOMETRY_POSTPROCESS,
        kind=ArtifactKind.MESH,
        relative_path="geometry/mesh.ply",
        size_bytes=10,
    )

    doc = build_scene_document(manifest, {"exact_scene_glb": "exact_scene.glb"}, {})

    assert doc.geometry.registered_images == 42
    assert doc.geometry.input_images == 50
    assert doc.geometry.dense_point_count == 850000
    assert doc.geometry.bounds is not None
    assert doc.geometry.bounds.max.z == 3.0
    # SfM output has no metric scale; the document must say so rather than imply metres.
    assert doc.scale_is_metric is False
    assert doc.units == "unknown"
    assert doc.provenance_summary == {"observed": 1}


def test_unbuilt_documents_are_explicitly_marked_ungenerated():
    manifest = _manifest_with_metrics()

    objects = build_objects_document(manifest)
    graph = build_scene_graph_document(manifest)

    assert objects.generated is False
    assert objects.object_count == 0
    assert objects.reason and "phase 7" in objects.reason
    assert graph.generated is False
    assert graph.reason and "phase 8" in graph.reason


def test_confidence_document_reports_observed_and_unregistered():
    doc = build_confidence_document(_manifest_with_metrics())

    assert doc.generated is True
    assert doc.tier_summary[ConfidenceTier.HIGH_OBSERVED.value] == 850000
    # No depth or generative stage has run, so those tiers must be zero, not guessed.
    assert doc.tier_summary[ConfidenceTier.MEDIUM_ENHANCED.value] == 0
    assert doc.tier_summary[ConfidenceTier.LOW_INFERRED.value] == 0

    region_ids = {region.region_id for region in doc.regions}
    assert "observed_geometry" in region_ids
    assert "unregistered_views" in region_ids

    unregistered = next(r for r in doc.regions if r.region_id == "unregistered_views")
    assert "8 keyframes" in unregistered.description


def test_confidence_document_without_geometry_has_no_regions():
    manifest = JobManifest(job_id="20260826-120000-abcdef", mode=PipelineMode.EXACT)
    doc = build_confidence_document(manifest)
    assert doc.regions == []
    assert doc.tier_summary[ConfidenceTier.HIGH_OBSERVED.value] == 0


def test_remote_result_contract_accepts_worker_success():
    payload = {
        "stage": "reconstruction_exact",
        "status": "completed",
        "worker": {"hostname": "modal-1", "gpu": "A10G"},
        "metrics": {"registered_images": 30},
        "artifacts": [
            {
                "remote_path": "/jobs/x/reconstruction/sparse_points.ply",
                "relative_path": "sparse_points.ply",
                "kind": "sparse_pointcloud",
                "size_bytes": 1024,
                "sha256": None,
                "metadata": {"point_count": 500},
            }
        ],
        "output_prefix": "/jobs/x/reconstruction",
        "logs": ["/jobs/x/reconstruction/logs/03_mapper.log"],
        "notes": [],
        "error": None,
    }

    result = RemoteStageResult.model_validate(payload)

    assert result.ok is True
    assert result.artifacts[0].kind == "sparse_pointcloud"
    assert result.artifacts[0].metadata["point_count"] == 500


def test_remote_result_contract_carries_failure_detail():
    payload = {
        "stage": "reconstruction_exact",
        "status": "failed",
        "error": {
            "exception_type": "CommandError",
            "message": "colmap mapper failed",
            "failed_command": "colmap mapper --database_path db",
            "log_tail": ["ERROR: no images registered"],
        },
    }

    result = RemoteStageResult.model_validate(payload)

    assert result.ok is False
    assert result.error is not None
    assert result.error.failed_command.startswith("colmap mapper")
    assert result.error.log_tail == ["ERROR: no images registered"]


def test_error_origins_distinguish_control_and_compute_plane():
    from godseye.schemas.enums import FailureOrigin

    assert RemoteTransportError("x").origin == FailureOrigin.LOCAL
    assert RemoteStageError("x").origin == FailureOrigin.MODAL


def test_pipeline_order_matches_dependency_graph():
    exact = [stage.name for stage in build_pipeline(PipelineMode.EXACT)]

    assert exact.index(StageName.FRAME_EXTRACTION) < exact.index(StageName.KEYFRAME_SELECTION)
    assert exact.index(StageName.KEYFRAME_SELECTION) < exact.index(
        StageName.RECONSTRUCTION_EXACT
    )
    assert exact.index(StageName.RECONSTRUCTION_EXACT) < exact.index(
        StageName.GEOMETRY_POSTPROCESS
    )
    assert exact[-1] == StageName.OUTPUT_PACKAGING
    # Generative completion is mode-specific.
    assert StageName.GENERATIVE_COMPLETION not in exact


def test_generative_mode_adds_completion_stage():
    generative = [stage.name for stage in build_pipeline(PipelineMode.GENERATIVE)]
    assert StageName.GENERATIVE_COMPLETION in generative
    assert generative.index(StageName.GENERATIVE_COMPLETION) < generative.index(
        StageName.OUTPUT_PACKAGING
    )


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["--video", "a.mp4"], ["run", "--video", "a.mp4"]),
        (["run", "--video", "a.mp4"], ["run", "--video", "a.mp4"]),
        (["doctor"], ["doctor"]),
        (["stages", "--mode", "exact"], ["stages", "--mode", "exact"]),
        (["--help"], ["--help"]),
        ([], []),
    ],
)
def test_entrypoint_makes_run_the_default_command(argv, expected):
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("run_pipeline", root / "run_pipeline.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module._normalize_argv(argv) == expected


def test_manifest_json_is_stable_and_reloadable():
    manifest = _manifest_with_metrics()
    payload = manifest.model_dump_json()
    reloaded = JobManifest.model_validate_json(payload)

    assert reloaded.job_id == manifest.job_id
    # Enum dict keys must survive the JSON round trip.
    assert StageName.RECONSTRUCTION_EXACT in reloaded.stages
    assert json.loads(payload)["stages"]["reconstruction_exact"]["target"] == "modal"

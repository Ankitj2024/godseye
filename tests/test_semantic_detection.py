"""Tests for the semantic detection stage (Phase 7).

Validates payload schema round-trips, provenance tagging, and the
packaging selectors for objects.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from godseye.artifacts import packaging
from godseye.orchestrator.job import JobPaths, new_job_id
from godseye.schemas.enums import ExecutionTarget, PipelineMode, Provenance, StageName
from godseye.schemas.manifest import JobManifest
from godseye.schemas.remote import SemanticRequest
from godseye.schemas.scene import ObjectsDocument, SceneObject, Transform, Vec3
from godseye.stages.semantic_detection import SemanticDetectionStage


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
    stage = SemanticDetectionStage()
    assert stage.name.value == "semantic_detection"
    assert stage.target == ExecutionTarget.MODAL
    assert stage.provenance == Provenance.OBSERVED


def test_stage_applies_to_both_modes():
    stage = SemanticDetectionStage()
    assert stage.applies_to(PipelineMode.EXACT) is True
    assert stage.applies_to(PipelineMode.GENERATIVE) is True


def test_semantic_request_schema_roundtrip():
    req = SemanticRequest(
        job_id="20260101-000000-aabbcc",
        frames_prefix="/vol/jobs/x/frames",
        reconstruction_prefix="/vol/jobs/x/reconstruction",
        output_prefix="/vol/jobs/x/semantics",
        confidence_threshold=0.40,
        classes=["vehicle", "building", "tree"],
        use_gpu=True,
    )
    reloaded = SemanticRequest.model_validate_json(req.model_dump_json())
    assert reloaded.confidence_threshold == pytest.approx(0.40)
    assert "vehicle" in reloaded.classes


def test_scene_object_schema():
    """SceneObject can hold all required 3D metadata and survive serialisation."""
    obj = SceneObject(
        object_id="obj_001",
        object_class="vehicle",
        transform=Transform(
            translation=Vec3(x=5.0, y=0.0, z=-2.0),
        ),
        dimensions=Vec3(x=4.5, y=2.0, z=1.8),
        confidence=0.78,
        provenance=Provenance.OBSERVED,
        supporting_frames=["frame_042.jpg", "frame_043.jpg"],
    )
    payload = json.loads(obj.model_dump_json())
    assert payload["object_class"] == "vehicle"
    assert payload["confidence"] == pytest.approx(0.78)
    assert len(payload["supporting_frames"]) == 2


def test_objects_document_empty_stub():
    doc = ObjectsDocument(
        job_id="20260101-000000-aabbcc",
        generated=False,
        reason="Not implemented",
        object_count=0,
        objects=[],
    )
    assert doc.generated is False
    assert doc.object_count == 0


def test_objects_document_with_objects():
    objs = [
        SceneObject(
            object_id=f"obj_{i:03d}",
            object_class="building",
            transform=Transform(translation=Vec3(x=float(i * 10), y=0.0, z=0.0)),
            dimensions=Vec3(x=10.0, y=8.0, z=20.0),
            confidence=0.85,
            provenance=Provenance.OBSERVED,
        )
        for i in range(3)
    ]
    doc = ObjectsDocument(
        job_id="20260101-000000-aabbcc",
        generated=True,
        object_count=len(objs),
        objects=objs,
    )
    assert doc.generated is True
    assert doc.object_count == 3
    assert doc.objects[2].object_class == "building"


def test_select_objects_document_found(manifest: JobManifest, job_paths: JobPaths):
    obj_file = job_paths.semantics_dir / "objects.json"
    obj_file.write_text("{}", encoding="utf-8")  # sentinel
    result = packaging.select_objects_document(manifest, job_paths)
    assert result == obj_file


def test_select_objects_document_not_found(manifest: JobManifest, job_paths: JobPaths):
    result = packaging.select_objects_document(manifest, job_paths)
    assert result is None


def test_build_objects_document_loads_from_disk(job_paths: JobPaths):
    """build_objects_document falls back gracefully; real loading tested via selector."""
    from godseye.artifacts.documents import build_objects_document
    from godseye.schemas.manifest import JobManifest
    from godseye.schemas.enums import PipelineMode

    manifest = JobManifest(job_id=job_paths.job_id, mode=PipelineMode.EXACT)

    obj = SceneObject(
        object_id="obj_001",
        object_class="tree",
        transform=Transform(translation=Vec3(x=1.0, y=0.0, z=0.0)),
        dimensions=Vec3(x=2.0, y=2.0, z=5.0),
        confidence=0.70,
        provenance=Provenance.OBSERVED,
    )
    doc_in = ObjectsDocument(
        job_id=job_paths.job_id,
        generated=True,
        object_count=1,
        objects=[obj],
    )
    (job_paths.semantics_dir / "objects.json").write_text(
        doc_in.model_dump_json(indent=2), encoding="utf-8"
    )

    doc_out = build_objects_document(manifest, job_paths)
    assert doc_out.generated is True
    assert doc_out.object_count == 1
    assert doc_out.objects[0].object_class == "tree"

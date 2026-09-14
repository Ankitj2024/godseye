"""Tests for the scene graph generation stage (Phase 8).

Covers spatial relationship reasoning (near, above, supports), node/edge
creation, and correct cycle-free graph structure when objects are present or
absent.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from godseye.artifacts import packaging
from godseye.artifacts.documents import build_scene_graph_document
from godseye.orchestrator.job import JobPaths, new_job_id
from godseye.schemas.enums import ExecutionTarget, PipelineMode, Provenance, StageName
from godseye.schemas.manifest import JobManifest
from godseye.schemas.scene import (
    ObjectsDocument,
    SceneGraphDocument,
    SceneObject,
    Transform,
    Vec3,
)
from godseye.stages.scene_graph import SceneGraphStage
from godseye.utils.fs import atomic_write_text, ensure_dir


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


def _make_objects_doc(job_id: str, objs: list[SceneObject]) -> ObjectsDocument:
    return ObjectsDocument(
        job_id=job_id,
        generated=True,
        object_count=len(objs),
        objects=objs,
    )


def _write_objects(paths: JobPaths, doc: ObjectsDocument) -> None:
    (paths.semantics_dir / "objects.json").write_text(
        doc.model_dump_json(indent=2), encoding="utf-8"
    )


def _make_ctx(manifest: JobManifest, job_paths: JobPaths):
    ctx = MagicMock()
    ctx.manifest = manifest
    ctx.paths = job_paths
    ctx.job_id = manifest.job_id

    import logging

    ctx.logger.return_value = logging.getLogger("test_scene_graph")
    return ctx


def _make_obj(object_id: str, x: float, y: float, z: float, cls: str = "vehicle") -> SceneObject:
    return SceneObject(
        object_id=object_id,
        object_class=cls,
        transform=Transform(translation=Vec3(x=x, y=y, z=z)),
        dimensions=Vec3(x=4.0, y=2.0, z=1.5),
        confidence=0.80,
        provenance=Provenance.OBSERVED,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_stage_identity():
    stage = SceneGraphStage()
    assert stage.name.value == "scene_graph"
    assert stage.target == ExecutionTarget.LOCAL


def test_stage_applies_to_both_modes():
    stage = SceneGraphStage()
    assert stage.applies_to(PipelineMode.EXACT) is True
    assert stage.applies_to(PipelineMode.GENERATIVE) is True


def test_scene_graph_empty_when_no_objects(manifest: JobManifest, job_paths: JobPaths):
    """Without objects.json the stage emits a minimal ungenerated graph."""
    ctx = _make_ctx(manifest, job_paths)
    stage = SceneGraphStage()
    outcome = stage.run(ctx)

    assert outcome.metrics["node_count"] == 0
    assert outcome.metrics["edge_count"] == 0
    assert outcome.metrics["generated"] is False

    written = job_paths.scene_graph_dir / "scene_graph.json"
    assert written.exists()
    doc = SceneGraphDocument.model_validate_json(written.read_text())
    assert doc.generated is False


def test_scene_graph_with_two_nearby_objects(manifest: JobManifest, job_paths: JobPaths):
    """Two close objects should get a 'near' edge plus 'supports' from terrain."""
    objs = [_make_obj("a", 0.0, 0.0, 0.0), _make_obj("b", 3.0, 0.0, 0.0)]
    _write_objects(job_paths, _make_objects_doc(manifest.job_id, objs))
    ctx = _make_ctx(manifest, job_paths)

    stage = SceneGraphStage()
    outcome = stage.run(ctx)

    assert outcome.metrics["node_count"] >= 3  # terrain + 2 objects
    relationships = {
        edge["relationship"]
        for edge in json.loads(
            (job_paths.scene_graph_dir / "scene_graph.json").read_text()
        )["edges"]
    }
    assert "near" in relationships
    assert "supports" in relationships


def test_scene_graph_above_edge_for_stacked_objects(manifest: JobManifest, job_paths: JobPaths):
    """Vertically separated objects with horizontal overlap should yield an 'above' edge."""
    objs = [
        _make_obj("bottom", 0.0, 0.0, 0.0),
        _make_obj("top", 0.0, 0.0, 5.0),  # directly above, large dz
    ]
    _write_objects(job_paths, _make_objects_doc(manifest.job_id, objs))
    ctx = _make_ctx(manifest, job_paths)

    stage = SceneGraphStage()
    stage.run(ctx)

    doc = SceneGraphDocument.model_validate_json(
        (job_paths.scene_graph_dir / "scene_graph.json").read_text()
    )
    rel_types = {e.relationship for e in doc.edges}
    assert "above" in rel_types


def test_scene_graph_distant_objects_no_near_edge(manifest: JobManifest, job_paths: JobPaths):
    """Objects far apart must NOT receive a 'near' edge."""
    objs = [_make_obj("a", 0.0, 0.0, 0.0), _make_obj("b", 500.0, 0.0, 0.0)]
    _write_objects(job_paths, _make_objects_doc(manifest.job_id, objs))
    ctx = _make_ctx(manifest, job_paths)

    stage = SceneGraphStage()
    stage.run(ctx)

    doc = SceneGraphDocument.model_validate_json(
        (job_paths.scene_graph_dir / "scene_graph.json").read_text()
    )
    near_edges = [e for e in doc.edges if e.relationship == "near"]
    assert len(near_edges) == 0


def test_scene_graph_node_ids_are_unique(manifest: JobManifest, job_paths: JobPaths):
    objs = [_make_obj(f"obj_{i}", float(i * 5), 0.0, 0.0) for i in range(5)]
    _write_objects(job_paths, _make_objects_doc(manifest.job_id, objs))
    ctx = _make_ctx(manifest, job_paths)

    stage = SceneGraphStage()
    stage.run(ctx)

    doc = SceneGraphDocument.model_validate_json(
        (job_paths.scene_graph_dir / "scene_graph.json").read_text()
    )
    node_ids = [n.node_id for n in doc.nodes]
    assert len(node_ids) == len(set(node_ids)), "Duplicate node IDs found"


def test_select_scene_graph_document_found(manifest: JobManifest, job_paths: JobPaths):
    sg_file = job_paths.scene_graph_dir / "scene_graph.json"
    sg_file.write_text("{}", encoding="utf-8")
    assert packaging.select_scene_graph_document(manifest, job_paths) == sg_file


def test_select_scene_graph_document_not_found(manifest: JobManifest, job_paths: JobPaths):
    assert packaging.select_scene_graph_document(manifest, job_paths) is None


def test_build_scene_graph_document_loads_from_disk(job_paths: JobPaths):
    manifest = JobManifest(job_id=job_paths.job_id, mode=PipelineMode.EXACT)
    doc_in = SceneGraphDocument(
        job_id=job_paths.job_id,
        generated=True,
        nodes=[],
        edges=[],
    )
    (job_paths.scene_graph_dir / "scene_graph.json").write_text(
        doc_in.model_dump_json(indent=2), encoding="utf-8"
    )
    doc_out = build_scene_graph_document(manifest, job_paths)
    assert doc_out.generated is True

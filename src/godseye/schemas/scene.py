"""Scene-level output documents.

These models define the deliverable JSON contract in ``outputs/<job_id>/``:
``scene.json``, ``objects.json``, ``scene_graph.json``, ``confidence.json`` and
``run_summary.json``.

Semantic, depth and generative stages are not implemented yet. Rather than
omitting their documents (which would leave consumers guessing), the pipeline
emits schema-valid documents with an explicit ``generated: false`` flag and a
reason. Absence of data is stated, never implied.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from godseye.schemas.enums import (
    ConfidenceTier,
    ExecutionTarget,
    PipelineMode,
    Provenance,
    StageName,
    StageStatus,
)
from godseye.schemas.manifest import utcnow


class SceneModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Vec3(SceneModel):
    x: float
    y: float
    z: float

    @classmethod
    def from_iterable(cls, values: Any) -> "Vec3":
        x, y, z = (float(v) for v in values)
        return cls(x=x, y=y, z=z)


class Transform(SceneModel):
    """Rigid transform plus scale, expressed in scene units."""

    translation: Vec3
    rotation_quaternion: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0, 1.0])
    scale: Vec3 = Field(default_factory=lambda: Vec3(x=1.0, y=1.0, z=1.0))


class BoundingBox(SceneModel):
    min: Vec3
    max: Vec3


class SceneObject(SceneModel):
    """A detected or inferred 3D object proxy."""

    object_id: str
    object_class: str
    transform: Transform
    dimensions: Vec3
    confidence: float
    provenance: Provenance
    source_asset: str | None = None
    supporting_frames: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ObjectsDocument(SceneModel):
    """``objects.json``"""

    job_id: str
    generated: bool = False
    reason: str | None = None
    object_count: int = 0
    objects: list[SceneObject] = Field(default_factory=list)


class SceneGraphNode(SceneModel):
    node_id: str
    node_type: str
    label: str
    object_id: str | None = None
    confidence: float | None = None
    provenance: Provenance | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SceneGraphEdge(SceneModel):
    edge_id: str
    source: str
    target: str
    relationship: str
    confidence: float | None = None


class SceneGraphDocument(SceneModel):
    """``scene_graph.json``"""

    job_id: str
    generated: bool = False
    reason: str | None = None
    nodes: list[SceneGraphNode] = Field(default_factory=list)
    edges: list[SceneGraphEdge] = Field(default_factory=list)


class ConfidenceRegion(SceneModel):
    region_id: str
    tier: ConfidenceTier
    provenance: Provenance
    description: str
    bounds: BoundingBox | None = None
    point_count: int | None = None
    score: float | None = None


class ConfidenceDocument(SceneModel):
    """``confidence.json``"""

    job_id: str
    generated: bool = True
    reason: str | None = None
    tier_summary: dict[str, int] = Field(default_factory=dict)
    regions: list[ConfidenceRegion] = Field(default_factory=list)


class GeometrySummary(SceneModel):
    sparse_point_count: int | None = None
    dense_point_count: int | None = None
    mesh_vertex_count: int | None = None
    mesh_triangle_count: int | None = None
    registered_images: int | None = None
    input_images: int | None = None
    bounds: BoundingBox | None = None


class SceneDocument(SceneModel):
    """``scene.json`` - the top-level description of the produced scene."""

    schema_version: int = 1
    job_id: str
    mode: PipelineMode
    created_at: datetime = Field(default_factory=utcnow)
    units: str = "unknown"
    scale_is_metric: bool = False
    scale_note: str = (
        "Scale is arbitrary. COLMAP structure-from-motion is scale-free; no metric "
        "reference was applied."
    )
    coordinate_system: str = "colmap_world (y-down, right-handed)"
    geometry: GeometrySummary = Field(default_factory=GeometrySummary)
    exports: dict[str, str] = Field(default_factory=dict)
    documents: dict[str, str] = Field(default_factory=dict)
    provenance_summary: dict[str, int] = Field(default_factory=dict)


class StageSummary(SceneModel):
    name: StageName
    status: StageStatus
    target: ExecutionTarget
    duration_seconds: float | None = None
    error: str | None = None
    notes: list[str] = Field(default_factory=list)


class RunSummaryDocument(SceneModel):
    """``run_summary.json`` - human-first record of what happened."""

    schema_version: int = 1
    job_id: str
    mode: PipelineMode
    status: str
    created_at: datetime
    finished_at: datetime = Field(default_factory=utcnow)
    total_duration_seconds: float = 0.0
    input_video: str | None = None
    keyframe_count: int | None = None
    stages: list[StageSummary] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

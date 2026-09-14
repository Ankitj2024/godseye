"""Builders for the deliverable JSON documents.

Kept separate from the packaging stage so the same builders can be reused later
by the semantic, confidence, and generative stages without touching packaging
logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from godseye.orchestrator.job import JobPaths


from godseye.schemas.enums import (
    ConfidenceTier,
    JobStatus,
    Provenance,
    StageName,
    StageStatus,
)
from godseye.schemas.manifest import JobManifest
from godseye.schemas.scene import (
    BoundingBox,
    ConfidenceDocument,
    ConfidenceRegion,
    GeometrySummary,
    ObjectsDocument,
    RunSummaryDocument,
    SceneDocument,
    SceneGraphDocument,
    StageSummary,
    Vec3,
)

NOT_IMPLEMENTED_REASON = (
    "Semantic 3D detection is not implemented yet (development plan phase 7). "
    "This document is intentionally empty rather than omitted."
)

SCENE_GRAPH_REASON = (
    "Scene graph generation is not implemented yet (development plan phase 8). "
    "This document is intentionally empty rather than omitted."
)


def _bounds_from_metrics(metrics: dict[str, Any]) -> BoundingBox | None:
    bounds = metrics.get("bounds")
    if not isinstance(bounds, dict):
        return None
    minimum = bounds.get("min")
    maximum = bounds.get("max")
    if not (isinstance(minimum, (list, tuple)) and isinstance(maximum, (list, tuple))):
        return None
    try:
        return BoundingBox(
            min=Vec3.from_iterable(minimum),
            max=Vec3.from_iterable(maximum),
        )
    except (TypeError, ValueError):
        return None


def build_geometry_summary(manifest: JobManifest) -> GeometrySummary:
    reconstruction = _metrics(manifest, StageName.RECONSTRUCTION_EXACT)
    geometry = _metrics(manifest, StageName.GEOMETRY_POSTPROCESS)

    return GeometrySummary(
        sparse_point_count=reconstruction.get("sparse_point_count"),
        dense_point_count=geometry.get("output_point_count")
        or reconstruction.get("dense_point_count"),
        mesh_vertex_count=geometry.get("mesh_vertex_count"),
        mesh_triangle_count=geometry.get("mesh_triangle_count"),
        registered_images=reconstruction.get("registered_images"),
        input_images=reconstruction.get("input_images"),
        bounds=_bounds_from_metrics(geometry),
    )


def build_scene_document(
    manifest: JobManifest,
    exports: dict[str, str],
    documents: dict[str, str],
) -> SceneDocument:
    provenance_summary: dict[str, int] = {}
    for artifact in manifest.artifacts.values():
        key = artifact.provenance.value
        provenance_summary[key] = provenance_summary.get(key, 0) + 1

    return SceneDocument(
        job_id=manifest.job_id,
        mode=manifest.mode,
        created_at=manifest.created_at,
        geometry=build_geometry_summary(manifest),
        exports=exports,
        documents=documents,
        provenance_summary=provenance_summary,
    )


def build_objects_document(
    manifest: JobManifest,
    paths: JobPaths | None = None,
) -> ObjectsDocument:
    if paths is not None and (paths.semantics_dir / "objects.json").exists():
        try:
            content = (paths.semantics_dir / "objects.json").read_text(encoding="utf-8")
            doc = ObjectsDocument.model_validate_json(content)
            if doc.generated:
                return doc
        except Exception:
            pass

    return ObjectsDocument(
        job_id=manifest.job_id,
        generated=False,
        reason=NOT_IMPLEMENTED_REASON,
        object_count=0,
        objects=[],
    )


def build_scene_graph_document(
    manifest: JobManifest,
    paths: JobPaths | None = None,
) -> SceneGraphDocument:
    if paths is not None and (paths.scene_graph_dir / "scene_graph.json").exists():
        try:
            content = (paths.scene_graph_dir / "scene_graph.json").read_text(encoding="utf-8")
            doc = SceneGraphDocument.model_validate_json(content)
            if doc.generated:
                return doc
        except Exception:
            pass

    return SceneGraphDocument(
        job_id=manifest.job_id,
        generated=False,
        reason=SCENE_GRAPH_REASON,
    )


def build_confidence_document(
    manifest: JobManifest,
    paths: JobPaths | None = None,
) -> ConfidenceDocument:
    """Derive a confidence report from reconstruction and enhancement facts."""
    summary = build_geometry_summary(manifest)
    geometry = _metrics(manifest, StageName.GEOMETRY_POSTPROCESS)
    depth_metrics = _metrics(manifest, StageName.DEPTH_ENHANCEMENT)
    completion_metrics = _metrics(manifest, StageName.GENERATIVE_COMPLETION)

    observed_points = summary.dense_point_count or summary.sparse_point_count or 0
    depth_points = int(depth_metrics.get("point_count", 0) or 0)
    inferred_objects = int(completion_metrics.get("proxy_assets_inserted", 0) or 0)

    regions: list[ConfidenceRegion] = []
    if observed_points:
        regions.append(
            ConfidenceRegion(
                region_id="observed_geometry",
                tier=ConfidenceTier.HIGH_OBSERVED,
                provenance=Provenance.OBSERVED,
                description=(
                    "Geometry triangulated directly from registered camera views by "
                    "COLMAP. No inference or fill applied."
                ),
                bounds=_bounds_from_metrics(geometry),
                point_count=observed_points,
            )
        )

    if depth_points > 0:
        regions.append(
            ConfidenceRegion(
                region_id="depth_enhanced_geometry",
                tier=ConfidenceTier.MEDIUM_ENHANCED,
                provenance=Provenance.DEPTH_ASSISTED,
                description=(
                    "Geometry densified through monocular depth estimation and "
                    "pose backprojection to strengthen weak surfaces."
                ),
                point_count=depth_points,
            )
        )

    if inferred_objects > 0:
        regions.append(
            ConfidenceRegion(
                region_id="inferred_proxy_geometry",
                tier=ConfidenceTier.LOW_INFERRED,
                provenance=Provenance.INFERRED,
                description=(
                    f"{inferred_objects} class-matched proxy 3D assets inserted to complete "
                    "ambiguous or unobserved semantic structures."
                ),
            )
        )

    unregistered = None
    if summary.input_images and summary.registered_images is not None:
        unregistered = summary.input_images - summary.registered_images
    if unregistered and unregistered > 0:
        regions.append(
            ConfidenceRegion(
                region_id="unregistered_views",
                tier=ConfidenceTier.LOW_INFERRED,
                provenance=Provenance.OBSERVED,
                description=(
                    f"{unregistered} keyframes failed to register. Areas seen only by "
                    "those views have no geometry at all and are absent, not inferred."
                ),
                score=round(unregistered / summary.input_images, 4),
            )
        )

    if depth_points == 0 and inferred_objects == 0:
        reason = (
            "Derived from reconstruction statistics. Depth-enhanced and inferred tiers "
            "are zero because those stages are not implemented yet."
        )
    else:
        reason = (
            "Derived from reconstruction, depth enhancement, and generative completion stages."
        )

    return ConfidenceDocument(
        job_id=manifest.job_id,
        generated=True,
        reason=reason,
        tier_summary={
            ConfidenceTier.HIGH_OBSERVED.value: observed_points,
            ConfidenceTier.MEDIUM_ENHANCED.value: depth_points,
            ConfidenceTier.LOW_INFERRED.value: inferred_objects,
        },
        regions=regions,
    )


def build_run_summary(
    manifest: JobManifest,
    deliverables: list[str],
    job_status: JobStatus,
) -> RunSummaryDocument:
    stages: list[StageSummary] = []
    warnings: list[str] = []

    for record in manifest.stages.values():
        stages.append(
            StageSummary(
                name=record.name,
                status=record.status,
                target=record.target,
                duration_seconds=record.duration_seconds,
                error=record.error.message if record.error else None,
                notes=list(record.notes),
            )
        )
        if record.status == StageStatus.FAILED and record.error:
            warnings.append(
                f"{record.name.value} failed ({record.error.origin.value}): "
                f"{record.error.message}"
            )
        if record.status == StageStatus.SKIPPED:
            for note in record.notes:
                warnings.append(f"{record.name.value} skipped: {note}")

    keyframes = _metrics(manifest, StageName.KEYFRAME_SELECTION).get("keyframe_count")

    return RunSummaryDocument(
        job_id=manifest.job_id,
        mode=manifest.mode,
        status=job_status.value,
        created_at=manifest.created_at,
        total_duration_seconds=manifest.total_duration_seconds(),
        input_video=manifest.video.source_path if manifest.video else None,
        keyframe_count=keyframes,
        stages=stages,
        deliverables=sorted(deliverables),
        warnings=warnings,
    )


def _metrics(manifest: JobManifest, stage: StageName) -> dict[str, Any]:
    record = manifest.stages.get(stage)
    return dict(record.metrics) if record else {}

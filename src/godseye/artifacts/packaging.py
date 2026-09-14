"""Output packaging helpers.

Maps internal artifacts onto the stable public filenames declared in the
architecture output contract, so consumers never have to understand the
``work/`` layout.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from godseye.artifacts.documents import build_run_summary
from godseye.orchestrator.job import JobPaths
from godseye.schemas.enums import ArtifactKind, JobStatus, StageName
from godseye.schemas.manifest import JobManifest
from godseye.utils.fs import atomic_write_text, copy_file, ensure_dir, relative_to

RUN_SUMMARY_FILENAME = "run_summary.json"
SCENE_FILENAME = "scene.json"
OBJECTS_FILENAME = "objects.json"
SCENE_GRAPH_FILENAME = "scene_graph.json"
CONFIDENCE_FILENAME = "confidence.json"
MANIFEST_COPY_FILENAME = "manifest.json"


@dataclass(frozen=True)
class Deliverable:
    """One copied output file."""

    name: str
    source: Path
    destination: Path
    kind: ArtifactKind


def select_scene_export(manifest: JobManifest, paths: JobPaths) -> Path | None:
    """Prefer a GLB scene export produced by geometry post-processing."""
    for record in manifest.artifacts.values():
        if record.kind == ArtifactKind.SCENE_EXPORT and record.relative_path.endswith(".glb"):
            candidate = paths.resolve(record.relative_path)
            if candidate.exists():
                return candidate
    return None


def select_pointcloud(manifest: JobManifest, paths: JobPaths) -> Path | None:
    """Best available point cloud: cleaned dense > raw dense > sparse."""
    priority = [
        (ArtifactKind.DENSE_POINTCLOUD, StageName.GEOMETRY_POSTPROCESS),
        (ArtifactKind.DENSE_POINTCLOUD, StageName.RECONSTRUCTION_EXACT),
        (ArtifactKind.SPARSE_POINTCLOUD, StageName.GEOMETRY_POSTPROCESS),
        (ArtifactKind.SPARSE_POINTCLOUD, StageName.RECONSTRUCTION_EXACT),
    ]
    for kind, stage in priority:
        for record in manifest.artifacts.values():
            if record.kind == kind and record.stage == stage:
                candidate = paths.resolve(record.relative_path)
                if candidate.exists():
                    return candidate
    return None


def select_meshes(manifest: JobManifest, paths: JobPaths) -> list[Path]:
    results: list[Path] = []
    for record in manifest.artifacts.values():
        if record.kind == ArtifactKind.MESH:
            candidate = paths.resolve(record.relative_path)
            if candidate.exists():
                results.append(candidate)
    return sorted(results)


def select_camera_poses(manifest: JobManifest, paths: JobPaths) -> list[Path]:
    results: list[Path] = []
    for record in manifest.artifacts.values():
        if record.kind == ArtifactKind.CAMERA_POSES:
            candidate = paths.resolve(record.relative_path)
            if candidate.exists():
                results.append(candidate)
    return sorted(results)


def select_depth_pointcloud(manifest: JobManifest, paths: JobPaths) -> Path | None:
    """Depth-enhanced dense point cloud produced by the depth enhancement stage."""
    candidate = paths.depth_dir / "depth_pointcloud.ply"
    if candidate.exists():
        return candidate
    # Fall back to any depth-provenance artifact in the manifest.
    for record in manifest.artifacts.values():
        if record.kind == ArtifactKind.DENSE_POINTCLOUD and "depth" in record.relative_path:
            resolved = paths.resolve(record.relative_path)
            if resolved.exists():
                return resolved
    return None


def select_generative_scene(manifest: JobManifest, paths: JobPaths) -> Path | None:
    """Proxy-enriched GLB scene produced by the generative completion stage."""
    candidate = paths.completion_dir / "generative_scene.glb"
    if candidate.exists():
        return candidate
    for record in manifest.artifacts.values():
        if (
            record.kind == ArtifactKind.SCENE_EXPORT
            and "generative" in record.relative_path
            and record.relative_path.endswith(".glb")
        ):
            resolved = paths.resolve(record.relative_path)
            if resolved.exists():
                return resolved
    return None


def select_objects_document(manifest: JobManifest, paths: JobPaths) -> Path | None:
    """Serialised ObjectsDocument from the semantic detection stage."""
    candidate = paths.semantics_dir / "objects.json"
    return candidate if candidate.exists() else None


def select_scene_graph_document(manifest: JobManifest, paths: JobPaths) -> Path | None:
    """Serialised SceneGraphDocument from the scene graph stage."""
    candidate = paths.scene_graph_dir / "scene_graph.json"
    return candidate if candidate.exists() else None


def copy_deliverable(source: Path, output_dir: Path, name: str, kind: ArtifactKind) -> Deliverable:
    destination = output_dir / name
    copy_file(source, destination)
    return Deliverable(name=name, source=source, destination=destination, kind=kind)


def copy_logs(paths: JobPaths, output_dir: Path) -> list[str]:
    """Mirror job logs next to the deliverables; logs are the debugging surface."""
    log_dir = ensure_dir(output_dir / "logs")
    copied: list[str] = []
    if not paths.logs_dir.exists():
        return copied
    for log_file in sorted(paths.logs_dir.glob("*")):
        if log_file.is_file():
            copy_file(log_file, log_dir / log_file.name)
            copied.append(f"logs/{log_file.name}")
    return copied


def write_run_summary(
    manifest: JobManifest,
    paths: JobPaths,
    job_status: JobStatus,
) -> Path | None:
    """Write ``run_summary.json`` after the pipeline has finished.

    Deliberately produced by the runner rather than the packaging stage: a
    summary written mid-stage would report its own stage as still running.
    """
    output_dir = paths.output_dir
    if not output_dir.exists():
        return None

    deliverables = [
        relative_to(path, output_dir)
        for path in sorted(output_dir.rglob("*"))
        if path.is_file() and path.name != RUN_SUMMARY_FILENAME
    ]
    summary = build_run_summary(manifest, deliverables, job_status)
    target = output_dir / RUN_SUMMARY_FILENAME
    atomic_write_text(target, summary.model_dump_json(indent=2) + "\n")
    return target

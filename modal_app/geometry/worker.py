"""Geometry post-processing and scene export worker (Open3D + trimesh).

Reads the COLMAP output straight off the jobs Volume - no re-upload - and turns
raw points into usable geometry:

1. optional voxel downsample (auto-enabled for very large clouds)
2. statistical outlier removal
3. kNN normal estimation (scale-free, since SfM output has arbitrary scale)
4. Poisson surface reconstruction with low-density trimming
5. quadric decimation to a target triangle budget
6. PLY / OBJ / GLB export

Poisson meshing interpolates a surface between observed points, so the mesh is
smoother than the evidence strictly supports. Density trimming removes the worst
of that, and the point cloud is always exported alongside the mesh so the raw
evidence stays inspectable.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

from modal_app.common.app import app
from modal_app.common.config import (
    GEOMETRY_CPU,
    GEOMETRY_MEMORY_MB,
    GEOMETRY_TIMEOUT_SECONDS,
    VOLUME_MOUNT,
)
from modal_app.common.results import artifact, collect_logs, failure, success, worker_info
from modal_app.common.volumes import jobs_volume, to_container_path
from modal_app.geometry.image import geometry_image

STAGE = "geometry_postprocess"

#: Above this point count, downsample before meshing regardless of config.
AUTO_DOWNSAMPLE_THRESHOLD = 8_000_000


class _Log:
    """Tiny append-only logger; the worker has no subprocess output to capture."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lines: list[str] = []

    def __call__(self, message: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {message}"
        self.lines.append(line)
        print(f"[godseye:geometry] {line}", flush=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


@app.function(
    image=geometry_image,
    cpu=GEOMETRY_CPU,
    memory=GEOMETRY_MEMORY_MB,
    timeout=GEOMETRY_TIMEOUT_SECONDS,
    volumes={VOLUME_MOUNT: jobs_volume},
)
def postprocess_geometry(payload: dict[str, Any]) -> dict[str, Any]:
    """Clean the reconstruction point cloud, mesh it, and export a GLB scene."""
    import numpy as np
    import open3d as o3d

    output_prefix = payload.get("output_prefix", "")
    output_root = to_container_path(output_prefix)
    work_dir = Path("/tmp/godseye/geometry")
    log = _Log(work_dir / "logs" / "geometry.log")
    info = worker_info({"open3d": o3d.__version__})

    try:
        jobs_volume.reload()

        if work_dir.exists():
            shutil.rmtree(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        log = _Log(work_dir / "logs" / "geometry.log")

        recon_root = to_container_path(payload["reconstruction_prefix"])
        source_path, source_name = _pick_source_cloud(recon_root)
        log(f"Input cloud: {source_name}")

        started = time.perf_counter()
        cloud = o3d.io.read_point_cloud(str(source_path))
        input_points = len(cloud.points)
        if input_points == 0:
            raise ValueError(
                f"Point cloud '{source_name}' contains no points. Reconstruction produced "
                "no usable geometry."
            )
        log(f"Loaded {input_points} points")

        metrics: dict[str, Any] = {
            "source_cloud": source_name,
            "input_point_count": input_points,
        }

        bbox = cloud.get_axis_aligned_bounding_box()
        diagonal = float(np.linalg.norm(bbox.get_max_bound() - bbox.get_min_bound()))
        log(f"Bounding box diagonal: {diagonal:.4f} (scene units)")

        voxel_size = float(payload.get("voxel_size", 0.0) or 0.0)
        if voxel_size <= 0.0 and input_points > AUTO_DOWNSAMPLE_THRESHOLD and diagonal > 0:
            voxel_size = diagonal / 2500.0
            metrics["auto_downsampled"] = True
            log(
                f"Auto-enabling voxel downsample at {voxel_size:.6f} "
                f"({input_points} points exceeds {AUTO_DOWNSAMPLE_THRESHOLD})"
            )

        if voxel_size > 0.0:
            cloud = cloud.voxel_down_sample(voxel_size)
            metrics["voxel_size"] = voxel_size
            log(f"After downsample: {len(cloud.points)} points")

        neighbors = int(payload.get("outlier_neighbors", 30))
        std_ratio = float(payload.get("outlier_std_ratio", 1.5))
        if len(cloud.points) > neighbors:
            cloud, _ = cloud.remove_statistical_outlier(
                nb_neighbors=neighbors, std_ratio=std_ratio
            )
            log(f"After outlier removal: {len(cloud.points)} points")

        output_points = len(cloud.points)
        metrics["output_point_count"] = output_points
        if output_points == 0:
            raise ValueError("Outlier removal discarded every point; thresholds are too strict.")

        # kNN rather than radius search: SfM output has no metric scale, so a
        # fixed radius would be meaningless across different scenes.
        normal_knn = int(payload.get("normal_knn", 50))
        cloud.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamKNN(knn=normal_knn))
        cloud.normalize_normals()
        log(f"Estimated normals (kNN={normal_knn})")

        clean_bbox = cloud.get_axis_aligned_bounding_box()
        metrics["bounds"] = {
            "min": [round(float(v), 6) for v in clean_bbox.get_min_bound()],
            "max": [round(float(v), 6) for v in clean_bbox.get_max_bound()],
        }

        artifacts: list[dict[str, Any]] = []
        notes: list[str] = []
        exports_dir = work_dir / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)

        clean_ply = exports_dir / "pointcloud_clean.ply"
        o3d.io.write_point_cloud(str(clean_ply), cloud)
        log(f"Wrote {clean_ply.name}")

        mesh = None
        mesh_skipped_reason = None
        if payload.get("build_mesh", True):
            if output_points < 1000:
                mesh_skipped_reason = (
                    f"only {output_points} points survived cleaning; meshing would be noise"
                )
            else:
                knn_color = int(payload.get("knn_color_transfer", 1))
                mesh, mesh_metrics = _build_mesh(o3d, np, cloud, payload, log, knn_color)
                metrics.update(mesh_metrics)
        else:
            mesh_skipped_reason = "disabled by configuration"

        if mesh_skipped_reason:
            metrics["mesh_skipped_reason"] = mesh_skipped_reason
            log(f"Mesh skipped: {mesh_skipped_reason}")

        if mesh is not None:
            mesh_ply = exports_dir / "mesh.ply"
            mesh_obj = exports_dir / "mesh.obj"
            o3d.io.write_triangle_mesh(str(mesh_ply), mesh)
            o3d.io.write_triangle_mesh(str(mesh_obj), mesh)
            log(f"Wrote {mesh_ply.name} and {mesh_obj.name}")
            notes.append(
                "Mesh is a Poisson surface fit over observed points; low-density regions "
                "were trimmed but the surface is still interpolated between samples."
            )

        glb_path = exports_dir / "exact_scene.glb"
        glb_kind = _export_glb(np, glb_path, mesh, cloud, log)

        # Publish to the Volume.
        if output_root.exists():
            shutil.rmtree(output_root)
        output_root.mkdir(parents=True, exist_ok=True)

        for path in sorted(exports_dir.iterdir()):
            if not path.is_file():
                continue
            target = output_root / path.name
            shutil.copy2(path, target)
            artifacts.append(artifact(target, output_root, _kind_for(path, glb_kind)))

        log_target_dir = output_root / "logs"
        log_target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(log.path, log_target_dir / log.path.name)
        artifacts.append(
            artifact(log_target_dir / log.path.name, output_root, "log", compute_hash=False)
        )

        metrics["total_seconds"] = round(time.perf_counter() - started, 3)

        jobs_volume.commit()
        return success(
            stage=STAGE,
            output_prefix=output_prefix,
            metrics=metrics,
            artifacts=artifacts,
            logs=collect_logs(log_target_dir),
            notes=notes,
            worker=info,
        )

    except BaseException as exc:  # noqa: BLE001 - reported as structured failure
        logs: list[str] = []
        try:
            output_root.mkdir(parents=True, exist_ok=True)
            target_dir = output_root / "logs"
            target_dir.mkdir(parents=True, exist_ok=True)
            if log.path.exists():
                shutil.copy2(log.path, target_dir / log.path.name)
            logs = collect_logs(target_dir)
            jobs_volume.commit()
        except Exception:  # noqa: BLE001 - never mask the original failure
            pass
        return failure(
            stage=STAGE,
            exc=exc,
            output_prefix=output_prefix,
            logs=logs,
            worker=info,
        )


def _pick_source_cloud(recon_root: Path) -> tuple[Path, str]:
    """Prefer the dense cloud; fall back to sparse when dense was skipped."""
    for name in ("dense_points.ply", "sparse_points.ply"):
        candidate = recon_root / name
        if candidate.exists() and candidate.stat().st_size > 0:
            return candidate, name
    raise FileNotFoundError(
        f"No point cloud found under '{recon_root}'. Expected dense_points.ply or "
        "sparse_points.ply from the reconstruction stage."
    )


def _build_mesh(o3d, np, cloud, payload: dict[str, Any], log, knn_color: int = 1) -> tuple[Any, dict[str, Any]]:
    depth = int(payload.get("poisson_depth", 12))
    quantile = float(payload.get("density_quantile", 0.12))
    target_triangles = int(payload.get("target_triangles", 1000000))

    log(f"Poisson reconstruction (depth={depth})")
    mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        cloud, depth=depth
    )
    raw_triangles = len(mesh.triangles)

    if quantile > 0.0 and len(densities) > 0:
        density_array = np.asarray(densities)
        threshold = float(np.quantile(density_array, quantile))
        mesh.remove_vertices_by_mask(density_array < threshold)
        log(
            f"Trimmed low-density vertices below quantile {quantile} "
            f"({raw_triangles} -> {len(mesh.triangles)} triangles)"
        )

    if target_triangles > 0 and len(mesh.triangles) > target_triangles:
        mesh = mesh.simplify_quadric_decimation(target_triangles)
        log(f"Decimated to {len(mesh.triangles)} triangles")

    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_triangles()
    mesh.remove_duplicated_vertices()
    mesh.remove_non_manifold_edges()
    mesh.compute_vertex_normals()

    # Transfer per-vertex colors from the source point cloud to the Poisson
    # mesh. Poisson reconstruction does not preserve vertex colors, so we
    # look up the nearest source point(s) for each mesh vertex.
    if cloud.has_colors() and len(mesh.vertices) > 0:
        kd_tree = o3d.geometry.KDTreeFlann(cloud)
        cloud_colors = np.asarray(cloud.colors)
        mesh_verts = np.asarray(mesh.vertices)
        vertex_colors = np.zeros((len(mesh_verts), 3), dtype=np.float64)

        knn_color = max(1, knn_color)
        for i, vert in enumerate(mesh_verts):
            _, idx, _ = kd_tree.search_knn_vector_3d(vert, knn_color)
            vertex_colors[i] = cloud_colors[idx].mean(axis=0)

        mesh.vertex_colors = o3d.utility.Vector3dVector(vertex_colors)
        log(f"Transferred vertex colors from point cloud (kNN={knn_color})")

    metrics = {
        "mesh_vertex_count": len(mesh.vertices),
        "mesh_triangle_count": len(mesh.triangles),
        "mesh_raw_triangle_count": raw_triangles,
        "poisson_depth": depth,
        "density_quantile": quantile,
        "knn_color_transfer": knn_color,
    }
    log(f"Final mesh: {metrics['mesh_vertex_count']}v / {metrics['mesh_triangle_count']}f")
    return mesh, metrics


def _export_glb(np, glb_path: Path, mesh, cloud, log) -> str:
    """Export a GLB. Falls back to a point-cloud GLB when there is no mesh."""
    import trimesh

    if mesh is not None and len(mesh.triangles) > 0:
        vertices = np.asarray(mesh.vertices)
        faces = np.asarray(mesh.triangles)
        colors = None
        if mesh.has_vertex_colors():
            colors = (np.asarray(mesh.vertex_colors) * 255).astype(np.uint8)
        scene_geometry = trimesh.Trimesh(
            vertices=vertices, faces=faces, vertex_colors=colors, process=False
        )
        kind = "mesh"
    else:
        points = np.asarray(cloud.points)
        colors = None
        if cloud.has_colors():
            colors = (np.asarray(cloud.colors) * 255).astype(np.uint8)
        scene_geometry = trimesh.PointCloud(vertices=points, colors=colors)
        kind = "pointcloud"

    scene_geometry.export(str(glb_path))
    log(f"Wrote {glb_path.name} ({kind} GLB)")
    return kind


def _kind_for(path: Path, glb_kind: str) -> str:
    name = path.name
    if name == "exact_scene.glb":
        return "scene_export"
    if name.startswith("mesh."):
        return "mesh"
    if name == "pointcloud_clean.ply":
        return "dense_pointcloud"
    return "metadata"

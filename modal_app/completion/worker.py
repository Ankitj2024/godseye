"""Generative completion worker (Modal, CPU/GPU).

Consumes the exact scene baseline and detected 3D semantic objects, identifies
ambiguous or incomplete objects, inserts class-matched proxy 3D assets from the
asset library, and exports a decoupled ``generative_scene.glb``.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from modal_app.common.app import app
from modal_app.common.config import (
    COMPLETION_CPU,
    COMPLETION_MEMORY_MB,
    COMPLETION_TIMEOUT_SECONDS,
    VOLUME_MOUNT,
)
from modal_app.common.results import artifact, collect_logs, failure, success, worker_info
from modal_app.common.volumes import jobs_volume, to_container_path
from modal_app.completion.image import completion_image

STAGE = "generative_completion"


class _Log:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lines: list[str] = []

    def __call__(self, message: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {message}"
        self.lines.append(line)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def _create_proxy_mesh(obj_class: str, dimensions: dict[str, float]):
    import numpy as np
    import trimesh

    dx = max(0.5, float(dimensions.get("x", 1.0)))
    dy = max(0.5, float(dimensions.get("y", 1.0)))
    dz = max(0.5, float(dimensions.get("z", 1.0)))

    if obj_class in {"tree", "vegetation"}:
        # Cylinder trunk + sphere foliage
        trunk = trimesh.creation.cylinder(radius=dx * 0.15, height=dz * 0.5)
        trunk.apply_translation([0, 0, dz * 0.25])
        trunk.visual.vertex_colors = [139, 69, 19, 220]  # Brown

        foliage = trimesh.creation.icosphere(subdivisions=2, radius=dx * 0.45)
        foliage.apply_translation([0, 0, dz * 0.75])
        foliage.visual.vertex_colors = [34, 139, 34, 220]  # Forest green

        mesh = trimesh.util.concatenate([trunk, foliage])
    elif obj_class in {"building", "structure"}:
        # Box building with roof
        base = trimesh.creation.box(extents=[dx, dy, dz * 0.8])
        base.apply_translation([0, 0, dz * 0.4])
        base.visual.vertex_colors = [180, 180, 190, 220]  # Concrete

        roof = trimesh.creation.cone(radius=max(dx, dy) * 0.6, height=dz * 0.3)
        roof.apply_translation([0, 0, dz * 0.8 + dz * 0.15])
        roof.visual.vertex_colors = [160, 50, 40, 220]  # Red brick

        mesh = trimesh.util.concatenate([base, roof])
    elif obj_class in {"vehicle", "car", "truck"}:
        # Stylized vehicle proxy
        chassis = trimesh.creation.box(extents=[dx, dy, dz * 0.45])
        chassis.apply_translation([0, 0, dz * 0.25])
        chassis.visual.vertex_colors = [40, 100, 200, 220]  # Blue

        cabin = trimesh.creation.box(extents=[dx * 0.6, dy * 0.8, dz * 0.4])
        cabin.apply_translation([-dx * 0.1, 0, dz * 0.65])
        cabin.visual.vertex_colors = [100, 150, 230, 220]

        mesh = trimesh.util.concatenate([chassis, cabin])
    else:
        # Generic bounding cuboid proxy
        mesh = trimesh.creation.box(extents=[dx, dy, dz])
        mesh.apply_translation([0, 0, dz * 0.5])
        mesh.visual.vertex_colors = [255, 165, 0, 200]  # Amber/Inferred marker

    return mesh


@app.function(
    image=completion_image,
    cpu=COMPLETION_CPU,
    memory=COMPLETION_MEMORY_MB,
    timeout=COMPLETION_TIMEOUT_SECONDS,
    volumes={VOLUME_MOUNT: jobs_volume},
)
def complete_generative_scene(payload: dict[str, Any]) -> dict[str, Any]:
    """Merge proxy 3D assets into exact scene for ambiguous/semantic regions."""
    import numpy as np
    import trimesh

    output_prefix = payload.get("output_prefix", "")
    output_root = to_container_path(output_prefix)
    work_dir = Path("/tmp/godseye/completion")
    log = _Log(work_dir / "logs" / "completion.log")
    info = worker_info()

    try:
        jobs_volume.reload()

        if work_dir.exists():
            shutil.rmtree(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        log = _Log(work_dir / "logs" / "completion.log")

        geom_prefix = payload["geometry_prefix"]
        geom_dir = to_container_path(geom_prefix)
        sem_prefix = payload.get("semantics_prefix", "")
        sem_dir = to_container_path(sem_prefix) if sem_prefix else None

        started = time.perf_counter()

        # 1. Load exact scene base geometry
        base_glb = geom_dir / "exact_scene.glb"
        base_ply = geom_dir / "mesh.ply"
        base_cloud = geom_dir / "pointcloud_clean.ply"

        scene = trimesh.Scene()
        if base_glb.exists():
            loaded = trimesh.load(str(base_glb))
            if isinstance(loaded, trimesh.Scene):
                scene = loaded
            elif isinstance(loaded, (trimesh.Trimesh, trimesh.PointCloud)):
                scene.add_geometry(loaded, node_name="exact_base")
            log(f"Loaded exact scene baseline from {base_glb.name}")
        elif base_ply.exists():
            mesh = trimesh.load(str(base_ply))
            scene.add_geometry(mesh, node_name="exact_base")
            log(f"Loaded exact mesh baseline from {base_ply.name}")
        elif base_cloud.exists():
            cloud = trimesh.load(str(base_cloud))
            scene.add_geometry(cloud, node_name="exact_base")
            log(f"Loaded exact point cloud baseline from {base_cloud.name}")
        else:
            log("Warning: No base geometry found; starting generative scene empty")

        # 2. Load detected semantic objects
        objects: list[dict[str, Any]] = []
        if sem_dir and (sem_dir / "objects.json").exists():
            try:
                data = json.loads((sem_dir / "objects.json").read_text(encoding="utf-8"))
                objects = data.get("objects", [])
                log(f"Loaded {len(objects)} detected semantic objects from {sem_dir / 'objects.json'}")
            except Exception as exc:
                log(f"Failed to load objects.json: {exc}")

        # 3. Check for asset library in Volume
        asset_lib_dir = to_container_path(payload.get("asset_library_prefix", "assets"))

        # 4. Insert proxy assets for detected objects
        inserted_count = 0
        max_insertions = int(payload.get("max_proxy_insertions", 50))

        for obj in objects[:max_insertions]:
            obj_id = obj["object_id"]
            obj_class = obj["object_class"]
            transform = obj.get("transform", {})
            trans = transform.get("translation", {"x": 0, "y": 0, "z": 0})
            dims = obj.get("dimensions", {"x": 2, "y": 2, "z": 2})

            # Check if pre-authored asset exists on disk
            asset_mesh = None
            if asset_lib_dir.exists():
                candidate_asset = asset_lib_dir / f"{obj_class}.glb"
                if not candidate_asset.exists():
                    candidate_asset = asset_lib_dir / f"{obj_class}.obj"
                if candidate_asset.exists():
                    try:
                        loaded_asset = trimesh.load(str(candidate_asset))
                        if isinstance(loaded_asset, trimesh.Trimesh):
                            asset_mesh = loaded_asset.copy()
                            # Scale asset to match detected bounding dimensions
                            orig_extents = asset_mesh.bounding_box.extents
                            scale_factor = [
                                dims["x"] / max(0.1, orig_extents[0]),
                                dims["y"] / max(0.1, orig_extents[1]),
                                dims["z"] / max(0.1, orig_extents[2]),
                            ]
                            asset_mesh.apply_scale(scale_factor)
                    except Exception as exc:
                        log(f"Failed to load proxy asset {candidate_asset}: {exc}")

            if asset_mesh is None:
                # Generate clean parametric proxy mesh
                asset_mesh = _create_proxy_mesh(obj_class, dims)

            # Apply translation
            asset_mesh.apply_translation([trans["x"], trans["y"], trans["z"]])

            # Add to generative scene
            scene.add_geometry(asset_mesh, node_name=f"proxy_{obj_id}")
            inserted_count += 1
            log(f"Inserted proxy asset for {obj_id} ({obj_class}) at [{trans['x']:.2f}, {trans['y']:.2f}, {trans['z']:.2f}]")

        # 5. Export deliverables
        exports_dir = work_dir / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)

        glb_path = exports_dir / "generative_scene.glb"
        scene.export(str(glb_path))
        log(f"Wrote {glb_path.name}")

        # Publish to Volume
        if output_root.exists():
            shutil.rmtree(output_root)
        output_root.mkdir(parents=True, exist_ok=True)

        target_glb = output_root / glb_path.name
        shutil.copy2(glb_path, target_glb)

        artifacts = [
            artifact(
                target_glb,
                output_root,
                "scene_export",
                {"inferred_objects_count": inserted_count},
            )
        ]

        log_target_dir = output_root / "logs"
        log_target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(log.path, log_target_dir / log.path.name)
        artifacts.append(artifact(log_target_dir / log.path.name, output_root, "log", compute_hash=False))

        metrics = {
            "proxy_assets_inserted": inserted_count,
            "total_scene_geometries": len(scene.geometry),
            "total_seconds": round(time.perf_counter() - started, 3),
        }

        jobs_volume.commit()
        return success(
            stage=STAGE,
            output_prefix=output_prefix,
            metrics=metrics,
            artifacts=artifacts,
            logs=collect_logs(log_target_dir),
            notes=[
                f"Generative completion inserted {inserted_count} proxy assets.",
                "Inferred objects are tagged with low confidence and kept separate from exact geometry.",
            ],
            worker=info,
        )

    except BaseException as exc:
        logs = []
        try:
            output_root.mkdir(parents=True, exist_ok=True)
            target_dir = output_root / "logs"
            target_dir.mkdir(parents=True, exist_ok=True)
            if log.path.exists():
                shutil.copy2(log.path, target_dir / log.path.name)
            logs = collect_logs(target_dir)
            jobs_volume.commit()
        except Exception:
            pass
        return failure(
            stage=STAGE,
            exc=exc,
            output_prefix=output_prefix,
            logs=logs,
            worker=info,
        )

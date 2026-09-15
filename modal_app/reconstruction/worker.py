"""Exact reconstruction worker (COLMAP, GPU).

Contract:

* input  - keyframes at ``payload["frames_prefix"]`` on the jobs Volume
* output - camera poses, sparse and (optionally) dense point clouds, logs and
  metrics written under ``payload["output_prefix"]``

The heavy intermediate workspace lives on container-local disk, not on the
Volume. Dense stereo generates thousands of depth/normal maps; writing those to a
distributed filesystem would be slow and would burn Volume inodes for data
nobody ever reads. Only real deliverables are committed back.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

from modal_app.common.app import app
from modal_app.common.config import (
    COLMAP_CPU,
    COLMAP_GPU,
    COLMAP_IMAGE_TAG,
    COLMAP_MEMORY_MB,
    COLMAP_TIMEOUT_SECONDS,
    VOLUME_MOUNT,
)
from modal_app.common.results import artifact, collect_logs, failure, success, worker_info
from modal_app.common.volumes import jobs_volume, to_container_path
from modal_app.reconstruction.colmap import (
    ColmapDriver,
    copy_tree_contents,
    count_ply_vertices,
    summarize,
)
from modal_app.reconstruction.image import colmap_image

STAGE = "reconstruction_exact"

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


@app.function(
    image=colmap_image,
    gpu=COLMAP_GPU,
    cpu=COLMAP_CPU,
    memory=COLMAP_MEMORY_MB,
    timeout=COLMAP_TIMEOUT_SECONDS,
    volumes={VOLUME_MOUNT: jobs_volume},
)
def reconstruct_exact(payload: dict[str, Any]) -> dict[str, Any]:
    """Run COLMAP structure-from-motion (and optional dense stereo)."""
    output_prefix = payload.get("output_prefix", "")
    output_root = to_container_path(output_prefix)
    log_dir = Path("/tmp/godseye/logs")
    info = worker_info({"colmap_image_tag": COLMAP_IMAGE_TAG})

    try:
        # A warm container may hold a stale view of the Volume, so pull the
        # frames the client just uploaded.
        jobs_volume.reload()

        frames_prefix = payload["frames_prefix"]
        remote_frames = to_container_path(frames_prefix)
        if not remote_frames.exists():
            raise FileNotFoundError(
                f"Frames not found at volume path '{frames_prefix}'. Upload failed or the "
                "job id is wrong."
            )

        workspace = Path("/tmp/godseye/workspace")
        if workspace.exists():
            shutil.rmtree(workspace)
        images_dir = workspace / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)

        image_count = _copy_images(remote_frames, images_dir)
        if image_count < 5:
            raise ValueError(
                f"Only {image_count} usable images were staged; COLMAP needs a handful of "
                "overlapping views to reconstruct anything."
            )

        masks_dir = None
        masks_prefix = payload.get("masks_prefix")
        if masks_prefix:
            remote_masks = to_container_path(masks_prefix)
            if remote_masks.exists():
                masks_dir = workspace / "masks"
                masks_dir.mkdir(parents=True, exist_ok=True)
                mask_count = _copy_masks(remote_masks, masks_dir)
                if mask_count > 0:
                    info["mask_count"] = mask_count
                else:
                    masks_dir = None

        driver = ColmapDriver(
            images_dir=images_dir,
            workspace=workspace,
            log_dir=log_dir,
            use_gpu=bool(payload.get("use_gpu", True)),
            masks_dir=masks_dir,
        )

        started = time.perf_counter()
        sparse = driver.run_sparse(
            camera_model=payload.get("camera_model", "OPENCV"),
            single_camera=bool(payload.get("single_camera", True)),
            max_image_size=int(payload.get("max_image_size", 2000)),
            matcher=payload.get("matcher", "exhaustive"),
            num_threads=int(payload.get("mapper_threads", 0) or 0),
            max_num_features=int(payload.get("max_num_features", 0) or 0),
            init_min_tri_angle=float(payload.get("init_min_tri_angle", 0.0) or 0.0),
            init_max_forward_motion=float(payload.get("init_max_forward_motion", 0.0) or 0.0),
            init_num_trials=int(payload.get("init_num_trials", 0) or 0),
        )

        notes: list[str] = []
        dense = None
        dense_skipped_reason = None

        if payload.get("run_dense", True):
            if sparse.stats.registered_images < 3:
                dense_skipped_reason = (
                    f"only {sparse.stats.registered_images} images registered; dense stereo "
                    "needs a usable multi-view baseline"
                )
            else:
                dense = driver.run_dense(
                    model_dir=sparse.model_dir,
                    max_image_size=int(payload.get("dense_max_image_size", 1600)),
                )
        else:
            dense_skipped_reason = "disabled by configuration"

        if dense_skipped_reason:
            notes.append(f"Dense reconstruction skipped: {dense_skipped_reason}")

        artifacts = _publish(output_root, sparse, dense, log_dir)

        metrics = summarize(sparse, dense)
        metrics.update(
            {
                "input_images": image_count,
                "matcher": payload.get("matcher", "exhaustive"),
                "total_seconds": round(time.perf_counter() - started, 3),
                "colmap_image_tag": COLMAP_IMAGE_TAG,
            }
        )
        if dense_skipped_reason:
            metrics["dense_skipped_reason"] = dense_skipped_reason

        if sparse.model_count > 1:
            notes.append(
                f"COLMAP produced {sparse.model_count} disconnected sub-models; the largest "
                f"({sparse.stats.registered_images} images) was kept."
            )

        # Option namespaces differ between COLMAP generations. If a flag was
        # dropped because this build does not accept it, say so rather than
        # letting the run look fully configured.
        if driver.unsupported_options:
            metrics["unsupported_options"] = driver.unsupported_options
            notes.append(
                "Some options are unsupported by this COLMAP build and were omitted "
                f"(defaults used): {'; '.join(driver.unsupported_options)}"
            )

        jobs_volume.commit()
        return success(
            stage=STAGE,
            output_prefix=output_prefix,
            metrics=metrics,
            artifacts=artifacts,
            logs=collect_logs(output_root / "logs"),
            notes=notes,
            worker=info,
        )

    except BaseException as exc:  # noqa: BLE001 - reported as structured failure
        logs = _publish_logs_only(output_root, log_dir)
        try:
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


def _copy_images(source: Path, destination: Path) -> int:
    count = 0
    for path in sorted(source.rglob("*")):
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            shutil.copy2(path, destination / path.name)
            count += 1
    return count


def _copy_masks(source: Path, destination: Path) -> int:
    count = 0
    for path in sorted(source.rglob("*.png")):
        if path.is_file():
            shutil.copy2(path, destination / path.name)
            count += 1
    return count


def _publish(
    output_root: Path,
    sparse: Any,
    dense: Any | None,
    log_dir: Path,
) -> list[dict[str, Any]]:
    """Copy deliverables from the local workspace onto the Volume."""
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    artifacts: list[dict[str, Any]] = []

    # Human/tool readable camera poses and points.
    model_txt = output_root / "model"
    for path in copy_tree_contents(sparse.txt_dir, model_txt):
        artifacts.append(artifact(path, output_root, "camera_poses"))

    # Binary model, kept so COLMAP-native tooling can reuse the reconstruction.
    model_bin = output_root / "model_bin"
    for path in copy_tree_contents(sparse.model_dir, model_bin):
        artifacts.append(artifact(path, output_root, "metadata", compute_hash=False))

    sparse_ply = output_root / "sparse_points.ply"
    shutil.copy2(sparse.ply_path, sparse_ply)
    artifacts.append(
        artifact(
            sparse_ply,
            output_root,
            "sparse_pointcloud",
            metadata={"point_count": count_ply_vertices(sparse_ply)},
        )
    )

    if dense is not None:
        dense_ply = output_root / "dense_points.ply"
        shutil.copy2(dense.fused_ply, dense_ply)
        artifacts.append(
            artifact(
                dense_ply,
                output_root,
                "dense_pointcloud",
                metadata={"point_count": dense.point_count},
                compute_hash=False,
            )
        )

    for path in copy_tree_contents(log_dir, output_root / "logs"):
        artifacts.append(artifact(path, output_root, "log", compute_hash=False))

    return artifacts


def _publish_logs_only(output_root: Path, log_dir: Path) -> list[str]:
    """Preserve logs even when the run failed - they are the only diagnosis path."""
    try:
        output_root.mkdir(parents=True, exist_ok=True)
        copy_tree_contents(log_dir, output_root / "logs")
        return collect_logs(output_root / "logs")
    except Exception:  # noqa: BLE001
        return []

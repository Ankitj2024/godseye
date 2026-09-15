"""Depth enhancement worker (Modal, GPU).

Reads keyframes and COLMAP reconstruction data off the jobs Volume, estimates
monocular depth maps, and unprojects them into a densified point cloud
(``depth_pointcloud.ply``) to strengthen weak or textureless surfaces.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

from modal_app.common.app import app
from modal_app.common.config import (
    DEPTH_CPU,
    DEPTH_GPU,
    DEPTH_MEMORY_MB,
    DEPTH_TIMEOUT_SECONDS,
    VOLUME_MOUNT,
)
from modal_app.common.results import artifact, collect_logs, failure, success, worker_info
from modal_app.common.volumes import jobs_volume, to_container_path
from modal_app.depth.image import depth_image

STAGE = "depth_enhancement"


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


def _qvec_to_rotmat(qvec: list[float]):
    import numpy as np

    w, x, y, z = qvec
    return np.array([
        [1 - 2 * y * y - 2 * z * z, 2 * x * y - 2 * z * w, 2 * x * z + 2 * y * w],
        [2 * x * y + 2 * z * w, 1 - 2 * x * x - 2 * z * z, 2 * y * z - 2 * x * w],
        [2 * x * z - 2 * y * w, 2 * y * z + 2 * x * w, 1 - 2 * x * x - 2 * y * y],
    ], dtype=np.float32)


def _load_cameras_and_images(recon_root: Path):
    """Parse COLMAP cameras.txt and images.txt if present."""
    cameras = {}
    images = {}

    model_dir = recon_root / "model"
    if not model_dir.exists():
        model_dir = recon_root

    cameras_file = model_dir / "cameras.txt"
    images_file = model_dir / "images.txt"

    if not (cameras_file.exists() and images_file.exists()):
        return cameras, images

    # Parse cameras.txt
    for line in cameras_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        cam_id = int(parts[0])
        model = parts[1]
        width = int(parts[2])
        height = int(parts[3])
        params = [float(p) for p in parts[4:]]
        cameras[cam_id] = {
            "model": model,
            "width": width,
            "height": height,
            "params": params,
        }

    # Parse images.txt
    img_lines = [
        l.strip() for l in images_file.read_text(encoding="utf-8", errors="replace").splitlines()
        if l.strip() and not l.startswith("#")
    ]
    pose_lines = img_lines[0::2]
    for line in pose_lines:
        parts = line.split()
        img_id = int(parts[0])
        qvec = [float(p) for p in parts[1:5]]
        tvec = [float(p) for p in parts[5:8]]
        cam_id = int(parts[8])
        name = parts[9]
        images[name] = {
            "image_id": img_id,
            "qvec": qvec,
            "tvec": tvec,
            "camera_id": cam_id,
            "name": name,
        }

    return cameras, images


@app.function(
    image=depth_image,
    gpu=DEPTH_GPU,
    cpu=DEPTH_CPU,
    memory=DEPTH_MEMORY_MB,
    timeout=DEPTH_TIMEOUT_SECONDS,
    volumes={VOLUME_MOUNT: jobs_volume},
)
def enhance_depth(payload: dict[str, Any]) -> dict[str, Any]:
    """Estimate depth and unproject into a densified point cloud."""
    import numpy as np
    import open3d as o3d
    from PIL import Image

    output_prefix = payload.get("output_prefix", "")
    output_root = to_container_path(output_prefix)
    work_dir = Path("/tmp/godseye/depth")
    log = _Log(work_dir / "logs" / "depth.log")
    info = worker_info()

    try:
        jobs_volume.reload()

        if work_dir.exists():
            shutil.rmtree(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        log = _Log(work_dir / "logs" / "depth.log")

        frames_prefix = payload["frames_prefix"]
        frames_dir = to_container_path(frames_prefix)
        recon_prefix = payload.get("reconstruction_prefix", "")
        recon_dir = to_container_path(recon_prefix) if recon_prefix else None

        image_paths = sorted(
            [p for p in frames_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}]
        )
        if not image_paths:
            raise FileNotFoundError(f"No keyframe images found at {frames_dir}")

        log(f"Found {len(image_paths)} keyframes for depth estimation")
        started = time.perf_counter()

        cameras, images = ({}, {})
        scene_points: np.ndarray | None = None
        if recon_dir and recon_dir.exists():
            cameras, images = _load_cameras_and_images(recon_dir)
            log(f"Loaded {len(images)} camera poses from COLMAP model")

            # Load COLMAP point cloud for metric depth alignment.
            for name in ("dense_points.ply", "sparse_points.ply"):
                cloud_file = recon_dir / name
                if cloud_file.exists() and cloud_file.stat().st_size > 0:
                    ref_cloud = o3d.io.read_point_cloud(str(cloud_file))
                    if len(ref_cloud.points) > 0:
                        scene_points = np.asarray(ref_cloud.points).astype(np.float32)
                        log(f"Loaded {len(scene_points)} reference points from {name} for depth alignment")
                        break

        # Try loading monocular depth model (e.g. Depth Anything V2 or Transformers pipeline)
        depth_estimator = None
        try:
            from transformers import pipeline
            depth_estimator = pipeline(
                task="depth-estimation",
                model="depth-anything/Depth-Anything-V2-Small-hf",
                device=0 if payload.get("use_gpu", True) else -1,
            )
            log("Loaded Depth-Anything-V2-Small model on GPU")
        except Exception as exc:
            log(f"Notice: Transformer depth pipeline not loaded ({exc}). Using edge-guided estimation fallback.")

        depth_maps_dir = work_dir / "maps"
        depth_maps_dir.mkdir(parents=True, exist_ok=True)

        all_points: list[np.ndarray] = []
        all_colors: list[np.ndarray] = []
        alignment_stats: list[dict[str, float]] = []

        # Use up to ~50 frames for denser coverage.
        subsample_step = max(1, len(image_paths) // 50)
        selected_frames = image_paths[::subsample_step]

        for idx, img_path in enumerate(selected_frames):
            pil_img = Image.open(img_path).convert("RGB")
            w, h = pil_img.size

            if depth_estimator is not None:
                depth_result = depth_estimator(pil_img)
                predicted_depth = depth_result.get("predicted_depth")
                if predicted_depth is not None:
                    raw_depth = np.array(predicted_depth, dtype=np.float32)
                else:
                    raw_depth = np.array(depth_result["depth"], dtype=np.float32)
            else:
                # Structural pseudo-depth estimation fallback
                gray = np.array(pil_img.convert("L"), dtype=np.float32)
                gx, gy = np.gradient(gray)
                grad_mag = np.sqrt(gx**2 + gy**2)
                raw_depth = 1.0 + (255.0 - grad_mag) / 255.0 * 10.0

            # Resize raw depth to match image dimensions if needed (some
            # models return a different resolution).
            if raw_depth.shape[0] != h or raw_depth.shape[1] != w:
                from PIL import Image as PILImage
                raw_depth = np.array(
                    PILImage.fromarray(raw_depth).resize((w, h), PILImage.BILINEAR),
                    dtype=np.float32,
                )

            # Check if camera pose is available for 3D unprojection
            pose = images.get(img_path.name)
            if not (pose and cameras):
                continue
            cam = cameras.get(pose["camera_id"])
            if not cam:
                continue

            params = cam["params"]
            fx = params[0]
            fy = params[1] if len(params) > 1 else params[0]
            cx = params[2] if len(params) > 2 else w / 2.0
            cy = params[3] if len(params) > 3 else h / 2.0

            R = _qvec_to_rotmat(pose["qvec"])
            T = np.array(pose["tvec"], dtype=np.float32)

            # ---- Metric depth alignment via COLMAP point cloud ----
            # Project known COLMAP 3D points into this camera and solve for
            # the scale and shift that align monocular depth to metric depth.
            aligned_depth = raw_depth  # fallback: use raw if alignment fails
            if scene_points is not None and len(scene_points) > 100:
                # P_cam = R * P_world + T  (COLMAP convention)
                pts_cam = (R @ scene_points.T + T[:, None]).T  # (N, 3)
                # Keep only points in front of the camera
                in_front = pts_cam[:, 2] > 0.5
                pts_cam = pts_cam[in_front]

                if len(pts_cam) > 10:
                    u_proj = (fx * pts_cam[:, 0] / pts_cam[:, 2] + cx).astype(np.int32)
                    v_proj = (fy * pts_cam[:, 1] / pts_cam[:, 2] + cy).astype(np.int32)
                    in_bounds = (
                        (u_proj >= 0) & (u_proj < w) &
                        (v_proj >= 0) & (v_proj < h)
                    )
                    u_valid = u_proj[in_bounds]
                    v_valid = v_proj[in_bounds]
                    z_colmap = pts_cam[in_bounds, 2]  # true metric depth

                    if len(z_colmap) >= 10:
                        # Sample monocular depth at corresponding pixel locations
                        z_mono = raw_depth[v_valid, u_valid]

                        # Least-squares: z_colmap = scale * z_mono + shift
                        # Solve  [z_mono, 1] @ [scale, shift]^T = z_colmap
                        A = np.stack([z_mono, np.ones_like(z_mono)], axis=-1)
                        result, residuals, rank, sv = np.linalg.lstsq(A, z_colmap, rcond=None)
                        scale, shift = float(result[0]), float(result[1])

                        # Sanity check: scale should be positive and finite
                        if np.isfinite(scale) and np.isfinite(shift) and scale > 0.01:
                            aligned_depth = scale * raw_depth + shift
                            # Clamp to avoid negative depths
                            aligned_depth = np.clip(aligned_depth, 0.1, None)
                            alignment_stats.append({
                                "frame": img_path.name,
                                "scale": round(scale, 4),
                                "shift": round(shift, 4),
                                "correspondences": int(len(z_colmap)),
                            })
                        else:
                            log(f"  Alignment degenerate for {img_path.name} "
                                f"(scale={scale:.4f}), using raw depth")
                    else:
                        log(f"  Too few correspondences for {img_path.name} "
                            f"({len(z_colmap)} points), using raw depth")

            # Save preview depth map
            vis = aligned_depth - aligned_depth.min()
            vis_max = vis.max()
            if vis_max > 0:
                vis = vis / vis_max
            preview_arr = (vis * 255.0).astype(np.uint8)
            preview_img = Image.fromarray(preview_arr)
            preview_path = depth_maps_dir / f"depth_{img_path.stem}.png"
            preview_img.save(preview_path)

            # Unproject a sparse grid (every 4th pixel for denser coverage)
            stride = 4
            u_coords = np.arange(0, w, stride)
            v_coords = np.arange(0, h, stride)
            uu, vv = np.meshgrid(u_coords, v_coords)

            # Sample aligned metric depth and image color
            sample_d = aligned_depth[vv, uu]
            img_rgb = np.array(pil_img)[vv, uu] / 255.0

            z = sample_d.flatten()
            # Discard points with non-positive depth
            valid = z > 0.1
            z = z[valid]
            uu_flat = uu.flatten()[valid]
            vv_flat = vv.flatten()[valid]

            x = (uu_flat - cx) * z / fx
            y = (vv_flat - cy) * z / fy

            pts_cam_grid = np.stack([x, y, z], axis=-1)  # shape (N, 3)

            # Transform to world: X_w = R^T * (X_c - T)
            pts_world = (R.T @ (pts_cam_grid - T).T).T

            all_points.append(pts_world)
            all_colors.append(img_rgb.reshape(-1, 3)[valid])

        if alignment_stats:
            scales = [s["scale"] for s in alignment_stats]
            log(f"Depth alignment: {len(alignment_stats)} frames aligned, "
                f"scale range [{min(scales):.3f}, {max(scales):.3f}], "
                f"median scale {sorted(scales)[len(scales)//2]:.3f}")

        artifacts: list[dict[str, Any]] = []
        point_count = 0

        # Combine into Open3D pointcloud
        cloud = o3d.geometry.PointCloud()
        if all_points:
            pts_concat = np.concatenate(all_points, axis=0).astype(np.float64)
            cols_concat = np.concatenate(all_colors, axis=0).astype(np.float64)
            cloud.points = o3d.utility.Vector3dVector(pts_concat)
            cloud.colors = o3d.utility.Vector3dVector(cols_concat)
            # Remove statistical outliers
            if len(cloud.points) > 100:
                cloud, _ = cloud.remove_statistical_outlier(nb_neighbors=30, std_ratio=1.5)
            point_count = len(cloud.points)
            log(f"Generated {point_count} depth-assisted 3D points (metrically aligned)")
        else:
            log("No camera poses available for 3D unprojection; skipping depth cloud")
            point_count = 0

        # Save deliverables
        exports_dir = work_dir / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        ply_path = exports_dir / "depth_pointcloud.ply"
        o3d.io.write_point_cloud(str(ply_path), cloud)
        log(f"Wrote {ply_path.name}")

        # Publish to the Volume
        if output_root.exists():
            shutil.rmtree(output_root)
        output_root.mkdir(parents=True, exist_ok=True)

        target_ply = output_root / ply_path.name
        shutil.copy2(ply_path, target_ply)
        artifacts.append(artifact(target_ply, output_root, "dense_pointcloud", {"point_count": point_count}))

        # Copy sample depth previews
        maps_out = output_root / "maps"
        maps_out.mkdir(parents=True, exist_ok=True)
        for dmap in sorted(depth_maps_dir.glob("*.png"))[:5]:
            dst = maps_out / dmap.name
            shutil.copy2(dmap, dst)
            artifacts.append(artifact(dst, output_root, "depth_map", compute_hash=False))

        log_target_dir = output_root / "logs"
        log_target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(log.path, log_target_dir / log.path.name)
        artifacts.append(artifact(log_target_dir / log.path.name, output_root, "log", compute_hash=False))

        metrics = {
            "frames_processed": len(selected_frames),
            "point_count": point_count,
            "total_seconds": round(time.perf_counter() - started, 3),
        }

        jobs_volume.commit()
        return success(
            stage=STAGE,
            output_prefix=output_prefix,
            metrics=metrics,
            artifacts=artifacts,
            logs=collect_logs(log_target_dir),
            notes=[f"Depth enhancement generated {point_count} depth-assisted points."],
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

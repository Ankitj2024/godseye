"""Semantic masking worker (Modal, GPU).

Runs 2D object detection across keyframes and generates image masks where
dynamic objects (vehicles, people) are blacked out. These masks are passed
to COLMAP so it ignores those pixels during reconstruction.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

from modal_app.common.app import app
from modal_app.common.config import (
    SEMANTIC_CPU,
    SEMANTIC_GPU,
    SEMANTIC_MEMORY_MB,
    SEMANTIC_TIMEOUT_SECONDS,
    VOLUME_MOUNT,
)
from modal_app.common.results import artifact, collect_logs, failure, success, worker_info
from modal_app.common.volumes import jobs_volume, to_container_path
from modal_app.semantics.image import semantic_image

STAGE = "semantic_masking"


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


@app.function(
    image=semantic_image,
    gpu=SEMANTIC_GPU,
    cpu=SEMANTIC_CPU,
    memory=SEMANTIC_MEMORY_MB,
    timeout=SEMANTIC_TIMEOUT_SECONDS,
    volumes={VOLUME_MOUNT: jobs_volume},
)
def generate_masks(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate 2D mask images from keyframes."""
    from PIL import Image, ImageDraw

    output_prefix = payload.get("output_prefix", "")
    output_root = to_container_path(output_prefix)
    work_dir = Path("/tmp/godseye/masking")
    log = _Log(work_dir / "logs" / "masking.log")
    info = worker_info()

    try:
        jobs_volume.reload()

        if work_dir.exists():
            shutil.rmtree(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        masks_dir = work_dir / "masks"
        masks_dir.mkdir(parents=True, exist_ok=True)
        log = _Log(work_dir / "logs" / "masking.log")

        frames_prefix = payload["frames_prefix"]
        frames_dir = to_container_path(frames_prefix)

        image_paths = sorted(
            [p for p in frames_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"}]
        )
        if not image_paths:
            raise FileNotFoundError(f"No keyframe images found at {frames_dir}")

        log(f"Found {len(image_paths)} keyframes for semantic masking")
        started = time.perf_counter()

        target_classes = payload.get(
            "classes", ["vehicle", "person"]
        )
        conf_thresh = float(payload.get("confidence_threshold", 0.35))

        detector = None
        try:
            from transformers import pipeline
            detector = pipeline(
                task="zero-shot-object-detection",
                model="google/owlv2-base-patch16-ensemble",
                device=0 if payload.get("use_gpu", True) else -1,
            )
            log("Loaded OWLv2 zero-shot object detector")
        except Exception as exc:
            log(f"Notice: Transformer zero-shot detector not loaded ({exc}). Using dummy masking.")

        total_masks_drawn = 0
        
        for img_path in image_paths:
            pil_img = Image.open(img_path).convert("RGB")
            w, h = pil_img.size
            
            # Create a white canvas (white = keep pixel)
            mask_img = Image.new("L", (w, h), 255)
            draw = ImageDraw.Draw(mask_img)

            masked_objects = 0
            if detector is not None:
                try:
                    preds = detector(
                        pil_img, candidate_labels=target_classes, threshold=conf_thresh
                    )
                    for pred in preds:
                        box = pred["box"]
                        # Draw black rectangle (black = mask out pixel)
                        draw.rectangle(
                            [box["xmin"], box["ymin"], box["xmax"], box["ymax"]],
                            fill=0
                        )
                        masked_objects += 1
                except Exception as exc:
                    log(f"Detection failed on frame {img_path.name}: {exc}")
            
            # Save mask as {image_name}.png
            # e.g. frame_0001.jpg -> frame_0001.jpg.png
            mask_path = masks_dir / f"{img_path.name}.png"
            mask_img.save(mask_path, format="PNG")
            
            if masked_objects > 0:
                total_masks_drawn += 1

        log(f"Generated {len(image_paths)} masks. {total_masks_drawn} frames had masked objects.")

        # Publish to Volume
        if output_root.exists():
            shutil.rmtree(output_root)
        output_root.mkdir(parents=True, exist_ok=True)

        for mask_path in masks_dir.iterdir():
            shutil.copy2(mask_path, output_root / mask_path.name)

        artifacts_list = []
        
        log_target_dir = output_root / "logs"
        log_target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(log.path, log_target_dir / log.path.name)
        artifacts_list.append(artifact(log_target_dir / log.path.name, output_root, "log", compute_hash=False))

        metrics = {
            "total_masks": len(image_paths),
            "frames_with_masks": total_masks_drawn,
            "total_seconds": round(time.perf_counter() - started, 3),
        }

        jobs_volume.commit()
        return success(
            stage=STAGE,
            output_prefix=output_prefix,
            metrics=metrics,
            artifacts=artifacts_list,
            logs=collect_logs(log_target_dir),
            notes=[f"Generated {len(image_paths)} image masks."],
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

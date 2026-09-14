"""Stage 2: intelligent keyframe selection (local, CPU).

Reduces the candidate set to a curated keyframe set that COLMAP can actually
work with. Three signals, applied in this order:

1. **Sharpness** - variance of the Laplacian. Motion-blurred drone frames poison
   feature matching, so they are dropped first.
2. **Novelty** - mean absolute difference between mean-centred low-resolution
   signatures. This removes near-duplicate frames from hover segments while
   keeping frames that actually add new viewpoints.
3. **Spacing** - a minimum candidate gap, so a burst of "novel" frames caused by
   noise cannot crowd out real coverage.

If the thresholds are too aggressive for a given video, they are relaxed
progressively rather than failing the run, and the relaxation is recorded.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from godseye.errors import StageExecutionError
from godseye.pipeline.context import StageContext
from godseye.pipeline.stage import Stage, StageOutcome
from godseye.schemas.enums import ArtifactKind, ExecutionTarget, StageName
from godseye.utils.fs import copy_file, read_json, reset_dir, write_json
from godseye.utils.video import require_cv2


class KeyframeSelectionStage(Stage):
    name = StageName.KEYFRAME_SELECTION
    target = ExecutionTarget.LOCAL
    description = "Score candidates on blur/novelty/spacing and curate the keyframe set."

    def reset(self, paths) -> None:
        reset_dir(paths.selected_frames_dir)

    def run(self, ctx: StageContext) -> StageOutcome:
        cv2 = require_cv2()
        log = ctx.logger(self.name)
        settings = ctx.config.keyframes

        index_path = ctx.paths.candidate_index_path
        if not index_path.exists():
            raise StageExecutionError(
                f"Candidate index not found at {index_path}. Run frame extraction first."
            )

        index = read_json(index_path)
        candidates: list[dict[str, Any]] = index.get("frames", [])
        if not candidates:
            raise StageExecutionError("Candidate index contains no frames.")

        candidate_dir = ctx.paths.candidate_frames_dir
        scores = self._score_candidates(cv2, candidate_dir, candidates, settings.signature_size, log)

        sharpness = np.array([s["sharpness"] for s in scores], dtype=np.float64)
        median_sharpness = float(np.median(sharpness))
        relative_floor = median_sharpness * settings.blur_relative_factor
        blur_threshold = max(settings.absolute_blur_floor, relative_floor)
        log.info(
            "Sharpness threshold %.2f (median=%.2f x %.2f, floor=%.2f)",
            blur_threshold,
            median_sharpness,
            settings.blur_relative_factor,
            settings.absolute_blur_floor,
        )

        sharp = [s for s in scores if s["sharpness"] >= blur_threshold]
        log.info("%d of %d candidates passed the sharpness gate.", len(sharp), len(scores))

        if len(sharp) < settings.min_count:
            log.warning(
                "Only %d frames passed the sharpness gate; falling back to the whole "
                "candidate set ranked by sharpness.",
                len(sharp),
            )
            sharp = sorted(scores, key=lambda s: s["sharpness"], reverse=True)
            sharp = sorted(sharp[: max(settings.min_count * 4, 40)], key=lambda s: s["candidate_index"])

        selected, novelty_used, relaxations = self._select_with_relaxation(
            sharp, settings, log
        )

        # Density is controlled here rather than by the novelty gate, so coverage
        # stays even across the whole flight instead of clustering where the
        # scene happened to change fastest.
        if len(selected) > settings.max_count:
            selected = _uniform_subsample(selected, settings.target_count)
            log.info("Subsampled to %d keyframes (max_count=%d).", len(selected), settings.max_count)

        if len(selected) < settings.min_count:
            raise StageExecutionError(
                f"Only {len(selected)} keyframes survived selection but at least "
                f"{settings.min_count} are needed for reconstruction. The footage may be "
                "too blurry, too static, or too short."
            )

        selected_dir = reset_dir(ctx.paths.selected_frames_dir)
        records = self._materialize(selected, candidate_dir, selected_dir)

        timestamps = [r["timestamp_s"] for r in records]
        selection_doc = {
            "job_id": ctx.job_id,
            "candidate_count": len(candidates),
            "sharp_count": len(sharp),
            "selected_count": len(records),
            "blur_threshold": round(blur_threshold, 4),
            "median_sharpness": round(median_sharpness, 4),
            "novelty_threshold": round(novelty_used, 6),
            "relaxation_steps": relaxations,
            "min_spacing_frames": settings.min_spacing_frames,
            "timespan_seconds": round(max(timestamps) - min(timestamps), 3) if timestamps else 0.0,
            "frames": records,
        }
        write_json(ctx.paths.selection_path, selection_doc)

        notes = [f"Selected {len(records)} of {len(candidates)} candidates."]
        if relaxations:
            notes.append(
                f"Novelty threshold relaxed {relaxations}x to {novelty_used:.5f} to reach "
                "a usable keyframe count."
            )

        outcome = StageOutcome(
            metrics={
                "candidate_count": len(candidates),
                "sharp_count": len(sharp),
                "keyframe_count": len(records),
                "blur_threshold": round(blur_threshold, 4),
                "median_sharpness": round(median_sharpness, 4),
                "novelty_threshold": round(novelty_used, 6),
                "relaxation_steps": relaxations,
                "mean_sharpness": round(float(np.mean([r["sharpness"] for r in records])), 3),
                "timespan_seconds": selection_doc["timespan_seconds"],
            },
            notes=notes,
        )
        outcome.add_artifact(
            ctx.paths.selection_path,
            ArtifactKind.METADATA,
            artifact_id="keyframe_selection:selection.json",
        )
        return outcome

    # -- internals ---------------------------------------------------------

    def _score_candidates(
        self,
        cv2: Any,
        candidate_dir: Path,
        candidates: list[dict[str, Any]],
        signature_size: int,
        log: Any,
    ) -> list[dict[str, Any]]:
        scores: list[dict[str, Any]] = []
        unreadable = 0

        for entry in candidates:
            path = candidate_dir / entry["filename"]
            image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if image is None:
                unreadable += 1
                continue

            sharpness = float(cv2.Laplacian(image, cv2.CV_64F).var())
            brightness = float(image.mean())
            thumb = cv2.resize(
                image, (signature_size, signature_size), interpolation=cv2.INTER_AREA
            ).astype(np.float32) / 255.0
            signature = thumb - float(thumb.mean())  # mean-centred: ignore exposure drift

            scores.append(
                {
                    "candidate_index": entry["candidate_index"],
                    "source_frame": entry["source_frame"],
                    "timestamp_s": entry["timestamp_s"],
                    "filename": entry["filename"],
                    "sharpness": round(sharpness, 4),
                    "brightness": round(brightness, 2),
                    "signature": signature.ravel(),
                }
            )

        if unreadable:
            log.warning("Skipped %d unreadable candidate frames.", unreadable)
        if not scores:
            raise StageExecutionError("No candidate frames could be read for scoring.")

        log.info("Scored %d candidate frames.", len(scores))
        return scores

    def _select_with_relaxation(
        self, sharp: list[dict[str, Any]], settings: Any, log: Any
    ) -> tuple[list[dict[str, Any]], float, int]:
        threshold = settings.novelty_threshold
        for step in range(settings.relax_steps + 1):
            selected = _greedy_select(sharp, threshold, settings.min_spacing_frames)
            if len(selected) >= settings.min_count or step == settings.relax_steps:
                return selected, threshold, step
            threshold /= 2.0
            log.info(
                "Only %d keyframes at novelty %.5f; relaxing threshold.",
                len(selected),
                threshold * 2.0,
            )
        return [], threshold, settings.relax_steps  # pragma: no cover - unreachable

    def _materialize(
        self,
        selected: list[dict[str, Any]],
        candidate_dir: Path,
        selected_dir: Path,
    ) -> list[dict[str, Any]]:
        """Copy chosen frames into COLMAP-friendly sequential filenames."""
        records: list[dict[str, Any]] = []
        for position, entry in enumerate(selected, start=1):
            filename = f"frame_{position:05d}.jpg"
            copy_file(candidate_dir / entry["filename"], selected_dir / filename)
            records.append(
                {
                    "keyframe_index": position,
                    "filename": filename,
                    "source_candidate": entry["filename"],
                    "source_frame": entry["source_frame"],
                    "timestamp_s": entry["timestamp_s"],
                    "sharpness": entry["sharpness"],
                    "brightness": entry["brightness"],
                }
            )
        return records


def _greedy_select(
    scored: list[dict[str, Any]], novelty_threshold: float, min_spacing: int
) -> list[dict[str, Any]]:
    """Walk forward in time, keeping frames that add new information."""
    selected: list[dict[str, Any]] = []
    last_signature: np.ndarray | None = None
    last_index: int | None = None

    for entry in scored:
        if last_signature is None:
            selected.append(entry)
            last_signature = entry["signature"]
            last_index = entry["candidate_index"]
            continue

        if last_index is not None and entry["candidate_index"] - last_index < min_spacing:
            continue

        distance = float(np.mean(np.abs(entry["signature"] - last_signature)))
        if distance >= novelty_threshold:
            selected.append(entry)
            last_signature = entry["signature"]
            last_index = entry["candidate_index"]

    return selected


def _uniform_subsample(items: list[dict[str, Any]], target: int) -> list[dict[str, Any]]:
    """Evenly thin a list while always keeping the first and last element."""
    if target <= 0 or len(items) <= target:
        return items
    positions = np.linspace(0, len(items) - 1, num=target)
    keep = sorted({int(round(p)) for p in positions})
    return [items[i] for i in keep]

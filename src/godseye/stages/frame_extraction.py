"""Stage 1: candidate frame extraction (local, CPU).

Decoding happens locally on purpose. A 10-minute 4K drone video is gigabytes;
uploading it to decode remotely would cost far more bandwidth than uploading the
few hundred keyframes that actually reach COLMAP. Decode is cheap, transfer is
not.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from godseye.errors import StageExecutionError
from godseye.pipeline.context import StageContext
from godseye.pipeline.stage import Stage, StageOutcome
from godseye.schemas.enums import ArtifactKind, ExecutionTarget, StageName
from godseye.utils.fs import reset_dir, write_json
from godseye.utils.video import require_cv2


class FrameExtractionStage(Stage):
    name = StageName.FRAME_EXTRACTION
    target = ExecutionTarget.LOCAL
    description = "Decode the video and write evenly spaced candidate frames to disk."

    def reset(self, paths) -> None:
        reset_dir(paths.candidate_frames_dir)

    def run(self, ctx: StageContext) -> StageOutcome:
        cv2 = require_cv2()
        log = ctx.logger(self.name)
        settings = ctx.config.frames

        video = ctx.manifest.video
        if video is None:
            raise StageExecutionError("Job manifest has no video metadata; job setup did not run.")

        video_path = ctx.paths.resolve(video.staged_relative_path)
        if not video_path.exists():
            raise StageExecutionError(f"Staged video is missing: {video_path}")

        source_fps = video.fps or 0.0
        if source_fps <= 0:
            raise StageExecutionError("Video frame rate is unknown; cannot plan sampling.")

        stride = max(1, int(round(source_fps / settings.sample_fps)))
        total_frames = video.frame_count or 0
        planned = (total_frames // stride) if total_frames else 0

        # Widen the stride rather than truncating the timeline, so candidates
        # always span the whole flight instead of stopping halfway through.
        if planned > settings.max_candidates and settings.max_candidates > 0:
            stride = max(stride, -(-total_frames // settings.max_candidates))
            planned = total_frames // stride

        log.info(
            "Sampling every %d frames (source %.2f fps -> ~%.2f fps, ~%d candidates)",
            stride,
            source_fps,
            source_fps / stride,
            planned,
        )

        output_dir = reset_dir(ctx.paths.candidate_frames_dir)
        records = self._decode(
            cv2=cv2,
            video_path=video_path,
            output_dir=output_dir,
            stride=stride,
            source_fps=source_fps,
            max_width=settings.max_width,
            jpeg_quality=settings.jpeg_quality,
            max_candidates=settings.max_candidates,
            log=log,
        )

        if not records:
            raise StageExecutionError(
                f"No frames could be decoded from {video_path}. The file may be corrupt."
            )

        index = {
            "job_id": ctx.job_id,
            "source_video": video.staged_relative_path,
            "source_fps": source_fps,
            "stride": stride,
            "effective_fps": round(source_fps / stride, 4),
            "max_width": settings.max_width,
            "candidate_count": len(records),
            "frames": records,
        }
        write_json(ctx.paths.candidate_index_path, index)

        outcome = StageOutcome(
            metrics={
                "candidate_count": len(records),
                "stride": stride,
                "effective_fps": round(source_fps / stride, 4),
                "first_timestamp_s": records[0]["timestamp_s"],
                "last_timestamp_s": records[-1]["timestamp_s"],
                "resized": records[0]["width"] != video.width,
            },
            notes=[f"Extracted {len(records)} candidate frames at stride {stride}."],
        )
        outcome.add_artifact(
            ctx.paths.candidate_index_path,
            ArtifactKind.METADATA,
            artifact_id="frame_extraction:candidates.json",
        )
        return outcome

    def _decode(
        self,
        *,
        cv2: Any,
        video_path: Path,
        output_dir: Path,
        stride: int,
        source_fps: float,
        max_width: int,
        jpeg_quality: int,
        max_candidates: int,
        log: Any,
    ) -> list[dict[str, Any]]:
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            raise StageExecutionError(f"OpenCV could not open {video_path}")

        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)]
        records: list[dict[str, Any]] = []
        frame_index = 0
        kept = 0

        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break

                if frame_index % stride == 0:
                    height, width = frame.shape[:2]
                    if max_width and width > max_width:
                        scale = max_width / float(width)
                        frame = cv2.resize(
                            frame,
                            (max_width, int(round(height * scale))),
                            interpolation=cv2.INTER_AREA,
                        )
                        height, width = frame.shape[:2]

                    filename = f"cand_{kept:06d}.jpg"
                    if not cv2.imwrite(str(output_dir / filename), frame, encode_params):
                        raise StageExecutionError(f"Failed to write frame {filename}")

                    records.append(
                        {
                            "candidate_index": kept,
                            "source_frame": frame_index,
                            "timestamp_s": round(frame_index / source_fps, 3),
                            "filename": filename,
                            "width": width,
                            "height": height,
                        }
                    )
                    kept += 1
                    if kept % 250 == 0:
                        log.info("Extracted %d candidate frames...", kept)
                    if max_candidates and kept >= max_candidates:
                        log.info("Reached max_candidates=%d, stopping decode.", max_candidates)
                        break

                frame_index += 1
        finally:
            capture.release()

        log.info("Decoded %d frames, kept %d candidates.", frame_index, kept)
        return records

"""Stage: semantic 2D masking (Modal, GPU).

Runs 2D object detection on keyframes and generates image masks before
3D reconstruction, so dynamic objects can be ignored by COLMAP.
"""

from __future__ import annotations

from typing import Any

from godseye.errors import StageExecutionError
from godseye.pipeline.context import StageContext
from godseye.remote.transport import ModalTransport
from godseye.schemas.enums import ExecutionTarget, Provenance, StageName
from godseye.schemas.remote import SemanticMaskingRequest
from godseye.stages.remote_stage import RemoteStage
from godseye.utils.fs import count_files


class SemanticMaskingStage(RemoteStage):
    name = StageName.SEMANTIC_MASKING
    target = ExecutionTarget.MODAL
    description = "2D Semantic Masking for dynamic objects."
    function_setting = "masking_function"
    remote_output_name = "masks"
    provenance = Provenance.OBSERVED

    def stage_inputs(self, ctx: StageContext, transport: ModalTransport) -> dict[str, Any]:
        frames_dir = ctx.paths.selected_frames_dir
        keyframe_count = count_files(frames_dir, "*.jpg")
        if keyframe_count == 0:
            raise StageExecutionError(
                f"No keyframes found in {frames_dir}. Run keyframe selection first."
            )

        remote_frames = transport.remote_path("frames")
        transport.remove_prefix(remote_frames)
        report = transport.upload_dir(frames_dir, remote_frames)
        return {
            "uploaded_keyframes": report.file_count,
            "uploaded_bytes": report.total_bytes,
        }

    def build_payload(self, ctx: StageContext, transport: ModalTransport) -> dict[str, Any]:
        settings = ctx.config.masking
        request = SemanticMaskingRequest(
            job_id=ctx.job_id,
            frames_prefix=transport.remote_path("frames"),
            output_prefix=transport.remote_path(self.remote_output_name),
            confidence_threshold=settings.confidence_threshold,
            classes=settings.classes,
            use_gpu=settings.use_gpu,
        )
        return request.model_dump()

    def enrich(self, ctx, result, outcome, local_dir) -> None:
        frames_with_masks = result.metrics.get("frames_with_masks")
        if frames_with_masks is not None:
            outcome.notes.append(f"Generated masks for {frames_with_masks} frames containing dynamic objects.")

"""Stage: semantic 3D object detection (Modal, GPU).

Runs 2D detection on keyframes, projects bounding boxes into 3D using camera poses
and triangulated geometry, and outputs structured 3D cuboid metadata (objects.json).
"""

from __future__ import annotations

from typing import Any

from godseye.pipeline.context import StageContext
from godseye.remote.transport import ModalTransport
from godseye.schemas.enums import ExecutionTarget, Provenance, StageName
from godseye.schemas.remote import SemanticRequest
from godseye.stages.remote_stage import RemoteStage


class SemanticDetectionStage(RemoteStage):
    name = StageName.SEMANTIC_DETECTION
    target = ExecutionTarget.MODAL
    description = "Semantic 3D object detection and cuboid metadata."
    function_setting = "semantic_function"
    remote_output_name = "semantics"
    provenance = Provenance.OBSERVED

    def build_payload(self, ctx: StageContext, transport: ModalTransport) -> dict[str, Any]:
        settings = ctx.config.semantics
        request = SemanticRequest(
            job_id=ctx.job_id,
            frames_prefix=transport.remote_path("frames"),
            reconstruction_prefix=transport.remote_path("reconstruction"),
            output_prefix=transport.remote_path(self.remote_output_name),
            confidence_threshold=settings.confidence_threshold,
            classes=settings.classes,
            use_gpu=settings.use_gpu,
        )
        return request.model_dump()

    def enrich(self, ctx, result, outcome, local_dir) -> None:
        object_count = result.metrics.get("object_count")
        if object_count is not None:
            outcome.notes.append(f"Detected {object_count} 3D semantic objects.")

"""Stage: depth enhancement (Modal, GPU).

Runs monocular depth estimation on keyframes and unprojects depth maps into a
densified point cloud to reinforce weakly triangulated or textureless surfaces.
"""

from __future__ import annotations

from typing import Any

from godseye.pipeline.context import StageContext
from godseye.remote.transport import ModalTransport
from godseye.schemas.enums import ExecutionTarget, Provenance, StageName
from godseye.schemas.remote import DepthRequest
from godseye.stages.remote_stage import RemoteStage


class DepthEnhancementStage(RemoteStage):
    name = StageName.DEPTH_ENHANCEMENT
    target = ExecutionTarget.MODAL
    description = "Monocular depth estimation to strengthen weak geometry."
    function_setting = "depth_function"
    remote_output_name = "depth"
    provenance = Provenance.DEPTH_ASSISTED

    def build_payload(self, ctx: StageContext, transport: ModalTransport) -> dict[str, Any]:
        settings = ctx.config.depth
        request = DepthRequest(
            job_id=ctx.job_id,
            frames_prefix=transport.remote_path("frames"),
            reconstruction_prefix=transport.remote_path("reconstruction"),
            output_prefix=transport.remote_path(self.remote_output_name),
            model_name=settings.model_name,
            max_depth=settings.max_depth,
            densify=settings.densify,
            use_gpu=settings.use_gpu,
        )
        return request.model_dump()

    def enrich(self, ctx, result, outcome, local_dir) -> None:
        point_count = result.metrics.get("point_count")
        if point_count is not None:
            outcome.notes.append(f"Depth enhancement produced {point_count} points.")

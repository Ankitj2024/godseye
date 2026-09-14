"""Stage: generative completion (Modal, CPU/GPU).

Enabled only in GENERATIVE mode. Consumes exact geometry and semantic objects,
matches detected classes against the asset library, scales/aligns proxy 3D models,
and outputs a separate generative_scene.glb.
"""

from __future__ import annotations

from typing import Any

from godseye.pipeline.context import StageContext
from godseye.remote.transport import ModalTransport
from godseye.schemas.enums import ExecutionTarget, PipelineMode, Provenance, StageName
from godseye.schemas.remote import GenerativeRequest
from godseye.stages.remote_stage import RemoteStage


class GenerativeCompletionStage(RemoteStage):
    name = StageName.GENERATIVE_COMPLETION
    target = ExecutionTarget.MODAL
    description = "Asset-library scene completion for ambiguous or incomplete regions."
    function_setting = "generative_function"
    remote_output_name = "completion"
    provenance = Provenance.INFERRED

    def applies_to(self, mode: PipelineMode) -> bool:
        return mode == PipelineMode.GENERATIVE

    def stage_inputs(self, ctx: StageContext, transport: ModalTransport) -> dict[str, Any]:
        assets_dir = ctx.config.assets_root
        if assets_dir.exists() and any(assets_dir.iterdir()):
            remote_assets = transport.remote_path("assets")
            report = transport.upload_dir(assets_dir, remote_assets)
            return {
                "uploaded_assets": report.file_count,
                "uploaded_asset_bytes": report.total_bytes,
            }
        return {}

    def build_payload(self, ctx: StageContext, transport: ModalTransport) -> dict[str, Any]:
        settings = ctx.config.generative
        request = GenerativeRequest(
            job_id=ctx.job_id,
            geometry_prefix=transport.remote_path("geometry"),
            semantics_prefix=transport.remote_path("semantics"),
            output_prefix=transport.remote_path(self.remote_output_name),
            asset_library_prefix=transport.remote_path("assets"),
            fill_missing=settings.fill_missing,
            max_proxy_insertions=settings.max_proxy_insertions,
        )
        return request.model_dump()

    def enrich(self, ctx, result, outcome, local_dir) -> None:
        inserted = result.metrics.get("proxy_assets_inserted")
        if inserted is not None:
            outcome.notes.append(f"Generative completion inserted {inserted} proxy 3D assets.")

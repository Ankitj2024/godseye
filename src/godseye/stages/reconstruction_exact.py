"""Stage 3: exact reconstruction with COLMAP (Modal, GPU).

This is the evidence-first baseline the whole product rests on. Nothing here
invents geometry: keyframes go in, camera poses and point clouds come out, and
weakly observed regions stay sparse.

Runs on Modal because it needs CUDA (SIFT extraction, patch-match stereo) and a
full COLMAP install, neither of which belongs on the control-plane machine.
"""

from __future__ import annotations

from typing import Any

from godseye.errors import StageExecutionError
from godseye.pipeline.context import StageContext
from godseye.remote.transport import ModalTransport
from godseye.schemas.enums import PipelineMode, StageName
from godseye.schemas.remote import ReconstructionRequest
from godseye.stages.remote_stage import RemoteStage
from godseye.utils.fs import count_files


class ExactReconstructionStage(RemoteStage):
    name = StageName.RECONSTRUCTION_EXACT
    description = "COLMAP structure-from-motion plus optional dense stereo fusion."
    function_setting = "reconstruction_function"
    remote_output_name = "reconstruction"

    def applies_to(self, mode: PipelineMode) -> bool:
        # Generative mode builds on top of the exact baseline, so it also needs this.
        return True

    def stage_inputs(self, ctx: StageContext, transport: ModalTransport) -> dict[str, Any]:
        frames_dir = ctx.paths.selected_frames_dir
        keyframe_count = count_files(frames_dir, "*.jpg")
        if keyframe_count == 0:
            raise StageExecutionError(
                f"No keyframes found in {frames_dir}. Run keyframe selection first."
            )

        remote_frames = transport.remote_path("frames")
        report = transport.upload_dir(frames_dir, remote_frames)
        return {
            "uploaded_keyframes": report.file_count,
            "uploaded_bytes": report.total_bytes,
        }

    def build_payload(self, ctx: StageContext, transport: ModalTransport) -> dict[str, Any]:
        settings = ctx.config.reconstruction
        keyframe_count = count_files(ctx.paths.selected_frames_dir, "*.jpg")
        matcher = self._resolve_matcher(settings, keyframe_count)

        ctx.logger(self.name).info(
            "Reconstructing %d keyframes with %s matcher (dense=%s)",
            keyframe_count,
            matcher,
            settings.run_dense,
        )

        request = ReconstructionRequest(
            job_id=ctx.job_id,
            frames_prefix=transport.remote_path("frames"),
            output_prefix=transport.remote_path(self.remote_output_name),
            camera_model=settings.camera_model,
            single_camera=settings.single_camera,
            matcher=matcher,
            run_dense=settings.run_dense,
            max_image_size=settings.max_image_size,
            dense_max_image_size=settings.dense_max_image_size,
            use_gpu=settings.use_gpu,
            max_num_features=settings.max_num_features,
            init_min_tri_angle=settings.init_min_tri_angle,
            init_max_forward_motion=settings.init_max_forward_motion,
            init_num_trials=settings.init_num_trials,
        )
        return request.model_dump()

    def _resolve_matcher(self, settings: Any, keyframe_count: int) -> str:
        """Exhaustive matching is best but is O(n^2); switch to sequential when large.

        Drone footage is captured as a continuous sweep, so sequential matching
        loses little for big keyframe sets and saves a lot of compute.
        """
        if settings.matcher != "auto":
            return settings.matcher
        return "exhaustive" if keyframe_count <= settings.exhaustive_max_images else "sequential"

    def enrich(self, ctx, result, outcome, local_dir) -> None:
        if result.metrics.get("dense_skipped_reason"):
            outcome.notes.append(
                f"Dense reconstruction skipped: {result.metrics['dense_skipped_reason']}"
            )

        settings = ctx.config.reconstruction
        registered = result.metrics.get("registered_images")
        submitted = result.metrics.get("input_images")
        if registered is None or not submitted:
            return

        ratio = registered / submitted
        outcome.metrics["registration_ratio"] = round(ratio, 4)

        # A reconstruction that dropped most of its views produces geometry that
        # only covers a fraction of the scene. Reporting that as success would be
        # dishonest, so it fails loudly with the specific levers to pull.
        if registered < settings.min_registered_images or ratio < settings.min_registration_ratio:
            raise StageExecutionError(
                f"Reconstruction registered only {registered}/{submitted} keyframes "
                f"({ratio:.0%}); the minimum is {settings.min_registered_images} images and "
                f"{settings.min_registration_ratio:.0%}.\n"
                "This usually means the footage lacks parallax (the camera rotates or flies "
                "straight along its viewing axis) rather than orbiting the subject.\n"
                "Things to try:\n"
                "  - increase keyframe density: GODSEYE_FRAMES__SAMPLE_FPS=6 --max-keyframes 150\n"
                "  - relax initialisation: GODSEYE_RECONSTRUCTION__INIT_MIN_TRI_ANGLE=1.0\n"
                "  - use footage with sideways/orbiting motion\n"
                f"Evidence kept for inspection in {local_dir}"
            )

        if ratio < 0.8:
            outcome.notes.append(
                f"Only {registered}/{submitted} images registered ({ratio:.0%}). Coverage is "
                "partial: expect gaps."
            )

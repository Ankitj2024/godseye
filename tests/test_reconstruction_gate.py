"""Reconstruction quality gate.

A reconstruction that registers only a handful of its keyframes covers a fraction
of the scene. These tests pin the behaviour that such a run fails loudly instead
of being reported as a success.
"""

from __future__ import annotations

import pytest

from godseye.config import PipelineConfig
from godseye.errors import StageExecutionError
from godseye.orchestrator.job import JobPaths, new_job_id
from godseye.orchestrator.manifest_store import ManifestStore
from godseye.pipeline.context import StageContext
from godseye.pipeline.stage import StageOutcome
from godseye.schemas.enums import PipelineMode
from godseye.schemas.remote import RemoteStageResult
from godseye.stages.reconstruction_exact import ExactReconstructionStage


def _ctx(config: PipelineConfig) -> StageContext:
    paths = JobPaths(
        job_id=new_job_id(),
        work_root=config.work_root,
        outputs_root=config.outputs_root,
    ).create()
    store = ManifestStore.create(paths, PipelineMode.EXACT, {})
    return StageContext(
        job_id=paths.job_id,
        mode=PipelineMode.EXACT,
        paths=paths,
        config=config,
        store=store,
    )


def _result(registered: int, submitted: int) -> RemoteStageResult:
    return RemoteStageResult.model_validate(
        {
            "stage": "reconstruction_exact",
            "status": "completed",
            "metrics": {"registered_images": registered, "input_images": submitted},
        }
    )


def test_mostly_unregistered_reconstruction_fails(config: PipelineConfig):
    ctx = _ctx(config)
    stage = ExactReconstructionStage()
    outcome = StageOutcome()

    # The real sample.mp4 failure mode: 2 of 17 keyframes registered.
    with pytest.raises(StageExecutionError) as excinfo:
        stage.enrich(ctx, _result(2, 17), outcome, ctx.paths.reconstruction_dir)

    message = str(excinfo.value)
    assert "2/17" in message
    assert "parallax" in message
    # The error must name the levers, not just complain.
    assert "SAMPLE_FPS" in message
    assert "INIT_MIN_TRI_ANGLE" in message


def test_too_few_absolute_images_fails_even_at_full_ratio(config: PipelineConfig):
    ctx = _ctx(config)
    with pytest.raises(StageExecutionError):
        # 100% registered, but 3 views cannot describe a scene.
        ExactReconstructionStage().enrich(
            ctx, _result(3, 3), StageOutcome(), ctx.paths.reconstruction_dir
        )


def test_good_reconstruction_passes_and_records_ratio(config: PipelineConfig):
    ctx = _ctx(config)
    outcome = StageOutcome()

    ExactReconstructionStage().enrich(
        ctx, _result(48, 50), outcome, ctx.paths.reconstruction_dir
    )

    assert outcome.metrics["registration_ratio"] == 0.96
    assert outcome.notes == []


def test_partial_coverage_passes_with_explicit_warning(config: PipelineConfig):
    ctx = _ctx(config)
    outcome = StageOutcome()

    ExactReconstructionStage().enrich(
        ctx, _result(35, 50), outcome, ctx.paths.reconstruction_dir
    )

    assert outcome.metrics["registration_ratio"] == 0.7
    assert any("70%" in note for note in outcome.notes)


def test_gate_thresholds_are_configurable(config: PipelineConfig):
    config.reconstruction.min_registration_ratio = 0.1
    config.reconstruction.min_registered_images = 2
    ctx = _ctx(config)

    outcome = StageOutcome()
    ExactReconstructionStage().enrich(
        ctx, _result(2, 17), outcome, ctx.paths.reconstruction_dir
    )
    assert outcome.metrics["registration_ratio"] == pytest.approx(0.1176, abs=1e-4)


def test_matcher_switches_to_sequential_for_large_sets(config: PipelineConfig):
    stage = ExactReconstructionStage()
    settings = config.reconstruction

    assert stage._resolve_matcher(settings, 20) == "exhaustive"
    assert stage._resolve_matcher(settings, settings.exhaustive_max_images + 1) == "sequential"

    settings.matcher = "sequential"
    assert stage._resolve_matcher(settings, 5) == "sequential"


def test_sfm_tuning_reaches_the_payload(config: PipelineConfig):
    """Aerial-motion defaults must actually be sent to the worker."""
    from godseye.schemas.remote import ReconstructionRequest

    request = ReconstructionRequest(
        job_id="x",
        frames_prefix="/jobs/x/frames",
        output_prefix="/jobs/x/reconstruction",
        max_num_features=config.reconstruction.max_num_features,
        init_min_tri_angle=config.reconstruction.init_min_tri_angle,
        init_max_forward_motion=config.reconstruction.init_max_forward_motion,
    )
    payload = request.model_dump()

    assert payload["max_num_features"] == 40000
    assert payload["init_min_tri_angle"] == 4.0
    assert payload["init_max_forward_motion"] == 1.0

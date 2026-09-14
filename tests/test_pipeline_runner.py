"""Runner semantics: resume, force, skip, and failure containment."""

from __future__ import annotations

from typing import ClassVar

import pytest

from godseye.config import PipelineConfig
from godseye.errors import RemoteStageError, StageExecutionError
from godseye.orchestrator.job import JobPaths, new_job_id
from godseye.orchestrator.manifest_store import ManifestStore
from godseye.orchestrator.runner import PipelineRunner
from godseye.pipeline.stage import NotImplementedStage, SkipStage, Stage, StageOutcome
from godseye.schemas.enums import (
    ArtifactKind,
    ExecutionTarget,
    FailureOrigin,
    JobStatus,
    PipelineMode,
    StageName,
    StageStatus,
)


class RecordingStage(Stage):
    """A stage that records how many times it ran."""

    name: ClassVar[StageName] = StageName.FRAME_EXTRACTION
    target: ClassVar[ExecutionTarget] = ExecutionTarget.LOCAL
    description = "test stage"

    def __init__(self) -> None:
        self.calls = 0
        self.resets = 0

    def reset(self, paths) -> None:
        self.resets += 1

    def run(self, ctx) -> StageOutcome:
        self.calls += 1
        target = ctx.paths.candidate_frames_dir / "cand_000000.jpg"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"jpeg-bytes")
        outcome = StageOutcome(metrics={"calls": self.calls})
        outcome.add_artifact(target, ArtifactKind.FRAME_SET, compute_hash=False)
        return outcome


class FailingStage(Stage):
    name: ClassVar[StageName] = StageName.KEYFRAME_SELECTION
    target: ClassVar[ExecutionTarget] = ExecutionTarget.LOCAL
    description = "always fails"

    def __init__(self, required: bool = True, remote: bool = False) -> None:
        type(self).required = required  # type: ignore[misc]
        self.remote = remote

    def run(self, ctx) -> StageOutcome:
        if self.remote:
            raise RemoteStageError(
                "colmap exited 1",
                exception_type="CommandError",
                failed_command="colmap mapper",
                log_tail=["error line"],
            )
        raise StageExecutionError("local boom")


class SkippingStage(Stage):
    name: ClassVar[StageName] = StageName.GEOMETRY_POSTPROCESS
    target: ClassVar[ExecutionTarget] = ExecutionTarget.MODAL
    description = "skips itself"

    def run(self, ctx) -> StageOutcome:
        raise SkipStage("nothing to do")


class TrailingStage(Stage):
    name: ClassVar[StageName] = StageName.OUTPUT_PACKAGING
    target: ClassVar[ExecutionTarget] = ExecutionTarget.LOCAL
    description = "runs last"

    def __init__(self) -> None:
        self.calls = 0

    def run(self, ctx) -> StageOutcome:
        self.calls += 1
        return StageOutcome(metrics={"packaged": True})


def _make(config: PipelineConfig, stages, force=None):
    paths = JobPaths(
        job_id=new_job_id(),
        work_root=config.work_root,
        outputs_root=config.outputs_root,
    ).create()
    store = ManifestStore.create(paths, PipelineMode.EXACT, {})
    runner = PipelineRunner(
        config=config,
        mode=PipelineMode.EXACT,
        paths=paths,
        store=store,
        stages=stages,
        force_stages=force,
    )
    return paths, store, runner


def test_successful_run_completes_and_registers_artifacts(config: PipelineConfig):
    stage = RecordingStage()
    paths, store, runner = _make(config, [stage])

    report = runner.run()

    assert report.status == JobStatus.COMPLETED
    assert report.executed == [StageName.FRAME_EXTRACTION]
    assert stage.calls == 1
    record = store.manifest.stages[StageName.FRAME_EXTRACTION]
    assert record.status == StageStatus.COMPLETED
    assert "wall_seconds" in record.metrics
    assert len(store.manifest.artifacts) == 1
    # A run summary is always produced, even without a packaging stage.
    assert (paths.output_dir / "run_summary.json").exists()


def test_completed_stage_is_reused_on_second_run(config: PipelineConfig):
    stage = RecordingStage()
    paths, store, runner = _make(config, [stage])
    runner.run()

    second = PipelineRunner(
        config=config,
        mode=PipelineMode.EXACT,
        paths=paths,
        store=store,
        stages=[stage],
    )
    report = second.run()

    assert stage.calls == 1
    assert report.reused == [StageName.FRAME_EXTRACTION]


def test_force_stage_reruns_and_calls_reset(config: PipelineConfig):
    stage = RecordingStage()
    paths, store, runner = _make(config, [stage])
    runner.run()

    forced = PipelineRunner(
        config=config,
        mode=PipelineMode.EXACT,
        paths=paths,
        store=store,
        stages=[stage],
        force_stages={StageName.FRAME_EXTRACTION},
    )
    report = forced.run()

    assert stage.calls == 2
    assert stage.resets == 1
    assert report.executed == [StageName.FRAME_EXTRACTION]


def test_required_failure_aborts_pipeline(config: PipelineConfig):
    trailing = TrailingStage()
    _, store, runner = _make(config, [FailingStage(required=True), trailing])

    report = runner.run()

    assert report.status == JobStatus.FAILED
    assert report.aborted is True
    assert trailing.calls == 0
    record = store.manifest.stages[StageName.KEYFRAME_SELECTION]
    assert record.error is not None
    assert record.error.origin == FailureOrigin.LOCAL


def test_optional_failure_is_partial_and_does_not_abort(config: PipelineConfig):
    trailing = TrailingStage()
    _, store, runner = _make(config, [FailingStage(required=False), trailing])

    report = runner.run()

    assert report.status == JobStatus.PARTIAL
    assert report.aborted is False
    assert trailing.calls == 1


def test_remote_failure_is_attributed_to_modal(config: PipelineConfig):
    _, store, runner = _make(config, [FailingStage(required=True, remote=True)])

    runner.run()

    error = store.manifest.stages[StageName.KEYFRAME_SELECTION].error
    assert error is not None
    assert error.origin == FailureOrigin.MODAL
    assert error.failed_command == "colmap mapper"
    assert error.log_tail == ["error line"]


def test_stage_can_skip_itself(config: PipelineConfig):
    _, store, runner = _make(config, [SkippingStage()])

    report = runner.run()

    assert report.status == JobStatus.COMPLETED
    assert report.skipped == [StageName.GEOMETRY_POSTPROCESS]
    record = store.manifest.stages[StageName.GEOMETRY_POSTPROCESS]
    assert record.status == StageStatus.SKIPPED
    assert record.notes == ["nothing to do"]


def test_unimplemented_stage_is_skipped_with_reason(config: PipelineConfig):
    stage = NotImplementedStage(
        name=StageName.SEMANTIC_DETECTION,
        target=ExecutionTarget.MODAL,
        description="planned",
        planned_phase="phase 7",
    )
    _, store, runner = _make(config, [stage])

    report = runner.run()

    assert report.skipped == [StageName.SEMANTIC_DETECTION]
    record = store.manifest.stages[StageName.SEMANTIC_DETECTION]
    assert record.status == StageStatus.SKIPPED
    assert "phase 7" in record.notes[0]
    # An unbuilt stage must not make the job look degraded.
    assert report.status == JobStatus.COMPLETED


def test_run_summary_reports_failure_details(config: PipelineConfig):
    import json

    paths, _, runner = _make(config, [FailingStage(required=True)])
    runner.run()

    summary = json.loads((paths.output_dir / "run_summary.json").read_text())
    assert summary["status"] == "failed"
    assert any("local boom" in warning for warning in summary["warnings"])
    assert summary["job_id"] == paths.job_id

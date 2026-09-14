"""The pipeline runner.

Owns every manifest state transition so that stage code stays focused on doing
work. Responsibilities:

* skip stages that already completed (resume), unless explicitly forced
* record planned-but-unimplemented stages as skipped, with the reason
* capture failures with the correct origin (local vs Modal)
* let optional stages fail without destroying an otherwise good run
* always leave behind a readable ``run_summary.json``
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Iterable

from godseye.artifacts import packaging
from godseye.config import PipelineConfig
from godseye.errors import GodsEyeError, RemoteStageError
from godseye.orchestrator.job import JobPaths
from godseye.orchestrator.manifest_store import ManifestStore
from godseye.pipeline.context import StageContext
from godseye.pipeline.stage import SkipStage, Stage, StageOutcome
from godseye.schemas.enums import (
    FailureOrigin,
    JobStatus,
    PipelineMode,
    StageName,
    StageStatus,
)
from godseye.schemas.manifest import JobManifest, StageError
from godseye.utils.fs import ensure_dir
from godseye.utils.logging import attach_stage_log, detach_handler, get_logger

logger = get_logger("runner")


@dataclass
class RunReport:
    """Outcome of a whole pipeline run."""

    manifest: JobManifest
    status: JobStatus
    executed: list[StageName] = field(default_factory=list)
    reused: list[StageName] = field(default_factory=list)
    skipped: list[StageName] = field(default_factory=list)
    failed: list[StageName] = field(default_factory=list)
    aborted: bool = False
    summary_path: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in (JobStatus.COMPLETED, JobStatus.PARTIAL)


class PipelineRunner:
    """Executes an ordered stage list against one job."""

    def __init__(
        self,
        config: PipelineConfig,
        mode: PipelineMode,
        paths: JobPaths,
        store: ManifestStore,
        stages: Iterable[Stage],
        force_stages: set[StageName] | None = None,
    ) -> None:
        self.config = config
        self.mode = mode
        self.paths = paths
        self.store = store
        self.stages = list(stages)
        self.force_stages = force_stages or set()
        self.context = StageContext(
            job_id=paths.job_id,
            mode=mode,
            paths=paths,
            config=config,
            store=store,
        )

    # -- main loop ---------------------------------------------------------

    def run(self) -> RunReport:
        report = RunReport(manifest=self.store.manifest, status=JobStatus.RUNNING)
        self.store.set_job_status(JobStatus.RUNNING)

        for stage in self.stages:
            record = self.store.ensure_stage(stage.name, stage.target)

            if not stage.implemented:
                reason = f"not implemented yet ({stage.planned_phase})"
                if record.status != StageStatus.SKIPPED:
                    self.store.skip_stage(stage.name, reason)
                logger.info("Skipping %s: %s", stage.name.value, reason)
                report.skipped.append(stage.name)
                continue

            forced = stage.name in self.force_stages
            if record.status == StageStatus.COMPLETED and not forced:
                logger.info("Reusing completed stage %s", stage.name.value)
                report.reused.append(stage.name)
                continue

            if forced and record.status != StageStatus.PENDING:
                logger.info("Forcing rerun of %s", stage.name.value)
                self.store.reset_stage(stage.name)
                stage.reset(self.paths)

            outcome_status = self._run_stage(stage, report)
            if outcome_status is StageStatus.FAILED and stage.required:
                report.aborted = True
                logger.error(
                    "Aborting pipeline: required stage %s failed.", stage.name.value
                )
                break

        report.status = self._finalize(report)
        return report

    def _run_stage(self, stage: Stage, report: RunReport) -> StageStatus:
        log = get_logger(stage.name.value)
        handler = attach_stage_log(stage.name.value, self.paths.stage_log_path(stage.name))
        self.store.start_stage(stage.name, stage.target)
        started = time.perf_counter()

        logger.info(
            "-> %s (%s): %s", stage.name.value, stage.target.value, stage.description
        )

        try:
            outcome = stage.run(self.context)
        except SkipStage as skip:
            self.store.skip_stage(stage.name, skip.reason)
            log.info("Stage skipped: %s", skip.reason)
            report.skipped.append(stage.name)
            detach_handler(handler)
            return StageStatus.SKIPPED
        except KeyboardInterrupt:
            self.store.fail_stage(
                stage.name,
                StageError(
                    origin=FailureOrigin.LOCAL,
                    exception_type="KeyboardInterrupt",
                    message="Interrupted by user. Rerun with --resume to continue.",
                ),
            )
            detach_handler(handler)
            raise
        except BaseException as exc:  # noqa: BLE001 - recorded, then re-raised or reported
            error = self._build_error(exc)
            self.store.fail_stage(stage.name, error)
            log.error("Stage %s failed: %s", stage.name.value, error.message)
            if error.failed_command:
                log.error("Failed command: %s", error.failed_command)
            for line in error.log_tail:
                log.error("remote| %s", line)
            report.failed.append(stage.name)
            detach_handler(handler)
            if not isinstance(exc, Exception):
                raise
            return StageStatus.FAILED

        self._register_outcome(stage, outcome)
        elapsed = time.perf_counter() - started
        outcome.metrics.setdefault("wall_seconds", round(elapsed, 3))
        self.store.complete_stage(stage.name, outcome.metrics, outcome.notes)
        log.info("Stage %s completed in %.1fs", stage.name.value, elapsed)
        report.executed.append(stage.name)
        detach_handler(handler)
        return StageStatus.COMPLETED

    def _register_outcome(self, stage: Stage, outcome: StageOutcome) -> None:
        for spec in outcome.artifacts:
            self.store.register_artifact(
                stage=stage.name,
                path=spec.path,
                kind=spec.kind,
                provenance=spec.provenance,
                artifact_id=spec.artifact_id,
                metadata=spec.metadata,
                compute_hash=spec.compute_hash,
            )

    # -- failure handling --------------------------------------------------

    @staticmethod
    def _build_error(exc: BaseException) -> StageError:
        origin = FailureOrigin.LOCAL
        failed_command = None
        log_tail: list[str] = []
        remote_logs: list[str] = []

        if isinstance(exc, RemoteStageError):
            origin = FailureOrigin.MODAL
            failed_command = exc.failed_command
            log_tail = exc.log_tail
            remote_logs = exc.remote_logs
        elif isinstance(exc, GodsEyeError):
            origin = exc.origin

        return StageError(
            origin=origin,
            exception_type=type(exc).__name__,
            message=str(exc) or type(exc).__name__,
            traceback=traceback.format_exc(),
            failed_command=failed_command,
            log_tail=log_tail,
            remote_log_paths=remote_logs,
        )

    # -- finalization ------------------------------------------------------

    def _finalize(self, report: RunReport) -> JobStatus:
        required = {stage.name for stage in self.stages if stage.required and stage.implemented}
        manifest = self.store.manifest

        failed = [name for name, rec in manifest.stages.items() if rec.status == StageStatus.FAILED]
        required_failed = [name for name in failed if name in required]

        if required_failed:
            status = JobStatus.FAILED
        elif failed:
            status = JobStatus.PARTIAL
        else:
            status = JobStatus.COMPLETED

        self.store.set_current_stage(None)
        self.store.set_job_status(status)

        # Always leave an output folder with a readable summary, even for a
        # failed run: without a frontend this is the primary status surface.
        ensure_dir(self.paths.output_dir)
        packaging.copy_logs(self.paths, self.paths.output_dir)
        summary_path = packaging.write_run_summary(manifest, self.paths, status)
        report.summary_path = str(summary_path) if summary_path else None
        report.failed = failed
        report.status = status
        return status

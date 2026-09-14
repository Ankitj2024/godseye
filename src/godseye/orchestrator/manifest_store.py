"""Manifest persistence.

Every mutation is followed by an atomic write. That is deliberately chatty but
it is what makes a long multi-stage job resumable after a crash, a Ctrl-C, or a
Modal-side failure.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from godseye.orchestrator.job import JobPaths
from godseye.schemas.enums import (
    ArtifactKind,
    ExecutionTarget,
    JobStatus,
    PipelineMode,
    Provenance,
    StageName,
    StageStatus,
)
from godseye.schemas.manifest import (
    ArtifactRecord,
    JobManifest,
    StageError,
    StageRecord,
    utcnow,
)
from godseye.utils.fs import atomic_write_text
from godseye.utils.hashing import sha256_file
from godseye.utils.logging import get_logger

logger = get_logger("manifest")


class ManifestError(RuntimeError):
    pass


class ManifestStore:
    """Read/write access to one job's ``manifest.json``."""

    def __init__(self, paths: JobPaths, manifest: JobManifest) -> None:
        self.paths = paths
        self.manifest = manifest

    # -- construction ------------------------------------------------------

    @classmethod
    def create(
        cls,
        paths: JobPaths,
        mode: PipelineMode,
        config_snapshot: dict[str, Any],
        planned_stages: list[tuple[StageName, ExecutionTarget]] | None = None,
    ) -> "ManifestStore":
        manifest = JobManifest(
            job_id=paths.job_id,
            mode=mode,
            status=JobStatus.CREATED,
            config=config_snapshot,
        )
        # Job setup always runs first, so it is recorded first: manifest stage
        # order is read as execution order by humans and by `godseye inspect`.
        manifest.stages[StageName.JOB_SETUP] = StageRecord(
            name=StageName.JOB_SETUP, target=ExecutionTarget.LOCAL
        )
        for stage_name, target in planned_stages or []:
            manifest.stages[stage_name] = StageRecord(name=stage_name, target=target)
        store = cls(paths, manifest)
        store.save()
        return store

    @classmethod
    def load(cls, paths: JobPaths) -> "ManifestStore":
        path = paths.manifest_path
        if not path.exists():
            raise ManifestError(f"No manifest at {path}. Is '{paths.job_id}' a real job id?")
        try:
            manifest = JobManifest.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - surfaced verbatim to the user
            raise ManifestError(f"Manifest at {path} is unreadable: {exc}") from exc
        return cls(paths, manifest)

    @classmethod
    def load_or_create(
        cls,
        paths: JobPaths,
        mode: PipelineMode,
        config_snapshot: dict[str, Any],
        planned_stages: list[tuple[StageName, ExecutionTarget]] | None = None,
    ) -> "ManifestStore":
        if paths.manifest_path.exists():
            return cls.load(paths)
        return cls.create(paths, mode, config_snapshot, planned_stages)

    # -- persistence -------------------------------------------------------

    def save(self) -> Path:
        self.manifest.updated_at = utcnow()
        payload = self.manifest.model_dump_json(indent=2)
        return atomic_write_text(self.paths.manifest_path, payload + "\n")

    # -- job level ---------------------------------------------------------

    def set_job_status(self, status: JobStatus) -> None:
        self.manifest.status = status
        self.save()

    def set_current_stage(self, stage: StageName | None) -> None:
        self.manifest.current_stage = stage
        self.save()

    def add_note(self, note: str) -> None:
        self.manifest.notes.append(note)
        self.save()

    def set_video_metadata(self, metadata) -> None:
        self.manifest.video = metadata
        self.save()

    # -- stage level -------------------------------------------------------

    def ensure_stage(self, stage: StageName, target: ExecutionTarget) -> StageRecord:
        record = self.manifest.stages.get(stage)
        if record is None:
            record = StageRecord(name=stage, target=target)
            self.manifest.stages[stage] = record
        else:
            record.target = target
        return record

    def start_stage(self, stage: StageName, target: ExecutionTarget) -> StageRecord:
        record = self.ensure_stage(stage, target)
        record.status = StageStatus.RUNNING
        record.attempts += 1
        record.started_at = utcnow()
        record.finished_at = None
        record.duration_seconds = None
        record.error = None
        self.manifest.current_stage = stage
        self.manifest.status = JobStatus.RUNNING
        self.save()
        return record

    def complete_stage(
        self,
        stage: StageName,
        metrics: dict[str, Any] | None = None,
        notes: list[str] | None = None,
    ) -> StageRecord:
        record = self.manifest.stage(stage)
        record.status = StageStatus.COMPLETED
        record.finished_at = utcnow()
        record.duration_seconds = _elapsed(record.started_at, record.finished_at)
        if metrics:
            record.metrics.update(metrics)
        if notes:
            record.notes.extend(notes)
        self.save()
        return record

    def fail_stage(self, stage: StageName, error: StageError) -> StageRecord:
        record = self.manifest.stage(stage)
        record.status = StageStatus.FAILED
        record.finished_at = utcnow()
        record.duration_seconds = _elapsed(record.started_at, record.finished_at)
        record.error = error
        self.save()
        return record

    def skip_stage(self, stage: StageName, reason: str) -> StageRecord:
        record = self.manifest.stage(stage)
        record.status = StageStatus.SKIPPED
        record.finished_at = utcnow()
        record.notes.append(reason)
        self.save()
        return record

    def reset_stage(self, stage: StageName) -> StageRecord:
        """Clear a stage so it can be rerun, dropping its artifact records."""
        record = self.manifest.stage(stage)
        for artifact_id in list(record.artifact_ids):
            self.manifest.artifacts.pop(artifact_id, None)
        record.status = StageStatus.PENDING
        record.started_at = None
        record.finished_at = None
        record.duration_seconds = None
        record.error = None
        record.metrics = {}
        record.artifact_ids = []
        record.notes = []
        self.save()
        return record

    # -- artifacts ---------------------------------------------------------

    def register_artifact(
        self,
        stage: StageName,
        path: Path,
        kind: ArtifactKind,
        provenance: Provenance = Provenance.OBSERVED,
        artifact_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        compute_hash: bool = True,
        max_hash_bytes: int = 512 * 1024 * 1024,
    ) -> ArtifactRecord | None:
        """Record a produced file. Returns ``None`` if the file is missing."""
        if not path.exists() or not path.is_file():
            logger.debug("Skipping artifact registration, file missing: %s", path)
            return None

        relative = self.paths.relative(path)
        resolved_id = artifact_id or f"{stage.value}:{Path(relative).name}"
        size = path.stat().st_size
        digest: str | None = None
        if compute_hash and size <= max_hash_bytes:
            digest = sha256_file(path)

        record = ArtifactRecord(
            artifact_id=resolved_id,
            stage=stage,
            kind=kind,
            relative_path=relative,
            size_bytes=size,
            sha256=digest,
            provenance=provenance,
            metadata=metadata or {},
        )
        self.manifest.artifacts[resolved_id] = record

        stage_record = self.manifest.stage(stage)
        if resolved_id not in stage_record.artifact_ids:
            stage_record.artifact_ids.append(resolved_id)
        return record

    def artifact_path(self, artifact_id: str) -> Path | None:
        record = self.manifest.artifacts.get(artifact_id)
        if record is None:
            return None
        return self.paths.resolve(record.relative_path)

    def first_artifact_path(self, kind: ArtifactKind) -> Path | None:
        for record in self.manifest.artifacts.values():
            if record.kind == kind:
                candidate = self.paths.resolve(record.relative_path)
                if candidate.exists():
                    return candidate
        return None


def _elapsed(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return round((end - start).total_seconds(), 3)

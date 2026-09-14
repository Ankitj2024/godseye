"""Job manifest models.

The manifest is the single source of truth for job state. There is no database:
``work/<job_id>/manifest.json`` is authoritative and is written atomically after
every stage transition so state survives crashes and can be resumed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from godseye.schemas.enums import (
    ArtifactKind,
    ExecutionTarget,
    FailureOrigin,
    JobStatus,
    PipelineMode,
    Provenance,
    StageName,
    StageStatus,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)


class VideoMetadata(StrictModel):
    """Facts about the input video, captured once at job setup."""

    source_path: str
    staged_relative_path: str
    staging_mode: str = "copy"
    size_bytes: int
    sha256: str | None = None
    sha256_skipped_reason: str | None = None
    fps: float | None = None
    frame_count: int | None = None
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    codec: str | None = None


class StageError(StrictModel):
    """Structured failure record.

    ``origin`` exists so a human reading the manifest can immediately tell
    whether the local orchestrator or a Modal worker broke.
    """

    origin: FailureOrigin
    exception_type: str
    message: str
    traceback: str | None = None
    failed_command: str | None = None
    log_tail: list[str] = Field(default_factory=list)
    remote_log_paths: list[str] = Field(default_factory=list)


class ArtifactRecord(StrictModel):
    """A file produced by a stage, addressed relative to the job root."""

    artifact_id: str
    stage: StageName
    kind: ArtifactKind
    relative_path: str
    size_bytes: int
    sha256: str | None = None
    provenance: Provenance = Provenance.OBSERVED
    created_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StageRecord(StrictModel):
    """Per-stage execution state."""

    name: StageName
    status: StageStatus = StageStatus.PENDING
    target: ExecutionTarget = ExecutionTarget.LOCAL
    attempts: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    error: StageError | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    artifact_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @property
    def is_terminal_success(self) -> bool:
        return self.status in (StageStatus.COMPLETED, StageStatus.SKIPPED)


class JobManifest(StrictModel):
    """Full job state, persisted to ``work/<job_id>/manifest.json``."""

    schema_version: int = 1
    job_id: str
    mode: PipelineMode
    status: JobStatus = JobStatus.CREATED
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    current_stage: StageName | None = None
    video: VideoMetadata | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    stages: dict[StageName, StageRecord] = Field(default_factory=dict)
    artifacts: dict[str, ArtifactRecord] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)

    # -- accessors ---------------------------------------------------------

    def stage(self, name: StageName) -> StageRecord:
        record = self.stages.get(name)
        if record is None:
            record = StageRecord(name=name)
            self.stages[name] = record
        return record

    def artifacts_for_stage(self, name: StageName) -> list[ArtifactRecord]:
        return [a for a in self.artifacts.values() if a.stage == name]

    def artifacts_of_kind(self, kind: ArtifactKind) -> list[ArtifactRecord]:
        return [a for a in self.artifacts.values() if a.kind == kind]

    def find_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        return self.artifacts.get(artifact_id)

    def completed_stages(self) -> list[StageName]:
        return [n for n, r in self.stages.items() if r.status == StageStatus.COMPLETED]

    def failed_stages(self) -> list[StageName]:
        return [n for n, r in self.stages.items() if r.status == StageStatus.FAILED]

    def total_duration_seconds(self) -> float:
        return round(
            sum(r.duration_seconds or 0.0 for r in self.stages.values()),
            3,
        )

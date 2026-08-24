"""Pydantic models for jobs and pipeline stages."""

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field

from app.models.enums import (
    ReconstructionMode,
    StageStatus,
    JobStatus,
    PIPELINE_STAGES,
    STAGE_DISPLAY_NAMES,
)


class StageInfo(BaseModel):
    """Status and metadata for one pipeline stage."""
    name: str
    display_name: str
    status: StageStatus = StageStatus.PENDING
    message: str = ""
    progress_pct: float = 0.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    artifact_paths: list[str] = Field(default_factory=list)


class VideoMetadata(BaseModel):
    """Metadata extracted from the uploaded video."""
    filename: str
    size_bytes: int
    content_type: str = ""
    duration_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    codec: Optional[str] = None


class JobRecord(BaseModel):
    """The full persisted job record."""
    job_id: str
    mode: ReconstructionMode
    status: JobStatus = JobStatus.CREATED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    video: Optional[VideoMetadata] = None
    stages: list[StageInfo] = Field(default_factory=list)
    progress_pct: float = 0.0
    current_stage: Optional[str] = None
    error: Optional[str] = None
    result_summary: Optional[str] = None

    def init_stages(self) -> None:
        """Initialize pipeline stages for tracking."""
        self.stages = []
        for stage_name in PIPELINE_STAGES:
            # Skip generative completion for exact mode
            if stage_name == "generative_completion" and self.mode == ReconstructionMode.EXACT:
                self.stages.append(StageInfo(
                    name=stage_name,
                    display_name=STAGE_DISPLAY_NAMES[stage_name],
                    status=StageStatus.SKIPPED,
                    message="Skipped in Exact Reconstruction mode",
                ))
            else:
                self.stages.append(StageInfo(
                    name=stage_name,
                    display_name=STAGE_DISPLAY_NAMES[stage_name],
                ))

    def update_timestamp(self) -> None:
        self.updated_at = datetime.now(timezone.utc)


# --- API response models ---

class JobCreateRequest(BaseModel):
    """Request body for job creation (mode comes as form field)."""
    mode: ReconstructionMode = ReconstructionMode.EXACT


class JobSummary(BaseModel):
    """Lightweight job info for list views."""
    job_id: str
    mode: ReconstructionMode
    status: JobStatus
    created_at: datetime
    progress_pct: float
    current_stage: Optional[str] = None
    video_filename: Optional[str] = None


class JobDetailResponse(BaseModel):
    """Full job detail for the detail page."""
    job_id: str
    mode: ReconstructionMode
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    video: Optional[VideoMetadata] = None
    stages: list[StageInfo] = Field(default_factory=list)
    progress_pct: float = 0.0
    current_stage: Optional[str] = None
    error: Optional[str] = None
    result_summary: Optional[str] = None


class JobProgressResponse(BaseModel):
    """Detailed progress response."""
    job_id: str
    status: JobStatus
    progress_pct: float
    current_stage: Optional[str] = None
    stages: list[StageInfo] = Field(default_factory=list)

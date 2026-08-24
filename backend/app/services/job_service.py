"""Job service — create, read, update, and list jobs via JSON file persistence."""

import uuid
import orjson
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.models import (
    JobRecord,
    JobSummary,
    JobDetailResponse,
    JobProgressResponse,
    VideoMetadata,
    ReconstructionMode,
    JobStatus,
)
from app.services.storage import get_job_metadata_dir, get_jobs_dir


def _job_file(job_id: str) -> Path:
    """Path to the job's JSON manifest."""
    return get_job_metadata_dir(job_id) / "job.json"


def _save_job(job: JobRecord) -> None:
    """Persist a job record to disk as JSON."""
    job.update_timestamp()
    path = _job_file(job.job_id)
    path.write_bytes(orjson.dumps(job.model_dump(mode="json"), option=orjson.OPT_INDENT_2))


def _load_job(job_id: str) -> Optional[JobRecord]:
    """Load a job record from disk. Returns None if not found."""
    path = _job_file(job_id)
    if not path.exists():
        return None
    data = orjson.loads(path.read_bytes())
    return JobRecord(**data)


def create_job(
    mode: ReconstructionMode,
    video_meta: VideoMetadata,
) -> JobRecord:
    """Create a new job, initialize stages, and persist to disk."""
    job_id = uuid.uuid4().hex[:12]
    job = JobRecord(
        job_id=job_id,
        mode=mode,
        status=JobStatus.CREATED,
        video=video_meta,
    )
    job.init_stages()
    _save_job(job)
    return job


def get_job(job_id: str) -> Optional[JobRecord]:
    """Load a job by ID."""
    return _load_job(job_id)


def update_job(job: JobRecord) -> None:
    """Persist an updated job record."""
    _save_job(job)


def list_jobs() -> list[JobSummary]:
    """List all jobs as lightweight summaries, sorted newest first."""
    jobs_dir = get_jobs_dir()
    summaries: list[JobSummary] = []

    if not jobs_dir.exists():
        return summaries

    for job_dir in sorted(jobs_dir.iterdir(), reverse=True):
        if not job_dir.is_dir():
            continue
        job_file = job_dir / "metadata" / "job.json"
        if not job_file.exists():
            continue
        try:
            data = orjson.loads(job_file.read_bytes())
            job = JobRecord(**data)
            summaries.append(JobSummary(
                job_id=job.job_id,
                mode=job.mode,
                status=job.status,
                created_at=job.created_at,
                progress_pct=job.progress_pct,
                current_stage=job.current_stage,
                video_filename=job.video.filename if job.video else None,
            ))
        except Exception:
            continue

    # Sort by created_at descending
    summaries.sort(key=lambda s: s.created_at, reverse=True)
    return summaries


def job_to_detail(job: JobRecord) -> JobDetailResponse:
    """Convert a full job record to the detail API response."""
    return JobDetailResponse(
        job_id=job.job_id,
        mode=job.mode,
        status=job.status,
        created_at=job.created_at,
        updated_at=job.updated_at,
        video=job.video,
        stages=job.stages,
        progress_pct=job.progress_pct,
        current_stage=job.current_stage,
        error=job.error,
        result_summary=job.result_summary,
    )


def job_to_progress(job: JobRecord) -> JobProgressResponse:
    """Convert a job record to the progress API response."""
    return JobProgressResponse(
        job_id=job.job_id,
        status=job.status,
        progress_pct=job.progress_pct,
        current_stage=job.current_stage,
        stages=job.stages,
    )

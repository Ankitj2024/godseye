"""Jobs API — upload, create, list, and inspect jobs."""

import logging
from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from app.models import (
    ReconstructionMode,
    VideoMetadata,
    JobSummary,
    JobDetailResponse,
    JobProgressResponse,
)
from app.services.job_service import (
    create_job,
    get_job,
    list_jobs,
    job_to_detail,
    job_to_progress,
)
from app.services.upload_service import validate_upload, save_upload

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/jobs", response_model=JobDetailResponse, status_code=201)
async def create_new_job(
    file: UploadFile = File(..., description="Drone video file"),
    mode: ReconstructionMode = Form(ReconstructionMode.EXACT),
):
    """
    Upload a drone video and create a new reconstruction job.

    - Accepts MP4, MOV, AVI, MKV, WEBM
    - Creates job record with all pipeline stages initialized
    - Saves video to local filesystem
    """
    # Validate
    is_valid, error_msg = validate_upload(file)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    # Create initial video metadata
    video_meta = VideoMetadata(
        filename=file.filename or "unknown",
        size_bytes=0,  # updated after save
        content_type=file.content_type or "",
    )

    # Create job
    job = create_job(mode=mode, video_meta=video_meta)
    logger.info(f"Created job {job.job_id} with mode={mode.value}")

    # Save file to disk
    try:
        saved_path, file_size = await save_upload(file, job.job_id)
        job.video.size_bytes = file_size
        from app.services.job_service import update_job
        update_job(job)
    except Exception as e:
        logger.error(f"Failed to save upload for job {job.job_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to save uploaded file")

    return job_to_detail(job)


@router.get("/jobs", response_model=list[JobSummary])
async def get_all_jobs():
    """List all jobs, sorted by creation time (newest first)."""
    return list_jobs()


@router.get("/jobs/{job_id}", response_model=JobDetailResponse)
async def get_job_detail(job_id: str):
    """Get full detail for a specific job."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return job_to_detail(job)


@router.get("/jobs/{job_id}/progress", response_model=JobProgressResponse)
async def get_job_progress(job_id: str):
    """Get detailed pipeline progress for a specific job."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return job_to_progress(job)


# --- Stub endpoints for future phases ---

@router.get("/jobs/{job_id}/scene")
async def get_job_scene(job_id: str):
    """[Phase 5] Return scene package metadata for viewer loading."""
    raise HTTPException(status_code=501, detail="Scene loading not yet implemented")


@router.get("/jobs/{job_id}/detections")
async def get_job_detections(job_id: str):
    """[Phase 7] Return semantic object detection data."""
    raise HTTPException(status_code=501, detail="Semantic detections not yet implemented")


@router.get("/jobs/{job_id}/scene-graph")
async def get_job_scene_graph(job_id: str):
    """[Phase 8] Return scene graph JSON."""
    raise HTTPException(status_code=501, detail="Scene graph not yet implemented")


@router.get("/jobs/{job_id}/confidence")
async def get_job_confidence(job_id: str):
    """[Phase 8] Return quality/confidence map data."""
    raise HTTPException(status_code=501, detail="Confidence map not yet implemented")


@router.get("/jobs/{job_id}/download")
async def download_job(job_id: str):
    """[Phase 11] Return packaged export bundle."""
    raise HTTPException(status_code=501, detail="Export not yet implemented")


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """[Future] Delete a job and its artifacts."""
    raise HTTPException(status_code=501, detail="Job deletion not yet implemented")

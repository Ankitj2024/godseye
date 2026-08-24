"""Upload service — handle saving uploaded files to the local filesystem."""

import shutil
import logging
from pathlib import Path
from fastapi import UploadFile

from app.services.storage import get_job_input_dir

logger = logging.getLogger(__name__)

# Allowed video content types
ALLOWED_CONTENT_TYPES = {
    "video/mp4",
    "video/quicktime",      # .mov
    "video/x-msvideo",      # .avi
    "video/x-matroska",     # .mkv
    "video/webm",
    "application/octet-stream",  # fallback for unknown
}

# Allowed extensions
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def validate_upload(file: UploadFile) -> tuple[bool, str]:
    """Validate the uploaded file. Returns (is_valid, error_message)."""
    if not file.filename:
        return False, "No filename provided"

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"Unsupported file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"

    return True, ""


async def save_upload(file: UploadFile, job_id: str) -> tuple[Path, int]:
    """
    Save uploaded file to the job's input directory.
    Returns (saved_path, file_size_bytes).
    """
    input_dir = get_job_input_dir(job_id)
    ext = Path(file.filename or "video.mp4").suffix.lower()
    dest = input_dir / f"video{ext}"

    size = 0
    chunk_size = 1024 * 1024  # 1 MB chunks

    with open(dest, "wb") as f:
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            size += len(chunk)

    logger.info(f"Saved upload for job {job_id}: {dest} ({size:,} bytes)")
    return dest, size

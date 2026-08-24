"""Storage path helpers for the God's Eye data directory layout."""

from pathlib import Path
from app.config import settings


def get_data_dir() -> Path:
    """Get the root data directory, creating it if needed."""
    p = settings.data_path
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_uploads_dir() -> Path:
    d = get_data_dir() / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_jobs_dir() -> Path:
    d = get_data_dir() / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_assets_dir() -> Path:
    d = get_data_dir() / "assets"
    d.mkdir(parents=True, exist_ok=True)
    return d


# --- Per-job directory helpers ---

def get_job_dir(job_id: str) -> Path:
    d = get_jobs_dir() / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_job_input_dir(job_id: str) -> Path:
    d = get_job_dir(job_id) / "input"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_job_metadata_dir(job_id: str) -> Path:
    d = get_job_dir(job_id) / "metadata"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_job_frames_dir(job_id: str) -> Path:
    d = get_job_dir(job_id) / "frames"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_job_candidates_dir(job_id: str) -> Path:
    d = get_job_frames_dir(job_id) / "candidates"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_job_selected_dir(job_id: str) -> Path:
    d = get_job_frames_dir(job_id) / "selected"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_job_reconstruction_dir(job_id: str) -> Path:
    d = get_job_dir(job_id) / "reconstruction"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_job_depth_dir(job_id: str) -> Path:
    d = get_job_dir(job_id) / "depth"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_job_semantics_dir(job_id: str) -> Path:
    d = get_job_dir(job_id) / "semantics"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_job_scene_graph_dir(job_id: str) -> Path:
    d = get_job_dir(job_id) / "scene_graph"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_job_completion_dir(job_id: str) -> Path:
    d = get_job_dir(job_id) / "completion"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_job_previews_dir(job_id: str) -> Path:
    d = get_job_dir(job_id) / "previews"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_job_exports_dir(job_id: str) -> Path:
    d = get_job_dir(job_id) / "exports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def init_data_directories() -> None:
    """Create the top-level data directory structure on startup."""
    get_data_dir()
    get_uploads_dir()
    get_jobs_dir()
    get_assets_dir()

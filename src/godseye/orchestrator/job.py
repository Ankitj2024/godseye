"""Job identity and the on-disk working layout.

``JobPaths`` is the single definition of where anything lives inside
``work/<job_id>/``. Stages must never hardcode paths; they ask ``JobPaths``.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from godseye.schemas.enums import StageName
from godseye.utils.fs import ensure_dir

JOB_ID_PATTERN = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")

MANIFEST_FILENAME = "manifest.json"
PIPELINE_LOG_FILENAME = "pipeline.log"


def new_job_id(now: datetime | None = None) -> str:
    """Sortable, collision-resistant job id: ``YYYYmmdd-HHMMSS-<rand6>``."""
    moment = now or datetime.now(timezone.utc)
    return f"{moment.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"


def is_valid_job_id(job_id: str) -> bool:
    return bool(JOB_ID_PATTERN.match(job_id))


@dataclass(frozen=True)
class JobPaths:
    """Resolved locations for one job."""

    job_id: str
    work_root: Path
    outputs_root: Path

    # -- roots -------------------------------------------------------------

    @property
    def job_dir(self) -> Path:
        return self.work_root / self.job_id

    @property
    def output_dir(self) -> Path:
        return self.outputs_root / self.job_id

    @property
    def manifest_path(self) -> Path:
        return self.job_dir / MANIFEST_FILENAME

    # -- stage directories -------------------------------------------------

    @property
    def input_dir(self) -> Path:
        return self.job_dir / "input"

    @property
    def frames_dir(self) -> Path:
        return self.job_dir / "frames"

    @property
    def candidate_frames_dir(self) -> Path:
        return self.frames_dir / "candidates"

    @property
    def selected_frames_dir(self) -> Path:
        return self.frames_dir / "selected"

    @property
    def candidate_index_path(self) -> Path:
        return self.frames_dir / "candidates.json"

    @property
    def selection_path(self) -> Path:
        return self.frames_dir / "selection.json"

    @property
    def reconstruction_dir(self) -> Path:
        return self.job_dir / "reconstruction"

    @property
    def geometry_dir(self) -> Path:
        return self.job_dir / "geometry"

    @property
    def depth_dir(self) -> Path:
        return self.job_dir / "depth"

    @property
    def semantics_dir(self) -> Path:
        return self.job_dir / "semantics"

    @property
    def scene_graph_dir(self) -> Path:
        return self.job_dir / "scene_graph"

    @property
    def completion_dir(self) -> Path:
        return self.job_dir / "completion"

    @property
    def exports_dir(self) -> Path:
        return self.job_dir / "exports"

    @property
    def logs_dir(self) -> Path:
        return self.job_dir / "logs"

    @property
    def pipeline_log_path(self) -> Path:
        return self.logs_dir / PIPELINE_LOG_FILENAME

    def stage_log_path(self, stage: StageName) -> Path:
        return self.logs_dir / f"{stage.value}.log"

    def stage_dir(self, stage: StageName) -> Path:
        """Directory a stage owns for its outputs."""
        mapping: dict[StageName, Path] = {
            StageName.JOB_SETUP: self.input_dir,
            StageName.FRAME_EXTRACTION: self.candidate_frames_dir,
            StageName.KEYFRAME_SELECTION: self.selected_frames_dir,
            StageName.RECONSTRUCTION_EXACT: self.reconstruction_dir,
            StageName.GEOMETRY_POSTPROCESS: self.geometry_dir,
            StageName.DEPTH_ENHANCEMENT: self.depth_dir,
            StageName.SEMANTIC_DETECTION: self.semantics_dir,
            StageName.SCENE_GRAPH: self.scene_graph_dir,
            StageName.GENERATIVE_COMPLETION: self.completion_dir,
            StageName.OUTPUT_PACKAGING: self.exports_dir,
        }
        return mapping[stage]

    def all_dirs(self) -> list[Path]:
        return [
            self.job_dir,
            self.input_dir,
            self.frames_dir,
            self.candidate_frames_dir,
            self.selected_frames_dir,
            self.reconstruction_dir,
            self.geometry_dir,
            self.depth_dir,
            self.semantics_dir,
            self.scene_graph_dir,
            self.completion_dir,
            self.exports_dir,
            self.logs_dir,
        ]

    def create(self) -> "JobPaths":
        for directory in self.all_dirs():
            ensure_dir(directory)
        return self

    def relative(self, path: Path) -> str:
        """Path relative to the job root, as stored in the manifest."""
        try:
            return path.resolve().relative_to(self.job_dir.resolve()).as_posix()
        except ValueError:
            return path.resolve().as_posix()

    def resolve(self, relative_path: str) -> Path:
        return self.job_dir / relative_path

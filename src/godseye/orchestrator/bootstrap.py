"""Job bootstrap: validation, directory creation, and input staging.

This runs before the stage loop. It is deliberately not a ``Stage`` because the
manifest it produces is what the stage loop needs in order to exist at all.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from godseye.config import PipelineConfig
from godseye.errors import InputValidationError
from godseye.orchestrator.job import JobPaths, is_valid_job_id, new_job_id
from godseye.orchestrator.manifest_store import ManifestStore
from godseye.pipeline.registry import planned_stage_targets
from godseye.schemas.enums import ArtifactKind, ExecutionTarget, PipelineMode, StageName
from godseye.schemas.manifest import VideoMetadata
from godseye.utils.fs import copy_file, ensure_dir, human_bytes
from godseye.utils.hashing import sha256_file
from godseye.utils.logging import get_logger
from godseye.utils.video import VideoError, probe_video, validate_video_path

logger = get_logger("bootstrap")

STAGED_VIDEO_NAME = "video"

#: Hashing a very large file costs real time for little benefit during a demo
#: run, so above this size the hash is skipped and the skip is recorded.
DEFAULT_MAX_HASH_BYTES = 2 * 1024**3


@dataclass
class PreparedJob:
    """Everything the runner needs to start executing stages."""

    paths: JobPaths
    store: ManifestStore
    mode: PipelineMode
    created: bool


def prepare_job(
    config: PipelineConfig,
    *,
    video: Path | None = None,
    mode: PipelineMode = PipelineMode.EXACT,
    job_id: str | None = None,
    hash_input: bool = True,
    max_hash_bytes: int = DEFAULT_MAX_HASH_BYTES,
) -> PreparedJob:
    """Create a new job, or reattach to an existing one when ``job_id`` is given."""
    ensure_dir(config.work_root)
    ensure_dir(config.outputs_root)

    if job_id:
        return _resume_job(config, job_id, mode_override=mode if video is None else mode)

    if video is None:
        raise InputValidationError("A video path is required to start a new job.")

    return _create_job(
        config,
        video=video,
        mode=mode,
        hash_input=hash_input,
        max_hash_bytes=max_hash_bytes,
    )


def _create_job(
    config: PipelineConfig,
    *,
    video: Path,
    mode: PipelineMode,
    hash_input: bool,
    max_hash_bytes: int,
) -> PreparedJob:
    try:
        source = validate_video_path(video)
    except VideoError as exc:
        raise InputValidationError(str(exc)) from exc

    paths = JobPaths(
        job_id=new_job_id(),
        work_root=config.work_root,
        outputs_root=config.outputs_root,
    ).create()

    logger.info("Created job %s", paths.job_id)

    staged, staging_mode = _stage_video(source, paths)
    try:
        probe = probe_video(staged)
    except VideoError as exc:
        raise InputValidationError(str(exc)) from exc

    size = staged.stat().st_size
    digest: str | None = None
    skip_reason: str | None = None
    if not hash_input:
        skip_reason = "hashing disabled by caller"
    elif size > max_hash_bytes:
        skip_reason = f"file larger than {human_bytes(max_hash_bytes)}"
    else:
        digest = sha256_file(staged)

    metadata = VideoMetadata(
        source_path=str(source),
        staged_relative_path=paths.relative(staged),
        staging_mode=staging_mode,
        size_bytes=size,
        sha256=digest,
        sha256_skipped_reason=skip_reason,
        fps=probe.fps,
        frame_count=probe.frame_count,
        duration_seconds=probe.duration_seconds,
        width=probe.width,
        height=probe.height,
        codec=probe.codec,
    )

    store = ManifestStore.create(
        paths=paths,
        mode=mode,
        config_snapshot=config.snapshot(),
        planned_stages=planned_stage_targets(mode),
    )
    store.set_video_metadata(metadata)

    setup = store.start_stage(StageName.JOB_SETUP, ExecutionTarget.LOCAL)
    store.register_artifact(
        stage=StageName.JOB_SETUP,
        path=staged,
        kind=ArtifactKind.VIDEO,
        artifact_id="job_setup:input_video",
        metadata={"staging_mode": staging_mode},
        compute_hash=False,
    )
    store.complete_stage(
        StageName.JOB_SETUP,
        metrics={
            "video_size_bytes": size,
            "duration_seconds": probe.duration_seconds,
            "fps": probe.fps,
            "resolution": f"{probe.width}x{probe.height}",
            "codec": probe.codec,
            "staging_mode": staging_mode,
        },
        notes=[f"Input staged via {staging_mode} from {source}"],
    )
    del setup

    logger.info(
        "Input: %s | %s | %.1fs @ %.2f fps | %dx%d",
        source.name,
        human_bytes(size),
        probe.duration_seconds,
        probe.fps,
        probe.width,
        probe.height,
    )

    return PreparedJob(paths=paths, store=store, mode=mode, created=True)


def _resume_job(
    config: PipelineConfig, job_id: str, mode_override: PipelineMode | None
) -> PreparedJob:
    if not is_valid_job_id(job_id):
        raise InputValidationError(
            f"'{job_id}' is not a valid job id (expected YYYYmmdd-HHMMSS-xxxxxx)."
        )

    paths = JobPaths(
        job_id=job_id,
        work_root=config.work_root,
        outputs_root=config.outputs_root,
    )
    if not paths.job_dir.exists():
        raise InputValidationError(f"Job directory not found: {paths.job_dir}")

    paths.create()
    store = ManifestStore.load(paths)
    manifest = store.manifest

    if manifest.video is None:
        raise InputValidationError(
            f"Job {job_id} has no recorded input video; it cannot be resumed."
        )

    staged = paths.resolve(manifest.video.staged_relative_path)
    if not staged.exists():
        raise InputValidationError(
            f"Staged input video is missing for job {job_id}: {staged}\n"
            "Re-run without --resume to start a fresh job."
        )

    mode = manifest.mode
    if mode_override is not None and mode_override != mode:
        logger.info("Switching job %s from mode '%s' to '%s'", job_id, mode.value, mode_override.value)
        manifest.mode = mode_override
        mode = mode_override
        for stage_name, target in planned_stage_targets(mode):
            store.ensure_stage(stage_name, target)
        store.save()

    logger.info(
        "Resuming job %s (completed: %s)",
        job_id,
        ", ".join(s.value for s in manifest.completed_stages()) or "none",
    )
    return PreparedJob(paths=paths, store=store, mode=mode, created=False)


def _stage_video(source: Path, paths: JobPaths) -> tuple[Path, str]:
    """Place the input inside the job folder without duplicating gigabytes.

    A hard link keeps ``work/<job_id>/input/`` self-contained at zero storage
    cost when the source is on the same filesystem; otherwise fall back to a
    real copy.
    """
    target = paths.input_dir / f"{STAGED_VIDEO_NAME}{source.suffix.lower()}"
    if target.exists():
        return target, "existing"

    try:
        os.link(source, target)
        logger.debug("Hard-linked input video to %s", target)
        return target, "hardlink"
    except OSError as exc:
        logger.debug("Hard link failed (%s); copying instead.", exc)

    copy_file(source, target)
    return target, "copy"

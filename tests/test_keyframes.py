"""Keyframe selection logic and the local frame stages end to end."""

from __future__ import annotations

import numpy as np
import pytest

from godseye.config import PipelineConfig
from godseye.orchestrator.bootstrap import prepare_job
from godseye.pipeline.context import StageContext
from godseye.schemas.enums import ExecutionTarget, PipelineMode, StageName
from godseye.stages.frame_extraction import FrameExtractionStage
from godseye.stages.keyframe_selection import (
    KeyframeSelectionStage,
    _greedy_select,
    _uniform_subsample,
)
from godseye.utils.fs import read_json


def _entry(index: int, signature: np.ndarray) -> dict:
    return {
        "candidate_index": index,
        "source_frame": index * 15,
        "timestamp_s": index * 0.5,
        "filename": f"cand_{index:06d}.jpg",
        "sharpness": 100.0,
        "brightness": 128.0,
        "signature": signature,
    }


def test_greedy_select_drops_near_duplicates():
    base = np.zeros(16, dtype=np.float32)
    scored = [_entry(i, base.copy()) for i in range(10)]
    selected = _greedy_select(scored, novelty_threshold=0.05, min_spacing=1)
    # Every frame is identical, so only the first can be justified.
    assert len(selected) == 1


def test_greedy_select_keeps_novel_frames():
    scored = [
        _entry(i, np.full(16, i * 0.2, dtype=np.float32))
        for i in range(10)
    ]
    selected = _greedy_select(scored, novelty_threshold=0.05, min_spacing=1)
    assert len(selected) == 10


def test_greedy_select_respects_minimum_spacing():
    scored = [
        _entry(i, np.full(16, i * 0.5, dtype=np.float32))
        for i in range(10)
    ]
    selected = _greedy_select(scored, novelty_threshold=0.01, min_spacing=3)
    indices = [entry["candidate_index"] for entry in selected]
    gaps = [b - a for a, b in zip(indices, indices[1:])]
    assert all(gap >= 3 for gap in gaps)


def test_uniform_subsample_keeps_endpoints():
    items = [{"candidate_index": i} for i in range(100)]
    result = _uniform_subsample(items, 10)
    assert len(result) == 10
    assert result[0]["candidate_index"] == 0
    assert result[-1]["candidate_index"] == 99


def test_uniform_subsample_is_noop_when_small_enough():
    items = [{"candidate_index": i} for i in range(5)]
    assert _uniform_subsample(items, 10) is items


@pytest.mark.usefixtures("synthetic_video")
def test_frame_stages_produce_curated_keyframes(config: PipelineConfig, synthetic_video):
    pytest.importorskip("cv2")

    config.frames.sample_fps = 4.0
    config.keyframes.min_count = 5
    config.keyframes.target_count = 20
    config.keyframes.max_count = 25

    prepared = prepare_job(
        config, video=synthetic_video, mode=PipelineMode.EXACT, hash_input=False
    )
    ctx = StageContext(
        job_id=prepared.paths.job_id,
        mode=PipelineMode.EXACT,
        paths=prepared.paths,
        config=config,
        store=prepared.store,
    )

    extraction = FrameExtractionStage().run(ctx)
    assert extraction.metrics["candidate_count"] > 10
    index = read_json(prepared.paths.candidate_index_path)
    assert index["candidate_count"] == extraction.metrics["candidate_count"]
    assert len(list(prepared.paths.candidate_frames_dir.glob("*.jpg"))) == index[
        "candidate_count"
    ]

    # The runner normally records metrics; do it manually for this direct call.
    prepared.store.start_stage(StageName.FRAME_EXTRACTION, ExecutionTarget.LOCAL)
    prepared.store.complete_stage(StageName.FRAME_EXTRACTION, extraction.metrics)

    selection = KeyframeSelectionStage().run(ctx)
    keyframes = sorted(prepared.paths.selected_frames_dir.glob("*.jpg"))

    assert selection.metrics["keyframe_count"] == len(keyframes)
    assert 5 <= len(keyframes) <= 25
    # Sequential, zero-padded names are what COLMAP consumes.
    assert keyframes[0].name == "frame_00001.jpg"

    doc = read_json(prepared.paths.selection_path)
    assert doc["selected_count"] == len(keyframes)
    assert doc["candidate_count"] >= doc["selected_count"]
    assert doc["timespan_seconds"] > 0


def test_video_metadata_recorded_at_bootstrap(config: PipelineConfig, synthetic_video):
    pytest.importorskip("cv2")

    prepared = prepare_job(
        config, video=synthetic_video, mode=PipelineMode.EXACT, hash_input=False
    )
    video = prepared.store.manifest.video

    assert video is not None
    assert video.fps and video.fps > 0
    assert video.frame_count and video.frame_count > 0
    assert video.width == 320 and video.height == 240
    assert video.sha256 is None
    assert video.sha256_skipped_reason == "hashing disabled by caller"
    assert prepared.paths.resolve(video.staged_relative_path).exists()

"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from godseye.config import PipelineConfig


@pytest.fixture
def config(tmp_path: Path) -> PipelineConfig:
    """A pipeline config rooted in a temp dir, so tests never touch repo state."""
    cfg = PipelineConfig(root=tmp_path)
    cfg.work_root.mkdir(parents=True, exist_ok=True)
    cfg.outputs_root.mkdir(parents=True, exist_ok=True)
    return cfg


@pytest.fixture(scope="session")
def synthetic_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A short video with real texture and a deliberately blurred segment.

    Texture matters: a flat-colour video would produce zero sharpness variance
    and zero novelty, which would not exercise selection at all.
    """
    cv2 = pytest.importorskip("cv2")

    target = tmp_path_factory.mktemp("video") / "synthetic.mp4"
    rng = np.random.default_rng(11)
    ground = rng.integers(0, 255, size=(600, 1400, 3), dtype=np.uint8)
    ground = cv2.GaussianBlur(ground, (5, 5), 0)

    width, height, fps, frames = 320, 240, 30, 300
    writer = cv2.VideoWriter(
        str(target), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height)
    )
    for index in range(frames):
        x = int(index * (1400 - width) / frames)
        y = int(150 + 80 * np.sin(index / 40))
        frame = ground[y : y + height, x : x + width].copy()
        if 120 <= index < 150:
            frame = cv2.GaussianBlur(frame, (21, 21), 0)
        writer.write(frame)
    writer.release()

    assert target.exists() and target.stat().st_size > 0
    return target

"""COLMAP output parsing.

These parsers are what the reported reconstruction quality numbers come from, so
they are tested against real COLMAP TXT/PLY formats rather than mocks.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from modal_app.reconstruction.colmap import (
    count_ply_vertices,
    parse_model_stats,
    summarize,
    SparseOutcome,
    DenseOutcome,
    ModelStats,
)

CAMERAS_TXT = """# Camera list with one line of data per camera:
#   CAMERA_ID, MODEL, WIDTH, HEIGHT, PARAMS[]
# Number of cameras: 1
1 OPENCV 1920 1080 1500 1500 960 540 0 0 0 0
"""

IMAGES_TXT = """# Image list with two lines of data per image:
#   IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME
#   POINTS2D[] as (X, Y, POINT3D_ID)
1 0.99 0.01 0.02 0.03 1.0 2.0 3.0 1 frame_00001.jpg
100.0 200.0 1 150.0 250.0 -1 300.0 400.0 2
2 0.98 0.02 0.03 0.04 1.1 2.1 3.1 1 frame_00002.jpg
110.0 210.0 1 160.0 260.0 3 310.0 410.0 -1
3 0.97 0.03 0.04 0.05 1.2 2.2 3.2 1 frame_00003.jpg
120.0 220.0 -1 170.0 270.0 -1 320.0 420.0 -1
"""

POINTS3D_TXT = """# 3D point list with one line of data per point:
#   POINT3D_ID, X, Y, Z, R, G, B, ERROR, TRACK[]
1 0.1 0.2 0.3 10 20 30 0.5 1 0 2 0
2 0.4 0.5 0.6 40 50 60 0.6 1 2
3 0.7 0.8 0.9 70 80 90 0.7 2 1
"""


def _write_model(tmp_path: Path) -> Path:
    model = tmp_path / "model"
    model.mkdir()
    (model / "cameras.txt").write_text(CAMERAS_TXT)
    (model / "images.txt").write_text(IMAGES_TXT)
    (model / "points3D.txt").write_text(POINTS3D_TXT)
    return model


def test_parse_model_stats_counts_images_cameras_points(tmp_path: Path):
    stats = parse_model_stats(_write_model(tmp_path))

    assert stats.registered_images == 3
    assert stats.camera_count == 1
    assert stats.point_count == 3
    # Only keypoints with a POINT3D_ID other than -1 are real observations:
    # image 1 contributes 2, image 2 contributes 2, image 3 contributes none.
    assert stats.observation_count == 4
    assert stats.mean_observations_per_image == pytest.approx(1.33, abs=0.01)


def test_parse_model_stats_handles_missing_files(tmp_path: Path):
    stats = parse_model_stats(tmp_path / "does-not-exist")
    assert stats.registered_images == 0
    assert stats.point_count == 0
    assert stats.mean_observations_per_image == 0.0


def test_count_ply_vertices_reads_header(tmp_path: Path):
    ply = tmp_path / "cloud.ply"
    ply.write_text(
        "ply\n"
        "format ascii 1.0\n"
        "element vertex 1234\n"
        "property float x\n"
        "end_header\n"
        "0 0 0\n"
    )
    assert count_ply_vertices(ply) == 1234


def test_count_ply_vertices_returns_zero_without_header(tmp_path: Path):
    ply = tmp_path / "broken.ply"
    ply.write_text("not really a ply file\n")
    assert count_ply_vertices(ply) == 0

    missing = tmp_path / "absent.ply"
    assert count_ply_vertices(missing) == 0


def test_summarize_merges_sparse_and_dense(tmp_path: Path):
    stats = ModelStats(
        registered_images=10, camera_count=1, point_count=500, observation_count=2000
    )
    sparse = SparseOutcome(
        model_dir=tmp_path,
        txt_dir=tmp_path,
        ply_path=tmp_path / "sparse.ply",
        stats=stats,
        model_count=2,
        timings={"mapping_s": 12.5},
    )
    dense = DenseOutcome(
        fused_ply=tmp_path / "fused.ply", point_count=90000, timings={"fusion_s": 30.0}
    )

    metrics = summarize(sparse, dense)

    assert metrics["registered_images"] == 10
    assert metrics["sparse_point_count"] == 500
    assert metrics["dense_point_count"] == 90000
    assert metrics["sparse_model_count"] == 2
    assert metrics["mapping_s"] == 12.5
    assert metrics["fusion_s"] == 30.0
    assert metrics["mean_observations_per_image"] == 200.0


def test_summarize_without_dense_omits_dense_keys(tmp_path: Path):
    stats = ModelStats(
        registered_images=4, camera_count=1, point_count=50, observation_count=100
    )
    sparse = SparseOutcome(
        model_dir=tmp_path,
        txt_dir=tmp_path,
        ply_path=tmp_path / "sparse.ply",
        stats=stats,
        model_count=1,
    )
    metrics = summarize(sparse, None)
    assert "dense_point_count" not in metrics

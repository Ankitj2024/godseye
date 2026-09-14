"""COLMAP driver.

A thin, explicit wrapper over the COLMAP command-line tools. Each step writes its
own log, and model statistics are parsed from COLMAP's own TXT export rather than
scraped from stdout, so the numbers reported back are trustworthy.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from modal_app.common.shell import CommandResult, run_command

COLMAP_BIN = "colmap"


@dataclass
class ModelStats:
    registered_images: int
    camera_count: int
    point_count: int
    observation_count: int

    @property
    def mean_observations_per_image(self) -> float:
        if self.registered_images == 0:
            return 0.0
        return round(self.observation_count / self.registered_images, 2)


@dataclass
class SparseOutcome:
    model_dir: Path
    txt_dir: Path
    ply_path: Path
    stats: ModelStats
    model_count: int
    timings: dict[str, float] = field(default_factory=dict)


@dataclass
class DenseOutcome:
    fused_ply: Path
    point_count: int
    timings: dict[str, float] = field(default_factory=dict)


class ColmapDriver:
    """Runs the COLMAP stages inside one workspace directory."""

    def __init__(
        self,
        images_dir: Path,
        workspace: Path,
        log_dir: Path,
        use_gpu: bool = True,
    ) -> None:
        self.images_dir = images_dir
        self.workspace = workspace
        self.log_dir = log_dir
        self.use_gpu = use_gpu

        self.database_path = workspace / "database.db"
        self.sparse_dir = workspace / "sparse"
        self.dense_dir = workspace / "dense"

        self._option_cache: dict[str, set[str]] = {}
        self.unsupported_options: list[str] = []

        for directory in (workspace, log_dir, self.sparse_dir):
            directory.mkdir(parents=True, exist_ok=True)

    # -- helpers -----------------------------------------------------------

    def _gpu_flag(self) -> str:
        return "1" if self.use_gpu else "0"

    def _run(self, subcommand: str, args: list[str], log_name: str) -> CommandResult:
        return run_command(
            [COLMAP_BIN, subcommand, *args],
            log_path=self.log_dir / f"{log_name}.log",
        )

    def available_options(self, subcommand: str) -> set[str]:
        """Option names a COLMAP subcommand actually accepts.

        COLMAP renamed several option namespaces between generations (for example
        ``--SiftExtraction.use_gpu`` became ``--FeatureExtraction.use_gpu``).
        Because the image tag is configurable, the driver asks the binary instead
        of assuming one COLMAP version.
        """
        if subcommand in self._option_cache:
            return self._option_cache[subcommand]

        log_path = self.log_dir / f"00_options_{subcommand}.log"
        run_command(
            [COLMAP_BIN, subcommand, "--help"],
            log_path=log_path,
            check=False,
        )
        text = log_path.read_text(encoding="utf-8", errors="replace")
        options = {
            token.split("=")[0]
            for line in text.splitlines()
            for token in [line.strip().split(" ")[0]]
            if token.startswith("--")
        }
        self._option_cache[subcommand] = options
        return options

    def resolve_option(self, subcommand: str, *candidates: str) -> str | None:
        """First candidate the binary supports, or ``None`` if none apply."""
        supported = self.available_options(subcommand)
        for candidate in candidates:
            if candidate in supported:
                return candidate
        self.unsupported_options.append(f"{subcommand}: {' | '.join(candidates)}")
        return None

    def version(self) -> str | None:
        try:
            result = run_command(
                [COLMAP_BIN, "-h"], log_path=self.log_dir / "colmap_version.log", check=False
            )
        except OSError:
            return None
        for line in result.tail:
            if "COLMAP" in line:
                return line.strip()
        return None

    # -- sparse ------------------------------------------------------------

    def extract_features(
        self, camera_model: str, single_camera: bool, max_image_size: int,
        max_num_features: int = 0,
    ) -> CommandResult:
        args = [
            "--database_path", str(self.database_path),
            "--image_path", str(self.images_dir),
            "--ImageReader.single_camera", "1" if single_camera else "0",
            "--ImageReader.camera_model", camera_model,
        ]

        gpu_option = self.resolve_option(
            "feature_extractor",
            "--FeatureExtraction.use_gpu",
            "--SiftExtraction.use_gpu",
        )
        if gpu_option:
            args += [gpu_option, self._gpu_flag()]

        size_option = self.resolve_option(
            "feature_extractor",
            "--FeatureExtraction.max_image_size",
            "--SiftExtraction.max_image_size",
        )
        if size_option:
            args += [size_option, str(max_image_size)]

        if max_num_features > 0:
            features_option = self.resolve_option(
                "feature_extractor", "--SiftExtraction.max_num_features"
            )
            if features_option:
                args += [features_option, str(max_num_features)]

        return self._run("feature_extractor", args, "01_feature_extractor")

    def match(self, matcher: str, sequential_overlap: int = 10) -> CommandResult:
        subcommand = "sequential_matcher" if matcher == "sequential" else "exhaustive_matcher"
        args = ["--database_path", str(self.database_path)]

        gpu_option = self.resolve_option(
            subcommand,
            "--FeatureMatching.use_gpu",
            "--SiftMatching.use_gpu",
        )
        if gpu_option:
            args += [gpu_option, self._gpu_flag()]

        if subcommand == "sequential_matcher":
            args += ["--SequentialMatching.overlap", str(sequential_overlap)]

        return self._run(subcommand, args, f"02_{subcommand}")

    def map_sparse(
        self,
        num_threads: int = 0,
        init_min_tri_angle: float = 0.0,
        init_max_forward_motion: float = 0.0,
        init_num_trials: int = 0,
    ) -> CommandResult:
        args = [
            "--database_path", str(self.database_path),
            "--image_path", str(self.images_dir),
            "--output_path", str(self.sparse_dir),
        ]
        if num_threads > 0:
            args += ["--Mapper.num_threads", str(num_threads)]

        # Aerial footage frequently moves along the optical axis, which yields
        # small triangulation angles. Relaxing initialisation is what lets such
        # scenes bootstrap at all.
        tunables = (
            (init_min_tri_angle, "--Mapper.init_min_tri_angle"),
            (init_max_forward_motion, "--Mapper.init_max_forward_motion"),
            (init_num_trials, "--Mapper.init_num_trials"),
        )
        for value, option in tunables:
            if value and value > 0:
                resolved = self.resolve_option("mapper", option)
                if resolved:
                    rendered = str(int(value)) if option.endswith("num_trials") else str(value)
                    args += [resolved, rendered]

        return self._run("mapper", args, "03_mapper")

    def convert_model(self, model_dir: Path, output: Path, output_type: str) -> CommandResult:
        if output_type == "TXT":
            output.mkdir(parents=True, exist_ok=True)
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
        return self._run(
            "model_converter",
            [
                "--input_path", str(model_dir),
                "--output_path", str(output),
                "--output_type", output_type,
            ],
            f"04_model_converter_{output_type.lower()}",
        )

    def candidate_models(self) -> list[Path]:
        """Sub-models produced by the mapper, in numeric order."""
        if not self.sparse_dir.exists():
            return []
        models = [
            path
            for path in self.sparse_dir.iterdir()
            if path.is_dir() and (path / "images.bin").exists()
        ]
        return sorted(models, key=lambda p: p.name)

    def select_best_model(self, txt_root: Path) -> tuple[Path, Path, ModelStats, int]:
        """Pick the sub-model with the most registered images.

        The mapper can split a scene into several disconnected models when
        tracking breaks. Choosing the largest is the honest default: it is the
        one supported by the most evidence.
        """
        candidates = self.candidate_models()
        if not candidates:
            raise RuntimeError(
                "COLMAP produced no sparse model. Feature matching likely failed: the "
                "keyframes may lack overlap, or the footage may be too blurry."
            )

        best: tuple[Path, Path, ModelStats] | None = None
        for model_dir in candidates:
            txt_dir = txt_root / model_dir.name
            self.convert_model(model_dir, txt_dir, "TXT")
            stats = parse_model_stats(txt_dir)
            if best is None or stats.registered_images > best[2].registered_images:
                best = (model_dir, txt_dir, stats)

        assert best is not None
        return best[0], best[1], best[2], len(candidates)

    def run_sparse(
        self,
        *,
        camera_model: str,
        single_camera: bool,
        max_image_size: int,
        matcher: str,
        num_threads: int = 0,
        max_num_features: int = 0,
        init_min_tri_angle: float = 0.0,
        init_max_forward_motion: float = 0.0,
        init_num_trials: int = 0,
    ) -> SparseOutcome:
        timings: dict[str, float] = {}

        result = self.extract_features(
            camera_model, single_camera, max_image_size, max_num_features
        )
        timings["feature_extraction_s"] = result.duration_seconds

        result = self.match(matcher)
        timings["matching_s"] = result.duration_seconds

        result = self.map_sparse(
            num_threads=num_threads,
            init_min_tri_angle=init_min_tri_angle,
            init_max_forward_motion=init_max_forward_motion,
            init_num_trials=init_num_trials,
        )
        timings["mapping_s"] = result.duration_seconds

        model_dir, txt_dir, stats, model_count = self.select_best_model(
            self.workspace / "model_txt_candidates"
        )

        ply_path = self.workspace / "sparse_points.ply"
        self.convert_model(model_dir, ply_path, "PLY")

        return SparseOutcome(
            model_dir=model_dir,
            txt_dir=txt_dir,
            ply_path=ply_path,
            stats=stats,
            model_count=model_count,
            timings=timings,
        )

    # -- dense -------------------------------------------------------------

    def run_dense(self, model_dir: Path, max_image_size: int) -> DenseOutcome:
        timings: dict[str, float] = {}
        self.dense_dir.mkdir(parents=True, exist_ok=True)

        result = self._run(
            "image_undistorter",
            [
                "--image_path", str(self.images_dir),
                "--input_path", str(model_dir),
                "--output_path", str(self.dense_dir),
                "--output_type", "COLMAP",
                "--max_image_size", str(max_image_size),
            ],
            "05_image_undistorter",
        )
        timings["undistort_s"] = result.duration_seconds

        result = self._run(
            "patch_match_stereo",
            [
                "--workspace_path", str(self.dense_dir),
                "--workspace_format", "COLMAP",
                "--PatchMatchStereo.geom_consistency", "true",
            ],
            "06_patch_match_stereo",
        )
        timings["stereo_s"] = result.duration_seconds

        fused = self.dense_dir / "fused.ply"
        result = self._run(
            "stereo_fusion",
            [
                "--workspace_path", str(self.dense_dir),
                "--workspace_format", "COLMAP",
                "--input_type", "geometric",
                "--output_path", str(fused),
            ],
            "07_stereo_fusion",
        )
        timings["fusion_s"] = result.duration_seconds

        if not fused.exists():
            raise RuntimeError("stereo_fusion reported success but produced no fused.ply")

        return DenseOutcome(
            fused_ply=fused,
            point_count=count_ply_vertices(fused),
            timings=timings,
        )


# -- parsing ---------------------------------------------------------------


def _data_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def parse_model_stats(txt_dir: Path) -> ModelStats:
    """Read counts straight out of COLMAP's TXT model export."""
    camera_lines = _data_lines(txt_dir / "cameras.txt")
    point_lines = _data_lines(txt_dir / "points3D.txt")
    image_lines = _data_lines(txt_dir / "images.txt")

    # images.txt stores two lines per image: pose, then its 2D observations.
    pose_lines = image_lines[0::2]
    observation_lines = image_lines[1::2]

    observations = 0
    for line in observation_lines:
        tokens = line.split()
        # Triplets of (X, Y, POINT3D_ID); -1 means the keypoint is untriangulated.
        for index in range(2, len(tokens), 3):
            if tokens[index] != "-1":
                observations += 1

    return ModelStats(
        registered_images=len(pose_lines),
        camera_count=len(camera_lines),
        point_count=len(point_lines),
        observation_count=observations,
    )


def count_ply_vertices(path: Path) -> int:
    """Read the vertex count from a PLY header without loading the file."""
    try:
        with path.open("rb") as handle:
            for _ in range(64):
                raw = handle.readline()
                if not raw:
                    break
                line = raw.decode("ascii", errors="replace").strip()
                if line.startswith("element vertex"):
                    return int(line.split()[-1])
                if line == "end_header":
                    break
    except (OSError, ValueError):
        return 0
    return 0


def copy_tree_contents(source: Path, destination: Path) -> list[Path]:
    """Copy a directory's files into ``destination``, returning what was written."""
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for item in sorted(source.iterdir()):
        if item.is_file():
            target = destination / item.name
            shutil.copy2(item, target)
            written.append(target)
    return written


def summarize(sparse: SparseOutcome, dense: DenseOutcome | None) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "registered_images": sparse.stats.registered_images,
        "sparse_point_count": sparse.stats.point_count,
        "camera_count": sparse.stats.camera_count,
        "observation_count": sparse.stats.observation_count,
        "mean_observations_per_image": sparse.stats.mean_observations_per_image,
        "sparse_model_count": sparse.model_count,
        **sparse.timings,
    }
    if dense is not None:
        metrics["dense_point_count"] = dense.point_count
        metrics.update(dense.timings)
    return metrics
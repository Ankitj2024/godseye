"""Configuration for the God's Eye pipeline.

Everything is overridable by environment variable using the ``GODSEYE_`` prefix
and ``__`` for nesting, e.g.::

    GODSEYE_MODAL__APP_NAME=godseye-staging
    GODSEYE_RECONSTRUCTION__RUN_DENSE=false
    GODSEYE_KEYFRAMES__TARGET_COUNT=180

A snapshot of the resolved config is written into every job manifest so a run is
reproducible after the fact.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]

SUPPORTED_VIDEO_SUFFIXES = frozenset(
    {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".mpg", ".mpeg", ".webm"}
)


class ConfigSection(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModalSettings(ConfigSection):
    """Where the compute plane lives and how we reach it."""

    app_name: str = "godseye"
    volume_name: str = "godseye-jobs"
    environment: str | None = None
    reconstruction_function: str = "reconstruct_exact"
    geometry_function: str = "postprocess_geometry"
    depth_function: str = "enhance_depth"
    semantic_function: str = "detect_semantics"
    masking_function: str = "generate_masks"
    generative_function: str = "complete_generative_scene"
    ping_function: str = "ping"
    jobs_prefix: str = "jobs"
    upload_concurrency: int = 8
    download_chunk_log_every: int = 25
    call_timeout_seconds: int = 6 * 60 * 60


class FrameSettings(ConfigSection):
    """Candidate frame extraction (local, CPU)."""

    sample_fps: float = 6.0
    max_candidates: int = 3000
    max_width: int = 1920
    jpeg_quality: int = 95

    @field_validator("sample_fps")
    @classmethod
    def _positive_fps(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("sample_fps must be > 0")
        return value


class KeyframeSettings(ConfigSection):
    """Intelligent keyframe selection (local, CPU).

    Tuned for structure-from-motion, which needs *overlap* between views. The
    novelty gate therefore only removes near-duplicates; overall density is
    controlled by ``target_count`` via even subsampling. An aggressive novelty
    threshold starves COLMAP of the shared observations it needs to register
    images at all.
    """

    target_count: int = 200
    max_count: int = 400
    min_count: int = 20
    #: Keep frames at least this sharp relative to the median. Adaptive on
    #: purpose: a fixed percentile would always discard that fraction of frames
    #: even when the whole clip is sharp.
    blur_relative_factor: float = 0.5
    absolute_blur_floor: float = 12.0
    novelty_threshold: float = 0.012
    min_spacing_frames: int = 1
    signature_size: int = 32
    relax_steps: int = 4

    @field_validator("blur_relative_factor")
    @classmethod
    def _valid_factor(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("blur_relative_factor must be in [0, 1]")
        return value


class ReconstructionSettings(ConfigSection):
    """COLMAP behaviour, executed on Modal."""

    camera_model: str = "OPENCV"
    single_camera: bool = True
    matcher: str = "auto"  # auto | exhaustive | sequential
    exhaustive_max_images: int = 150
    run_dense: bool = True
    max_image_size: int = 3200
    dense_max_image_size: int = 1920
    use_gpu: bool = True

    #: Drone footage is feature-rich; higher feature extraction yields denser
    #: point clouds and sharper geometric registration.
    max_num_features: int = 40000

    #: Aerial video often translates along the viewing axis (descending or
    #: flying forward), which produces small triangulation angles. COLMAP's
    #: defaults (16 degrees, forward-motion guard) reject such pairs and then
    #: report "no good initial image pair found". These relax that.
    init_min_tri_angle: float = 4.0
    init_max_forward_motion: float = 1.0
    init_num_trials: int = 400

    #: Quality gate. A reconstruction that registers a small fraction of its
    #: keyframes is a failure, and must not be reported as a success.
    min_registration_ratio: float = 0.5
    min_registered_images: int = 5

    @field_validator("matcher")
    @classmethod
    def _valid_matcher(cls, value: str) -> str:
        allowed = {"auto", "exhaustive", "sequential"}
        if value not in allowed:
            raise ValueError(f"matcher must be one of {sorted(allowed)}")
        return value

    @field_validator("min_registration_ratio")
    @classmethod
    def _valid_ratio(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("min_registration_ratio must be in [0, 1]")
        return value


class GeometrySettings(ConfigSection):
    """Open3D post-processing, executed on Modal."""

    voxel_size: float = 0.0  # 0 disables downsampling
    outlier_neighbors: int = 30
    outlier_std_ratio: float = 1.5
    poisson_depth: int = 12
    density_quantile: float = 0.12
    target_triangles: int = 1000000
    normal_knn: int = 50
    knn_color_transfer: int = 1
    build_mesh: bool = True


class DepthSettings(ConfigSection):
    """Monocular depth enhancement, executed on Modal."""

    model_name: str = "depth_anything_v2"
    max_depth: float = 100.0
    densify: bool = True
    use_gpu: bool = True


class MaskingSettings(ConfigSection):
    """2D semantic masking to ignore dynamic objects during reconstruction."""

    classes: list[str] = Field(
        default_factory=lambda: ["vehicle", "person"]
    )
    use_gpu: bool = True
    confidence_threshold: float = 0.35


class SemanticSettings(ConfigSection):
    """3D semantic object detection, executed on Modal."""

    confidence_threshold: float = 0.35
    classes: list[str] = Field(
        default_factory=lambda: ["vehicle", "building", "tree", "road", "person"]
    )
    use_gpu: bool = True


class GenerativeSettings(ConfigSection):
    """Generative completion and proxy asset mapping."""

    enabled: bool = True
    asset_library_prefix: str = "assets"
    fill_missing: bool = True
    max_proxy_insertions: int = 50


class PipelineConfig(BaseSettings):
    """Top-level resolved configuration."""

    model_config = SettingsConfigDict(
        env_prefix="GODSEYE_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    root: Path = REPO_ROOT
    work_dirname: str = "work"
    outputs_dirname: str = "outputs"
    assets_dirname: str = "assets"
    keep_intermediates: bool = True
    log_level: str = "INFO"

    modal: ModalSettings = Field(default_factory=ModalSettings)
    frames: FrameSettings = Field(default_factory=FrameSettings)
    keyframes: KeyframeSettings = Field(default_factory=KeyframeSettings)
    reconstruction: ReconstructionSettings = Field(default_factory=ReconstructionSettings)
    geometry: GeometrySettings = Field(default_factory=GeometrySettings)
    depth: DepthSettings = Field(default_factory=DepthSettings)
    masking: MaskingSettings = Field(default_factory=MaskingSettings)
    semantics: SemanticSettings = Field(default_factory=SemanticSettings)
    generative: GenerativeSettings = Field(default_factory=GenerativeSettings)

    # -- derived paths -----------------------------------------------------

    @property
    def work_root(self) -> Path:
        return self.root / self.work_dirname

    @property
    def outputs_root(self) -> Path:
        return self.root / self.outputs_dirname

    @property
    def assets_root(self) -> Path:
        return self.root / self.assets_dirname

    def snapshot(self) -> dict:
        """Config as stored in the manifest (paths stringified)."""
        data = self.model_dump(mode="json")
        data["root"] = str(self.root)
        return data


def load_config(**overrides) -> PipelineConfig:
    """Build config from env/.env plus explicit overrides."""
    return PipelineConfig(**{k: v for k, v in overrides.items() if v is not None})

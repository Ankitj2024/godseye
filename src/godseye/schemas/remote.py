"""Local <-> Modal stage contract.

Payloads cross the boundary as plain JSON-compatible dicts so the worker images
never need to import the local ``godseye`` package or match its pydantic
version. The dicts are validated with these models on the local side, which
keeps the contract explicit without coupling the two runtimes.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RemoteModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class RemoteArtifact(RemoteModel):
    """A file a worker produced, addressed by its path inside the Modal Volume."""

    remote_path: str
    relative_path: str
    kind: str
    size_bytes: int
    sha256: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RemoteError(RemoteModel):
    exception_type: str
    message: str
    traceback: str | None = None
    failed_command: str | None = None
    log_tail: list[str] = Field(default_factory=list)


class RemoteStageResult(RemoteModel):
    """Uniform return shape for every Modal worker."""

    stage: str
    status: str
    worker: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[RemoteArtifact] = Field(default_factory=list)
    output_prefix: str | None = None
    logs: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    error: RemoteError | None = None

    @property
    def ok(self) -> bool:
        return self.status == "completed"


class ReconstructionRequest(RemoteModel):
    """Payload for the COLMAP reconstruction worker."""

    job_id: str
    frames_prefix: str
    output_prefix: str
    masks_prefix: str | None = None
    camera_model: str = "OPENCV"
    single_camera: bool = True
    matcher: str = "auto"
    run_dense: bool = True
    max_image_size: int = 3200
    dense_max_image_size: int = 1920
    use_gpu: bool = True
    mapper_threads: int = 0
    max_num_features: int = 40000
    init_min_tri_angle: float = 4.0
    init_max_forward_motion: float = 1.0
    init_num_trials: int = 400


class GeometryRequest(RemoteModel):
    """Payload for the Open3D geometry post-processing worker."""

    job_id: str
    reconstruction_prefix: str
    output_prefix: str
    voxel_size: float = 0.0
    outlier_neighbors: int = 30
    outlier_std_ratio: float = 1.5
    poisson_depth: int = 12
    density_quantile: float = 0.12
    target_triangles: int = 1000000
    normal_knn: int = 50
    knn_color_transfer: int = 1
    build_mesh: bool = True


class DepthRequest(RemoteModel):
    """Payload for the monocular depth enhancement worker."""

    job_id: str
    frames_prefix: str
    reconstruction_prefix: str
    output_prefix: str
    model_name: str = "depth_anything_v2"
    max_depth: float = 100.0
    densify: bool = True
    use_gpu: bool = True


class SemanticRequest(RemoteModel):
    """Payload for the 3D semantic object detection worker."""

    job_id: str
    frames_prefix: str
    reconstruction_prefix: str
    output_prefix: str
    confidence_threshold: float = 0.35
    classes: list[str] = Field(
        default_factory=lambda: ["vehicle", "building", "tree", "road", "person"]
    )
    use_gpu: bool = True


class SemanticMaskingRequest(RemoteModel):
    """Payload for the 2D semantic masking worker."""

    job_id: str
    frames_prefix: str
    output_prefix: str
    confidence_threshold: float = 0.35
    classes: list[str] = Field(
        default_factory=lambda: ["vehicle", "person"]
    )
    use_gpu: bool = True


class GenerativeRequest(RemoteModel):
    """Payload for the generative completion worker."""

    job_id: str
    geometry_prefix: str
    semantics_prefix: str
    output_prefix: str
    asset_library_prefix: str = "assets"
    fill_missing: bool = True
    max_proxy_insertions: int = 50


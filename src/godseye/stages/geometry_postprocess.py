"""Stage 4: geometry post-processing and scene export (Modal, CPU).

Turns raw COLMAP point clouds into something usable: outlier removal, optional
downsampling, normal estimation, Poisson meshing, decimation, and a ``GLB``
export.

Runs on Modal rather than locally for a concrete reason: Open3D has no Python
3.13 wheels, so pinning it to a controlled 3.11 worker image is the only
reproducible option. It also reads its input straight from the Volume, so the
COLMAP output never has to be re-uploaded.
"""

from __future__ import annotations

from typing import Any

from godseye.pipeline.context import StageContext
from godseye.remote.transport import ModalTransport
from godseye.schemas.enums import StageName
from godseye.schemas.remote import GeometryRequest
from godseye.stages.remote_stage import RemoteStage


class GeometryPostprocessStage(RemoteStage):
    name = StageName.GEOMETRY_POSTPROCESS
    description = "Clean point clouds, build a mesh, and export the exact scene as GLB."
    function_setting = "geometry_function"
    remote_output_name = "geometry"

    def build_payload(self, ctx: StageContext, transport: ModalTransport) -> dict[str, Any]:
        settings = ctx.config.geometry
        request = GeometryRequest(
            job_id=ctx.job_id,
            reconstruction_prefix=transport.remote_path("reconstruction"),
            output_prefix=transport.remote_path(self.remote_output_name),
            voxel_size=settings.voxel_size,
            outlier_neighbors=settings.outlier_neighbors,
            outlier_std_ratio=settings.outlier_std_ratio,
            poisson_depth=settings.poisson_depth,
            density_quantile=settings.density_quantile,
            target_triangles=settings.target_triangles,
            build_mesh=settings.build_mesh,
        )
        return request.model_dump()

    def enrich(self, ctx, result, outcome, local_dir) -> None:
        if result.metrics.get("mesh_skipped_reason"):
            outcome.notes.append(
                f"Mesh generation skipped: {result.metrics['mesh_skipped_reason']}"
            )
        if result.metrics.get("source_cloud"):
            outcome.notes.append(
                f"Post-processing used '{result.metrics['source_cloud']}' as input."
            )

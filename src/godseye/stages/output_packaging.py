"""Stage 5: root output packaging (local).

Copies the run's real deliverables into ``outputs/<job_id>/`` under stable
names and writes the scene metadata documents. This is the only stage a user is
expected to look at the output of.
"""

from __future__ import annotations

from godseye.artifacts import packaging
from godseye.artifacts.documents import (
    build_confidence_document,
    build_objects_document,
    build_scene_document,
    build_scene_graph_document,
)
from godseye.errors import StageExecutionError
from godseye.pipeline.context import StageContext
from godseye.pipeline.stage import Stage, StageOutcome
from godseye.schemas.enums import ArtifactKind, ExecutionTarget, StageName
from godseye.utils.fs import atomic_write_text, ensure_dir


class OutputPackagingStage(Stage):
    name = StageName.OUTPUT_PACKAGING
    target = ExecutionTarget.LOCAL
    description = "Copy final scene outputs and metadata into outputs/<job_id>/."

    def run(self, ctx: StageContext) -> StageOutcome:
        log = ctx.logger(self.name)
        manifest = ctx.manifest
        paths = ctx.paths
        output_dir = ensure_dir(paths.output_dir)

        exports: dict[str, str] = {}
        copied: list[packaging.Deliverable] = []

        scene_export = packaging.select_scene_export(manifest, paths)
        if scene_export is not None:
            deliverable = packaging.copy_deliverable(
                scene_export, output_dir, "exact_scene.glb", ArtifactKind.SCENE_EXPORT
            )
            copied.append(deliverable)
            exports["exact_scene_glb"] = deliverable.name

        pointcloud = packaging.select_pointcloud(manifest, paths)
        if pointcloud is not None:
            deliverable = packaging.copy_deliverable(
                pointcloud, output_dir, "pointcloud.ply", ArtifactKind.DENSE_POINTCLOUD
            )
            copied.append(deliverable)
            exports["pointcloud_ply"] = deliverable.name

        for mesh in packaging.select_meshes(manifest, paths):
            name = f"mesh{mesh.suffix}"
            deliverable = packaging.copy_deliverable(mesh, output_dir, name, ArtifactKind.MESH)
            copied.append(deliverable)
            exports[f"mesh_{mesh.suffix.lstrip('.')}"] = deliverable.name

        pose_files = packaging.select_camera_poses(manifest, paths)
        if pose_files:
            cameras_dir = ensure_dir(output_dir / "cameras")
            for pose_file in pose_files:
                packaging.copy_deliverable(
                    pose_file, cameras_dir, pose_file.name, ArtifactKind.CAMERA_POSES
                )
            exports["camera_poses"] = "cameras/"

        if not copied:
            raise StageExecutionError(
                "No 3D deliverables were produced, so there is nothing to package. "
                "Check the reconstruction and geometry stage logs."
            )

        documents = {
            "scene": packaging.SCENE_FILENAME,
            "objects": packaging.OBJECTS_FILENAME,
            "scene_graph": packaging.SCENE_GRAPH_FILENAME,
            "confidence": packaging.CONFIDENCE_FILENAME,
            "run_summary": packaging.RUN_SUMMARY_FILENAME,
        }

        scene_doc = build_scene_document(manifest, exports, documents)
        self._write(output_dir / packaging.SCENE_FILENAME, scene_doc)
        self._write(output_dir / packaging.OBJECTS_FILENAME, build_objects_document(manifest))
        self._write(
            output_dir / packaging.SCENE_GRAPH_FILENAME, build_scene_graph_document(manifest)
        )
        self._write(
            output_dir / packaging.CONFIDENCE_FILENAME, build_confidence_document(manifest)
        )

        # A copy of the manifest travels with the deliverables so an output
        # folder is self-describing even if work/ is cleaned up.
        atomic_write_text(
            output_dir / packaging.MANIFEST_COPY_FILENAME,
            manifest.model_dump_json(indent=2) + "\n",
        )

        log_files = packaging.copy_logs(paths, output_dir)
        log.info("Packaged %d deliverables into %s", len(copied) + len(documents), output_dir)

        outcome = StageOutcome(
            metrics={
                "output_dir": str(output_dir),
                "deliverable_count": len(copied),
                "document_count": len(documents),
                "log_file_count": len(log_files),
                "exports": exports,
            },
            notes=[f"Deliverables written to {output_dir}"],
        )
        for deliverable in copied:
            outcome.add_artifact(
                deliverable.destination,
                deliverable.kind,
                artifact_id=f"{self.name.value}:{deliverable.name}",
                compute_hash=False,
            )
        outcome.add_artifact(
            output_dir / packaging.SCENE_FILENAME,
            ArtifactKind.METADATA,
            artifact_id=f"{self.name.value}:{packaging.SCENE_FILENAME}",
            compute_hash=False,
        )
        return outcome

    @staticmethod
    def _write(path, document) -> None:
        atomic_write_text(path, document.model_dump_json(indent=2) + "\n")

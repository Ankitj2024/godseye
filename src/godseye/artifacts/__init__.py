"""Artifact document builders and output packaging."""

from godseye.artifacts.documents import (
    build_confidence_document,
    build_geometry_summary,
    build_objects_document,
    build_run_summary,
    build_scene_document,
    build_scene_graph_document,
)
from godseye.artifacts.packaging import (
    CONFIDENCE_FILENAME,
    MANIFEST_COPY_FILENAME,
    OBJECTS_FILENAME,
    RUN_SUMMARY_FILENAME,
    SCENE_FILENAME,
    SCENE_GRAPH_FILENAME,
    Deliverable,
    copy_deliverable,
    copy_logs,
    select_camera_poses,
    select_meshes,
    select_pointcloud,
    select_scene_export,
    write_run_summary,
)

__all__ = [
    "CONFIDENCE_FILENAME",
    "MANIFEST_COPY_FILENAME",
    "OBJECTS_FILENAME",
    "RUN_SUMMARY_FILENAME",
    "SCENE_FILENAME",
    "SCENE_GRAPH_FILENAME",
    "Deliverable",
    "build_confidence_document",
    "build_geometry_summary",
    "build_objects_document",
    "build_run_summary",
    "build_scene_document",
    "build_scene_graph_document",
    "copy_deliverable",
    "copy_logs",
    "select_camera_poses",
    "select_meshes",
    "select_pointcloud",
    "select_scene_export",
    "write_run_summary",
]

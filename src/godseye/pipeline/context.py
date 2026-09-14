"""Execution context handed to every stage.

The context is the only thing a stage needs: paths, config, a logger, read
access to the manifest, and a lazily-created Modal transport.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from godseye.config import PipelineConfig
from godseye.errors import StageExecutionError
from godseye.orchestrator.job import JobPaths
from godseye.orchestrator.manifest_store import ManifestStore
from godseye.schemas.enums import ArtifactKind, PipelineMode, StageName
from godseye.schemas.manifest import JobManifest
from godseye.utils.logging import get_logger

if TYPE_CHECKING:
    from godseye.remote.transport import ModalTransport


@dataclass
class StageContext:
    """Per-run context, shared across stages within one job."""

    job_id: str
    mode: PipelineMode
    paths: JobPaths
    config: PipelineConfig
    store: ManifestStore
    _transport: "ModalTransport | None" = field(default=None, repr=False)

    # -- convenience -------------------------------------------------------

    @property
    def manifest(self) -> JobManifest:
        return self.store.manifest

    def logger(self, stage: StageName | str) -> logging.Logger:
        name = stage.value if isinstance(stage, StageName) else stage
        return get_logger(name)

    def stage_dir(self, stage: StageName) -> Path:
        return self.paths.stage_dir(stage)

    # -- remote plane ------------------------------------------------------

    @property
    def remote(self) -> "ModalTransport":
        """Lazily construct the Modal transport.

        Imported here so that local-only runs and unit tests never pay the cost
        of importing the Modal client.
        """
        if self._transport is None:
            from godseye.remote.transport import ModalTransport  # noqa: PLC0415

            self._transport = ModalTransport(self.config.modal, self.job_id)
        return self._transport

    # -- artifact lookup ---------------------------------------------------

    def artifact_path(self, artifact_id: str) -> Path | None:
        return self.store.artifact_path(artifact_id)

    def require_artifact(self, artifact_id: str) -> Path:
        path = self.store.artifact_path(artifact_id)
        if path is None or not path.exists():
            raise StageExecutionError(
                f"Required artifact '{artifact_id}' is missing. Rerun the stage that "
                "produces it, or use --force-stage."
            )
        return path

    def find_artifact_of_kind(self, kind: ArtifactKind) -> Path | None:
        return self.store.first_artifact_path(kind)

    def stage_metrics(self, stage: StageName) -> dict:
        record = self.manifest.stages.get(stage)
        return dict(record.metrics) if record else {}

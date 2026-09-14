"""The stage contract.

Every unit of pipeline work implements ``Stage``. A stage:

* declares where it runs (``target``) and whether it is implemented yet
* writes its outputs into the directory it owns (``paths.stage_dir(name)``)
* returns a ``StageOutcome`` describing metrics and produced artifacts

Stages never write the manifest themselves. The runner owns all state
transitions, which is what keeps reruns and resume behaviour consistent.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from godseye.orchestrator.job import JobPaths
from godseye.schemas.enums import (
    ArtifactKind,
    ExecutionTarget,
    PipelineMode,
    Provenance,
    StageName,
)

if TYPE_CHECKING:
    from godseye.pipeline.context import StageContext


@dataclass
class ArtifactSpec:
    """A file a stage produced, to be registered by the runner."""

    path: Path
    kind: ArtifactKind
    provenance: Provenance = Provenance.OBSERVED
    artifact_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    compute_hash: bool = True


@dataclass
class StageOutcome:
    """What a stage reports back to the runner."""

    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: list[ArtifactSpec] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add_artifact(
        self,
        path: Path,
        kind: ArtifactKind,
        provenance: Provenance = Provenance.OBSERVED,
        artifact_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        compute_hash: bool = True,
    ) -> None:
        self.artifacts.append(
            ArtifactSpec(
                path=path,
                kind=kind,
                provenance=provenance,
                artifact_id=artifact_id,
                metadata=metadata or {},
                compute_hash=compute_hash,
            )
        )


class SkipStage(Exception):
    """Raised by a stage that determines it has nothing to do."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class Stage(ABC):
    """Base class for all pipeline stages."""

    name: ClassVar[StageName]
    target: ClassVar[ExecutionTarget] = ExecutionTarget.LOCAL
    description: ClassVar[str] = ""

    #: False for stages that are planned but not built yet. The runner records
    #: them as skipped with an explicit reason instead of pretending they ran.
    implemented: ClassVar[bool] = True

    #: When False, a failure is recorded but the pipeline continues. Used so a
    #: generative-path failure cannot destroy an otherwise good exact run.
    required: ClassVar[bool] = True

    #: Which phase of the development plan will deliver an unimplemented stage.
    planned_phase: ClassVar[str | None] = None

    def applies_to(self, mode: PipelineMode) -> bool:
        """Whether this stage participates in the given mode."""
        return True

    def output_dir(self, paths: JobPaths) -> Path:
        return paths.stage_dir(self.name)

    def reset(self, paths: JobPaths) -> None:
        """Hook for clearing stage outputs before a forced rerun."""

    @abstractmethod
    def run(self, ctx: "StageContext") -> StageOutcome:
        """Do the work. Raise on failure; the runner records it."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} {self.name.value} target={self.target.value}>"


class NotImplementedStage(Stage):
    """Placeholder for a planned stage.

    Registering these keeps the full pipeline visible in ``manifest.json`` and
    ``godseye stages`` so nobody mistakes 'not built yet' for 'not needed'.
    """

    implemented = False
    required = False

    def __init__(
        self,
        name: StageName,
        target: ExecutionTarget,
        description: str,
        planned_phase: str,
        modes: tuple[PipelineMode, ...] = (PipelineMode.EXACT, PipelineMode.GENERATIVE),
    ) -> None:
        self.name = name  # type: ignore[misc]
        self.target = target  # type: ignore[misc]
        self.description = description  # type: ignore[misc]
        self.planned_phase = planned_phase  # type: ignore[misc]
        self._modes = modes

    def applies_to(self, mode: PipelineMode) -> bool:
        return mode in self._modes

    def run(self, ctx: "StageContext") -> StageOutcome:  # pragma: no cover
        raise SkipStage(f"{self.name.value} is not implemented yet ({self.planned_phase})")

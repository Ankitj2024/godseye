"""Exception hierarchy.

The split between local and remote failures is load-bearing: the manifest
records a ``FailureOrigin`` so that whoever reads the logs immediately knows
whether to debug the orchestrator or the Modal worker.
"""

from __future__ import annotations

from godseye.schemas.enums import FailureOrigin


class GodsEyeError(RuntimeError):
    """Base class for all pipeline errors."""

    origin: FailureOrigin = FailureOrigin.LOCAL


class ConfigurationError(GodsEyeError):
    """Invalid or missing configuration."""


class InputValidationError(GodsEyeError):
    """The user-supplied input is unusable."""


class StageExecutionError(GodsEyeError):
    """A stage failed on the local control plane."""


class RemoteTransportError(GodsEyeError):
    """Could not reach Modal, resolve a function, or move files.

    This is a control-plane/plumbing failure, not a worker failure.
    """


class RemoteStageError(GodsEyeError):
    """A Modal worker ran and reported failure."""

    origin = FailureOrigin.MODAL

    def __init__(
        self,
        message: str,
        *,
        exception_type: str = "RemoteStageError",
        traceback_text: str | None = None,
        failed_command: str | None = None,
        log_tail: list[str] | None = None,
        remote_logs: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.exception_type = exception_type
        self.traceback_text = traceback_text
        self.failed_command = failed_command
        self.log_tail = log_tail or []
        self.remote_logs = remote_logs or []

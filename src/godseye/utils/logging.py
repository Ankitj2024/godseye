"""Logging setup: rich console for humans, plain file log for post-mortems.

Without a frontend, logs are the primary debugging surface, so every job gets a
durable ``logs/pipeline.log`` in addition to console output.
"""

from __future__ import annotations

import logging
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

LOGGER_NAME = "godseye"

_FILE_FORMAT = "%(asctime)s %(levelname)-8s %(name)s %(message)s"

console = Console(stderr=False, highlight=False, soft_wrap=False)


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a namespaced child of the root ``godseye`` logger."""
    if not name:
        return logging.getLogger(LOGGER_NAME)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


def setup_logging(level: str = "INFO", log_file: Path | None = None) -> logging.Logger:
    """Configure the root ``godseye`` logger. Safe to call more than once."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    resolved = getattr(logging, level.upper(), logging.INFO)

    has_console = any(isinstance(h, RichHandler) for h in logger.handlers)
    if not has_console:
        handler = RichHandler(
            console=console,
            show_path=False,
            rich_tracebacks=True,
            markup=False,
            omit_repeated_times=False,
        )
        handler.setFormatter(logging.Formatter("%(message)s", datefmt="%H:%M:%S"))
        handler.setLevel(resolved)
        logger.addHandler(handler)
    else:
        for handler in logger.handlers:
            if isinstance(handler, RichHandler):
                handler.setLevel(resolved)

    if log_file is not None:
        target = str(log_file.resolve())
        already = any(
            isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == target
            for h in logger.handlers
        )
        if not already:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(logging.Formatter(_FILE_FORMAT))
            file_handler.setLevel(logging.DEBUG)
            logger.addHandler(file_handler)

    return logger


def attach_stage_log(stage_name: str, log_file: Path) -> logging.Handler:
    """Add a dedicated per-stage file handler; caller must detach it."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter(_FILE_FORMAT))
    handler.setLevel(logging.DEBUG)
    handler.addFilter(lambda record: stage_name in record.name)
    logging.getLogger(LOGGER_NAME).addHandler(handler)
    return handler


def detach_handler(handler: logging.Handler) -> None:
    logger = logging.getLogger(LOGGER_NAME)
    if handler in logger.handlers:
        logger.removeHandler(handler)
    handler.close()

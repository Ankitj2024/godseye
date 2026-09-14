#!/usr/bin/env python3
"""God's Eye entrypoint.

    python run_pipeline.py --video ./drone.mp4 --mode exact
    python run_pipeline.py --video ./drone.mp4 --mode generative

Also exposes the other commands directly::

    python run_pipeline.py doctor
    python run_pipeline.py stages --mode generative
    python run_pipeline.py resume 20260826-120000-ab12cd
    python run_pipeline.py inspect 20260826-120000-ab12cd

The package does not need to be installed: ``src/`` is added to ``sys.path`` when
it is missing, so a fresh clone works with nothing but the requirements.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SRC_DIR = REPO_ROOT / "src"

if SRC_DIR.is_dir() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

COMMANDS = {"run", "resume", "stages", "inspect", "doctor"}
PASSTHROUGH = {"--help", "-h", "--install-completion", "--show-completion"}


def _normalize_argv(argv: list[str]) -> list[str]:
    """Let ``run`` be implicit so the documented usage works verbatim."""
    if not argv:
        return argv
    first = argv[0]
    if first in COMMANDS or first in PASSTHROUGH:
        return argv
    return ["run", *argv]


def main() -> None:
    try:
        from godseye.cli.app import app
    except ImportError as exc:  # pragma: no cover - dependency guidance
        sys.stderr.write(
            f"Failed to import God's Eye: {exc}\n\n"
            "Install the local requirements first:\n"
            "  python -m pip install -r requirements.txt\n"
        )
        raise SystemExit(1) from exc

    sys.argv = [sys.argv[0], *_normalize_argv(sys.argv[1:])]
    app()


if __name__ == "__main__":
    main()

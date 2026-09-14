"""Subprocess execution with durable logs.

COLMAP is a family of command-line tools, so this is the workhorse of the
reconstruction worker. Output is streamed to a log file on the Volume (so it
survives the container) while a bounded tail is kept in memory to attach to any
error the local side receives.
"""

from __future__ import annotations

import os
import subprocess
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path


class CommandError(RuntimeError):
    """A subprocess exited non-zero."""

    def __init__(self, command: str, returncode: int, tail: list[str]) -> None:
        super().__init__(
            f"Command failed with exit code {returncode}: {command}\n"
            + "\n".join(tail[-15:])
        )
        self.command = command
        self.returncode = returncode
        self.tail = tail


@dataclass
class CommandResult:
    command: str
    returncode: int
    duration_seconds: float
    log_path: Path
    tail: list[str]


def run_command(
    args: list[str],
    log_path: Path,
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    tail_lines: int = 200,
    check: bool = True,
) -> CommandResult:
    """Run ``args``, appending combined stdout/stderr to ``log_path``."""
    command = " ".join(str(a) for a in args)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    merged_env = {**os.environ, **(env or {})}
    tail: deque[str] = deque(maxlen=tail_lines)
    started = time.perf_counter()

    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(f"\n$ {command}\n")
        log_file.flush()

        process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            [str(a) for a in args],
            cwd=str(cwd) if cwd else None,
            env=merged_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            log_file.write(line)
            stripped = line.rstrip("\n")
            if stripped:
                tail.append(stripped)
        process.stdout.close()
        returncode = process.wait()

        duration = time.perf_counter() - started
        log_file.write(f"[exit {returncode} after {duration:.1f}s]\n")

    result = CommandResult(
        command=command,
        returncode=returncode,
        duration_seconds=round(duration, 3),
        log_path=log_path,
        tail=list(tail),
    )

    if check and returncode != 0:
        raise CommandError(command, returncode, result.tail)
    return result


def which(binary: str) -> str | None:
    from shutil import which as _which  # noqa: PLC0415

    return _which(binary)

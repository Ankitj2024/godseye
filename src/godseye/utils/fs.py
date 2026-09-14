"""Filesystem helpers.

Atomic writes matter here: the manifest is rewritten after every stage
transition, and a partially written manifest would make a job unresumable.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def atomic_write_bytes(path: Path, data: bytes) -> Path:
    """Write ``data`` to ``path`` via a temp file + ``os.replace``."""
    ensure_dir(path.parent)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return path


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> Path:
    return atomic_write_bytes(path, text.encode(encoding))


def write_json(path: Path, payload: Any, indent: int = 2) -> Path:
    return atomic_write_text(path, json.dumps(payload, indent=indent, default=str) + "\n")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_files(root: Path) -> Iterator[Path]:
    """Yield every file under ``root``, sorted for deterministic behaviour."""
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        if path.is_file():
            yield path


def count_files(root: Path, pattern: str = "*") -> int:
    if not root.exists():
        return 0
    return sum(1 for p in root.glob(pattern) if p.is_file())


def dir_size_bytes(root: Path) -> int:
    return sum(p.stat().st_size for p in iter_files(root))


def copy_file(src: Path, dst: Path) -> Path:
    ensure_dir(dst.parent)
    shutil.copy2(src, dst)
    return dst


def copy_tree(src: Path, dst: Path) -> Path:
    ensure_dir(dst.parent)
    shutil.copytree(src, dst, dirs_exist_ok=True)
    return dst


def reset_dir(path: Path) -> Path:
    """Remove and recreate a directory, for clean stage reruns."""
    if path.exists():
        shutil.rmtree(path)
    return ensure_dir(path)


def relative_to(path: Path, root: Path) -> str:
    """POSIX-style relative path, falling back to absolute if unrelated."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def human_bytes(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024.0:
            return f"{num:.1f} {unit}" if unit != "B" else f"{int(num)} B"
        num /= 1024.0
    return f"{num:.1f} PB"

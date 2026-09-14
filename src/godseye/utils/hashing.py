"""Content hashing for artifact identity and input deduplication."""

from __future__ import annotations

import hashlib
from pathlib import Path

_CHUNK = 1024 * 1024


def sha256_file(path: Path, chunk_size: int = _CHUNK) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def short_hash(value: str, length: int = 6) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]

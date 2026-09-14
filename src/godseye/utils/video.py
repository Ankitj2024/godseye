"""Video probing and decoding helpers.

OpenCV is imported lazily so that importing the package (for tests, ``--help``,
or manifest inspection) never requires the CV stack to be installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from godseye.config import SUPPORTED_VIDEO_SUFFIXES


class VideoError(RuntimeError):
    """Raised when a video cannot be opened or probed."""


def require_cv2() -> Any:
    try:
        import cv2  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise VideoError(
            "opencv-python is required for frame extraction. Install it with "
            "`pip install -r requirements.txt`."
        ) from exc
    return cv2


@dataclass(frozen=True)
class VideoProbe:
    """Basic stream facts, used for sampling decisions and the manifest."""

    fps: float
    frame_count: int
    width: int
    height: int
    codec: str
    duration_seconds: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "fps": self.fps,
            "frame_count": self.frame_count,
            "width": self.width,
            "height": self.height,
            "codec": self.codec,
            "duration_seconds": self.duration_seconds,
        }


def validate_video_path(path: Path) -> Path:
    """Resolve and sanity-check a user-supplied video path."""
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise VideoError(f"Video not found: {resolved}")
    if not resolved.is_file():
        raise VideoError(f"Not a file: {resolved}")
    if resolved.stat().st_size == 0:
        raise VideoError(f"Video is empty: {resolved}")
    if resolved.suffix.lower() not in SUPPORTED_VIDEO_SUFFIXES:
        raise VideoError(
            f"Unsupported video extension '{resolved.suffix}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_VIDEO_SUFFIXES))}"
        )
    return resolved


def _fourcc_to_str(value: float) -> str:
    code = int(value)
    if code <= 0:
        return "unknown"
    chars = [chr((code >> (8 * i)) & 0xFF) for i in range(4)]
    text = "".join(chars).strip()
    return text or "unknown"


def probe_video(path: Path) -> VideoProbe:
    """Read stream metadata without decoding the whole file."""
    cv2 = require_cv2()
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        capture.release()
        raise VideoError(
            f"OpenCV could not open '{path}'. The file may be corrupt or use an "
            "unsupported codec."
        )
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        codec = _fourcc_to_str(capture.get(cv2.CAP_PROP_FOURCC))
    finally:
        capture.release()

    if fps <= 0.0:
        raise VideoError(
            f"Could not determine frame rate for '{path}'. Re-encode the file "
            "(for example with ffmpeg) and try again."
        )

    duration = round(frame_count / fps, 3) if frame_count > 0 else 0.0
    return VideoProbe(
        fps=round(fps, 4),
        frame_count=frame_count,
        width=width,
        height=height,
        codec=codec,
        duration_seconds=duration,
    )

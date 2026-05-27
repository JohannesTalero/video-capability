"""ffmpeg-based frame extraction for Phase 3a visual planning."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class FrameExtractionError(RuntimeError):
    """Raised when ffmpeg fails to extract a requested frame."""


def _format_timestamp_token(t: float) -> str:
    if t == int(t):
        return f"t{int(t)}"
    return f"t{t:.2f}".replace(".", "p").rstrip("0").rstrip("p") or "t0"


def extract_frames(
    video: Path,
    timestamps_seconds: list[float],
    out_dir: Path,
    prefix: str,
) -> list[Path]:
    """Extract PNG frames at the given timestamps."""
    if not video.exists():
        raise FrameExtractionError(f"video not found: {video}")
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for t in timestamps_seconds:
        out_path = out_dir / f"{prefix}_{_format_timestamp_token(t)}.png"
        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-ss",
            str(t),
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-update",
            "1",
            str(out_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0 or not out_path.exists() or out_path.stat().st_size < 1024:
            raise FrameExtractionError(
                f"ffmpeg failed for t={t}s on {video.name}: "
                f"returncode={result.returncode}, stderr={result.stderr.strip()[:200]}"
            )
        paths.append(out_path)
    return paths

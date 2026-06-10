"""Technical validation of rendered .webm outputs via ffprobe."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


class OutputValidationError(RuntimeError):
    """Raised when a rendered .webm fails technical checks."""


def _ffprobe_streams(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise OutputValidationError(f"ffprobe failed: {result.stderr[:200]}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise OutputValidationError(f"ffprobe output not valid JSON: {e}") from e


def validate_webm(
    path: Path,
    expected_duration: float,
    duration_tolerance: float = 0.2,
    expected_width: int = 1920,
    expected_height: int = 1080,
    require_alpha: bool = True,
) -> None:
    """Validate that path is a webm matching the technical spec.

    Raises OutputValidationError on any mismatch.
    """
    if not path.exists():
        raise OutputValidationError(f"output not found: {path}")
    if path.stat().st_size < 1024:
        raise OutputValidationError(f"output too small ({path.stat().st_size} bytes): {path}")
    info = _ffprobe_streams(path)
    video_streams = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    if not video_streams:
        raise OutputValidationError(f"no video stream in {path.name}")
    vs = video_streams[0]
    if vs.get("width") != expected_width or vs.get("height") != expected_height:
        raise OutputValidationError(
            f"dimensions mismatch {vs.get('width')}x{vs.get('height')} "
            f"vs expected {expected_width}x{expected_height}"
        )
    fmt_duration_str = info.get("format", {}).get("duration")
    if fmt_duration_str is None:
        raise OutputValidationError(f"no duration in ffprobe output for {path.name}")
    try:
        duration = float(fmt_duration_str)
    except (TypeError, ValueError) as e:
        raise OutputValidationError(
            f"duration not parseable ({fmt_duration_str!r}) for {path.name}: {e}"
        ) from e
    if abs(duration - expected_duration) > duration_tolerance:
        raise OutputValidationError(
            f"duration {duration:.2f}s vs expected {expected_duration:.2f}s "
            f"(tolerance ±{duration_tolerance}s)"
        )
    if require_alpha:
        tags = vs.get("tags") or {}
        alpha_mode = tags.get("alpha_mode") or tags.get("ALPHA_MODE")
        if alpha_mode != "1":
            raise OutputValidationError(
                f"alpha not present (alpha_mode={alpha_mode!r}) in {path.name}"
            )

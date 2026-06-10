"""Tests for frame_extractor."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from pipeline.vision.frame_extractor import (
    FrameExtractionError,
    extract_frames,
)


@pytest.fixture
def sample_video(tmp_path: Path) -> Path:
    """Synthetic 10s testsrc video 1920x1080 @ 30fps."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not available on PATH")
    video = tmp_path / "sample.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=10:size=1920x1080:rate=30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(video),
        ],
        check=True,
    )
    return video


def test_extract_single_frame(sample_video: Path, tmp_path: Path):
    out_dir = tmp_path / "frames"
    paths = extract_frames(sample_video, [5.0], out_dir, prefix="x")
    assert len(paths) == 1
    assert paths[0].exists()
    assert paths[0].suffix == ".png"
    assert paths[0].stat().st_size > 0


def test_extract_multiple_frames(sample_video: Path, tmp_path: Path):
    out_dir = tmp_path / "frames"
    paths = extract_frames(sample_video, [1.0, 5.0, 9.0], out_dir, prefix="m1")
    assert len(paths) == 3
    for p in paths:
        assert p.exists()
        assert p.stat().st_size > 0
    names = sorted(p.name for p in paths)
    assert any("t1" in n for n in names)
    assert any("t5" in n for n in names)
    assert any("t9" in n for n in names)


def test_extract_out_of_bounds_raises(sample_video: Path, tmp_path: Path):
    out_dir = tmp_path / "frames"
    with pytest.raises(FrameExtractionError):
        extract_frames(sample_video, [999.0], out_dir, prefix="oob")


def test_extract_creates_output_dir(sample_video: Path, tmp_path: Path):
    out_dir = tmp_path / "nested" / "frames"
    assert not out_dir.exists()
    extract_frames(sample_video, [5.0], out_dir, prefix="x")
    assert out_dir.exists()


def test_extract_missing_video_raises(tmp_path: Path):
    out_dir = tmp_path / "frames"
    bogus = tmp_path / "does-not-exist.mp4"
    with pytest.raises(FrameExtractionError):
        extract_frames(bogus, [1.0], out_dir, prefix="x")

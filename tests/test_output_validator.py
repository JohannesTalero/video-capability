"""Tests for output_validator."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pipeline.renderers.output_validator import (
    OutputValidationError,
    validate_webm,
)


@pytest.fixture
def sample_webm_alpha(tmp_path: Path) -> Path:
    """A 2.2s webm 1920x1080 with alpha channel via libvpx-vp9 yuva420p."""
    raw = tmp_path / "raw.mov"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=color=red@0.5:size=1920x1080:duration=2.2:rate=30",
            "-c:v",
            "prores_ks",
            "-profile:v",
            "4444",
            "-pix_fmt",
            "yuva444p10le",
            str(raw),
        ],
        check=True,
    )
    out = tmp_path / "out.webm"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(raw),
            "-c:v",
            "libvpx-vp9",
            "-pix_fmt",
            "yuva420p",
            "-auto-alt-ref",
            "0",
            "-b:v",
            "0",
            "-crf",
            "30",
            "-an",
            str(out),
        ],
        check=True,
    )
    return out


def test_validate_webm_alpha_ok(sample_webm_alpha: Path):
    # Expect duration=2.2s, 1920x1080
    validate_webm(sample_webm_alpha, expected_duration=2.2, duration_tolerance=0.3)


def test_validate_webm_dimensions_mismatch(sample_webm_alpha: Path):
    with pytest.raises(OutputValidationError, match="dimensions"):
        validate_webm(
            sample_webm_alpha,
            expected_duration=2.2,
            duration_tolerance=0.3,
            expected_width=1280,
            expected_height=720,
        )


def test_validate_webm_duration_mismatch(sample_webm_alpha: Path):
    with pytest.raises(OutputValidationError, match="duration"):
        validate_webm(sample_webm_alpha, expected_duration=10.0, duration_tolerance=0.2)


def test_validate_webm_missing_file(tmp_path: Path):
    with pytest.raises(OutputValidationError, match="not found"):
        validate_webm(tmp_path / "no.webm", expected_duration=5.0)

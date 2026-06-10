"""Tests for Phase 3 validator."""

from __future__ import annotations

from unittest.mock import patch

from pipeline.validator import validate_phase3


def _entry(
    material_id,
    status="ok",
    r2_key=None,
    decision="keep",
    tipo="lower_third",
    original_tipo=None,
    reasoning="OK",
):
    return {
        "material_id": material_id,
        "block_id": "b",
        "original_spec": {
            "tipo": original_tipo or tipo,
            "contenido": "x",
            "timestamp_relativo": 0,
            "metadata": {},
        },
        "refined_spec": (
            {"tipo": tipo, "contenido": "x", "timestamp_relativo": 0, "metadata": {}}
            if status != "dropped"
            else None
        ),
        "decision": decision,
        "position": "bottom-left" if status != "dropped" else None,
        "reframe": None,
        "reasoning": reasoning,
        "render_status": status,
        "r2_key": r2_key
        or (f"projects/p/phase3/materials/{material_id}.webm" if status != "dropped" else None),
        "render_seconds": 50.0,
    }


@patch("pipeline.validator.head_object_exists", return_value=True)
@patch("pipeline.validator._ffprobe_webm_summary")
def test_validate_phase3_all_pass(mock_ffprobe, mock_head):
    mock_ffprobe.return_value = {
        "width": 1920,
        "height": 1080,
        "duration": 6.0,
        "alpha_mode": "1",
    }
    manifest = [_entry("m1", "ok"), _entry("m2", "ok")]
    whitelist = ["lower_third", "pull_quote"]
    result = validate_phase3(manifest, whitelist=whitelist)
    assert result.passed is True
    assert result.critical_failures == []


@patch("pipeline.validator.head_object_exists", return_value=False)
def test_validate_phase3_critical_r2_missing(mock_head):
    manifest = [_entry("m1", "ok")]
    result = validate_phase3(manifest, whitelist=["lower_third"])
    assert result.passed is False
    assert any("r2_key" in c.lower() or "resolvable" in c.lower() for c in result.critical_failures)


def test_validate_phase3_critical_whitelist_violation():
    manifest = [_entry("m1", "ok", tipo="not_in_whitelist")]
    with (
        patch("pipeline.validator.head_object_exists", return_value=True),
        patch(
            "pipeline.validator._ffprobe_webm_summary",
            return_value={
                "width": 1920,
                "height": 1080,
                "duration": 6.0,
                "alpha_mode": "1",
            },
        ),
    ):
        result = validate_phase3(manifest, whitelist=["lower_third"])
    assert result.passed is False
    assert any("whitelist" in c.lower() for c in result.critical_failures)


def test_validate_phase3_warning_high_drop_rate():
    # 4 dropped out of 10 → 40% > 30% threshold
    manifest = [_entry(f"m{i}", "ok") for i in range(6)] + [
        _entry(f"d{i}", "dropped", decision="drop") for i in range(4)
    ]
    with (
        patch("pipeline.validator.head_object_exists", return_value=True),
        patch(
            "pipeline.validator._ffprobe_webm_summary",
            return_value={
                "width": 1920,
                "height": 1080,
                "duration": 6.0,
                "alpha_mode": "1",
            },
        ),
    ):
        result = validate_phase3(manifest, whitelist=["lower_third"])
    assert any("drop" in w.lower() for w in result.warnings)


def test_validate_phase3_warning_high_fallback_rate():
    # 2 fallback out of 10 → 20% > 10% threshold
    manifest = [_entry(f"m{i}", "ok") for i in range(8)] + [
        _entry(f"f{i}", "fallback") for i in range(2)
    ]
    with (
        patch("pipeline.validator.head_object_exists", return_value=True),
        patch(
            "pipeline.validator._ffprobe_webm_summary",
            return_value={
                "width": 1920,
                "height": 1080,
                "duration": 6.0,
                "alpha_mode": "1",
            },
        ),
    ):
        result = validate_phase3(manifest, whitelist=["lower_third"])
    assert any("fallback" in w.lower() for w in result.warnings)

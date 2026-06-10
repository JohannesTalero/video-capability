"""Tests for visual_planner — Phase 3a LLM-vision."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.models import MaterialSpec
from pipeline.vision.visual_planner import (
    VisualPlannerError,
    plan_material_visual,
)

_MIN_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xfa\xcf"
    b"\x00\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _spec() -> MaterialSpec:
    return MaterialSpec(
        tipo="lower_third",
        contenido="Edson Cúdris — Profesor de Física",
        timestamp_relativo=222,
        metadata={},
    )


def _ctx(tmp_path: Path) -> dict:
    paths = []
    for tag in ("tm1", "t0", "tp1"):
        p = tmp_path / f"{tag}.png"
        p.write_bytes(_MIN_PNG)
        paths.append(p)
    return {
        "frames_paths": paths,
        "phase2_context": {
            "block_id": "b1",
            "block_name": "Intro",
            "material_spec": _spec().to_dict(),
            "transcript_window": "...habla sobre vocación...",
        },
        "brand": {"colors": {"primary": "#2962FF", "accent": "#FF6D00"}},
        "visual_specs_summary": {"lower_third": "banner bottom-left primary"},
        "diagram_template_registry": [],
    }


def _llm_resp(payload: dict) -> MagicMock:
    return MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps(payload)))])


@patch("pipeline.vision.visual_planner.get_llm_client")
@patch("pipeline.vision.visual_planner.is_llm_available", return_value=True)
def test_keep_default_position(mock_avail, mock_client, tmp_path):
    fake = MagicMock()
    fake.chat.completions.create.return_value = _llm_resp(
        {
            "decision": "keep",
            "spec_refined": _spec().to_dict(),
            "position": "bottom-left",
            "reframe": None,
            "reasoning": "Speaker centrado, fondo libre.",
        }
    )
    mock_client.return_value = fake
    planned = plan_material_visual(
        material_id="b1_m00_x",
        block_id="b1",
        original_spec=_spec(),
        **_ctx(tmp_path),
    )
    assert planned.decision == "keep"
    assert planned.position == "bottom-left"
    assert planned.spec_refined is not None


@patch("pipeline.vision.visual_planner.get_llm_client")
@patch("pipeline.vision.visual_planner.is_llm_available", return_value=True)
def test_drop_clears_fields(mock_avail, mock_client, tmp_path):
    fake = MagicMock()
    fake.chat.completions.create.return_value = _llm_resp(
        {
            "decision": "drop",
            "spec_refined": None,
            "position": None,
            "reframe": None,
            "reasoning": "Frame demasiado ocupado.",
        }
    )
    mock_client.return_value = fake
    planned = plan_material_visual(
        material_id="b1_m00_x",
        block_id="b1",
        original_spec=_spec(),
        **_ctx(tmp_path),
    )
    assert planned.decision == "drop"
    assert planned.spec_refined is None
    assert planned.position is None


@patch("pipeline.vision.visual_planner.get_llm_client")
@patch("pipeline.vision.visual_planner.is_llm_available", return_value=True)
def test_retry_on_malformed_then_success(mock_avail, mock_client, tmp_path):
    fake = MagicMock()
    fake.chat.completions.create.side_effect = [
        MagicMock(choices=[MagicMock(message=MagicMock(content="not json"))]),
        _llm_resp(
            {
                "decision": "keep",
                "spec_refined": _spec().to_dict(),
                "position": "bottom-left",
                "reframe": None,
                "reasoning": "OK.",
            }
        ),
    ]
    mock_client.return_value = fake
    planned = plan_material_visual(
        material_id="b1_m00_x",
        block_id="b1",
        original_spec=_spec(),
        **_ctx(tmp_path),
    )
    assert planned.decision == "keep"
    assert fake.chat.completions.create.call_count == 2


@patch("pipeline.vision.visual_planner.get_llm_client")
@patch("pipeline.vision.visual_planner.is_llm_available", return_value=True)
def test_fallback_when_retry_fails(mock_avail, mock_client, tmp_path):
    fake = MagicMock()
    fake.chat.completions.create.side_effect = [
        MagicMock(choices=[MagicMock(message=MagicMock(content="bad"))]),
        MagicMock(choices=[MagicMock(message=MagicMock(content="still bad"))]),
    ]
    mock_client.return_value = fake
    planned = plan_material_visual(
        material_id="b1_m00_x",
        block_id="b1",
        original_spec=_spec(),
        **_ctx(tmp_path),
    )
    assert planned.decision == "keep"
    assert planned.position == "bottom-left"
    assert "fallback" in planned.reasoning.lower()


@patch("pipeline.vision.visual_planner.is_llm_available", return_value=False)
def test_raises_when_llm_unavailable(mock_avail, tmp_path):
    with pytest.raises(VisualPlannerError):
        plan_material_visual(
            material_id="b1_m00_x",
            block_id="b1",
            original_spec=_spec(),
            **_ctx(tmp_path),
        )

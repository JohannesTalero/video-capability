"""Tests for phase3_materials orchestrator (mocked external IO)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pipeline.models import (
    Block,
    MaterialSpec,
    NarrativePlan,
    PlannedMaterial,
)


@pytest.fixture
def sample_plan() -> NarrativePlan:
    mat = MaterialSpec(tipo="lower_third", contenido="X", timestamp_relativo=0, metadata={})
    b1 = Block(
        id="b1",
        name="Intro",
        segments=[0],
        estimated_duration="1:00",
        support_material=[mat],
        transition_next="cut",
    )
    # NarrativePlan has no total_duration_estimate field
    return NarrativePlan(project_id="p1", blocks=[b1])


@patch("pipeline.phases.phase3_materials.render_material")
@patch("pipeline.phases.phase3_materials.plan_material_visual")
@patch("pipeline.phases.phase3_materials.extract_frames")
@patch("pipeline.phases.phase3_materials.download_video_to_local")
@patch("pipeline.phases.phase3_materials.load_visual_plan", return_value=None)
@patch("pipeline.phases.phase3_materials.load_manifest", return_value=None)
@patch("pipeline.phases.phase3_materials.upload_manifest")
@patch("pipeline.phases.phase3_materials.upload_visual_plan")
@patch("pipeline.phases.phase3_materials.upload_frame")
@patch("pipeline.phases.phase3_materials.head_object_exists", return_value=False)
def test_orchestrator_happy_path(
    mock_head,
    mock_up_frame,
    mock_up_plan,
    mock_up_man,
    mock_load_man,
    mock_load_plan,
    mock_dl,
    mock_extract,
    mock_plan,
    mock_render,
    sample_plan,
    tmp_path,
):
    from pipeline.phases.phase3_materials import run_phase3

    # frames — create real files so upload_frame receives existing paths
    frame_files = [
        tmp_path / "f-1.png",
        tmp_path / "f0.png",
        tmp_path / "f1.png",
    ]
    for p in frame_files:
        p.write_bytes(b"\x00" * 2048)
    mock_extract.return_value = frame_files

    # planned visual decision
    spec = sample_plan.blocks[0].support_material[0]
    mock_plan.return_value = PlannedMaterial(
        material_id="b1_m00_xxx",
        block_id="b1",
        original_spec=spec,
        decision="keep",
        spec_refined=spec,
        position="bottom-left",
        reframe=None,
        reasoning="OK.",
    )

    # render.map returns manifest entries
    render_entry = {
        "material_id": "b1_m00_xxx",
        "block_id": "b1",
        "original_spec": spec.to_dict(),
        "refined_spec": spec.to_dict(),
        "decision": "keep",
        "position": "bottom-left",
        "reframe": None,
        "reasoning": "OK.",
        "render_status": "ok",
        "r2_key": "projects/p1/phase3/materials/b1_m00_xxx.webm",
        "render_seconds": 50.0,
    }
    mock_render.map = MagicMock(return_value=[render_entry])

    brand = {
        "id": "phymac",
        "colors": {
            "primary": "#000",
            "primary_dark": "#000",
            "accent": "#000",
            "accent_dark": "#000",
            "carbon": "#000",
            "carbon_light": "#000",
            "surface": "#fff",
            "background": "#fff",
        },
    }

    with patch("pipeline.phases.phase3_materials.modal_app") as mock_app:
        mock_app.run.return_value.__enter__ = MagicMock(return_value=None)
        mock_app.run.return_value.__exit__ = MagicMock(return_value=False)
        result = run_phase3(
            sample_plan,
            brand=brand,
            visual_specs_summary={},
        )

    assert len(result["manifest"]) == 1
    assert result["manifest"][0]["render_status"] == "ok"
    mock_up_man.assert_called_once()

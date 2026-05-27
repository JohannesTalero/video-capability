"""Tests for modal_render.render_one — runs in Modal worker but unit-tested locally."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from pipeline.models import MaterialSpec, PlannedMaterial


def _planned_keep(material_id="b1_m00_x") -> PlannedMaterial:
    spec = MaterialSpec(
        tipo="lower_third",
        contenido="Edson — Profe",
        timestamp_relativo=0,
        metadata={},
    )
    return PlannedMaterial(
        material_id=material_id,
        block_id="b1",
        original_spec=spec,
        decision="keep",
        spec_refined=spec,
        position="bottom-left",
        reframe=None,
        reasoning="OK.",
    )


def _planned_drop(material_id="b1_m01_y") -> PlannedMaterial:
    spec = MaterialSpec(tipo="pull_quote", contenido="X", timestamp_relativo=0, metadata={})
    return PlannedMaterial(
        material_id=material_id,
        block_id="b1",
        original_spec=spec,
        decision="drop",
        spec_refined=None,
        position=None,
        reframe=None,
        reasoning="No encaja.",
    )


@patch("pipeline.modal_render.upload_webm", return_value="projects/p/phase3/materials/x.webm")
@patch("pipeline.modal_render.validate_webm")
@patch("pipeline.modal_render.subprocess.run")
@patch("pipeline.modal_render.write_brand_assets")
def test_render_one_keep_ok_path(mock_brand, mock_run, mock_validate, mock_upload, tmp_path):
    from pipeline.modal_render import render_one

    # Force happy path: subprocess.run returns success
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

    # Simulate that ffmpeg created the webm by touching the expected path
    def write_output(*args, **kwargs):
        # Last positional arg is the output path in the ffmpeg call
        cmd = args[0] if args else kwargs.get("args")
        if cmd and "libvpx-vp9" in cmd:
            Path(cmd[-1]).write_bytes(b"\x00" * 2048)
        if cmd and "hyperframes" in " ".join(cmd):
            # Touch the .mov target
            for i, a in enumerate(cmd):
                if a == "--output":
                    Path(cmd[i + 1]).write_bytes(b"\x00" * 2048)
        return MagicMock(returncode=0, stdout="", stderr="")

    mock_run.side_effect = write_output
    payload = {
        "planned": _planned_keep().to_dict(),
        "project_id": "p1",
        "material_id": "b1_m00_x",
        "brand": {
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
            "id": "phymac",
        },
    }
    result = render_one(payload, hf_project_dir=tmp_path / "hfp", tmp_dir=tmp_path / "work")
    assert result["render_status"] == "ok"
    assert result["r2_key"] == "projects/p/phase3/materials/x.webm"
    assert result["material_id"] == "b1_m00_x"


def test_render_one_drop_short_circuits(tmp_path):
    from pipeline.modal_render import render_one

    payload = {
        "planned": _planned_drop().to_dict(),
        "project_id": "p1",
        "material_id": "b1_m01_y",
        "brand": {
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
            "id": "phymac",
        },
    }
    result = render_one(payload, hf_project_dir=tmp_path, tmp_dir=tmp_path)
    assert result["render_status"] == "dropped"
    assert result["r2_key"] is None

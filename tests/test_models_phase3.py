"""Tests for Phase 3 dataclasses in pipeline.models."""

from __future__ import annotations

import json

from pipeline.models import (
    ManifestEntry,
    MaterialSpec,
    PlannedMaterial,
    RenderResult,
)


def _sample_material_spec() -> MaterialSpec:
    return MaterialSpec(
        tipo="lower_third",
        contenido="Edson Cúdris — Profesor de Física",
        timestamp_relativo=222,
        metadata={},
    )


def test_planned_material_keep_to_dict_roundtrip():
    pm = PlannedMaterial(
        material_id="b1_m00_abcd1234",
        block_id="b1",
        original_spec=_sample_material_spec(),
        decision="keep",
        spec_refined=_sample_material_spec(),
        position="bottom-left",
        reframe=None,
        reasoning="Speaker centrado, fondo libre.",
    )
    d = pm.to_dict()
    assert d["material_id"] == "b1_m00_abcd1234"
    assert d["decision"] == "keep"
    assert d["spec_refined"]["tipo"] == "lower_third"
    assert d["reframe"] is None
    pm2 = PlannedMaterial.from_dict(d)
    assert pm2 == pm


def test_planned_material_drop_has_null_refined():
    pm = PlannedMaterial(
        material_id="b1_m01_dead",
        block_id="b1",
        original_spec=_sample_material_spec(),
        decision="drop",
        spec_refined=None,
        position=None,
        reframe=None,
        reasoning="Frame demasiado ocupado, lower-third distrae.",
    )
    d = pm.to_dict()
    assert d["spec_refined"] is None
    assert d["position"] is None
    pm2 = PlannedMaterial.from_dict(d)
    assert pm2 == pm


def test_planned_material_position_as_dict():
    pm = PlannedMaterial(
        material_id="b1_m02_beef",
        block_id="b1",
        original_spec=_sample_material_spec(),
        decision="modify",
        spec_refined=_sample_material_spec(),
        position={"x_pct": 0.05, "y_pct": 0.85},
        reframe={
            "type": "zoom",
            "params": {"scale": 1.2, "center_x_pct": 0.3, "center_y_pct": 0.5},
            "t_start_relative": 220.5,
            "t_end_relative": 226.5,
        },
        reasoning="Zoom suave a la cara, lower-third a coordenada custom.",
    )
    d = pm.to_dict()
    assert d["position"]["x_pct"] == 0.05
    assert d["reframe"]["type"] == "zoom"
    pm2 = PlannedMaterial.from_dict(d)
    assert pm2 == pm


def test_render_result_ok():
    rr = RenderResult(
        material_id="b1_m00_abcd1234",
        status="ok",
        r2_key="projects/x/phase3/materials/b1_m00_abcd1234.webm",
        render_seconds=58.4,
        error=None,
    )
    assert rr.to_dict()["status"] == "ok"


def test_render_result_fallback_records_error():
    rr = RenderResult(
        material_id="b1_m00_abcd1234",
        status="fallback",
        r2_key="projects/x/phase3/materials/b1_m00_abcd1234.webm",
        render_seconds=62.1,
        error="ffmpeg returncode=1: invalid LaTeX",
    )
    assert rr.status == "fallback"
    assert rr.error is not None


def test_manifest_entry_full_serialization():
    spec_dict = _sample_material_spec().to_dict()
    me = ManifestEntry(
        material_id="b1_m00_abcd1234",
        block_id="b1",
        original_spec=spec_dict,
        refined_spec=spec_dict,
        decision="keep",
        position="bottom-left",
        reframe=None,
        reasoning="OK",
        render_status="ok",
        r2_key="projects/x/phase3/materials/b1_m00_abcd1234.webm",
        render_seconds=58.4,
    )
    js = json.dumps(me.to_dict())
    parsed = json.loads(js)
    assert parsed["material_id"] == "b1_m00_abcd1234"


def test_manifest_entry_dropped_no_r2_key():
    spec_dict = _sample_material_spec().to_dict()
    me = ManifestEntry(
        material_id="b1_m01_dead",
        block_id="b1",
        original_spec=spec_dict,
        refined_spec=None,
        decision="drop",
        position=None,
        reframe=None,
        reasoning="No encaja con el frame.",
        render_status="dropped",
        r2_key=None,
        render_seconds=0.0,
    )
    d = me.to_dict()
    assert d["r2_key"] is None
    assert d["render_status"] == "dropped"

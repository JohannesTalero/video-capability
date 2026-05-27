"""Tests for phase3_helpers."""

from __future__ import annotations

from pipeline.models import Block, MaterialSpec, NarrativePlan
from pipeline.phase3_helpers import compute_material_id, flatten_plan_to_materials


def test_compute_material_id_format():
    spec = MaterialSpec(tipo="lower_third", contenido="X", timestamp_relativo=0, metadata={})
    mid = compute_material_id("block_1", 0, spec)
    # Formato: <block_id>_m<idx02d>_<8hex>
    parts = mid.split("_m")
    assert parts[0] == "block_1"
    rest = parts[1]
    idx_str, _, hexpart = rest.partition("_")
    assert idx_str == "00"
    assert len(hexpart) == 8
    assert all(c in "0123456789abcdef" for c in hexpart)


def test_compute_material_id_deterministic():
    spec = MaterialSpec(tipo="lower_third", contenido="X", timestamp_relativo=0, metadata={})
    assert compute_material_id("b1", 0, spec) == compute_material_id("b1", 0, spec)


def test_compute_material_id_changes_with_content():
    s1 = MaterialSpec(tipo="lower_third", contenido="A", timestamp_relativo=0, metadata={})
    s2 = MaterialSpec(tipo="lower_third", contenido="B", timestamp_relativo=0, metadata={})
    assert compute_material_id("b1", 0, s1) != compute_material_id("b1", 0, s2)


def test_compute_material_id_changes_with_metadata():
    s1 = MaterialSpec(
        tipo="diagrama", contenido="X", timestamp_relativo=0, metadata={"tipo_visual": "barras"}
    )
    s2 = MaterialSpec(
        tipo="diagrama", contenido="X", timestamp_relativo=0, metadata={"tipo_visual": "ciclo"}
    )
    assert compute_material_id("b1", 0, s1) != compute_material_id("b1", 0, s2)


def test_compute_material_id_stable_across_metadata_key_order():
    s1 = MaterialSpec(
        tipo="pull_quote",
        contenido="X",
        timestamp_relativo=0,
        metadata={"speaker": "A", "duration": 6.0},
    )
    s2 = MaterialSpec(
        tipo="pull_quote",
        contenido="X",
        timestamp_relativo=0,
        metadata={"duration": 6.0, "speaker": "A"},
    )
    assert compute_material_id("b1", 0, s1) == compute_material_id("b1", 0, s2)


def test_flatten_plan_to_materials_empty_plan():
    plan = NarrativePlan(project_id="p1", blocks=[])
    out = flatten_plan_to_materials(plan)
    assert out == []


def test_flatten_plan_to_materials_multi_block():
    mat_a = MaterialSpec(tipo="lower_third", contenido="A", timestamp_relativo=10, metadata={})
    mat_b = MaterialSpec(tipo="pull_quote", contenido="B", timestamp_relativo=20, metadata={})
    mat_c = MaterialSpec(
        tipo="chapter_marker", contenido="C", timestamp_relativo=30, metadata={"chapter_number": 2}
    )
    b1 = Block(
        id="b1",
        name="Intro",
        segments=[0, 1],
        estimated_duration="1:00",
        support_material=[mat_a, mat_b],
        transition_next="cut",
    )
    b2 = Block(
        id="b2",
        name="Body",
        segments=[2],
        estimated_duration="2:00",
        support_material=[mat_c],
        transition_next="cut",
    )
    plan = NarrativePlan(project_id="p1", blocks=[b1, b2])
    out = flatten_plan_to_materials(plan)
    assert len(out) == 3
    mid0, block_id0, spec0 = out[0]
    assert block_id0 == "b1"
    assert spec0.tipo == "lower_third"
    assert mid0.startswith("b1_m00_")
    mid1, _, _ = out[1]
    assert mid1.startswith("b1_m01_")
    mid2, block_id2, spec2 = out[2]
    assert block_id2 == "b2"
    assert mid2.startswith("b2_m00_")
    assert spec2.tipo == "chapter_marker"

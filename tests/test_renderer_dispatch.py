"""Tests for renderer dispatch."""

from __future__ import annotations

import pytest

from pipeline.models import MaterialSpec, PlannedMaterial
from pipeline.renderers.dispatch import (
    DispatchError,
    build_render_input,
    load_diagram_registry,
)


def _planned(tipo: str, contenido: str, metadata: dict, position="bottom-left") -> PlannedMaterial:
    spec = MaterialSpec(tipo=tipo, contenido=contenido, timestamp_relativo=0, metadata=metadata)
    return PlannedMaterial(
        material_id="x",
        block_id="b",
        original_spec=spec,
        decision="keep",
        spec_refined=spec,
        position=position,
        reframe=None,
        reasoning="",
    )


def test_dispatch_lower_third():
    pm = _planned("lower_third", "Edson Cúdris — Profesor de Física", {})
    comp, vars_ = build_render_input(pm)
    assert comp == "compositions/lower_third.html"
    assert vars_["name"] == "Edson Cúdris"
    assert vars_["subtitle"] == "Profesor de Física"
    assert vars_["position"] == "bottom-left"


def test_dispatch_lower_third_no_subtitle():
    pm = _planned("lower_third", "Solo Nombre", {})
    _, vars_ = build_render_input(pm)
    assert vars_["name"] == "Solo Nombre"
    assert vars_["subtitle"] == ""


def test_dispatch_pull_quote_with_speaker():
    pm = _planned("pull_quote", "La cita", {"speaker": "S"}, position="center")
    comp, vars_ = build_render_input(pm)
    assert comp == "compositions/pull_quote.html"
    assert vars_["quote"] == "La cita"
    assert vars_["speaker"] == "S"


def test_dispatch_chapter_marker():
    pm = _planned("chapter_marker", "El primer alumno", {"chapter_number": 3}, position=None)
    comp, vars_ = build_render_input(pm)
    assert comp == "compositions/chapter_marker.html"
    assert vars_["chapter_number"] == 3
    assert vars_["chapter_title"] == "El primer alumno"


def test_dispatch_animacion_texto():
    pm = _planned("animacion_texto", "VOCACIÓN", {}, position="top-right")
    comp, vars_ = build_render_input(pm)
    assert comp == "compositions/animacion_texto.html"
    assert vars_["text"] == "VOCACIÓN"
    assert vars_["position"] == "top-right"


def test_dispatch_ecuacion_latex():
    pm = _planned("ecuacion_latex", "E = mc^2", {"caption": "Energía"}, position="bottom-right")
    comp, vars_ = build_render_input(pm)
    assert comp == "compositions/ecuacion_latex.html"
    assert vars_["latex"] == "E = mc^2"
    assert vars_["caption"] == "Energía"


def test_dispatch_diagrama_barras():
    pm = _planned(
        "diagrama",
        "Comparación",
        {"tipo_visual": "barras", "data": [{"label": "A", "value": 1}, {"label": "B", "value": 2}]},
        position="center",
    )
    comp, vars_ = build_render_input(pm)
    assert comp == "compositions/diagrama_barras.html"
    assert vars_["title"] == "Comparación"
    import json

    data = json.loads(vars_["data_json"])
    assert data[0]["label"] == "A"


def test_dispatch_diagrama_ciclo():
    pm = _planned(
        "diagrama",
        "Ciclo del agua",
        {"tipo_visual": "ciclo", "nodes": ["Evapora", "Condensa", "Llueve"]},
        position="center",
    )
    comp, vars_ = build_render_input(pm)
    assert comp == "compositions/diagrama_ciclo.html"
    import json

    nodes = json.loads(vars_["nodes_json"])
    assert nodes == ["Evapora", "Condensa", "Llueve"]


def test_dispatch_diagrama_esquema_libre_with_template():
    pm = _planned(
        "diagrama",
        "bloque en plano inclinado con fricción",
        {
            "tipo_visual": "esquema_libre",
            "template_id": "bloque_inclinado",
            "params": {"angle_deg": 25, "show_friction": True},
        },
        position="center",
    )
    comp, vars_ = build_render_input(pm)
    assert comp == "compositions/diagrama_bloque_inclinado.html"
    assert vars_["angle_deg"] == 25
    assert vars_["show_friction"] is True


def test_dispatch_diagrama_esquema_libre_unknown_template_falls_to_text_card():
    pm = _planned(
        "diagrama",
        "esquema random",
        {"tipo_visual": "esquema_libre", "template_id": "no_existe", "params": {}},
        position="center",
    )
    comp, vars_ = build_render_input(pm)
    assert comp == "compositions/text_card_fallback.html"
    assert "esquema random" in vars_["text"]


def test_dispatch_unknown_tipo_raises():
    pm = _planned("nonexistent_tipo", "x", {}, position=None)
    with pytest.raises(DispatchError):
        build_render_input(pm)


def test_load_diagram_registry():
    reg = load_diagram_registry()
    assert "templates" in reg
    ids = [t["id"] for t in reg["templates"]]
    assert "bloque_inclinado" in ids

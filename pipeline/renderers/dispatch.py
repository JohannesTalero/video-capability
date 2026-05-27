"""Renderer dispatch: PlannedMaterial → (composition_path, variables_dict)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.models import PlannedMaterial

_REGISTRY_PATH = Path(__file__).parent / "diagram_templates" / "registry.json"


class DispatchError(RuntimeError):
    """Raised when no composition can handle a given tipo."""


def load_diagram_registry() -> dict[str, Any]:
    return json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))


def _parse_lower_third_contenido(s: str) -> tuple[str, str]:
    """'Nombre — Subtítulo' → ('Nombre', 'Subtítulo'). Sin separador → ('s', '')."""
    if " — " in s:
        name, _, subtitle = s.partition(" — ")
        return name.strip(), subtitle.strip()
    return s.strip(), ""


def _text_card_fallback_input(planned: PlannedMaterial) -> tuple[str, dict[str, Any]]:
    spec = planned.spec_refined or planned.original_spec
    return (
        "compositions/text_card_fallback.html",
        {
            "text": spec.contenido,
            "position": planned.position if isinstance(planned.position, str) else "center",
        },
    )


def build_render_input(planned: PlannedMaterial) -> tuple[str, dict[str, Any]]:
    """Map a PlannedMaterial to its (composition_path, variables) tuple."""
    spec = planned.spec_refined or planned.original_spec
    tipo = spec.tipo
    position = planned.position if isinstance(planned.position, str) else None

    if tipo == "lower_third":
        name, subtitle = _parse_lower_third_contenido(spec.contenido)
        return "compositions/lower_third.html", {
            "name": name,
            "subtitle": subtitle,
            "position": position or "bottom-left",
        }

    if tipo == "pull_quote":
        return "compositions/pull_quote.html", {
            "quote": spec.contenido,
            "speaker": spec.metadata.get("speaker", ""),
        }

    if tipo == "chapter_marker":
        return "compositions/chapter_marker.html", {
            "chapter_number": spec.metadata.get("chapter_number", 1),
            "chapter_title": spec.contenido,
        }

    if tipo == "animacion_texto":
        return "compositions/animacion_texto.html", {
            "text": spec.contenido,
            "position": position or "top-right",
        }

    if tipo == "ecuacion_latex":
        return "compositions/ecuacion_latex.html", {
            "latex": spec.contenido,
            "caption": spec.metadata.get("caption", "Ecuación"),
            "position": position or "bottom-right",
        }

    if tipo == "diagrama":
        tipo_visual = spec.metadata.get("tipo_visual")
        if tipo_visual == "barras":
            return "compositions/diagrama_barras.html", {
                "title": spec.contenido,
                "data_json": json.dumps(spec.metadata.get("data", []), ensure_ascii=False),
            }
        if tipo_visual == "ciclo":
            return "compositions/diagrama_ciclo.html", {
                "title": spec.contenido,
                "nodes_json": json.dumps(spec.metadata.get("nodes", []), ensure_ascii=False),
            }
        if tipo_visual == "esquema_libre":
            template_id = spec.metadata.get("template_id")
            params = spec.metadata.get("params", {})
            registry = load_diagram_registry()
            match = next((t for t in registry["templates"] if t["id"] == template_id), None)
            if match is None:
                return _text_card_fallback_input(planned)
            return f"compositions/{match['composition']}", params

    raise DispatchError(f"no dispatch rule for tipo={tipo!r}")

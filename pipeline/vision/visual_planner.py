"""Phase 3a — LLM-vision visual planning per material."""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

from pipeline.config import LLM_MODEL_VISION_PLANNER
from pipeline.llm import build_image_content, get_llm_client, is_llm_available
from pipeline.models import MaterialSpec, PlannedMaterial

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "visual_planner_system.md"

_DEFAULT_POSITION: dict[str, str | None] = {
    "lower_third": "bottom-left",
    "pull_quote": "center",
    "chapter_marker": None,
    "animacion_texto": "top-right",
    "ecuacion_latex": "bottom-right",
    "diagrama": "center",
    "transcript_fix": None,
}


class VisualPlannerError(RuntimeError):
    """Raised when the LLM-vision client cannot be used."""


def _system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _encode_frame(path: Path) -> dict[str, Any]:
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return build_image_content(b64, media_type="image/png")


def _build_user_message(
    frames_paths: list[Path],
    phase2_context: dict,
    brand: dict,
    visual_specs_summary: dict,
    diagram_template_registry: list[dict],
) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = [_encode_frame(p) for p in frames_paths]
    payload = {
        "phase2_context": phase2_context,
        "brand": brand,
        "visual_specs_summary": visual_specs_summary,
        "diagram_template_registry": diagram_template_registry,
    }
    parts.append({"type": "text", "text": json.dumps(payload, ensure_ascii=False)})
    return parts


def _parse_response(content: str) -> dict[str, Any]:
    s = content.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()
    return json.loads(s)


def _fallback_keep(
    material_id: str,
    block_id: str,
    original_spec: MaterialSpec,
    reason: str,
) -> PlannedMaterial:
    return PlannedMaterial(
        material_id=material_id,
        block_id=block_id,
        original_spec=original_spec,
        decision="keep",
        spec_refined=original_spec,
        position=_DEFAULT_POSITION.get(original_spec.tipo, "bottom-left"),
        reframe=None,
        reasoning=f"[fallback] {reason}",
    )


def _planned_from_dict(
    material_id: str,
    block_id: str,
    original_spec: MaterialSpec,
    d: dict[str, Any],
) -> PlannedMaterial:
    decision = d["decision"]
    if decision not in {"keep", "modify", "drop"}:
        raise KeyError(f"invalid decision: {decision}")
    refined_dict = d.get("spec_refined")
    refined = MaterialSpec(**refined_dict) if refined_dict else None
    if decision != "drop" and refined is None:
        raise KeyError("decision != 'drop' requires spec_refined")
    return PlannedMaterial(
        material_id=material_id,
        block_id=block_id,
        original_spec=original_spec,
        decision=decision,
        spec_refined=refined,
        position=d.get("position"),
        reframe=d.get("reframe"),
        reasoning=d.get("reasoning", ""),
    )


def plan_material_visual(
    material_id: str,
    block_id: str,
    original_spec: MaterialSpec,
    frames_paths: list[Path],
    phase2_context: dict,
    brand: dict,
    visual_specs_summary: dict,
    diagram_template_registry: list[dict],
    *,
    model: str = LLM_MODEL_VISION_PLANNER,
) -> PlannedMaterial:
    """LLM-vision per-material. Retries 1× on malformed JSON; fallback on retry failure."""
    if not is_llm_available():
        raise VisualPlannerError("OpenRouter LLM not configured")
    client = get_llm_client()
    messages = [
        {"role": "system", "content": _system_prompt()},
        {
            "role": "user",
            "content": _build_user_message(
                frames_paths,
                phase2_context,
                brand,
                visual_specs_summary,
                diagram_template_registry,
            ),
        },
    ]
    last_error = ""
    for attempt in range(2):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore[arg-type]
                temperature=0.2,
            )
            content = resp.choices[0].message.content or ""
            parsed = _parse_response(content)
            return _planned_from_dict(material_id, block_id, original_spec, parsed)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            last_error = f"{type(e).__name__}: {e}"
            logger.warning(
                "visual_planner attempt %d/2 failed for %s: %s",
                attempt + 1,
                material_id,
                last_error,
            )
    return _fallback_keep(
        material_id,
        block_id,
        original_spec,
        f"LLM output unparseable after retry ({last_error})",
    )

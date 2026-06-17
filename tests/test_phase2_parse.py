"""Tests de _parse_plan — tolerancia a code fences markdown del LLM.

Claude (Sonnet 4.6 vía OpenRouter) envuelve su JSON en ```json ... ``` incluso
con response_format=json_object; el parser debe quitar el fence antes de
json.loads(). El modelo free anterior devolvía JSON crudo, de ahí la regresión.
"""

from __future__ import annotations

import json

import pytest

from pipeline.phases.phase2_narrative import _parse_plan

_PLAN = {
    "blocks": [
        {
            "id": "block_1",
            "name": "Cold open",
            "segments": [197, 255, 523],
            "estimated_duration": "00:28",
            "support_material": [],
            "transition_next": "corte_directo",
        }
    ]
}


def _raw() -> str:
    return json.dumps(_PLAN)


def test_parses_plain_json():
    plan = _parse_plan(_raw(), "p1", "k1")
    assert len(plan.blocks) == 1
    assert plan.blocks[0].id == "block_1"
    assert plan.project_id == "p1"


def test_parses_json_fenced_with_lang():
    fenced = f"```json\n{_raw()}\n```"
    plan = _parse_plan(fenced, "p1", "k1")
    assert plan.blocks[0].name == "Cold open"


def test_parses_plain_fence_no_lang():
    fenced = f"```\n{_raw()}\n```"
    plan = _parse_plan(fenced, "p1", "k1")
    assert plan.blocks[0].segments == [197, 255, 523]


def test_parses_fence_with_surrounding_whitespace():
    fenced = f"  \n```json\n{_raw()}\n```  \n"
    plan = _parse_plan(fenced, "p1", "k1")
    assert len(plan.blocks) == 1


def test_invalid_json_still_raises():
    with pytest.raises(RuntimeError, match="not valid JSON"):
        _parse_plan("no soy json", "p1", "k1")

"""Smoke test E2E para Phase 3 sobre un proyecto existente.

Requiere:
- Modal secrets `phymac-r2-creds` y `phymac-openrouter` configurados.
- Phase 2 plan ya en R2 para el project_id (`projects/<id>/phase2/plan.json`).
- Video crudo en R2 (`projects/<id>/phase1/video.mp4`).

Costo aproximado por episodio (~30 materiales):
- Modal compute: ~$0.70
- LLM-vision (Claude Sonnet 4.6): ~$0.20-0.40
- Total: ~$1

Usage:
    uv run python scripts/run_phase3_smoke.py <project_id>

Ejemplo:
    uv run python scripts/run_phase3_smoke.py cudris-20260526
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.formats import load_format  # noqa: E402
from pipeline.models import NarrativePlan  # noqa: E402
from pipeline.phases.phase3_materials import run_phase3  # noqa: E402
from pipeline.storage import StorageAdapter, StorageKey  # noqa: E402
from pipeline.validator import validate_phase3  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


def main(project_id: str) -> int:
    storage = StorageAdapter()
    plan_key = StorageKey.narrative_plan(project_id)
    if not storage.exists(plan_key):
        print(f"ERROR: no Phase 2 plan at {plan_key}. Run Phase 2 first.")
        return 1
    plan_dict = storage.download_json(plan_key)
    plan = NarrativePlan.from_dict(plan_dict)
    total_materials = sum(len(b.support_material) for b in plan.blocks)
    print(f"Loaded plan: {len(plan.blocks)} blocks, {total_materials} materials total")

    brand = json.loads(Path("brands/phymac/brand.json").read_text(encoding="utf-8"))
    visual_specs_summary = {
        "lower_third": {
            "description": "banner bottom-left primary",
            "default_position": "bottom-left",
        },
        "pull_quote": {
            "description": "card centrada surface, accent border-left",
            "default_position": "center",
        },
        "chapter_marker": {"description": "full-screen gradient primary", "default_position": None},
        "animacion_texto": {"description": "badge accent rotado", "default_position": "top-right"},
        "ecuacion_latex": {
            "description": "card carbon bottom-right, KaTeX",
            "default_position": "bottom-right",
        },
        "diagrama": {"description": "card surface border-top accent", "default_position": "center"},
    }

    result = run_phase3(plan, brand=brand, visual_specs_summary=visual_specs_summary)
    manifest = result["manifest"]

    print(f"\n=== Manifest ({len(manifest)} entries) ===")
    for e in manifest:
        refined = e.get("refined_spec") or {}
        tipo = refined.get("tipo", "N/A")
        print(
            f"  {e['material_id']} | status={e['render_status']:9} | "
            f"decision={e['decision']:6} | tipo={tipo}"
        )

    format_obj = load_format(plan.format_id) if hasattr(plan, "format_id") else None
    whitelist = (
        format_obj.materials_whitelist
        if format_obj
        else [
            "lower_third",
            "pull_quote",
            "chapter_marker",
            "animacion_texto",
            "ecuacion_latex",
            "diagrama",
            "transcript_fix",
        ]
    )
    validation = validate_phase3(manifest, whitelist=whitelist)
    print("\n=== Validation ===")
    print(f"passed={validation.passed}  score={validation.score}")
    if validation.critical_failures:
        print("CRITICAL:")
        for c in validation.critical_failures:
            print(f"  - {c}")
    if validation.warnings:
        print("WARNINGS:")
        for w in validation.warnings:
            print(f"  - {w}")
    print(f"\nrecommendation: {validation.recommendation}")
    return 0 if validation.passed else 2


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    sys.exit(main(sys.argv[1]))

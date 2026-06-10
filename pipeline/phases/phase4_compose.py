"""Fase 4 — Composición + Branding (Unit 5).

Contrato (spec 2026-06-09 §4):
    Inputs (R2): phase2/plan.json, phase3/materials_manifest.json,
                 phase3/visual_plan.json, phase1/video original,
                 brands/<brand_id>/brand.json
    Outputs (R2): StorageKey.composed_video(project_id)
                  StorageKey.phase4_timeline(project_id)
                  StorageKey.brand_render(project_id, "intro"|"outro")
    Runner output dict: {"composed_key": str, "timeline_key": str}
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline.models import ProjectState
    from pipeline.orchestrator import PipelineOrchestrator


def run_phase_4(state: ProjectState) -> dict:
    """Adapter del orchestrator. Unit 5 implementa el cuerpo."""
    raise NotImplementedError("Unit 5 (Fase 4 Composición) no implementada aún")


def register(orchestrator: PipelineOrchestrator) -> None:
    orchestrator.register_phase(4, run_phase_4)

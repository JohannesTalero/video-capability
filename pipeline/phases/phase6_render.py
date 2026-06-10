"""Fase 6 — Render Final (Unit 7).

Contrato (spec 2026-06-09 §6):
    Inputs (R2): StorageKey.audio_processed_video(project_id)
    Outputs (R2): StorageKey.final_video(project_id) + presigned URL
    Runner output dict: Phase4RenderResult.to_dict() (cubre fases 4-6)
    Render: RenderConfig defaults (libx264 CRF18 slow, AAC 192k, 1080p,
    +faststart).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline.models import ProjectState
    from pipeline.orchestrator import PipelineOrchestrator


def run_phase_6(state: ProjectState) -> dict:
    """Adapter del orchestrator. Unit 7 implementa el cuerpo."""
    raise NotImplementedError("Unit 7 (Fase 6 Render) no implementada aún")


def register(orchestrator: PipelineOrchestrator) -> None:
    orchestrator.register_phase(6, run_phase_6)

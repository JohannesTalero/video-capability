"""Fase 5 — Procesamiento de Audio (Unit 6).

Contrato (spec 2026-06-09 §5):
    Inputs (R2): StorageKey.composed_video(project_id)
    Outputs (R2): StorageKey.audio_processed_video(project_id)
    Runner output dict: Phase5AudioResult.to_dict()
    Pipeline: extract WAV 48kHz → DeepFilterNet (fallback: skip con
    noise_reduction_applied=False) → loudnorm 2-pass -14 LUFS / TP -1 dBTP
    → remux -c:v copy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipeline.models import ProjectState
    from pipeline.orchestrator import PipelineOrchestrator


def run_phase_5(state: ProjectState) -> dict:
    """Adapter del orchestrator. Unit 6 implementa el cuerpo."""
    raise NotImplementedError("Unit 6 (Fase 5 Audio) no implementada aún")


def register(orchestrator: PipelineOrchestrator) -> None:
    orchestrator.register_phase(5, run_phase_5)

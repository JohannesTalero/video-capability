"""
Phase 2 — Narrative Plan & Cuts

Responsibilities:
- Load the Phase 1 transcription from storage.
- Load the project's FormatConfig (narrative prompt + materials whitelist).
- Ask the LLM (via OpenRouter) for a structured editorial plan.
- Parse, persist the plan JSON to storage, and return outputs for validation.

The Phase 2 runner is registered with PipelineOrchestrator via `register()`.
"""

from __future__ import annotations

import json
import logging

from pipeline.config import LLM_MODEL_PLANNER
from pipeline.formats import load_format
from pipeline.llm import get_llm_client
from pipeline.models import (
    Block,
    NarrativePlan,
    ProjectState,
    StorageKey,
    TranscriptionResult,
)
from pipeline.storage import StorageAdapter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase 2 Runner
# ---------------------------------------------------------------------------


def run_phase_2(state: ProjectState) -> dict:
    """
    Phase 2 runner. Registered with PipelineOrchestrator.

    Idempotent: if `narrative_plan.json` already exists in storage the
    cached plan is reused — the LLM is not called again. To force regen,
    delete the plan key from storage.
    """
    project_id = state.project.project_id
    format_id = state.project.format_id
    storage = StorageAdapter()
    plan_key = StorageKey.narrative_plan(project_id)

    # Transcription is needed in both branches: by the LLM call AND
    # by the ValidationAgent (segment-id check). Load it once up front.
    transcription_key = StorageKey.transcription(project_id)
    logger.info(f"[Phase 2] Loading transcription: {transcription_key}")
    transcription = TranscriptionResult.from_json(storage.download_json(transcription_key))

    # 1. Idempotency: reuse cached plan if present, UNLESS the orchestrator
    # is retrying this phase — a retry implies the previous output failed
    # validation, so re-running the LLM is the whole point.
    phase_state = state.phases.get(2)
    is_retry = phase_state is not None and phase_state.attempt > 1
    if storage.exists(plan_key) and not is_retry:
        logger.info(f"[Phase 2] Plan already in storage: {plan_key} — reusing")
        plan = NarrativePlan.from_json(storage.download_json(plan_key))
        return _outputs(plan_key, plan, format_id, transcription)
    if is_retry and storage.exists(plan_key):
        assert phase_state is not None  # is_retry implies non-None — narrow for mypy
        logger.info(
            f"[Phase 2] Retry attempt {phase_state.attempt} — ignoring cached "
            f"plan at {plan_key} and re-running LLM."
        )

    # 2. Load format config.
    logger.info(f"[Phase 2] Loading format: {format_id}")
    fmt = load_format(format_id)

    # 3. Build LLM messages.
    transcript_table = _format_transcript(transcription)
    char_count = len(transcript_table)
    logger.info(
        f"[Phase 2] Transcript table built: {len(transcription.segments)} segments, "
        f"{char_count} chars (~{char_count // 4} tokens approx)"
    )

    messages = [
        {"role": "system", "content": fmt.narrative_prompt},
        {"role": "user", "content": transcript_table},
    ]

    # 4. LLM call.
    logger.info(f"[Phase 2] Calling LLM (model={LLM_MODEL_PLANNER})...")
    client = get_llm_client()
    response = client.chat.completions.create(  # type: ignore[call-overload]
        model=LLM_MODEL_PLANNER,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.4,
    )
    plan_json_text = response.choices[0].message.content
    if not plan_json_text:
        raise RuntimeError("LLM returned an empty response. Inspect OpenRouter logs.")

    logger.info(f"[Phase 2] LLM responded with {len(plan_json_text)} chars")

    # 5. Parse the LLM output into a NarrativePlan.
    plan = _parse_plan(plan_json_text, project_id, plan_key)
    logger.info(
        f"[Phase 2] Parsed plan: {len(plan.blocks)} blocks, "
        f"{sum(len(b.segments) for b in plan.blocks)} segments used"
    )

    # 6. Persist to storage.
    logger.info(f"[Phase 2] Saving plan → {plan_key}")
    storage.upload_json(plan.to_json(), plan_key)

    return _outputs(plan_key, plan, format_id, transcription)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _outputs(
    plan_key: str,
    plan: NarrativePlan,
    format_id: str,
    transcription: TranscriptionResult,
) -> dict:
    """Build the runner output dict (validator + orchestrator consumers).

    The orchestrator persists only JSON-scalar values (str/int/float/bool/None);
    `plan` and `transcription` survive as in-memory objects passed through to
    the ValidationAgent in the same call, but they don't end up in state.json.
    """
    return {
        "plan_key": plan_key,
        "plan": plan,  # consumed by ValidationAgent
        "transcription": transcription,  # consumed by ValidationAgent
        "block_count": len(plan.blocks),
        "total_segments_used": sum(len(b.segments) for b in plan.blocks),
        "format_id": format_id,
    }


def _format_transcript(transcription: TranscriptionResult) -> str:
    """
    Render the transcription as a plain-text table that the LLM consumes:

        [id]  [start→end]  texto del segmento

    One row per segment. Designed to be unambiguous (square-bracketed
    fields) and compact (no markdown formatting).
    """
    lines = []
    for seg in transcription.segments:
        # Cap text at 1000 chars per row defensively; long single segments
        # almost never occur (Whisper splits on ~10s boundaries) but if
        # one slipped through it could blow up the prompt size.
        text = seg.text.strip()
        if len(text) > 1000:
            text = text[:1000] + "…"
        lines.append(f"[{seg.id}]  [{seg.start:.1f}→{seg.end:.1f}]  {text}")
    return "\n".join(lines)


def _parse_plan(plan_text: str, project_id: str, plan_key: str) -> NarrativePlan:
    """
    Parse the LLM response into a NarrativePlan, raising RuntimeError with
    a descriptive message on any failure. The orchestrator will catch and
    retry up to MAX_PHASE_RETRIES.
    """
    try:
        plan_dict = json.loads(plan_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"LLM response was not valid JSON: {e.msg} at pos {e.pos}. "
            f"First 200 chars: {plan_text[:200]!r}"
        ) from e

    blocks_data = plan_dict.get("blocks")
    if not isinstance(blocks_data, list) or not blocks_data:
        raise RuntimeError(
            f"LLM response missing or empty 'blocks' list. Got keys: {list(plan_dict.keys())}"
        )

    try:
        blocks = [Block.from_dict(b) for b in blocks_data]
    except (KeyError, TypeError) as e:
        raise RuntimeError(
            f"LLM response has invalid block structure: {e}. "
            f"First block: {blocks_data[0] if blocks_data else None}"
        ) from e

    return NarrativePlan(
        project_id=project_id,
        blocks=blocks,
        storage_key=plan_key,
    )


# ---------------------------------------------------------------------------
# Orchestrator registration
# ---------------------------------------------------------------------------


def register(orchestrator) -> None:
    """Register the Phase 2 runner with the orchestrator."""
    orchestrator.register_phase(2, run_phase_2)
    logger.info("Phase 2 (Narrative Plan) registered.")

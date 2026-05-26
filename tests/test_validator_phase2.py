"""Unit tests for ValidationAgent._validate_phase_2.

These don't hit the network. The llm_coherence check is auto-passed when
OPENROUTER_API_KEY isn't set in the test environment, but to be safe we
focus the assertions on the rule-based checks.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from pipeline.models import (
    Block,
    MaterialSpec,
    NarrativePlan,
    PhaseState,
    PhaseStatus,
    Project,
    ProjectState,
    ProjectStatus,
    TranscriptionResult,
    TranscriptionSegment,
)
from pipeline.validator import ValidationAgent

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _transcription(n_segments: int = 50) -> TranscriptionResult:
    segs = [
        TranscriptionSegment(
            id=i, start=i * 10.0, end=(i + 1) * 10.0, text=f"segmento {i}", confidence=0.9
        )
        for i in range(n_segments)
    ]
    return TranscriptionResult(
        project_id="test-proj",
        segments=segs,
        full_text=" ".join(s.text for s in segs),
        duration_seconds=n_segments * 10.0,
        language="es",
        model="large-v3",
        storage_key="projects/test-proj/phase1/transcription.json",
    )


def _state() -> ProjectState:
    now = datetime.now(UTC).isoformat()
    project = Project(
        project_id="test-proj",
        title="Test",
        brand_id="phymac",
        format_id="podcast_hablando_con_profes",
        video_original_key="projects/test-proj/input/v.mp4",
        created_at=now,
        updated_at=now,
        current_phase=2,
        status=ProjectStatus.RUNNING,
    )
    phases = {n: PhaseState(phase_num=n, status=PhaseStatus.PENDING) for n in range(1, 7)}
    phases[1] = PhaseState(phase_num=1, status=PhaseStatus.COMPLETED)
    return ProjectState(project=project, phases=phases)


def _cold_open(segments=(0, 1, 2)) -> Block:
    return Block(
        id="block_0",
        name="Cold open",
        segments=list(segments),
        estimated_duration="00:45",
        support_material=[],
        transition_next="corte_directo",
    )


def _block(
    idx: int,
    name: str,
    segments: list[int],
    materials: list[MaterialSpec] | None = None,
    duration: str = "04:00",
) -> Block:
    return Block(
        id=f"block_{idx}",
        name=name,
        segments=segments,
        estimated_duration=duration,
        support_material=materials or [],
        transition_next="corte_directo",
    )


def _good_plan() -> NarrativePlan:
    """A clean plan that should pass all critical checks."""
    blocks = [
        _cold_open(),
        _block(
            1,
            "Presentación",
            [3, 4],
            [
                MaterialSpec("lower_third", "Edson — Docente", 5),
            ],
            "01:00",
        ),
        _block(
            2,
            "Capítulo uno",
            [5, 6, 7, 8],
            [
                MaterialSpec("chapter_marker", "Cap 1", 0),
                MaterialSpec("pull_quote", "Una frase.", 30),
            ],
            "06:00",
        ),
        _block(
            3,
            "Capítulo dos",
            [9, 10, 11, 12, 13],
            [
                MaterialSpec("chapter_marker", "Cap 2", 0),
            ],
            "07:00",
        ),
        _block(
            4,
            "Capítulo tres",
            [14, 15, 16, 17],
            [
                MaterialSpec("chapter_marker", "Cap 3", 0),
            ],
            "06:00",
        ),
        _block(5, "Cierre", [18, 19], duration="01:30"),
    ]
    return NarrativePlan(project_id="test-proj", blocks=blocks)


def _validate(plan: NarrativePlan, transcription: TranscriptionResult | None = None):
    if transcription is None:
        transcription = _transcription(50)
    state = _state()
    output = {"plan": plan, "transcription": transcription}
    context = {"project_id": state.project.project_id, "state": state}
    agent = ValidationAgent()
    return agent._validate_phase_2(output, context)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_validates_clean_plan():
    plan = _good_plan()
    result = _validate(plan)
    assert result.passed, f"Expected pass, critical_failures={result.critical_failures}"
    assert not result.critical_failures


def test_no_blocks_critical():
    plan = NarrativePlan(project_id="test-proj", blocks=[])
    result = _validate(plan)
    assert not result.passed
    assert any("blocks" in f.lower() for f in result.critical_failures)


def test_orphan_segment_id_critical():
    plan = _good_plan()
    plan.blocks[2].segments.append(9999)  # not in transcription
    result = _validate(plan)
    assert not result.passed
    failures = " ".join(result.critical_failures).lower()
    assert "orphan" in failures or "segment" in failures


def test_duplicate_segment_critical():
    plan = _good_plan()
    plan.blocks[3].segments.append(5)  # 5 already in block_2
    result = _validate(plan)
    assert not result.passed
    failures = " ".join(result.critical_failures).lower()
    assert "duplicate" in failures


def test_cold_open_overlap_with_chapter_allowed():
    """A segment in the cold open may also appear in its natural chapter."""
    plan = _good_plan()
    # Cold open uses [0, 1, 2]; reuse segment 1 in chapter "Capítulo uno" (block_2).
    plan.blocks[2].segments.append(1)
    result = _validate(plan)
    assert result.passed, f"Cold-open overlap should pass; got: {result.critical_failures}"


def test_triple_appearance_still_critical():
    """If a segment appears in cold open + 2 chapters, the 2nd chapter dup is critical."""
    plan = _good_plan()
    plan.blocks[2].segments.append(1)  # cold open + chapter — allowed
    plan.blocks[3].segments.append(1)  # second chapter — not allowed
    result = _validate(plan)
    assert not result.passed
    failures = " ".join(result.critical_failures).lower()
    assert "duplicate" in failures


def test_unknown_material_tipo_critical():
    plan = _good_plan()
    plan.blocks[1].support_material.append(
        MaterialSpec("ecuacion_latex", "F=ma", 10),
    )
    result = _validate(plan)
    assert not result.passed
    failures = " ".join(result.critical_failures).lower()
    assert "tipo" in failures or "unknown" in failures or "ecuacion" in failures


def test_pull_quote_excess_only_warning():
    plan = _good_plan()
    # Cram 15 pull quotes into one block
    plan.blocks[2].support_material = [
        MaterialSpec("pull_quote", f"Quote {i}.", i) for i in range(15)
    ]
    result = _validate(plan)
    # Should still pass critical-wise; pull_quote excess is just a warning.
    assert result.passed, f"Pull-quote excess should not be critical: {result.critical_failures}"


def test_cold_open_wrong_count_warning_only():
    plan = _good_plan()
    plan.blocks[0] = replace(plan.blocks[0], segments=[0, 1])  # only 2
    result = _validate(plan)
    assert result.passed  # Cold open issues are warnings, not critical.


def test_cold_open_wrong_name_warning_only():
    plan = _good_plan()
    plan.blocks[0] = replace(plan.blocks[0], name="Intro")
    result = _validate(plan)
    assert result.passed

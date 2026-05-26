"""Smoke tests for the dataclasses in pipeline.models — no network, no I/O."""

from __future__ import annotations

from datetime import UTC, datetime

from pipeline.models import (
    Block,
    CheckResult,
    MaterialSpec,
    NarrativePlan,
    PhaseState,
    PhaseStatus,
    Project,
    ProjectState,
    ProjectStatus,
    StorageKey,
    TranscriptionSegment,
    ValidationResult,
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def test_project_round_trip_via_dict():
    project = Project(
        project_id="test-20260526",
        title="Test",
        brand_id="phymac",
        format_id="podcast_hablando_con_profes",
        video_original_key="projects/test/input/video.mp4",
        created_at=_now(),
        updated_at=_now(),
        current_phase=0,
        status=ProjectStatus.CREATED,
    )
    revived = Project.from_dict(project.to_dict())
    assert revived == project


def test_project_backward_compat_without_format_id():
    """Older state.json files predate format_id — load_format default must kick in."""
    data = {
        "project_id": "old-project",
        "title": "Legacy",
        "brand_id": "phymac",
        "video_original_key": "projects/old/input/v.mp4",
        "created_at": _now(),
        "updated_at": _now(),
        "current_phase": 1,
        "status": "running",
    }
    project = Project.from_dict(data)
    assert project.format_id == "podcast_hablando_con_profes"


def test_project_state_round_trip_via_json():
    now = _now()
    project = Project(
        project_id="p1",
        title="t",
        brand_id="phymac",
        format_id="podcast_hablando_con_profes",
        video_original_key="projects/p1/input/v.mp4",
        created_at=now,
        updated_at=now,
        current_phase=0,
        status=ProjectStatus.CREATED,
    )
    phases = {n: PhaseState(phase_num=n, status=PhaseStatus.PENDING) for n in range(1, 7)}
    state = ProjectState(project=project, phases=phases)
    revived = ProjectState.from_json(state.to_json())
    assert revived.project == project
    assert set(revived.phases.keys()) == set(state.phases.keys())


def test_material_spec_metadata_defaults_empty():
    m = MaterialSpec(tipo="pull_quote", contenido="Una cita.", timestamp_relativo=15)
    assert m.metadata == {}


def test_storage_key_paths_are_stable():
    assert StorageKey.project_state("p1") == "projects/p1/state.json"
    assert StorageKey.transcription("p1") == "projects/p1/phase1/transcription.json"
    assert StorageKey.narrative_plan("p1") == "projects/p1/phase2/plan.json"
    assert StorageKey.extracted_audio("p1") == "projects/p1/phase1/audio.wav"


def test_narrative_plan_round_trip():
    plan = NarrativePlan(
        project_id="p1",
        blocks=[
            Block(
                id="block_1",
                name="Cold open",
                segments=[1, 2, 3],
                estimated_duration="00:45",
                support_material=[
                    MaterialSpec(tipo="animacion_texto", contenido="clave", timestamp_relativo=0),
                ],
                transition_next="corte_directo",
            )
        ],
    )
    revived = NarrativePlan.from_json(plan.to_json())
    assert revived.project_id == "p1"
    assert len(revived.blocks) == 1
    assert revived.blocks[0].segments == [1, 2, 3]
    assert revived.blocks[0].support_material[0].tipo == "animacion_texto"


def test_transcription_segment_defaults():
    seg = TranscriptionSegment(id=0, start=0.0, end=1.0, text="hola")
    # confidence defaults to 1.0 (full confidence when not provided by Whisper)
    assert seg.confidence == 1.0


def test_validation_result_can_be_built():
    vr = ValidationResult(
        passed=True,
        phase=2,
        score=0.95,
        checks=[CheckResult(name="ok", passed=True, value=1, threshold="any", message="ok")],
    )
    assert vr.passed and vr.score == 0.95

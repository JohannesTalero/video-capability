"""
Tests for phase3_materials orchestrator integration:
  - register() wires phase 3 into the orchestrator
  - run_phase_3() happy-path with fully mocked IO
  - run_phase_3() raises ValueError on critical validation failures
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from pipeline.models import (
    Block,
    MaterialSpec,
    NarrativePlan,
    PhaseState,
    PhaseStatus,
    Project,
    ProjectState,
    ProjectStatus,
    StorageKey,
)
from pipeline.orchestrator import PipelineOrchestrator
from pipeline.storage import StorageAdapter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_project_state(project_id: str = "test-project-001") -> ProjectState:
    project = Project(
        project_id=project_id,
        title="Test Project",
        brand_id="phymac",
        format_id="podcast_hablando_con_profes",
        video_original_key=f"projects/{project_id}/input/video.mp4",
        created_at="2026-05-27T00:00:00Z",
        updated_at="2026-05-27T00:00:00Z",
        current_phase=3,
        status=ProjectStatus.RUNNING,
    )
    phases = {
        3: PhaseState(phase_num=3, status=PhaseStatus.PENDING, attempt=1),
    }
    return ProjectState(project=project, phases=phases)


def _make_plan(project_id: str = "test-project-001") -> NarrativePlan:
    mat = MaterialSpec(
        tipo="lower_third", contenido="Test — Docente, UNAL", timestamp_relativo=10, metadata={}
    )
    block = Block(
        id="b1",
        name="Cold open",
        segments=[0, 1, 2],
        estimated_duration="2:00",
        support_material=[mat],
        transition_next="corte_directo",
    )
    return NarrativePlan(project_id=project_id, blocks=[block])


def _make_manifest_entry(material_id: str = "b1_m00_abcd1234") -> dict:
    return {
        "material_id": material_id,
        "block_id": "b1",
        "original_spec": {
            "tipo": "lower_third",
            "contenido": "Test — Docente, UNAL",
            "timestamp_relativo": 10,
            "metadata": {},
        },
        "refined_spec": None,
        "decision": "keep",
        "position": "bottom-left",
        "reframe": None,
        "reasoning": "Frame OK, lower-third fits.",
        "render_status": "ok",
        "r2_key": "projects/test-project-001/phase3/materials/b1_m00_abcd1234.webm",
        "render_seconds": 4.2,
    }


# ---------------------------------------------------------------------------
# register() test
# ---------------------------------------------------------------------------


def test_register_phase3_wires_runner():
    """register() should add phase 3 to the orchestrator's runner map."""
    storage = MagicMock(spec=StorageAdapter)
    orchestrator = PipelineOrchestrator(storage=storage)

    from pipeline.phases.phase3_materials import register

    register(orchestrator)

    assert 3 in orchestrator._phase_runners
    assert orchestrator._phase_runners[3].__name__ == "run_phase_3"


# ---------------------------------------------------------------------------
# run_phase_3() happy path
# ---------------------------------------------------------------------------


@patch("pipeline.phases.phase3_materials.validate_phase3")
@patch("pipeline.phases.phase3_materials.run_phase3")
@patch("pipeline.phases.phase3_materials.load_format")
def test_run_phase_3_happy_path(
    mock_load_format,
    mock_run_phase3,
    mock_validate_phase3,
):
    """run_phase_3 loads plan + brand, calls run_phase3, validates, returns outputs."""
    project_id = "test-project-001"
    state = _make_project_state(project_id)
    plan = _make_plan(project_id)
    manifest_entry = _make_manifest_entry()

    # Storage mock: returns plan JSON on narrative_plan key, brand JSON on brand key
    storage = MagicMock(spec=StorageAdapter)
    storage.download_json.side_effect = lambda key: (
        plan.to_json()
        if key == StorageKey.narrative_plan(project_id)
        else json.dumps({"brand_id": "phymac", "colors": {"primary": "#fff"}})
    )

    # Format mock
    fmt = MagicMock()
    fmt.materials_whitelist = ("lower_third", "pull_quote", "chapter_marker")
    mock_load_format.return_value = fmt

    # Phase 3 runner mock
    mock_run_phase3.return_value = {"manifest": [manifest_entry]}

    # Validator mock — no critical failures
    validation_result = MagicMock()
    validation_result.critical_failures = []
    mock_validate_phase3.return_value = validation_result

    # Patch StorageAdapter constructor inside phase3_materials to return our mock
    with patch("pipeline.phases.phase3_materials.StorageAdapter", return_value=storage):
        from pipeline.phases.phase3_materials import run_phase_3

        outputs = run_phase_3(state)

    assert outputs["manifest_count"] == 1
    assert outputs["manifest_storage_key"] == StorageKey.materials_manifest(project_id)

    # Confirm run_phase3 was called with plan, brand dict, and specs summary
    mock_run_phase3.assert_called_once()
    call_args = mock_run_phase3.call_args[0]
    assert call_args[0].project_id == project_id  # NarrativePlan
    assert isinstance(call_args[1], dict)  # brand dict
    assert isinstance(call_args[2], dict)  # visual_specs_summary

    # Confirm validate was called with manifest and whitelist as list
    mock_validate_phase3.assert_called_once()
    _, call_kwargs = mock_validate_phase3.call_args
    assert call_kwargs["whitelist"] == list(fmt.materials_whitelist)


# ---------------------------------------------------------------------------
# run_phase_3() critical validation failure → ValueError
# ---------------------------------------------------------------------------


@patch("pipeline.phases.phase3_materials.validate_phase3")
@patch("pipeline.phases.phase3_materials.run_phase3")
@patch("pipeline.phases.phase3_materials.load_format")
def test_run_phase_3_raises_on_critical_failures(
    mock_load_format,
    mock_run_phase3,
    mock_validate_phase3,
):
    """run_phase_3 raises ValueError when validate_phase3 returns critical failures."""
    project_id = "test-project-001"
    state = _make_project_state(project_id)
    plan = _make_plan(project_id)
    manifest_entry = _make_manifest_entry()

    storage = MagicMock(spec=StorageAdapter)
    storage.download_json.side_effect = lambda key: (
        plan.to_json()
        if key == StorageKey.narrative_plan(project_id)
        else json.dumps({"brand_id": "phymac"})
    )

    fmt = MagicMock()
    fmt.materials_whitelist = ("lower_third",)
    mock_load_format.return_value = fmt

    mock_run_phase3.return_value = {"manifest": [manifest_entry]}

    # Validator returns critical failures
    validation_result = MagicMock()
    validation_result.critical_failures = ["r2_key not resolvable for 1 entries"]
    mock_validate_phase3.return_value = validation_result

    with patch("pipeline.phases.phase3_materials.StorageAdapter", return_value=storage):
        from pipeline.phases.phase3_materials import run_phase_3

        with pytest.raises(ValueError, match="critical failure"):
            run_phase_3(state)


# ---------------------------------------------------------------------------
# StorageKey.materials_manifest exists
# ---------------------------------------------------------------------------


def test_storage_key_materials_manifest_format():
    key = StorageKey.materials_manifest("my-project-42")
    assert key == "projects/my-project-42/phase3/materials_manifest.json"

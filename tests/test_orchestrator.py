"""Smoke tests for PipelineOrchestrator — mocked StorageAdapter, no network."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pipeline.models import ProjectStatus
from pipeline.orchestrator import (
    InvalidPhaseOrderError,
    PipelineOrchestrator,
    ProjectNotFoundError,
)
from pipeline.storage import StorageKeyNotFoundError


def _orchestrator_with_mocked_storage() -> tuple[PipelineOrchestrator, MagicMock]:
    storage = MagicMock()
    orchestrator = PipelineOrchestrator(storage=storage)
    return orchestrator, storage


def test_orchestrator_constructs_without_network():
    o, _ = _orchestrator_with_mocked_storage()
    assert o.TOTAL_PHASES == 6
    assert o._phase_runners == {}


def test_register_phase_records_runner():
    o, _ = _orchestrator_with_mocked_storage()
    runner = lambda state: {}                 # noqa: E731 — minimal stub
    o.register_phase(1, runner)
    assert 1 in o._phase_runners
    assert o._phase_runners[1] is runner


def test_load_checkpoint_raises_on_missing_project():
    o, storage = _orchestrator_with_mocked_storage()
    storage.download_json.side_effect = StorageKeyNotFoundError("not found")
    with pytest.raises(ProjectNotFoundError):
        o.load_checkpoint("does-not-exist")


def test_create_project_uses_supplied_format_id():
    o, storage = _orchestrator_with_mocked_storage()
    storage.exists.return_value = False        # project_id slug is unused
    state = o.create_project(
        title="Test",
        video_local_path="/tmp/v.mp4",
        brand_id="phymac",
        format_id="podcast_hablando_con_profes",
    )
    assert state.project.format_id == "podcast_hablando_con_profes"
    assert state.project.status == ProjectStatus.CREATED


def test_run_rejects_invalid_end_at_phase():
    o, storage = _orchestrator_with_mocked_storage()
    # load_checkpoint will be called; mock a minimal valid response.
    # Simpler: monkey-patch load_checkpoint directly.
    fake_state = MagicMock()
    fake_state.project.title = "x"
    o.load_checkpoint = MagicMock(return_value=fake_state)
    o._validate_start_phase = MagicMock()
    with pytest.raises(ValueError, match="Invalid end_at_phase"):
        o.run(project_id="x", start_from_phase=3, end_at_phase=2)

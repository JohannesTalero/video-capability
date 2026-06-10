"""Los stubs del contrato deben existir, registrarse y fallar explícitamente."""

import pytest

from pipeline.orchestrator import PipelineOrchestrator
from pipeline.phases import phase4_compose, phase5_audio, phase6_render


@pytest.mark.parametrize(
    ("module", "phase_num"),
    [(phase4_compose, 4), (phase5_audio, 5), (phase6_render, 6)],
)
def test_stub_registers_and_raises(module, phase_num, monkeypatch):
    registered: dict[int, object] = {}
    orch = object.__new__(PipelineOrchestrator)  # sin storage real
    monkeypatch.setattr(
        PipelineOrchestrator,
        "register_phase",
        lambda self, n, fn: registered.__setitem__(n, fn),
    )
    module.register(orch)
    assert phase_num in registered
    with pytest.raises(NotImplementedError):
        registered[phase_num](None)

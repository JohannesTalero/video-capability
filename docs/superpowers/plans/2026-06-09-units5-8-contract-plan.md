# Units 5–8 Shared Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Congelar las interfaces compartidas (modelos, storage keys, stubs de fases 4–6, regiones del validator) para que Units 5, 6 y 8 puedan desarrollarse en worktrees paralelos sin conflictos.

**Architecture:** PR pequeño a `develop` que solo toca `pipeline/models.py`, `pipeline/storage` keys, crea 3 stubs de fase con el patrón `register(orchestrator)` existente, y marca regiones en `pipeline/validator.py`. Cero lógica de negocio.

**Tech Stack:** Python 3.11/3.12, dataclasses, pytest. Spec: `docs/superpowers/specs/2026-06-09-units5-8-pipeline-completion-design.md` §3.

---

### Task 1: Reconciliar `BrandConfig` con el schema real de `brands/phymac/brand.json`

**Files:**
- Modify: `pipeline/models.py` (sección Brand Config, líneas ~450–495)
- Test: `tests/test_models_phase45.py` (create)

- [ ] **Step 1: Write the failing test**

```python
"""Tests para modelos compartidos de Fases 4-6 (contrato Units 5-8)."""

import json
from pathlib import Path

from pipeline.models import BrandConfig

BRAND_JSON = Path(__file__).parent.parent / "brands" / "phymac" / "brand.json"


def test_brand_config_loads_real_brand_json():
    data = json.loads(BRAND_JSON.read_text(encoding="utf-8"))
    cfg = BrandConfig.from_dict(data)
    assert cfg.id == "phymac"
    assert cfg.name == "PhyMaC"
    assert cfg.colors["primary"] == "#2962FF"
    assert cfg.fonts["display"]["family"] == "Montserrat"
    assert cfg.assets["logo"] == "brand-assets/logo.svg"
    assert cfg.pattern["type"] == "cross-grid"


def test_brand_config_roundtrip():
    data = json.loads(BRAND_JSON.read_text(encoding="utf-8"))
    cfg = BrandConfig.from_dict(data)
    assert cfg.to_dict() == data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models_phase45.py -v`
Expected: FAIL (`BrandConfig.from_dict` exige claves `brand_id`/`display_name` que el JSON real no tiene).

- [ ] **Step 3: Replace the Brand Config section in `pipeline/models.py`**

Reemplazar `BrandColors`, `BrandFonts`, `BrandAssets`, `BrandConfig` por:

```python
@dataclass
class BrandConfig:
    """Brand kit, espejo 1:1 de brands/<id>/brand.json (schema del spike 2026-05-26).

    Los sub-objetos quedan como dicts: el JSON es la fuente de verdad y los
    consumidores (brand_css.py, HF compositions) los leen por clave.
    """

    id: str
    name: str
    colors: dict[str, str]
    fonts: dict[str, Any]
    shadows: dict[str, str]
    radius: dict[str, int]
    pattern: dict[str, Any]
    assets: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "colors": self.colors,
            "fonts": self.fonts,
            "shadows": self.shadows,
            "radius": self.radius,
            "pattern": self.pattern,
            "assets": self.assets,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BrandConfig:
        return cls(
            id=d["id"],
            name=d["name"],
            colors=d["colors"],
            fonts=d["fonts"],
            shadows=d.get("shadows", {}),
            radius=d.get("radius", {}),
            pattern=d.get("pattern", {}),
            assets=d["assets"],
        )
```

Eliminar `BrandColors`, `BrandFonts`, `BrandAssets` (verificado: sin usos fuera de `models.py`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_models_phase45.py tests/ -x -q`
Expected: PASS (todos; nada más importaba los modelos eliminados).

- [ ] **Step 5: Commit**

```bash
git add pipeline/models.py tests/test_models_phase45.py
git commit -m "feat(contract): reconcile BrandConfig with real brand.json schema"
```

---

### Task 2: `Phase5AudioResult` + storage keys nuevos

**Files:**
- Modify: `pipeline/models.py` (junto a `Phase4RenderResult`, ~línea 515)
- Modify: `pipeline/models.py` clase `StorageKey` (~línea 227)
- Test: `tests/test_models_phase45.py` (append)

- [ ] **Step 1: Write the failing tests (append)**

```python
from pipeline.models import Phase5AudioResult, StorageKey


def test_phase5_audio_result_roundtrip():
    r = Phase5AudioResult(
        project_id="p1",
        storage_key="projects/p1/phase5/audio_processed.mp4",
        loudness_in_lufs=-23.5,
        loudness_out_lufs=-14.1,
        true_peak_dbtp=-1.4,
        noise_reduction_applied=True,
        duration_seconds=712.3,
        process_time_seconds=95.0,
    )
    d = r.to_dict()
    assert d["loudness_out_lufs"] == -14.1
    assert Phase5AudioResult.from_dict(d) == r


def test_storage_keys_phase4():
    assert StorageKey.phase4_timeline("p1") == "projects/p1/phase4/timeline.json"
    assert StorageKey.brand_render("p1", "intro") == "projects/p1/phase4/brand/intro.mp4"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_models_phase45.py -v`
Expected: FAIL with ImportError (`Phase5AudioResult`).

- [ ] **Step 3: Implement**

En `StorageKey` (seguir el estilo de los staticmethods existentes):

```python
    @staticmethod
    def phase4_timeline(project_id: str) -> str:
        return f"projects/{project_id}/phase4/timeline.json"

    @staticmethod
    def brand_render(project_id: str, name: str) -> str:
        return f"projects/{project_id}/phase4/brand/{name}.mp4"
```

Debajo de `Phase4RenderResult`:

```python
@dataclass
class Phase5AudioResult:
    """Output del procesamiento de audio (Fase 5, Unit 6)."""

    project_id: str
    storage_key: str
    loudness_in_lufs: float
    loudness_out_lufs: float
    true_peak_dbtp: float
    noise_reduction_applied: bool
    duration_seconds: float
    process_time_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "storage_key": self.storage_key,
            "loudness_in_lufs": self.loudness_in_lufs,
            "loudness_out_lufs": self.loudness_out_lufs,
            "true_peak_dbtp": self.true_peak_dbtp,
            "noise_reduction_applied": self.noise_reduction_applied,
            "duration_seconds": self.duration_seconds,
            "process_time_seconds": self.process_time_seconds,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Phase5AudioResult:
        return cls(**d)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_models_phase45.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/models.py tests/test_models_phase45.py
git commit -m "feat(contract): Phase5AudioResult + phase4 storage keys"
```

---

### Task 3: Stubs de fases 4–6 con patrón `register()`

**Files:**
- Create: `pipeline/phases/phase4_compose.py`
- Create: `pipeline/phases/phase5_audio.py`
- Create: `pipeline/phases/phase6_render.py`
- Test: `tests/test_phase_stubs.py` (create)

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_phase_stubs.py -v`
Expected: FAIL with ModuleNotFoundError.

- [ ] **Step 3: Create the three stubs**

`pipeline/phases/phase4_compose.py`:

```python
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
```

`pipeline/phases/phase5_audio.py` — mismo esqueleto con:

```python
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
```

`pipeline/phases/phase6_render.py` — mismo esqueleto con:

```python
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
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_phase_stubs.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add pipeline/phases/phase4_compose.py pipeline/phases/phase5_audio.py pipeline/phases/phase6_render.py tests/test_phase_stubs.py
git commit -m "feat(contract): phase 4-6 stubs with register() pattern"
```

---

### Task 4: Regiones del validator + CI gates + PR

**Files:**
- Modify: `pipeline/validator.py` (final del archivo)

- [ ] **Step 1: Append section markers to `pipeline/validator.py`**

```python
# ---------------------------------------------------------------------------
# Phase 4 — Composición (Unit 5): validate_phase4() se implementa aquí.
# Checks (spec §4): duración ≈ Σ keep + intro/outro + markers (±5%),
# 1920x1080, fps, audio stream presente, objeto R2 > 0 bytes,
# timeline.json parseable y consistente con el plan.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Phase 5 — Audio (Unit 6): validate_phase5() se implementa aquí.
# Checks (spec §5): loudness -14 ±1 LUFS, true peak < -1 dBTP,
# duración = input ±0.1s, video stream intacto, tamaño > 0.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Phase 6 — Render final (Unit 7): validate_phase6() se implementa aquí.
# Checks (spec §6): h264+AAC, 1080p, faststart, duración = phase5 ±0.1s,
# URL descargable.
# ---------------------------------------------------------------------------
```

- [ ] **Step 2: CI gates locales**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy pipeline && uv run pytest -q`
Expected: todo verde.

- [ ] **Step 3: Commit + push + PR**

```bash
git add pipeline/validator.py
git commit -m "feat(contract): validator section markers for phases 4-6"
git push -u origin feature/units5-8-contract
gh pr create --base develop --title "feat(contract): shared interfaces for Units 5-8" --body "..."
```

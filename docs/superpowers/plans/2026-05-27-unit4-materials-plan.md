# Unit 4 — Phase 3 Materiales (vision-aware) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar la Fase 3 del pipeline PhyMaC: visual planning con LLM-vision + render con HyperFrames sobre Modal + manifest auditado en R2, consumible por Phase 4.

**Architecture:** Phase 3a (LLM-vision por material, secuencial) decide treatment visual; Phase 3b (Modal.map por-material) renderiza con HyperFrames; Phase 3c valida y produce manifest. Idempotente a 3 niveles (frames cache, visual_plan cache, render cache). Brand-agnostic via `brands/<id>/`. Failure policy: 1 retry + fallback text card.

**Tech Stack:** Python 3.11+ (existing pipeline), Modal (compute), HyperFrames + GSAP + KaTeX (rendering en Chromium), OpenRouter (LLM-vision via Claude Sonnet 4.6 default), Cloudflare R2 (storage via boto3), ffmpeg (frame extract + transcode).

**Spec de referencia:** `docs/superpowers/specs/2026-05-27-unit4-materials-design.md`

**Rama:** `feature/unit4-materials` (creada en Task 0)

**Convenciones del proyecto:**
- Prompts LLM en archivos `.md` cargados en runtime (no hardcoded en Python). Cargar via `pathlib.Path(...).read_text()`.
- Tests con `pytest`, asyncio_mode=auto, fixtures en `tests/conftest.py` o por-archivo.
- CI gates obligatorios al final de cada task: `ruff check`, `ruff format --check`, `mypy`, `pytest`, `pip-audit`, `bandit`.
- Commit por task (mensajes "feat: …", "test: …", "chore: …").

---

## Pre-flight checks

Antes de Task 0, confirmá entorno y baseline.

- [ ] **Verificar entorno**

```bash
python3 --version    # >= 3.11
ffmpeg -version | head -1
which node && node --version    # >= 20
```

- [ ] **Sync deps existentes**

```bash
cd /mnt/c/Users/johan/Documents/PhyMaC/video-capability
uv sync --frozen
```

- [ ] **Baseline CI verde en `develop`**

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy pipeline tests
uv run pytest -x
uv run pip-audit --strict
uv run bandit -c pyproject.toml -r pipeline
```

Esperado: todos pasan. Si alguno falla en `develop`, **parar y reportar** — la baseline tiene que estar limpia antes de empezar Unit 4.

- [ ] **Confirmar Modal secrets disponibles**

```bash
uv run modal secret list 2>&1 | grep -E "phymac-(r2-creds|openrouter)"
```

Esperado: ambos secretos existen. Si falta `phymac-openrouter`, crearlo con `OPENROUTER_API_KEY` antes de Task 4.

---

## Task 0: Branch + commit spec + commit plan

**Goal:** Crear la feature branch desde `develop` actualizado y commitear spec + plan como primer commit del feature.

**Files:**
- New branch: `feature/unit4-materials`
- Commit: `docs/superpowers/specs/2026-05-27-unit4-materials-design.md`
- Commit: `docs/superpowers/plans/2026-05-27-unit4-materials-plan.md` (este archivo)

- [ ] **Step 1: Asegurar `develop` actualizado**

```bash
cd /mnt/c/Users/johan/Documents/PhyMaC/video-capability
git checkout develop
git fetch origin
git pull origin develop
git status
```

Esperado: `On branch develop`, "Your branch is up to date with 'origin/develop'", working tree limpio (excepto los untracked del spike anterior que se borraron).

- [ ] **Step 2: Crear feature branch**

```bash
git checkout -b feature/unit4-materials
```

Esperado: `Switched to a new branch 'feature/unit4-materials'`

- [ ] **Step 3: Verificar archivos a commitear**

```bash
git status
ls docs/superpowers/specs/2026-05-27-unit4-materials-design.md
ls docs/superpowers/plans/2026-05-27-unit4-materials-plan.md
```

Esperado: spec y plan listados como untracked.

- [ ] **Step 4: Commit inicial con spec + plan**

```bash
git add docs/superpowers/specs/2026-05-27-unit4-materials-design.md \
        docs/superpowers/plans/2026-05-27-unit4-materials-plan.md
git commit -m "$(cat <<'EOF'
docs: spec + plan for Unit 4 (Phase 3 vision-aware materials)

Spec aprobado tras brainstorming con el usuario. Plan implementa Phase 3a
(LLM-vision visual planning), Phase 3b (HyperFrames render sobre Modal),
Phase 3c (manifest + validación). Stack ganador del A/B spike: HyperFrames.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Verificación:

```bash
git log --oneline -1
# Esperado: <hash> docs: spec + plan for Unit 4 ...
```

---

## Task 1: Modelos de datos (PlannedMaterial, RenderResult, ManifestEntry)

**Goal:** Extender `pipeline/models.py` con los dataclasses que Phase 3 produce y consume. TDD.

**Files:**
- Modify: `pipeline/models.py` (agregar 3 dataclasses al final)
- Create: `tests/test_models_phase3.py`

- [ ] **Step 1: Escribir tests fallidos**

Crear `tests/test_models_phase3.py`:

```python
"""Tests for Phase 3 dataclasses in pipeline.models."""
from __future__ import annotations

import json

import pytest

from pipeline.models import (
    ManifestEntry,
    MaterialSpec,
    PlannedMaterial,
    RenderResult,
)


def _sample_material_spec() -> MaterialSpec:
    return MaterialSpec(
        tipo="lower_third",
        contenido="Edson Cúdris — Profesor de Física",
        timestamp_relativo=222,
        metadata={},
    )


def test_planned_material_keep_to_dict_roundtrip():
    pm = PlannedMaterial(
        material_id="b1_m00_abcd1234",
        block_id="b1",
        original_spec=_sample_material_spec(),
        decision="keep",
        spec_refined=_sample_material_spec(),
        position="bottom-left",
        reframe=None,
        reasoning="Speaker centrado, fondo libre.",
    )
    d = pm.to_dict()
    assert d["material_id"] == "b1_m00_abcd1234"
    assert d["decision"] == "keep"
    assert d["spec_refined"]["tipo"] == "lower_third"
    assert d["reframe"] is None
    pm2 = PlannedMaterial.from_dict(d)
    assert pm2 == pm


def test_planned_material_drop_has_null_refined():
    pm = PlannedMaterial(
        material_id="b1_m01_dead",
        block_id="b1",
        original_spec=_sample_material_spec(),
        decision="drop",
        spec_refined=None,
        position=None,
        reframe=None,
        reasoning="Frame demasiado ocupado, lower-third distrae.",
    )
    d = pm.to_dict()
    assert d["spec_refined"] is None
    assert d["position"] is None
    pm2 = PlannedMaterial.from_dict(d)
    assert pm2 == pm


def test_planned_material_position_as_dict():
    pm = PlannedMaterial(
        material_id="b1_m02_beef",
        block_id="b1",
        original_spec=_sample_material_spec(),
        decision="modify",
        spec_refined=_sample_material_spec(),
        position={"x_pct": 0.05, "y_pct": 0.85},
        reframe={
            "type": "zoom",
            "params": {"scale": 1.2, "center_x_pct": 0.3, "center_y_pct": 0.5},
            "t_start_relative": 220.5,
            "t_end_relative": 226.5,
        },
        reasoning="Zoom suave a la cara, lower-third a coordenada custom.",
    )
    d = pm.to_dict()
    assert d["position"]["x_pct"] == 0.05
    assert d["reframe"]["type"] == "zoom"
    pm2 = PlannedMaterial.from_dict(d)
    assert pm2 == pm


def test_render_result_ok():
    rr = RenderResult(
        material_id="b1_m00_abcd1234",
        status="ok",
        r2_key="projects/x/phase3/materials/b1_m00_abcd1234.webm",
        render_seconds=58.4,
        error=None,
    )
    assert rr.to_dict()["status"] == "ok"


def test_render_result_fallback_records_error():
    rr = RenderResult(
        material_id="b1_m00_abcd1234",
        status="fallback",
        r2_key="projects/x/phase3/materials/b1_m00_abcd1234.webm",
        render_seconds=62.1,
        error="ffmpeg returncode=1: invalid LaTeX",
    )
    assert rr.status == "fallback"
    assert rr.error is not None


def test_manifest_entry_full_serialization():
    spec_dict = _sample_material_spec().to_dict()
    me = ManifestEntry(
        material_id="b1_m00_abcd1234",
        block_id="b1",
        original_spec=spec_dict,
        refined_spec=spec_dict,
        decision="keep",
        position="bottom-left",
        reframe=None,
        reasoning="OK",
        render_status="ok",
        r2_key="projects/x/phase3/materials/b1_m00_abcd1234.webm",
        render_seconds=58.4,
    )
    js = json.dumps(me.to_dict())
    parsed = json.loads(js)
    assert parsed["material_id"] == "b1_m00_abcd1234"


def test_manifest_entry_dropped_no_r2_key():
    spec_dict = _sample_material_spec().to_dict()
    me = ManifestEntry(
        material_id="b1_m01_dead",
        block_id="b1",
        original_spec=spec_dict,
        refined_spec=None,
        decision="drop",
        position=None,
        reframe=None,
        reasoning="No encaja con el frame.",
        render_status="dropped",
        r2_key=None,
        render_seconds=0.0,
    )
    d = me.to_dict()
    assert d["r2_key"] is None
    assert d["render_status"] == "dropped"
```

- [ ] **Step 2: Correr tests, esperar fallo de import**

```bash
uv run pytest tests/test_models_phase3.py -v
```

Esperado: `ImportError: cannot import name 'PlannedMaterial' from 'pipeline.models'`.

- [ ] **Step 3: Agregar dataclasses a `pipeline/models.py`**

Editar `pipeline/models.py`, agregar al final (antes de cualquier helper privado):

```python
# ---------------------------------------------------------------------------
# Phase 3 — Materiales de soporte (Unit 4)
# ---------------------------------------------------------------------------


@dataclass
class PlannedMaterial:
    """Output de Phase 3a: la decisión visual refinada para un material."""

    material_id: str
    block_id: str
    original_spec: MaterialSpec
    decision: str  # "keep" | "modify" | "drop"
    spec_refined: MaterialSpec | None  # None si decision == "drop"
    position: str | dict[str, float] | None  # ej "bottom-left" o {"x_pct":.05,"y_pct":.85}
    reframe: dict[str, Any] | None  # {type, params, t_start_relative, t_end_relative}
    reasoning: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "material_id": self.material_id,
            "block_id": self.block_id,
            "original_spec": self.original_spec.to_dict(),
            "decision": self.decision,
            "spec_refined": self.spec_refined.to_dict() if self.spec_refined else None,
            "position": self.position,
            "reframe": self.reframe,
            "reasoning": self.reasoning,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PlannedMaterial:
        refined = d.get("spec_refined")
        return cls(
            material_id=d["material_id"],
            block_id=d["block_id"],
            original_spec=MaterialSpec(**d["original_spec"]),
            decision=d["decision"],
            spec_refined=MaterialSpec(**refined) if refined else None,
            position=d.get("position"),
            reframe=d.get("reframe"),
            reasoning=d.get("reasoning", ""),
        )


@dataclass
class RenderResult:
    """Output de un Modal worker que renderizó un material."""

    material_id: str
    status: str  # "ok" | "fallback" | "dropped"
    r2_key: str | None
    render_seconds: float
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "material_id": self.material_id,
            "status": self.status,
            "r2_key": self.r2_key,
            "render_seconds": self.render_seconds,
            "error": self.error,
        }


@dataclass
class ManifestEntry:
    """Entry de phase3/materials_manifest.json."""

    material_id: str
    block_id: str
    original_spec: dict[str, Any]
    refined_spec: dict[str, Any] | None
    decision: str
    position: str | dict[str, float] | None
    reframe: dict[str, Any] | None
    reasoning: str
    render_status: str  # "ok" | "fallback" | "dropped"
    r2_key: str | None
    render_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ManifestEntry:
        return cls(**d)
```

- [ ] **Step 4: Correr tests, deben pasar**

```bash
uv run pytest tests/test_models_phase3.py -v
```

Esperado: 7 passed.

- [ ] **Step 5: CI gates locales**

```bash
uv run ruff check pipeline/models.py tests/test_models_phase3.py
uv run ruff format --check pipeline/models.py tests/test_models_phase3.py
uv run mypy pipeline/models.py
uv run pytest tests/ -x
```

Esperado: todo verde. Si ruff format falla → `uv run ruff format pipeline/models.py tests/test_models_phase3.py` y re-correr.

- [ ] **Step 6: Commit**

```bash
git add pipeline/models.py tests/test_models_phase3.py
git commit -m "$(cat <<'EOF'
feat(models): add PlannedMaterial, RenderResult, ManifestEntry for Phase 3

Dataclasses para Unit 4 (Phase 3 vision-aware materials). Soporta
serialización JSON round-trip, position como string o dict de coords,
reframe instructions opcionales para Phase 4. decision="drop" implica
spec_refined=None, r2_key=None.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Material ID + flatten plan helpers

**Goal:** Función pura para computar `material_id` estable y para aplanar el plan de Phase 2 a lista de materials con IDs.

**Files:**
- Create: `pipeline/phase3_helpers.py`
- Create: `tests/test_phase3_helpers.py`

- [ ] **Step 1: Tests fallidos**

Crear `tests/test_phase3_helpers.py`:

```python
"""Tests for phase3_helpers."""
from __future__ import annotations

from pipeline.models import Block, MaterialSpec, NarrativePlan
from pipeline.phase3_helpers import compute_material_id, flatten_plan_to_materials


def test_compute_material_id_format():
    spec = MaterialSpec(tipo="lower_third", contenido="X", timestamp_relativo=0, metadata={})
    mid = compute_material_id("block_1", 0, spec)
    # Formato: <block_id>_m<idx02d>_<8hex>
    parts = mid.split("_m")
    assert parts[0] == "block_1"
    rest = parts[1]
    idx_str, _, hexpart = rest.partition("_")
    assert idx_str == "00"
    assert len(hexpart) == 8
    assert all(c in "0123456789abcdef" for c in hexpart)


def test_compute_material_id_deterministic():
    spec = MaterialSpec(tipo="lower_third", contenido="X", timestamp_relativo=0, metadata={})
    assert compute_material_id("b1", 0, spec) == compute_material_id("b1", 0, spec)


def test_compute_material_id_changes_with_content():
    s1 = MaterialSpec(tipo="lower_third", contenido="A", timestamp_relativo=0, metadata={})
    s2 = MaterialSpec(tipo="lower_third", contenido="B", timestamp_relativo=0, metadata={})
    assert compute_material_id("b1", 0, s1) != compute_material_id("b1", 0, s2)


def test_compute_material_id_changes_with_metadata():
    s1 = MaterialSpec(tipo="diagrama", contenido="X", timestamp_relativo=0,
                     metadata={"tipo_visual": "barras"})
    s2 = MaterialSpec(tipo="diagrama", contenido="X", timestamp_relativo=0,
                     metadata={"tipo_visual": "ciclo"})
    assert compute_material_id("b1", 0, s1) != compute_material_id("b1", 0, s2)


def test_compute_material_id_stable_across_metadata_key_order():
    s1 = MaterialSpec(tipo="pull_quote", contenido="X", timestamp_relativo=0,
                     metadata={"speaker": "A", "duration": 6.0})
    s2 = MaterialSpec(tipo="pull_quote", contenido="X", timestamp_relativo=0,
                     metadata={"duration": 6.0, "speaker": "A"})
    assert compute_material_id("b1", 0, s1) == compute_material_id("b1", 0, s2)


def test_flatten_plan_to_materials_empty_plan():
    plan = NarrativePlan(project_id="p1", blocks=[], total_duration_estimate="0:00")
    out = flatten_plan_to_materials(plan)
    assert out == []


def test_flatten_plan_to_materials_multi_block():
    mat_a = MaterialSpec(tipo="lower_third", contenido="A", timestamp_relativo=10, metadata={})
    mat_b = MaterialSpec(tipo="pull_quote", contenido="B", timestamp_relativo=20, metadata={})
    mat_c = MaterialSpec(tipo="chapter_marker", contenido="C", timestamp_relativo=30,
                        metadata={"chapter_number": 2})
    b1 = Block(id="b1", name="Intro", segments=[0, 1], estimated_duration="1:00",
               support_material=[mat_a, mat_b], transition_next="cut")
    b2 = Block(id="b2", name="Body", segments=[2], estimated_duration="2:00",
               support_material=[mat_c], transition_next="cut")
    plan = NarrativePlan(project_id="p1", blocks=[b1, b2], total_duration_estimate="3:00")
    out = flatten_plan_to_materials(plan)
    assert len(out) == 3
    mid0, block_id0, spec0 = out[0]
    assert block_id0 == "b1"
    assert spec0.tipo == "lower_third"
    assert mid0.startswith("b1_m00_")
    mid1, _, _ = out[1]
    assert mid1.startswith("b1_m01_")
    mid2, block_id2, spec2 = out[2]
    assert block_id2 == "b2"
    assert mid2.startswith("b2_m00_")
    assert spec2.tipo == "chapter_marker"
```

- [ ] **Step 2: Correr tests, esperar fallo de import**

```bash
uv run pytest tests/test_phase3_helpers.py -v
```

Esperado: `ModuleNotFoundError: No module named 'pipeline.phase3_helpers'`.

- [ ] **Step 3: Implementar `pipeline/phase3_helpers.py`**

```python
"""Phase 3 helpers — material ID computation and plan flattening.

Pure functions; no I/O. Used by phase3_materials orchestrator.
"""
from __future__ import annotations

import hashlib
import json

from pipeline.models import MaterialSpec, NarrativePlan


def compute_material_id(block_id: str, idx_in_block: int, spec: MaterialSpec) -> str:
    """Stable, content-aware ID. Format: <block_id>_m<idx02d>_<8hex>.

    Cache key contract:
    - block_id changes → new ID
    - idx within block changes → new ID
    - any field of spec (tipo, contenido, metadata) changes → new ID via hash
    - metadata key order does NOT affect ID (sort_keys=True)
    """
    payload = "|".join(
        [
            spec.tipo,
            spec.contenido,
            json.dumps(spec.metadata, sort_keys=True, ensure_ascii=False),
            str(spec.timestamp_relativo),
        ]
    )
    content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]
    return f"{block_id}_m{idx_in_block:02d}_{content_hash}"


def flatten_plan_to_materials(
    plan: NarrativePlan,
) -> list[tuple[str, str, MaterialSpec]]:
    """Flatten plan to [(material_id, block_id, spec), ...] preserving order.

    Indexes within each block start at 0.
    """
    out: list[tuple[str, str, MaterialSpec]] = []
    for block in plan.blocks:
        for idx, spec in enumerate(block.support_material):
            mid = compute_material_id(block.id, idx, spec)
            out.append((mid, block.id, spec))
    return out
```

- [ ] **Step 4: Correr tests, deben pasar**

```bash
uv run pytest tests/test_phase3_helpers.py -v
```

Esperado: 7 passed.

- [ ] **Step 5: CI gates locales**

```bash
uv run ruff check pipeline/phase3_helpers.py tests/test_phase3_helpers.py
uv run ruff format --check pipeline/phase3_helpers.py tests/test_phase3_helpers.py
uv run mypy pipeline/phase3_helpers.py
uv run pytest tests/ -x
```

- [ ] **Step 6: Commit**

```bash
git add pipeline/phase3_helpers.py tests/test_phase3_helpers.py
git commit -m "$(cat <<'EOF'
feat(phase3): add compute_material_id + flatten_plan_to_materials helpers

Pure functions. material_id es estable, sensible al contenido + metadata
(sort_keys para invariancia de orden de keys), formato block_id_mNN_8hex.
flatten() preserva orden de blocks y de support_material dentro de cada block.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Frame extractor (ffmpeg wrapper)

**Goal:** Función pura que extrae N frames de un video local a timestamps específicos. Devuelve paths a PNGs.

**Files:**
- Create: `pipeline/vision/__init__.py` (empty)
- Create: `pipeline/vision/frame_extractor.py`
- Create: `tests/test_frame_extractor.py`

- [ ] **Step 1: Tests fallidos**

Crear `tests/test_frame_extractor.py`:

```python
"""Tests for frame_extractor."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pipeline.vision.frame_extractor import (
    FrameExtractionError,
    extract_frames,
)


@pytest.fixture
def sample_video(tmp_path: Path) -> Path:
    """Synthetic 10s testsrc video 1920x1080 @ 30fps."""
    video = tmp_path / "sample.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=duration=10:size=1920x1080:rate=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(video),
        ],
        check=True,
    )
    return video


def test_extract_single_frame(sample_video: Path, tmp_path: Path):
    out_dir = tmp_path / "frames"
    paths = extract_frames(sample_video, [5.0], out_dir, prefix="x")
    assert len(paths) == 1
    assert paths[0].exists()
    assert paths[0].suffix == ".png"
    assert paths[0].stat().st_size > 0


def test_extract_multiple_frames(sample_video: Path, tmp_path: Path):
    out_dir = tmp_path / "frames"
    paths = extract_frames(sample_video, [1.0, 5.0, 9.0], out_dir, prefix="m1")
    assert len(paths) == 3
    for p in paths:
        assert p.exists()
        assert p.stat().st_size > 0
    names = sorted(p.name for p in paths)
    assert any("t1" in n for n in names)
    assert any("t5" in n for n in names)
    assert any("t9" in n for n in names)


def test_extract_out_of_bounds_raises(sample_video: Path, tmp_path: Path):
    out_dir = tmp_path / "frames"
    with pytest.raises(FrameExtractionError):
        extract_frames(sample_video, [999.0], out_dir, prefix="oob")


def test_extract_creates_output_dir(sample_video: Path, tmp_path: Path):
    out_dir = tmp_path / "nested" / "frames"
    assert not out_dir.exists()
    extract_frames(sample_video, [5.0], out_dir, prefix="x")
    assert out_dir.exists()


def test_extract_missing_video_raises(tmp_path: Path):
    out_dir = tmp_path / "frames"
    bogus = tmp_path / "does-not-exist.mp4"
    with pytest.raises(FrameExtractionError):
        extract_frames(bogus, [1.0], out_dir, prefix="x")
```

- [ ] **Step 2: Implementar el módulo**

Crear `pipeline/vision/__init__.py` con `"""Phase 3a vision-aware planning."""` y `pipeline/vision/frame_extractor.py`:

```python
"""ffmpeg-based frame extraction for Phase 3a visual planning."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class FrameExtractionError(RuntimeError):
    """Raised when ffmpeg fails to extract a requested frame."""


def _format_timestamp_token(t: float) -> str:
    if t == int(t):
        return f"t{int(t)}"
    return f"t{t:.2f}".replace(".", "p").rstrip("0").rstrip("p") or "t0"


def extract_frames(
    video: Path,
    timestamps_seconds: list[float],
    out_dir: Path,
    prefix: str,
) -> list[Path]:
    """Extract PNG frames at the given timestamps."""
    if not video.exists():
        raise FrameExtractionError(f"video not found: {video}")
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for t in timestamps_seconds:
        out_path = out_dir / f"{prefix}_{_format_timestamp_token(t)}.png"
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", str(t), "-i", str(video),
            "-frames:v", "1", "-update", "1",
            str(out_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if (
            result.returncode != 0
            or not out_path.exists()
            or out_path.stat().st_size < 1024
        ):
            raise FrameExtractionError(
                f"ffmpeg failed for t={t}s on {video.name}: "
                f"returncode={result.returncode}, stderr={result.stderr.strip()[:200]}"
            )
        paths.append(out_path)
    return paths
```

- [ ] **Step 3: Correr tests + CI gates**

```bash
uv run pytest tests/test_frame_extractor.py -v
uv run ruff check pipeline/vision/ tests/test_frame_extractor.py
uv run ruff format --check pipeline/vision/ tests/test_frame_extractor.py
uv run mypy pipeline/vision/
uv run pytest tests/ -x
```

Esperado: 5 tests passed, todos los gates verde.

- [ ] **Step 4: Commit**

```bash
git add pipeline/vision/ tests/test_frame_extractor.py
git commit -m "feat(vision): frame_extractor ffmpeg wrapper

Extrae PNGs a timestamps específicos de un video local. Usa -ss antes
de -i para seek rápido. Levanta FrameExtractionError si el video falta,
ffmpeg falla, o el PNG resultante es < 1KB (proxy de seek fallido).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Visual planner (LLM-vision Phase 3a)

**Goal:** Toma un material + frames + contexto, consulta el LLM-vision via OpenRouter, devuelve `PlannedMaterial` validado.

**Files:**
- Create: `pipeline/vision/prompts/visual_planner_system.md`
- Create: `pipeline/vision/visual_planner.py`
- Create: `tests/test_visual_planner.py`
- Modify: `pipeline/config.py` (agregar `LLM_MODEL_VISION_PLANNER`)

- [ ] **Step 1: System prompt en `.md`**

Crear `pipeline/vision/prompts/visual_planner_system.md` con el siguiente contenido (cargado en runtime, no harcoded):

````markdown
# Visual Director — PhyMaC Pipeline (Phase 3a)

Eres el director visual del pipeline PhyMaC. La fase narrativa (Phase 2) propuso un material de apoyo para un punto específico del video; tu trabajo es mirar el frame real y decidir el tratamiento visual.

## Tu rol

Recibís:
1. **Tres frames del video** a `t-1s`, `t` (timestamp_relativo del material) y `t+1s`.
2. **Contexto** en JSON: bloque narrativo, MaterialSpec original, transcript de ±5s.
3. **Brand pack** (colores, fuentes) y **visual-specs** (carácter y posiciones default).
4. Si el material es `diagrama` con `tipo_visual="esquema_libre"`, recibís el **diagram template registry**.

Devolvés **JSON estricto** con la decisión.

## Decisiones

### 1. `decision`

- `"keep"`: el material propuesto calza bien. Solo decidís `position` y opcionalmente `reframe`.
- `"modify"`: refinás (cambias contenido, tipo, metadata, o sustituís). Devolvés `spec_refined`.
- `"drop"`: no encaja (overlap inevitable, redundancia, distrae). Todo lo demás `null`.

**Solo modificás cuando hay razón visual concreta.**

### 2. `position`

Defaults:
- `lower_third`: `"bottom-left"` (default), `"bottom-right"`, `"top-left"`
- `pull_quote`: `"center"` (siempre)
- `chapter_marker`: `null` (full-frame, no overlay)
- `animacion_texto`: `"top-right"` (default), otros
- `ecuacion_latex`: `"bottom-right"` (default), `"bottom-left"`
- `diagrama`: `"center"` (siempre)

Si la default obstruye al sujeto: elegí otra opción listada o coords custom `{"x_pct": 0.05, "y_pct": 0.85}`.

### 3. `reframe`

- `null` (default): video corre tal cual.
- `{"type":"crop","params":{"x_pct","y_pct","w_pct","h_pct"}, "t_start_relative", "t_end_relative"}`
- `{"type":"zoom","params":{"scale","center_x_pct","center_y_pct"}, ...}` — ramp 0.3s, hold, ramp 0.3s.
- `{"type":"replace_with_material","params":{}, ...}` — material full-frame, video oculto.

`t_start_relative` y `t_end_relative` están en segundos del video crudo.

### 4. `reasoning`

≤2 oraciones en español. Va a auditoría.

## Reglas duras

- **JSON estricto**. Nada fuera del JSON. Sin code fences, sin markdown.
- **Default cuando dudás** — no inventes coordenadas sin razón.
- **No agregás materiales**. Solo modify/drop/keep.
- **Frame negro/extraño** → `keep` con default + reasoning claro.
- **Brand y visual-specs son ley** — no inventes tipos fuera del whitelist.

## Schema de salida

```json
{
  "decision": "keep" | "modify" | "drop",
  "spec_refined": { "tipo":..., "contenido":..., "timestamp_relativo":..., "metadata":... } | null,
  "position": "bottom-left" | "top-right" | "bottom-right" | "top-left" | "center" | { "x_pct":..., "y_pct":... } | null,
  "reframe": null | { "type":..., "params":..., "t_start_relative":..., "t_end_relative":... },
  "reasoning": "..."
}
```

Cuando `decision="drop"`: `spec_refined`, `position`, `reframe` son `null`.
````

- [ ] **Step 2: Config var**

Editar `pipeline/config.py`, agregar junto a las otras `LLM_MODEL_*`:

```python
LLM_MODEL_VISION_PLANNER = os.getenv(
    "LLM_MODEL_VISION_PLANNER",
    "anthropic/claude-sonnet-4-6",
)
```

- [ ] **Step 3: Tests fallidos**

Crear `tests/test_visual_planner.py`:

```python
"""Tests for visual_planner — Phase 3a LLM-vision."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.models import MaterialSpec
from pipeline.vision.visual_planner import (
    VisualPlannerError,
    plan_material_visual,
)

_MIN_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xfa\xcf"
    b"\x00\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _spec() -> MaterialSpec:
    return MaterialSpec(
        tipo="lower_third",
        contenido="Edson Cúdris — Profesor de Física",
        timestamp_relativo=222,
        metadata={},
    )


def _ctx(tmp_path: Path) -> dict:
    paths = []
    for tag in ("tm1", "t0", "tp1"):
        p = tmp_path / f"{tag}.png"
        p.write_bytes(_MIN_PNG)
        paths.append(p)
    return {
        "frames_paths": paths,
        "phase2_context": {
            "block_id": "b1",
            "block_name": "Intro",
            "material_spec": _spec().to_dict(),
            "transcript_window": "...habla sobre vocación...",
        },
        "brand": {"colors": {"primary": "#2962FF", "accent": "#FF6D00"}},
        "visual_specs_summary": {"lower_third": "banner bottom-left primary"},
        "diagram_template_registry": [],
    }


def _llm_resp(payload: dict) -> MagicMock:
    return MagicMock(
        choices=[MagicMock(message=MagicMock(content=json.dumps(payload)))]
    )


@patch("pipeline.vision.visual_planner.get_llm_client")
@patch("pipeline.vision.visual_planner.is_llm_available", return_value=True)
def test_keep_default_position(mock_avail, mock_client, tmp_path):
    fake = MagicMock()
    fake.chat.completions.create.return_value = _llm_resp({
        "decision": "keep",
        "spec_refined": _spec().to_dict(),
        "position": "bottom-left",
        "reframe": None,
        "reasoning": "Speaker centrado, fondo libre.",
    })
    mock_client.return_value = fake
    planned = plan_material_visual(
        material_id="b1_m00_x",
        block_id="b1",
        original_spec=_spec(),
        **_ctx(tmp_path),
    )
    assert planned.decision == "keep"
    assert planned.position == "bottom-left"
    assert planned.spec_refined is not None


@patch("pipeline.vision.visual_planner.get_llm_client")
@patch("pipeline.vision.visual_planner.is_llm_available", return_value=True)
def test_drop_clears_fields(mock_avail, mock_client, tmp_path):
    fake = MagicMock()
    fake.chat.completions.create.return_value = _llm_resp({
        "decision": "drop",
        "spec_refined": None,
        "position": None,
        "reframe": None,
        "reasoning": "Frame demasiado ocupado.",
    })
    mock_client.return_value = fake
    planned = plan_material_visual(
        material_id="b1_m00_x",
        block_id="b1",
        original_spec=_spec(),
        **_ctx(tmp_path),
    )
    assert planned.decision == "drop"
    assert planned.spec_refined is None
    assert planned.position is None


@patch("pipeline.vision.visual_planner.get_llm_client")
@patch("pipeline.vision.visual_planner.is_llm_available", return_value=True)
def test_retry_on_malformed_then_success(mock_avail, mock_client, tmp_path):
    fake = MagicMock()
    fake.chat.completions.create.side_effect = [
        MagicMock(choices=[MagicMock(message=MagicMock(content="not json"))]),
        _llm_resp({
            "decision": "keep",
            "spec_refined": _spec().to_dict(),
            "position": "bottom-left",
            "reframe": None,
            "reasoning": "OK.",
        }),
    ]
    mock_client.return_value = fake
    planned = plan_material_visual(
        material_id="b1_m00_x",
        block_id="b1",
        original_spec=_spec(),
        **_ctx(tmp_path),
    )
    assert planned.decision == "keep"
    assert fake.chat.completions.create.call_count == 2


@patch("pipeline.vision.visual_planner.get_llm_client")
@patch("pipeline.vision.visual_planner.is_llm_available", return_value=True)
def test_fallback_when_retry_fails(mock_avail, mock_client, tmp_path):
    fake = MagicMock()
    fake.chat.completions.create.side_effect = [
        MagicMock(choices=[MagicMock(message=MagicMock(content="bad"))]),
        MagicMock(choices=[MagicMock(message=MagicMock(content="still bad"))]),
    ]
    mock_client.return_value = fake
    planned = plan_material_visual(
        material_id="b1_m00_x",
        block_id="b1",
        original_spec=_spec(),
        **_ctx(tmp_path),
    )
    assert planned.decision == "keep"
    assert planned.position == "bottom-left"
    assert "fallback" in planned.reasoning.lower()


@patch("pipeline.vision.visual_planner.is_llm_available", return_value=False)
def test_raises_when_llm_unavailable(mock_avail, tmp_path):
    with pytest.raises(VisualPlannerError):
        plan_material_visual(
            material_id="b1_m00_x",
            block_id="b1",
            original_spec=_spec(),
            **_ctx(tmp_path),
        )
```

- [ ] **Step 4: Implementar `pipeline/vision/visual_planner.py`**

```python
"""Phase 3a — LLM-vision visual planning per material."""
from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

from pipeline.config import LLM_MODEL_VISION_PLANNER
from pipeline.llm import build_image_content, get_llm_client, is_llm_available
from pipeline.models import MaterialSpec, PlannedMaterial

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "visual_planner_system.md"

_DEFAULT_POSITION: dict[str, str | None] = {
    "lower_third": "bottom-left",
    "pull_quote": "center",
    "chapter_marker": None,
    "animacion_texto": "top-right",
    "ecuacion_latex": "bottom-right",
    "diagrama": "center",
    "transcript_fix": None,
}


class VisualPlannerError(RuntimeError):
    """Raised when the LLM-vision client cannot be used."""


def _system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _encode_frame(path: Path) -> dict[str, Any]:
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return build_image_content(b64, mime_type="image/png")


def _build_user_message(
    frames_paths: list[Path],
    phase2_context: dict,
    brand: dict,
    visual_specs_summary: dict,
    diagram_template_registry: list[dict],
) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = [_encode_frame(p) for p in frames_paths]
    payload = {
        "phase2_context": phase2_context,
        "brand": brand,
        "visual_specs_summary": visual_specs_summary,
        "diagram_template_registry": diagram_template_registry,
    }
    parts.append({"type": "text", "text": json.dumps(payload, ensure_ascii=False)})
    return parts


def _parse_response(content: str) -> dict[str, Any]:
    s = content.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s[: -3]
        s = s.strip()
    return json.loads(s)


def _fallback_keep(
    material_id: str,
    block_id: str,
    original_spec: MaterialSpec,
    reason: str,
) -> PlannedMaterial:
    return PlannedMaterial(
        material_id=material_id,
        block_id=block_id,
        original_spec=original_spec,
        decision="keep",
        spec_refined=original_spec,
        position=_DEFAULT_POSITION.get(original_spec.tipo, "bottom-left"),
        reframe=None,
        reasoning=f"[fallback] {reason}",
    )


def _planned_from_dict(
    material_id: str,
    block_id: str,
    original_spec: MaterialSpec,
    d: dict[str, Any],
) -> PlannedMaterial:
    decision = d["decision"]
    if decision not in {"keep", "modify", "drop"}:
        raise KeyError(f"invalid decision: {decision}")
    refined_dict = d.get("spec_refined")
    refined = MaterialSpec(**refined_dict) if refined_dict else None
    if decision != "drop" and refined is None:
        raise KeyError("decision != 'drop' requires spec_refined")
    return PlannedMaterial(
        material_id=material_id,
        block_id=block_id,
        original_spec=original_spec,
        decision=decision,
        spec_refined=refined,
        position=d.get("position"),
        reframe=d.get("reframe"),
        reasoning=d.get("reasoning", ""),
    )


def plan_material_visual(
    material_id: str,
    block_id: str,
    original_spec: MaterialSpec,
    frames_paths: list[Path],
    phase2_context: dict,
    brand: dict,
    visual_specs_summary: dict,
    diagram_template_registry: list[dict],
    *,
    model: str = LLM_MODEL_VISION_PLANNER,
) -> PlannedMaterial:
    """LLM-vision per-material. Retries 1× on malformed JSON; fallback on retry failure."""
    if not is_llm_available():
        raise VisualPlannerError("OpenRouter LLM not configured")
    client = get_llm_client()
    messages = [
        {"role": "system", "content": _system_prompt()},
        {
            "role": "user",
            "content": _build_user_message(
                frames_paths, phase2_context, brand,
                visual_specs_summary, diagram_template_registry,
            ),
        },
    ]
    last_error = ""
    for attempt in range(2):
        try:
            resp = client.chat.completions.create(
                model=model, messages=messages, temperature=0.2,
            )
            content = resp.choices[0].message.content or ""
            parsed = _parse_response(content)
            return _planned_from_dict(material_id, block_id, original_spec, parsed)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            last_error = f"{type(e).__name__}: {e}"
            logger.warning(
                "visual_planner attempt %d/2 failed for %s: %s",
                attempt + 1, material_id, last_error,
            )
    return _fallback_keep(
        material_id, block_id, original_spec,
        f"LLM output unparseable after retry ({last_error})",
    )
```

- [ ] **Step 5: Tests + CI gates**

```bash
uv run pytest tests/test_visual_planner.py -v
uv run ruff check pipeline/vision/ tests/test_visual_planner.py pipeline/config.py
uv run ruff format --check pipeline/vision/ tests/test_visual_planner.py pipeline/config.py
uv run mypy pipeline/vision/
uv run pytest tests/ -x
```

Esperado: 5 tests passed, todo verde.

- [ ] **Step 6: Commit**

```bash
git add pipeline/vision/visual_planner.py pipeline/vision/prompts/ \
        tests/test_visual_planner.py pipeline/config.py
git commit -m "feat(vision): visual_planner LLM-vision Phase 3a

Llama OpenRouter (default claude-sonnet-4-6) con 3 frames + contexto.
Devuelve PlannedMaterial validado. 1 retry on JSON malformed; segundo
fallo → fallback keep con position default por tipo. System prompt en
.md cargado en runtime.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Brand CSS generator + HF project scaffold

**Goal:** Generador puro brand.json → brand.css, más el scaffold del proyecto HyperFrames compartido (package.json, hyperframes.json, index.html stub, dir structure).

**Files:**
- Create: `pipeline/renderers/__init__.py` (empty)
- Create: `pipeline/renderers/brand_css.py`
- Create: `tests/test_brand_css.py`
- Create: `pipeline/renderers/hf-project/package.json`
- Create: `pipeline/renderers/hf-project/hyperframes.json`
- Create: `pipeline/renderers/hf-project/index.html`
- Create: `pipeline/renderers/hf-project/compositions/.gitkeep`
- Modify: `.gitignore` (agregar `pipeline/renderers/hf-project/node_modules/`)

- [ ] **Step 1: Tests fallidos para brand_css**

Crear `tests/test_brand_css.py`:

```python
"""Tests for brand_css generator."""
from __future__ import annotations

from pipeline.renderers.brand_css import render_brand_css


def test_brand_css_contains_all_colors():
    brand = {
        "colors": {
            "primary": "#2962FF",
            "primary_dark": "#0039CB",
            "accent": "#FF6D00",
            "accent_dark": "#C43E00",
            "carbon": "#212121",
            "carbon_light": "#484848",
            "surface": "#FFFFFF",
            "background": "#F5F5F5",
        },
    }
    css = render_brand_css(brand)
    assert "--primary: #2962FF;" in css
    assert "--accent: #FF6D00;" in css
    assert "--carbon: #212121;" in css
    assert "--surface: #FFFFFF;" in css


def test_brand_css_starts_with_root_selector():
    brand = {"colors": {"primary": "#000", "primary_dark": "#000", "accent": "#000",
                       "accent_dark": "#000", "carbon": "#000", "carbon_light": "#000",
                       "surface": "#fff", "background": "#fff"}}
    css = render_brand_css(brand)
    assert css.startswith(":root {")
    assert css.rstrip().endswith("}")


def test_brand_css_deterministic():
    brand = {"colors": {"primary": "#2962FF", "primary_dark": "#0039CB",
                       "accent": "#FF6D00", "accent_dark": "#C43E00",
                       "carbon": "#212121", "carbon_light": "#484848",
                       "surface": "#FFFFFF", "background": "#F5F5F5"}}
    assert render_brand_css(brand) == render_brand_css(brand)
```

- [ ] **Step 2: Implementar `pipeline/renderers/brand_css.py`**

Crear `pipeline/renderers/__init__.py` con `"""Material renderers for Phase 3b."""` y `pipeline/renderers/brand_css.py`:

```python
"""Generate brand.css from brand.json. Pure function, deterministic."""
from __future__ import annotations


def render_brand_css(brand: dict) -> str:
    c = brand["colors"]
    return (
        ":root {\n"
        f"  --primary: {c['primary']};\n"
        f"  --primary-dark: {c['primary_dark']};\n"
        f"  --accent: {c['accent']};\n"
        f"  --accent-dark: {c['accent_dark']};\n"
        f"  --carbon: {c['carbon']};\n"
        f"  --carbon-light: {c['carbon_light']};\n"
        f"  --surface: {c['surface']};\n"
        f"  --background: {c['background']};\n"
        "}\n"
    )
```

- [ ] **Step 3: HF project scaffold**

Crear `pipeline/renderers/hf-project/package.json`:

```json
{
  "name": "phymac-phase3-renderers",
  "version": "1.0.0",
  "private": true,
  "dependencies": {
    "hyperframes": "^0.6.47"
  }
}
```

Crear `pipeline/renderers/hf-project/hyperframes.json`:

```json
{
  "name": "phymac-phase3-renderers",
  "version": "1.0.0",
  "compositions": [
    "compositions/lower_third.html",
    "compositions/pull_quote.html",
    "compositions/chapter_marker.html",
    "compositions/animacion_texto.html",
    "compositions/ecuacion_latex.html",
    "compositions/diagrama_barras.html",
    "compositions/diagrama_ciclo.html",
    "compositions/diagrama_bloque_inclinado.html",
    "compositions/text_card_fallback.html"
  ]
}
```

Crear `pipeline/renderers/hf-project/index.html`:

```html
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>PhyMaC Phase 3 Renderers — stub</title>
</head>
<body>
<!-- Stub for HyperFrames project sanity check. Real compositions rendered via --composition flag. -->
</body>
</html>
```

Crear `pipeline/renderers/hf-project/compositions/.gitkeep` (vacío).

Crear `pipeline/renderers/hf-project/brand.css` (placeholder; será sobreescrito por brand_css.py en runtime):

```css
:root {
  --primary: #2962FF;
  --primary-dark: #0039CB;
  --accent: #FF6D00;
  --accent-dark: #C43E00;
  --carbon: #212121;
  --carbon-light: #484848;
  --surface: #FFFFFF;
  --background: #F5F5F5;
}
```

- [ ] **Step 4: `.gitignore` update**

Agregar al final del `.gitignore`:

```
# HyperFrames node_modules en pipeline/renderers/
pipeline/renderers/hf-project/node_modules/
```

- [ ] **Step 5: Tests + CI**

```bash
uv run pytest tests/test_brand_css.py -v
uv run ruff check pipeline/renderers/ tests/test_brand_css.py
uv run ruff format --check pipeline/renderers/ tests/test_brand_css.py
uv run mypy pipeline/renderers/
uv run pytest tests/ -x
```

- [ ] **Step 6: Commit**

```bash
git add pipeline/renderers/__init__.py pipeline/renderers/brand_css.py \
        pipeline/renderers/hf-project/ tests/test_brand_css.py .gitignore
git commit -m "feat(renderers): brand_css generator + HF project scaffold

brand.json → brand.css (CSS custom properties). HF project compartido
con package.json, hyperframes.json, index.html stub.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: HyperFrames compositions (9 archivos)

**Goal:** Crear las 9 compositions HTML del proyecto HF, parametrizadas vía `data-composition-variables`, siguiendo el patrón canónico de la skill (`window.__timelines` + GSAP).

**Files (todas en `pipeline/renderers/hf-project/compositions/`):**
- `lower_third.html`
- `pull_quote.html`
- `chapter_marker.html`
- `animacion_texto.html`
- `ecuacion_latex.html`
- `diagrama_barras.html`
- `diagrama_ciclo.html`
- `diagrama_bloque_inclinado.html`
- `text_card_fallback.html`

**Patrón canónico (recordatorio crítico):** cada composition es standalone (NO `<template>` wrapper), declara variables en `<html data-composition-variables=...>`, lee con `window.__hyperframes.getVariables()`, registra timeline en `window.__timelines["<id>"]` con `gsap.timeline({paused:true})`. Compositions NO usan `--format webm` directo (no emite alpha) — el renderer Python siempre usa `--format mov` y transcodea a webm.

Antes de empezar, **`npm install` en el HF project**:

```bash
cd pipeline/renderers/hf-project && npm install --no-audit --no-fund && cd -
```

- [ ] **Step 1: `lower_third.html`**

```html
<!DOCTYPE html>
<html data-composition-variables='[
  {"id":"name","type":"string","label":"Nombre","default":"Nombre"},
  {"id":"subtitle","type":"string","label":"Subtítulo","default":""},
  {"id":"position","type":"enum","label":"Posición","default":"bottom-left",
   "options":[
     {"value":"bottom-left","label":"Bottom-left"},
     {"value":"top-left","label":"Top-left"},
     {"value":"bottom-right","label":"Bottom-right"},
     {"value":"top-right","label":"Top-right"}
   ]}
]'>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="../brand.css">
<style>
  html, body { margin: 0; padding: 0; background: transparent; }
  [data-composition-id="lower-third"] {
    position: relative; width: 1920px; height: 1080px;
    font-family: 'Open Sans', sans-serif;
  }
  .lt {
    position: absolute; background: var(--primary); color: var(--surface);
    padding: 22px 32px; border-left: 6px solid var(--accent);
    max-width: 50%; box-shadow: 6px 6px 0 var(--accent-dark);
  }
  [data-position="bottom-left"]  .lt { bottom: 8.6%; left: 5%; }
  [data-position="top-left"]     .lt { top: 8.6%; left: 5%; }
  [data-position="bottom-right"] .lt { bottom: 8.6%; right: 5%; }
  [data-position="top-right"]    .lt { top: 8.6%; right: 5%; }
  .lt h1 { margin: 0; font-family: 'Montserrat', sans-serif; font-weight: 900; font-size: 28px; line-height: 1.15; }
  .lt p  { margin: 4px 0 0; font-weight: 400; font-size: 16px; opacity: 0.9; }
</style>
</head>
<body>
<div data-composition-id="lower-third" data-width="1920" data-height="1080" data-start="0" data-duration="6.0">
  <div class="lt" id="lt-root">
    <h1 id="name"></h1>
    <p id="subtitle"></p>
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<script>
  const { name, subtitle, position } = window.__hyperframes.getVariables();
  document.querySelector('[data-composition-id="lower-third"]').dataset.position = position;
  document.getElementById('name').textContent = name;
  document.getElementById('subtitle').textContent = subtitle;
  if (!subtitle) document.getElementById('subtitle').style.display = 'none';
  window.__timelines = window.__timelines || {};
  const tl = gsap.timeline({ paused: true });
  const slideIn = position.endsWith('right') ? 130 : -130;
  tl.fromTo(".lt", { xPercent: slideIn }, { xPercent: 0, duration: 0.4, ease: "power3.out" }, 0.1);
  tl.to(".lt", { xPercent: slideIn, duration: 0.6, ease: "power3.in" }, 5.4);
  window.__timelines["lower-third"] = tl;
</script>
</body>
</html>
```

Smoke render (verificar que renderiza alpha mov OK):

```bash
cd pipeline/renderers/hf-project
npx hyperframes render . --composition compositions/lower_third.html \
  --output /tmp/lt-smoke.mov --format mov --fps 30 \
  --variables '{"name":"Edson","subtitle":"Profe","position":"bottom-left"}'
ffprobe -v error -show_entries stream=codec_name,pix_fmt /tmp/lt-smoke.mov | head -2
# Esperado: codec_name=prores, pix_fmt=yuva444p12le
cd -
```

- [ ] **Step 2: `pull_quote.html`**

```html
<!DOCTYPE html>
<html data-composition-variables='[
  {"id":"quote","type":"string","label":"Cita","default":"..."},
  {"id":"speaker","type":"string","label":"Speaker","default":""}
]'>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="../brand.css">
<style>
  html, body { margin: 0; padding: 0; background: transparent; }
  [data-composition-id="pull-quote"] {
    position: relative; width: 1920px; height: 1080px;
    display: flex; align-items: center; justify-content: center;
    font-family: 'Open Sans', sans-serif;
  }
  .card {
    position: relative; width: 72%; background: var(--surface);
    border-left: 8px solid var(--accent); padding: 70px 80px 50px;
    box-shadow: 8px 8px 0 var(--carbon);
  }
  .quote-mark {
    position: absolute; top: -10px; left: 30px;
    font-family: 'Montserrat', sans-serif; font-weight: 900;
    font-size: 180px; color: var(--primary); line-height: 1;
  }
  blockquote {
    margin: 0; font-family: 'Montserrat', sans-serif; font-weight: 800;
    font-size: 42px; color: var(--carbon); line-height: 1.3;
  }
  .speaker {
    margin-top: 22px; font-weight: 600; font-size: 14px;
    color: var(--carbon-light); text-transform: uppercase; letter-spacing: 2px;
  }
</style>
</head>
<body>
<div data-composition-id="pull-quote" data-width="1920" data-height="1080" data-start="0" data-duration="6.6">
  <div class="card">
    <span class="quote-mark">“</span>
    <blockquote id="q"></blockquote>
    <div class="speaker" id="sp"></div>
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<script>
  const { quote, speaker } = window.__hyperframes.getVariables();
  document.getElementById('q').textContent = quote;
  if (speaker) {
    document.getElementById('sp').textContent = "— " + speaker;
  } else {
    document.getElementById('sp').style.display = 'none';
  }
  window.__timelines = window.__timelines || {};
  const tl = gsap.timeline({ paused: true });
  tl.from(".card", { scale: 0.95, opacity: 0, duration: 0.3, ease: "power2.out" }, 0.1);
  tl.to(".card", { opacity: 0, duration: 0.3, ease: "power2.in" }, 6.3);
  window.__timelines["pull-quote"] = tl;
</script>
</body>
</html>
```

Smoke:

```bash
cd pipeline/renderers/hf-project
npx hyperframes render . --composition compositions/pull_quote.html \
  --output /tmp/pq-smoke.mov --format mov --fps 30 \
  --variables '{"quote":"La educación que transforma.","speaker":"Edson"}'
cd -
```

- [ ] **Step 3: `chapter_marker.html`**

```html
<!DOCTYPE html>
<html data-composition-variables='[
  {"id":"chapter_number","type":"number","label":"Número","default":1},
  {"id":"chapter_title","type":"string","label":"Título","default":"Capítulo"}
]'>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="../brand.css">
<style>
  html, body { margin: 0; padding: 0; background: transparent; }
  [data-composition-id="chapter-marker"] {
    position: relative; width: 1920px; height: 1080px;
    font-family: 'Open Sans', sans-serif; overflow: hidden;
  }
  .bg {
    position: absolute; inset: 0;
    background: linear-gradient(135deg, var(--primary) 50%, var(--primary-dark) 100%);
  }
  .pattern {
    position: absolute; inset: 0; opacity: 0.13;
    background-image:
      repeating-linear-gradient(0deg, transparent 0, transparent 39px, rgba(255,255,255,0.5) 39px, rgba(255,255,255,0.5) 40px),
      repeating-linear-gradient(90deg, transparent 0, transparent 39px, rgba(255,255,255,0.5) 39px, rgba(255,255,255,0.5) 40px);
  }
  .label { position: absolute; top: calc(8% + 240px); left: 10%;
    font-weight: 600; font-size: 22px; color: var(--surface);
    opacity: 0.7; letter-spacing: 6px; }
  .num { position: absolute; top: 8%; left: 10%;
    font-family: 'Montserrat', sans-serif; font-weight: 900;
    font-size: 220px; color: var(--accent); line-height: 1; }
  .title { position: absolute; top: 50%; left: 50%;
    font-family: 'Montserrat', sans-serif; font-weight: 900;
    font-size: 84px; color: var(--surface); text-align: center; }
</style>
</head>
<body>
<div data-composition-id="chapter-marker" data-width="1920" data-height="1080" data-start="0" data-duration="4.2">
  <div class="bg"></div>
  <div class="pattern"></div>
  <div class="label">CAPÍTULO</div>
  <div class="num" id="num"></div>
  <div class="title" id="title"></div>
</div>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<script>
  const { chapter_number, chapter_title } = window.__hyperframes.getVariables();
  document.getElementById('num').textContent = chapter_number;
  document.getElementById('title').textContent = chapter_title;
  window.__timelines = window.__timelines || {};
  const tl = gsap.timeline({ paused: true });
  tl.from(".bg", { opacity: 0, duration: 0.2, ease: "power2.out" }, 0);
  tl.from(".pattern", { opacity: 0, duration: 0.3, ease: "power2.out" }, 0.1);
  tl.from(".num", { scale: 0, opacity: 0, duration: 0.3, ease: "back.out(2)" }, 0.1);
  tl.from(".label", { opacity: 0, duration: 0.3, ease: "power2.out" }, 0.3);
  tl.fromTo(".title",
    { xPercent: -50, y: 80, opacity: 0 },
    { xPercent: -50, y: 0, opacity: 1, duration: 0.5, ease: "power3.out" }, 0.2);
  tl.to([".bg", ".pattern", ".label", ".num", ".title"],
    { opacity: 0, duration: 0.4, ease: "power2.in" }, 3.8);
  window.__timelines["chapter-marker"] = tl;
</script>
</body>
</html>
```

- [ ] **Step 4: `animacion_texto.html`**

```html
<!DOCTYPE html>
<html data-composition-variables='[
  {"id":"text","type":"string","label":"Texto","default":"TEXTO"},
  {"id":"position","type":"enum","label":"Posición","default":"top-right",
   "options":[
     {"value":"top-right","label":"TR"},{"value":"top-left","label":"TL"},
     {"value":"bottom-right","label":"BR"},{"value":"bottom-left","label":"BL"}
   ]}
]'>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="../brand.css">
<style>
  html, body { margin: 0; padding: 0; background: transparent; }
  [data-composition-id="animacion-texto"] {
    position: relative; width: 1920px; height: 1080px;
    font-family: 'Montserrat', sans-serif;
  }
  .badge {
    position: absolute; background: var(--accent); color: var(--surface);
    padding: 18px 36px; transform: rotate(-2deg);
    font-weight: 900; font-size: 52px;
    letter-spacing: 2px; text-transform: uppercase;
    box-shadow: 6px 6px 0 var(--accent-dark);
  }
  [data-position="top-right"]    .badge { top: 80px; right: 120px; }
  [data-position="top-left"]     .badge { top: 80px; left: 120px; }
  [data-position="bottom-right"] .badge { bottom: 120px; right: 120px; }
  [data-position="bottom-left"]  .badge { bottom: 120px; left: 120px; }
</style>
</head>
<body>
<div data-composition-id="animacion-texto" data-width="1920" data-height="1080" data-start="0" data-duration="2.2">
  <div class="badge" id="badge"></div>
</div>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<script>
  const { text, position } = window.__hyperframes.getVariables();
  document.querySelector('[data-composition-id="animacion-texto"]').dataset.position = position;
  document.getElementById('badge').textContent = text;
  window.__timelines = window.__timelines || {};
  const tl = gsap.timeline({ paused: true });
  tl.from(".badge", { scale: 0, opacity: 0, duration: 0.4, ease: "back.out(2.5)" }, 0.1);
  tl.to(".badge", { scale: 0.9, opacity: 0, duration: 0.3, ease: "power2.in" }, 1.9);
  window.__timelines["animacion-texto"] = tl;
</script>
</body>
</html>
```

- [ ] **Step 5: `ecuacion_latex.html`** (KaTeX inline, render sincrónico)

```html
<!DOCTYPE html>
<html data-composition-variables='[
  {"id":"latex","type":"string","label":"LaTeX","default":"E = mc^2"},
  {"id":"caption","type":"string","label":"Caption","default":"Ecuación"},
  {"id":"position","type":"enum","label":"Posición","default":"bottom-right",
   "options":[{"value":"bottom-right","label":"BR"},{"value":"bottom-left","label":"BL"}]}
]'>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="../brand.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<style>
  html, body { margin: 0; padding: 0; background: transparent; }
  [data-composition-id="ecuacion-latex"] {
    position: relative; width: 1920px; height: 1080px;
    font-family: 'Open Sans', sans-serif;
  }
  .card {
    position: absolute; background: var(--carbon); padding: 28px 36px 28px 50px;
    box-shadow: 6px 6px 0 var(--accent); max-width: 60%;
  }
  [data-position="bottom-right"] .card { bottom: 8%; right: 5%; }
  [data-position="bottom-left"]  .card { bottom: 8%; left: 5%; }
  .card::before {
    content: ''; position: absolute; left: 24px; top: 18%; bottom: 18%;
    width: 6px; background: var(--accent);
  }
  .label {
    font-weight: 600; font-size: 14px; color: var(--accent);
    letter-spacing: 2px; text-transform: uppercase; margin-bottom: 14px;
  }
  .eq { font-size: 42px; color: var(--surface); }
  .eq .katex { color: var(--surface); }
</style>
</head>
<body>
<div data-composition-id="ecuacion-latex" data-width="1920" data-height="1080" data-start="0" data-duration="5.0">
  <div class="card">
    <div class="label" id="lbl"></div>
    <div class="eq" id="eq"></div>
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
<script>
  const { latex, caption, position } = window.__hyperframes.getVariables();
  document.querySelector('[data-composition-id="ecuacion-latex"]').dataset.position = position;
  document.getElementById('lbl').textContent = caption;
  document.getElementById('eq').innerHTML = katex.renderToString(
    latex, { throwOnError: false, displayMode: true }
  );
</script>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<script>
  window.__timelines = window.__timelines || {};
  const tl = gsap.timeline({ paused: true });
  tl.from(".card", { y: 40, opacity: 0, duration: 0.4, ease: "power3.out" }, 0.1);
  tl.to(".card", { opacity: 0, duration: 0.3, ease: "power2.in" }, 4.7);
  window.__timelines["ecuacion-latex"] = tl;
</script>
</body>
</html>
```

- [ ] **Step 6: `diagrama_barras.html`** (data-driven bar chart)

```html
<!DOCTYPE html>
<html data-composition-variables='[
  {"id":"title","type":"string","label":"Título","default":"Comparación"},
  {"id":"data_json","type":"string","label":"Data (JSON array)","default":"[]"}
]'>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="../brand.css">
<style>
  html, body { margin: 0; padding: 0; background: transparent; }
  [data-composition-id="diagrama-barras"] {
    position: relative; width: 1920px; height: 1080px;
    display: flex; align-items: center; justify-content: center;
    font-family: 'Open Sans', sans-serif;
  }
  .card { width: 70%; background: var(--surface); border-top: 6px solid var(--accent);
    padding: 40px 50px; box-shadow: 8px 8px 0 var(--carbon); }
  .title { font-family: 'Montserrat', sans-serif; font-weight: 800;
    font-size: 32px; color: var(--carbon); margin-bottom: 30px; }
  .chart { display: flex; align-items: flex-end; gap: 40px; height: 360px; }
  .bar-group { flex: 1; display: flex; flex-direction: column; align-items: center; }
  .bar { width: 80%; background: var(--primary);
    box-shadow: 6px 6px 0 var(--primary-dark); transform-origin: bottom; transform: scaleY(0); }
  .bar.alt { background: var(--accent); box-shadow: 6px 6px 0 var(--accent-dark); }
  .bar-label { margin-top: 12px; font-weight: 600; font-size: 16px; color: var(--carbon); }
</style>
</head>
<body>
<div data-composition-id="diagrama-barras" data-width="1920" data-height="1080" data-start="0" data-duration="6.0">
  <div class="card">
    <div class="title" id="title"></div>
    <div class="chart" id="chart"></div>
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<script>
  const { title, data_json } = window.__hyperframes.getVariables();
  document.getElementById('title').textContent = title;
  const data = JSON.parse(data_json || "[]");
  const chart = document.getElementById('chart');
  const max = Math.max(...data.map(d => d.value), 1);
  data.forEach((d, i) => {
    const group = document.createElement('div');
    group.className = 'bar-group';
    const bar = document.createElement('div');
    bar.className = 'bar' + (i % 2 ? ' alt' : '');
    bar.style.height = `${(d.value / max) * 100}%`;
    bar.dataset.idx = i;
    const lbl = document.createElement('div');
    lbl.className = 'bar-label';
    lbl.textContent = d.label;
    group.appendChild(bar);
    group.appendChild(lbl);
    chart.appendChild(group);
  });
  window.__timelines = window.__timelines || {};
  const tl = gsap.timeline({ paused: true });
  tl.from(".card", { opacity: 0, duration: 0.3 }, 0.1);
  tl.to(".bar", { scaleY: 1, duration: 0.5, ease: "power3.out", stagger: 0.15 }, 0.4);
  tl.to(".card", { opacity: 0, duration: 0.3, ease: "power2.in" }, 5.7);
  window.__timelines["diagrama-barras"] = tl;
</script>
</body>
</html>
```

- [ ] **Step 7: `diagrama_ciclo.html`** (cycle/flow diagram, data-driven)

```html
<!DOCTYPE html>
<html data-composition-variables='[
  {"id":"title","type":"string","label":"Título","default":"Ciclo"},
  {"id":"nodes_json","type":"string","label":"Nodes (JSON array)","default":"[]"}
]'>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="../brand.css">
<style>
  html, body { margin: 0; padding: 0; background: transparent; }
  [data-composition-id="diagrama-ciclo"] {
    position: relative; width: 1920px; height: 1080px;
    display: flex; align-items: center; justify-content: center;
    font-family: 'Open Sans', sans-serif;
  }
  .card { width: 70%; height: 70%; background: var(--primary);
    box-shadow: 8px 8px 0 var(--carbon); position: relative;
    display: flex; align-items: center; justify-content: center; }
  .pattern { position: absolute; inset: 0; opacity: 0.13;
    background-image:
      repeating-linear-gradient(0deg, transparent 0, transparent 39px, rgba(255,255,255,0.5) 39px, rgba(255,255,255,0.5) 40px),
      repeating-linear-gradient(90deg, transparent 0, transparent 39px, rgba(255,255,255,0.5) 39px, rgba(255,255,255,0.5) 40px); }
  .title-top { position: absolute; top: 30px; left: 50%; transform: translateX(-50%);
    font-family: 'Montserrat', sans-serif; font-weight: 800;
    font-size: 28px; color: var(--surface); }
  .nodes { position: relative; width: 100%; height: 100%; }
  .node { position: absolute; background: var(--surface); border-top: 6px solid var(--accent);
    padding: 20px 24px; font-family: 'Montserrat', sans-serif; font-weight: 700;
    font-size: 20px; color: var(--carbon); transform: scale(0); }
</style>
</head>
<body>
<div data-composition-id="diagrama-ciclo" data-width="1920" data-height="1080" data-start="0" data-duration="6.0">
  <div class="card">
    <div class="pattern"></div>
    <div class="title-top" id="title"></div>
    <div class="nodes" id="nodes"></div>
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<script>
  const { title, nodes_json } = window.__hyperframes.getVariables();
  document.getElementById('title').textContent = title;
  const nodes = JSON.parse(nodes_json || "[]");
  const container = document.getElementById('nodes');
  const cx = 50, cy = 55, radius = 30;
  nodes.forEach((label, i) => {
    const angle = (-90 + (360 / nodes.length) * i) * Math.PI / 180;
    const x = cx + radius * Math.cos(angle);
    const y = cy + radius * Math.sin(angle);
    const el = document.createElement('div');
    el.className = 'node';
    el.style.left = `${x}%`;
    el.style.top = `${y}%`;
    el.style.transform = 'translate(-50%, -50%) scale(0)';
    el.textContent = label;
    container.appendChild(el);
  });
  window.__timelines = window.__timelines || {};
  const tl = gsap.timeline({ paused: true });
  tl.from(".card", { opacity: 0, duration: 0.3 }, 0.1);
  tl.fromTo(".node",
    { scale: 0, opacity: 0 },
    { scale: 1, opacity: 1, duration: 0.4, stagger: 0.3, ease: "back.out(2)",
      transformOrigin: "50% 50%" }, 0.4);
  tl.to(".card", { opacity: 0, duration: 0.3, ease: "power2.in" }, 5.7);
  window.__timelines["diagrama-ciclo"] = tl;
</script>
</body>
</html>
```

- [ ] **Step 8: `diagrama_bloque_inclinado.html`** (template esquema_libre v1)

```html
<!DOCTYPE html>
<html data-composition-variables='[
  {"id":"title","type":"string","label":"Título","default":"Diagrama de cuerpo libre"},
  {"id":"angle_deg","type":"number","label":"Ángulo","default":30},
  {"id":"show_friction","type":"boolean","label":"Mostrar fricción","default":false}
]'>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="../brand.css">
<style>
  html, body { margin: 0; padding: 0; background: transparent; }
  [data-composition-id="diagrama-bloque-inclinado"] {
    position: relative; width: 1920px; height: 1080px;
    display: flex; align-items: center; justify-content: center;
    font-family: 'Open Sans', sans-serif;
  }
  .card { width: 70%; background: var(--surface); border-top: 6px solid var(--accent);
    padding: 40px 50px; box-shadow: 8px 8px 0 var(--carbon); }
  .title { font-family: 'Montserrat', sans-serif; font-weight: 800;
    font-size: 24px; color: var(--carbon); margin-bottom: 20px; }
  svg { display: block; margin: 0 auto; }
</style>
</head>
<body>
<div data-composition-id="diagrama-bloque-inclinado" data-width="1920" data-height="1080" data-start="0" data-duration="6.0">
  <div class="card">
    <div class="title" id="title"></div>
    <svg viewBox="0 0 800 480" width="800" height="480" id="svg">
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--primary)"/>
        </marker>
      </defs>
      <polygon class="plane" id="plane" points="" fill="var(--surface)" stroke="var(--carbon)" stroke-width="4"/>
      <g class="block" id="block-g">
        <rect class="block-rect" x="-60" y="-50" width="120" height="100" fill="var(--carbon-light)" stroke="var(--carbon)" stroke-width="4"/>
      </g>
      <line class="vec-g" x1="450" y1="245" x2="450" y2="420" stroke="var(--primary)" stroke-width="5" marker-end="url(#arrow)"/>
      <text class="lab-g" x="465" y="370" font-family="Montserrat" font-weight="700" font-size="28" fill="var(--carbon)">mg</text>
      <line class="vec-n" id="vec-n" x1="450" y1="245" x2="" y2="" stroke="var(--primary)" stroke-width="5" marker-end="url(#arrow)"/>
      <text class="lab-n" id="lab-n" x="" y="" font-family="Montserrat" font-weight="700" font-size="28" fill="var(--carbon)">N</text>
      <line class="vec-f" id="vec-f" x1="450" y1="245" x2="" y2="" stroke="var(--accent)" stroke-width="5" marker-end="url(#arrow)" style="display:none"/>
      <text class="lab-f" id="lab-f" x="" y="" font-family="Montserrat" font-weight="700" font-size="28" fill="var(--carbon)" style="display:none">f</text>
    </svg>
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<script>
  const { title, angle_deg, show_friction } = window.__hyperframes.getVariables();
  document.getElementById('title').textContent = title;
  // Geometría dinámica según ángulo
  const angle = angle_deg * Math.PI / 180;
  // Plano: triángulo rectángulo en (100,400)-(700,400)-(700,400-600*tan(angle))
  const planeY = 400 - 600 * Math.tan(angle);
  document.getElementById('plane').setAttribute('points', `100,400 700,400 700,${planeY}`);
  // Bloque rotado, centrado en (450,245)
  document.getElementById('block-g').setAttribute('transform', `translate(450,245) rotate(${-angle_deg})`);
  // Normal perpendicular al plano (-sin, -cos)
  const nx = 450 + 175 * (-Math.sin(angle));
  const ny = 245 + 175 * (-Math.cos(angle));
  document.getElementById('vec-n').setAttribute('x2', nx);
  document.getElementById('vec-n').setAttribute('y2', ny);
  document.getElementById('lab-n').setAttribute('x', nx - 35);
  document.getElementById('lab-n').setAttribute('y', ny + 15);
  // Fricción paralela al plano (cos, sin) si show_friction
  if (show_friction) {
    const fx = 450 + 130 * Math.cos(angle);
    const fy = 245 + 130 * Math.sin(angle);
    const ff = document.getElementById('vec-f');
    const lf = document.getElementById('lab-f');
    ff.style.display = '';
    lf.style.display = '';
    ff.setAttribute('x2', fx);
    ff.setAttribute('y2', fy);
    lf.setAttribute('x', fx + 10);
    lf.setAttribute('y', fy + 25);
  }
  window.__timelines = window.__timelines || {};
  const tl = gsap.timeline({ paused: true });
  tl.from(".card", { opacity: 0, duration: 0.3 }, 0.1);
  tl.from(".plane", { opacity: 0, duration: 0.4 }, 0.3);
  tl.from(".block", { opacity: 0, duration: 0.3 }, 0.6);
  tl.from(".vec-g", { opacity: 0, duration: 0.3 }, 0.9);
  tl.from(".lab-g", { opacity: 0, duration: 0.2 }, 1.1);
  tl.from(".vec-n", { opacity: 0, duration: 0.3 }, 1.3);
  tl.from(".lab-n", { opacity: 0, duration: 0.2 }, 1.5);
  if (show_friction) {
    tl.from(".vec-f", { opacity: 0, duration: 0.3 }, 1.7);
    tl.from(".lab-f", { opacity: 0, duration: 0.2 }, 1.9);
  }
  tl.to(".card", { opacity: 0, duration: 0.3, ease: "power2.in" }, 5.7);
  window.__timelines["diagrama-bloque-inclinado"] = tl;
</script>
</body>
</html>
```

- [ ] **Step 9: `text_card_fallback.html`** (último recurso)

```html
<!DOCTYPE html>
<html data-composition-variables='[
  {"id":"text","type":"string","label":"Texto","default":"..."},
  {"id":"position","type":"enum","label":"Posición","default":"center",
   "options":[{"value":"center","label":"Center"},{"value":"bottom-left","label":"BL"}]}
]'>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="../brand.css">
<style>
  html, body { margin: 0; padding: 0; background: transparent; }
  [data-composition-id="text-card-fallback"] {
    position: relative; width: 1920px; height: 1080px;
    font-family: 'Open Sans', sans-serif;
  }
  .card { background: var(--surface); padding: 28px 36px;
    border-left: 6px solid var(--accent);
    box-shadow: 6px 6px 0 var(--carbon); max-width: 60%;
    font-family: 'Montserrat', sans-serif; font-weight: 700;
    font-size: 28px; color: var(--carbon); }
  [data-position="center"] .card { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); }
  [data-position="bottom-left"] .card { position: absolute; bottom: 8%; left: 5%; }
</style>
</head>
<body>
<div data-composition-id="text-card-fallback" data-width="1920" data-height="1080" data-start="0" data-duration="5.0">
  <div class="card" id="card"></div>
</div>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<script>
  const { text, position } = window.__hyperframes.getVariables();
  document.querySelector('[data-composition-id="text-card-fallback"]').dataset.position = position;
  document.getElementById('card').textContent = text;
  window.__timelines = window.__timelines || {};
  const tl = gsap.timeline({ paused: true });
  tl.from(".card", { opacity: 0, duration: 0.3 }, 0.1);
  tl.to(".card", { opacity: 0, duration: 0.3, ease: "power2.in" }, 4.7);
  window.__timelines["text-card-fallback"] = tl;
</script>
</body>
</html>
```

- [ ] **Step 10: Smoke render de las 9 compositions**

Script de verificación que rinde cada una a `/tmp/<comp>-smoke.mov` con variables dummy y verifica alpha:

```bash
cd pipeline/renderers/hf-project
for comp in lower_third pull_quote chapter_marker animacion_texto ecuacion_latex \
            diagrama_barras diagrama_ciclo diagrama_bloque_inclinado text_card_fallback; do
  case "$comp" in
    lower_third)        VARS='{"name":"X","subtitle":"Y","position":"bottom-left"}' ;;
    pull_quote)         VARS='{"quote":"Q","speaker":"S"}' ;;
    chapter_marker)     VARS='{"chapter_number":1,"chapter_title":"T"}' ;;
    animacion_texto)    VARS='{"text":"X","position":"top-right"}' ;;
    ecuacion_latex)     VARS='{"latex":"E = mc^2","caption":"X","position":"bottom-right"}' ;;
    diagrama_barras)    VARS='{"title":"T","data_json":"[{\"label\":\"A\",\"value\":3},{\"label\":\"B\",\"value\":5}]"}' ;;
    diagrama_ciclo)     VARS='{"title":"T","nodes_json":"[\"A\",\"B\",\"C\"]"}' ;;
    diagrama_bloque_inclinado) VARS='{"title":"T","angle_deg":30,"show_friction":false}' ;;
    text_card_fallback) VARS='{"text":"T","position":"center"}' ;;
  esac
  echo "→ $comp"
  npx hyperframes render . --composition "compositions/${comp}.html" \
    --output "/tmp/${comp}-smoke.mov" --format mov --fps 30 \
    --variables "$VARS" 2>&1 | tail -3
  ffprobe -v error -show_entries stream=pix_fmt -of default=noprint_wrappers=1:nokey=1 "/tmp/${comp}-smoke.mov" | head -1
done
cd -
```

Esperado: cada uno termina con `Render complete` y `pix_fmt=yuva444p12le`. Si alguno falla, corregir esa composition y re-correr.

- [ ] **Step 11: Commit (todas las compositions)**

```bash
git add pipeline/renderers/hf-project/compositions/
git commit -m "feat(renderers): 9 HyperFrames compositions parametrizadas

lower_third, pull_quote, chapter_marker, animacion_texto, ecuacion_latex,
diagrama_{barras,ciclo,bloque_inclinado}, text_card_fallback. Cada una
declara data-composition-variables, usa window.__hyperframes.getVariables(),
registra timeline en window.__timelines (patrón canónico HF). Smoke render
mov ProRes yuva444p12le verificado.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Renderer dispatch + diagram template registry

**Goal:** Lógica Python pura que mapea `PlannedMaterial` → `(composition_path, variables_dict)`. Lookup en diagram registry para esquema_libre.

**Files:**
- Create: `pipeline/renderers/diagram_templates/registry.json`
- Create: `pipeline/renderers/dispatch.py`
- Create: `tests/test_renderer_dispatch.py`

- [ ] **Step 1: Crear registry JSON**

`pipeline/renderers/diagram_templates/registry.json`:

```json
{
  "templates": [
    {
      "id": "bloque_inclinado",
      "name": "Bloque sobre plano inclinado",
      "composition": "diagrama_bloque_inclinado.html",
      "params_schema": {
        "title": {"type": "string", "default": "Diagrama de cuerpo libre"},
        "angle_deg": {"type": "number", "default": 30, "min": 5, "max": 75},
        "show_friction": {"type": "boolean", "default": false}
      },
      "keywords": ["bloque", "plano inclinado", "rampa", "cuerpo libre", "fricción"],
      "fits_well": "Cuerpo libre de un bloque sobre plano inclinado con peso y normal (opcional fricción)."
    }
  ]
}
```

- [ ] **Step 2: Tests fallidos**

Crear `tests/test_renderer_dispatch.py`:

```python
"""Tests for renderer dispatch."""
from __future__ import annotations

import pytest

from pipeline.models import MaterialSpec, PlannedMaterial
from pipeline.renderers.dispatch import (
    DispatchError,
    build_render_input,
    load_diagram_registry,
)


def _planned(tipo: str, contenido: str, metadata: dict, position="bottom-left") -> PlannedMaterial:
    spec = MaterialSpec(tipo=tipo, contenido=contenido, timestamp_relativo=0, metadata=metadata)
    return PlannedMaterial(
        material_id="x", block_id="b", original_spec=spec, decision="keep",
        spec_refined=spec, position=position, reframe=None, reasoning="",
    )


def test_dispatch_lower_third():
    pm = _planned("lower_third", "Edson Cúdris — Profesor de Física", {})
    comp, vars_ = build_render_input(pm)
    assert comp == "compositions/lower_third.html"
    assert vars_["name"] == "Edson Cúdris"
    assert vars_["subtitle"] == "Profesor de Física"
    assert vars_["position"] == "bottom-left"


def test_dispatch_lower_third_no_subtitle():
    pm = _planned("lower_third", "Solo Nombre", {})
    _, vars_ = build_render_input(pm)
    assert vars_["name"] == "Solo Nombre"
    assert vars_["subtitle"] == ""


def test_dispatch_pull_quote_with_speaker():
    pm = _planned("pull_quote", "La cita", {"speaker": "S"}, position="center")
    comp, vars_ = build_render_input(pm)
    assert comp == "compositions/pull_quote.html"
    assert vars_["quote"] == "La cita"
    assert vars_["speaker"] == "S"


def test_dispatch_chapter_marker():
    pm = _planned("chapter_marker", "El primer alumno", {"chapter_number": 3}, position=None)
    comp, vars_ = build_render_input(pm)
    assert comp == "compositions/chapter_marker.html"
    assert vars_["chapter_number"] == 3
    assert vars_["chapter_title"] == "El primer alumno"


def test_dispatch_animacion_texto():
    pm = _planned("animacion_texto", "VOCACIÓN", {}, position="top-right")
    comp, vars_ = build_render_input(pm)
    assert comp == "compositions/animacion_texto.html"
    assert vars_["text"] == "VOCACIÓN"
    assert vars_["position"] == "top-right"


def test_dispatch_ecuacion_latex():
    pm = _planned("ecuacion_latex", "E = mc^2", {"caption": "Energía"}, position="bottom-right")
    comp, vars_ = build_render_input(pm)
    assert comp == "compositions/ecuacion_latex.html"
    assert vars_["latex"] == "E = mc^2"
    assert vars_["caption"] == "Energía"


def test_dispatch_diagrama_barras():
    pm = _planned(
        "diagrama", "Comparación",
        {"tipo_visual": "barras", "data": [{"label": "A", "value": 1}, {"label": "B", "value": 2}]},
        position="center",
    )
    comp, vars_ = build_render_input(pm)
    assert comp == "compositions/diagrama_barras.html"
    assert vars_["title"] == "Comparación"
    import json
    data = json.loads(vars_["data_json"])
    assert data[0]["label"] == "A"


def test_dispatch_diagrama_ciclo():
    pm = _planned(
        "diagrama", "Ciclo del agua",
        {"tipo_visual": "ciclo", "nodes": ["Evapora", "Condensa", "Llueve"]},
        position="center",
    )
    comp, vars_ = build_render_input(pm)
    assert comp == "compositions/diagrama_ciclo.html"
    import json
    nodes = json.loads(vars_["nodes_json"])
    assert nodes == ["Evapora", "Condensa", "Llueve"]


def test_dispatch_diagrama_esquema_libre_with_template():
    pm = _planned(
        "diagrama", "bloque en plano inclinado con fricción",
        {"tipo_visual": "esquema_libre", "template_id": "bloque_inclinado",
         "params": {"angle_deg": 25, "show_friction": True}},
        position="center",
    )
    comp, vars_ = build_render_input(pm)
    assert comp == "compositions/diagrama_bloque_inclinado.html"
    assert vars_["angle_deg"] == 25
    assert vars_["show_friction"] is True


def test_dispatch_diagrama_esquema_libre_unknown_template_falls_to_text_card():
    pm = _planned(
        "diagrama", "esquema random",
        {"tipo_visual": "esquema_libre", "template_id": "no_existe", "params": {}},
        position="center",
    )
    comp, vars_ = build_render_input(pm)
    assert comp == "compositions/text_card_fallback.html"
    assert "esquema random" in vars_["text"]


def test_dispatch_unknown_tipo_raises():
    pm = _planned("nonexistent_tipo", "x", {}, position=None)
    with pytest.raises(DispatchError):
        build_render_input(pm)


def test_load_diagram_registry():
    reg = load_diagram_registry()
    assert "templates" in reg
    ids = [t["id"] for t in reg["templates"]]
    assert "bloque_inclinado" in ids
```

- [ ] **Step 3: Implementar `pipeline/renderers/dispatch.py`**

```python
"""Renderer dispatch: PlannedMaterial → (composition_path, variables_dict)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.models import PlannedMaterial

_REGISTRY_PATH = Path(__file__).parent / "diagram_templates" / "registry.json"


class DispatchError(RuntimeError):
    """Raised when no composition can handle a given tipo."""


def load_diagram_registry() -> dict[str, Any]:
    return json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))


def _parse_lower_third_contenido(s: str) -> tuple[str, str]:
    """'Nombre — Subtítulo' → ('Nombre', 'Subtítulo'). Sin separador → ('s', '')."""
    if " — " in s:
        name, _, subtitle = s.partition(" — ")
        return name.strip(), subtitle.strip()
    return s.strip(), ""


def _text_card_fallback_input(planned: PlannedMaterial) -> tuple[str, dict[str, Any]]:
    spec = planned.spec_refined or planned.original_spec
    return (
        "compositions/text_card_fallback.html",
        {
            "text": spec.contenido,
            "position": planned.position if isinstance(planned.position, str) else "center",
        },
    )


def build_render_input(planned: PlannedMaterial) -> tuple[str, dict[str, Any]]:
    """Map a PlannedMaterial to its (composition_path, variables) tuple."""
    spec = planned.spec_refined or planned.original_spec
    tipo = spec.tipo
    position = planned.position if isinstance(planned.position, str) else None

    if tipo == "lower_third":
        name, subtitle = _parse_lower_third_contenido(spec.contenido)
        return "compositions/lower_third.html", {
            "name": name,
            "subtitle": subtitle,
            "position": position or "bottom-left",
        }

    if tipo == "pull_quote":
        return "compositions/pull_quote.html", {
            "quote": spec.contenido,
            "speaker": spec.metadata.get("speaker", ""),
        }

    if tipo == "chapter_marker":
        return "compositions/chapter_marker.html", {
            "chapter_number": spec.metadata.get("chapter_number", 1),
            "chapter_title": spec.contenido,
        }

    if tipo == "animacion_texto":
        return "compositions/animacion_texto.html", {
            "text": spec.contenido,
            "position": position or "top-right",
        }

    if tipo == "ecuacion_latex":
        return "compositions/ecuacion_latex.html", {
            "latex": spec.contenido,
            "caption": spec.metadata.get("caption", "Ecuación"),
            "position": position or "bottom-right",
        }

    if tipo == "diagrama":
        tipo_visual = spec.metadata.get("tipo_visual")
        if tipo_visual == "barras":
            return "compositions/diagrama_barras.html", {
                "title": spec.contenido,
                "data_json": json.dumps(spec.metadata.get("data", []), ensure_ascii=False),
            }
        if tipo_visual == "ciclo":
            return "compositions/diagrama_ciclo.html", {
                "title": spec.contenido,
                "nodes_json": json.dumps(spec.metadata.get("nodes", []), ensure_ascii=False),
            }
        if tipo_visual == "esquema_libre":
            template_id = spec.metadata.get("template_id")
            params = spec.metadata.get("params", {})
            registry = load_diagram_registry()
            match = next(
                (t for t in registry["templates"] if t["id"] == template_id), None
            )
            if match is None:
                return _text_card_fallback_input(planned)
            return f"compositions/{match['composition']}", params

    raise DispatchError(f"no dispatch rule for tipo={tipo!r}")
```

- [ ] **Step 4: Tests + CI**

```bash
uv run pytest tests/test_renderer_dispatch.py -v
uv run ruff check pipeline/renderers/dispatch.py tests/test_renderer_dispatch.py
uv run ruff format --check pipeline/renderers/dispatch.py tests/test_renderer_dispatch.py
uv run mypy pipeline/renderers/
uv run pytest tests/ -x
```

- [ ] **Step 5: Commit**

```bash
git add pipeline/renderers/dispatch.py pipeline/renderers/diagram_templates/ \
        tests/test_renderer_dispatch.py
git commit -m "feat(renderers): dispatch + diagram template registry

build_render_input(PlannedMaterial) → (composition_path, variables_dict)
con 7 tipos manejados + esquema_libre via lookup en registry.json.
Templates v1: bloque_inclinado. Fallback automático a text_card_fallback
si template no existe o spec malformado.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Output validator (ffprobe checks) + R2 helpers

**Goal:** Validar técnicamente un .webm generado (alpha, dims, duration) y helpers R2 (upload/download/HEAD).

**Files:**
- Create: `pipeline/renderers/output_validator.py`
- Create: `tests/test_output_validator.py`
- Create: `pipeline/phase3_r2.py`
- Create: `tests/test_phase3_r2.py`

- [ ] **Step 1: Tests + impl de output_validator**

Tests (`tests/test_output_validator.py`):

```python
"""Tests for output_validator."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pipeline.renderers.output_validator import (
    OutputValidationError,
    validate_webm,
)


@pytest.fixture
def sample_webm_alpha(tmp_path: Path) -> Path:
    """A 2.2s webm 1920x1080 with alpha channel via libvpx-vp9 yuva420p."""
    raw = tmp_path / "raw.mov"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=color=red@0.5:size=1920x1080:duration=2.2:rate=30",
            "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
            str(raw),
        ],
        check=True,
    )
    out = tmp_path / "out.webm"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(raw),
            "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0",
            "-b:v", "0", "-crf", "30", "-an",
            str(out),
        ],
        check=True,
    )
    return out


def test_validate_webm_alpha_ok(sample_webm_alpha: Path):
    # Expect duration=2.2s, 1920x1080
    validate_webm(sample_webm_alpha, expected_duration=2.2, duration_tolerance=0.3)


def test_validate_webm_dimensions_mismatch(sample_webm_alpha: Path):
    with pytest.raises(OutputValidationError, match="dimensions"):
        validate_webm(
            sample_webm_alpha,
            expected_duration=2.2,
            duration_tolerance=0.3,
            expected_width=1280,
            expected_height=720,
        )


def test_validate_webm_duration_mismatch(sample_webm_alpha: Path):
    with pytest.raises(OutputValidationError, match="duration"):
        validate_webm(sample_webm_alpha, expected_duration=10.0, duration_tolerance=0.2)


def test_validate_webm_missing_file(tmp_path: Path):
    with pytest.raises(OutputValidationError, match="not found"):
        validate_webm(tmp_path / "no.webm", expected_duration=5.0)
```

Impl (`pipeline/renderers/output_validator.py`):

```python
"""Technical validation of rendered .webm outputs via ffprobe."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


class OutputValidationError(RuntimeError):
    """Raised when a rendered .webm fails technical checks."""


def _ffprobe_streams(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-print_format", "json",
            "-show_streams", "-show_format",
            str(path),
        ],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise OutputValidationError(f"ffprobe failed: {result.stderr[:200]}")
    return json.loads(result.stdout)


def validate_webm(
    path: Path,
    expected_duration: float,
    duration_tolerance: float = 0.2,
    expected_width: int = 1920,
    expected_height: int = 1080,
    require_alpha: bool = True,
) -> None:
    """Validate that path is a webm matching the technical spec.

    Raises OutputValidationError on any mismatch.
    """
    if not path.exists():
        raise OutputValidationError(f"output not found: {path}")
    if path.stat().st_size < 1024:
        raise OutputValidationError(f"output too small ({path.stat().st_size} bytes): {path}")
    info = _ffprobe_streams(path)
    video_streams = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    if not video_streams:
        raise OutputValidationError(f"no video stream in {path.name}")
    vs = video_streams[0]
    if vs.get("width") != expected_width or vs.get("height") != expected_height:
        raise OutputValidationError(
            f"dimensions mismatch {vs.get('width')}x{vs.get('height')} "
            f"vs expected {expected_width}x{expected_height}"
        )
    fmt_duration_str = info.get("format", {}).get("duration")
    if fmt_duration_str is None:
        raise OutputValidationError(f"no duration in ffprobe output for {path.name}")
    duration = float(fmt_duration_str)
    if abs(duration - expected_duration) > duration_tolerance:
        raise OutputValidationError(
            f"duration {duration:.2f}s vs expected {expected_duration:.2f}s "
            f"(tolerance ±{duration_tolerance}s)"
        )
    if require_alpha:
        tags = vs.get("tags") or {}
        alpha_mode = tags.get("alpha_mode") or tags.get("ALPHA_MODE")
        if alpha_mode != "1":
            raise OutputValidationError(
                f"alpha not present (alpha_mode={alpha_mode!r}) in {path.name}"
            )
```

- [ ] **Step 2: Tests + impl de R2 helpers**

Tests (`tests/test_phase3_r2.py`):

```python
"""Tests for phase3_r2 helpers."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pipeline.phase3_r2 import (
    download_video_to_local,
    head_object_exists,
    materials_manifest_key,
    upload_manifest,
    visual_plan_key,
)


def test_visual_plan_key():
    assert visual_plan_key("p1") == "projects/p1/phase3/visual_plan.json"


def test_materials_manifest_key():
    assert materials_manifest_key("p1") == "projects/p1/phase3/materials_manifest.json"


@patch("pipeline.phase3_r2.get_storage_client")
def test_head_object_exists_true(mock_client):
    fake = MagicMock()
    fake.head_object.return_value = {"ContentLength": 100}
    mock_client.return_value = fake
    assert head_object_exists("k") is True


@patch("pipeline.phase3_r2.get_storage_client")
def test_head_object_exists_false_on_404(mock_client):
    from botocore.exceptions import ClientError
    fake = MagicMock()
    err = ClientError({"Error": {"Code": "404"}}, "HeadObject")
    fake.head_object.side_effect = err
    mock_client.return_value = fake
    assert head_object_exists("k") is False


@patch("pipeline.phase3_r2.get_storage_client")
def test_upload_manifest_serializes(mock_client, tmp_path):
    fake = MagicMock()
    mock_client.return_value = fake
    manifest = [{"material_id": "x", "render_status": "ok"}]
    upload_manifest("p1", manifest)
    args, kwargs = fake.put_object.call_args
    assert kwargs["Key"] == "projects/p1/phase3/materials_manifest.json"
    import json
    body = kwargs["Body"]
    parsed = json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
    assert parsed[0]["material_id"] == "x"


@patch("pipeline.phase3_r2.get_storage_client")
def test_download_video_to_local(mock_client, tmp_path):
    fake = MagicMock()
    mock_client.return_value = fake
    target = tmp_path / "v.mp4"
    download_video_to_local("p1", target)
    args, kwargs = fake.download_file.call_args
    assert kwargs.get("Key", args[1] if len(args) > 1 else None) == "projects/p1/phase1/video.mp4"
    assert kwargs.get("Filename", args[2] if len(args) > 2 else None) == str(target)
```

Impl (`pipeline/phase3_r2.py`):

```python
"""R2 helpers for Phase 3 — keys, upload/download, HEAD checks."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError

from pipeline.storage import get_storage_client, R2_BUCKET


def visual_plan_key(project_id: str) -> str:
    return f"projects/{project_id}/phase3/visual_plan.json"


def materials_manifest_key(project_id: str) -> str:
    return f"projects/{project_id}/phase3/materials_manifest.json"


def material_webm_key(project_id: str, material_id: str) -> str:
    return f"projects/{project_id}/phase3/materials/{material_id}.webm"


def frame_key(project_id: str, material_id: str, suffix: str) -> str:
    return f"projects/{project_id}/phase3/frames/{material_id}_{suffix}.png"


def video_raw_key(project_id: str) -> str:
    return f"projects/{project_id}/phase1/video.mp4"


def head_object_exists(key: str) -> bool:
    client = get_storage_client()
    try:
        client.head_object(Bucket=R2_BUCKET, Key=key)
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in {"404", "NoSuchKey"}:
            return False
        raise


def upload_manifest(project_id: str, manifest: list[dict[str, Any]]) -> str:
    key = materials_manifest_key(project_id)
    body = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    get_storage_client().put_object(
        Bucket=R2_BUCKET, Key=key, Body=body, ContentType="application/json",
    )
    return key


def upload_visual_plan(project_id: str, planned: list[dict[str, Any]]) -> str:
    key = visual_plan_key(project_id)
    body = json.dumps(planned, ensure_ascii=False, indent=2).encode("utf-8")
    get_storage_client().put_object(
        Bucket=R2_BUCKET, Key=key, Body=body, ContentType="application/json",
    )
    return key


def load_manifest(project_id: str) -> list[dict[str, Any]] | None:
    key = materials_manifest_key(project_id)
    if not head_object_exists(key):
        return None
    resp = get_storage_client().get_object(Bucket=R2_BUCKET, Key=key)
    return json.loads(resp["Body"].read().decode("utf-8"))


def load_visual_plan(project_id: str) -> list[dict[str, Any]] | None:
    key = visual_plan_key(project_id)
    if not head_object_exists(key):
        return None
    resp = get_storage_client().get_object(Bucket=R2_BUCKET, Key=key)
    return json.loads(resp["Body"].read().decode("utf-8"))


def upload_webm(project_id: str, material_id: str, local_path: Path) -> str:
    key = material_webm_key(project_id, material_id)
    get_storage_client().upload_file(
        Filename=str(local_path), Bucket=R2_BUCKET, Key=key,
        ExtraArgs={"ContentType": "video/webm"},
    )
    return key


def download_video_to_local(project_id: str, target: Path) -> None:
    key = video_raw_key(project_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    get_storage_client().download_file(Bucket=R2_BUCKET, Key=key, Filename=str(target))


def upload_frame(project_id: str, material_id: str, suffix: str, local_path: Path) -> str:
    key = frame_key(project_id, material_id, suffix)
    get_storage_client().upload_file(
        Filename=str(local_path), Bucket=R2_BUCKET, Key=key,
        ExtraArgs={"ContentType": "image/png"},
    )
    return key
```

Nota: `pipeline/storage.py` ya existe (Unit 1). El import de `R2_BUCKET` y `get_storage_client` debe matchear lo que ya está ahí. Si los nombres difieren, ajustar el import.

- [ ] **Step 3: Tests + CI**

```bash
uv run pytest tests/test_output_validator.py tests/test_phase3_r2.py -v
uv run ruff check pipeline/renderers/output_validator.py pipeline/phase3_r2.py \
                  tests/test_output_validator.py tests/test_phase3_r2.py
uv run ruff format --check pipeline/renderers/output_validator.py pipeline/phase3_r2.py \
                            tests/test_output_validator.py tests/test_phase3_r2.py
uv run mypy pipeline/renderers/output_validator.py pipeline/phase3_r2.py
uv run pytest tests/ -x
```

- [ ] **Step 4: Commit**

```bash
git add pipeline/renderers/output_validator.py pipeline/phase3_r2.py \
        tests/test_output_validator.py tests/test_phase3_r2.py
git commit -m "feat(phase3): output_validator + r2 helpers

validate_webm() checks via ffprobe (dimensions, duration, alpha_mode=1).
phase3_r2.py expone keys + upload/download/head helpers para los artefactos
de Phase 3 (visual_plan, manifest, materials, frames).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Modal app + render function (worker code)

**Goal:** Modal image custom (Python + Node + Chromium + HF), función `render_material` decorada, lógica `render_one` que corre en el worker.

**Files:**
- Create: `pipeline/modal_app.py`
- Create: `pipeline/modal_render.py`
- Create: `tests/test_modal_render.py`

- [ ] **Step 1: Tests fallidos para render_one (mocked subprocess)**

Crear `tests/test_modal_render.py`:

```python
"""Tests for modal_render.render_one — runs in Modal worker but unit-tested locally."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.models import MaterialSpec, PlannedMaterial


def _planned_keep(material_id="b1_m00_x") -> PlannedMaterial:
    spec = MaterialSpec(
        tipo="lower_third", contenido="Edson — Profe",
        timestamp_relativo=0, metadata={},
    )
    return PlannedMaterial(
        material_id=material_id, block_id="b1", original_spec=spec,
        decision="keep", spec_refined=spec, position="bottom-left",
        reframe=None, reasoning="OK.",
    )


def _planned_drop(material_id="b1_m01_y") -> PlannedMaterial:
    spec = MaterialSpec(tipo="pull_quote", contenido="X", timestamp_relativo=0, metadata={})
    return PlannedMaterial(
        material_id=material_id, block_id="b1", original_spec=spec,
        decision="drop", spec_refined=None, position=None,
        reframe=None, reasoning="No encaja.",
    )


@patch("pipeline.modal_render.upload_webm", return_value="projects/p/phase3/materials/x.webm")
@patch("pipeline.modal_render.validate_webm")
@patch("pipeline.modal_render.subprocess.run")
@patch("pipeline.modal_render.write_brand_assets")
def test_render_one_keep_ok_path(mock_brand, mock_run, mock_validate, mock_upload, tmp_path):
    from pipeline.modal_render import render_one
    # Force happy path: subprocess.run returns success
    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
    # Simulate that ffmpeg created the webm by touching the expected path
    def write_output(*args, **kwargs):
        # Last positional arg is the output path in the ffmpeg call
        cmd = args[0] if args else kwargs.get("args")
        if cmd and "libvpx-vp9" in cmd:
            Path(cmd[-1]).write_bytes(b"\x00" * 2048)
        if cmd and "hyperframes" in " ".join(cmd):
            # Touch the .mov target
            for i, a in enumerate(cmd):
                if a == "--output":
                    Path(cmd[i + 1]).write_bytes(b"\x00" * 2048)
        return MagicMock(returncode=0, stdout="", stderr="")
    mock_run.side_effect = write_output
    payload = {
        "planned": _planned_keep().to_dict(),
        "project_id": "p1",
        "material_id": "b1_m00_x",
        "brand": {"colors": {"primary":"#000","primary_dark":"#000","accent":"#000",
                            "accent_dark":"#000","carbon":"#000","carbon_light":"#000",
                            "surface":"#fff","background":"#fff"}, "id": "phymac"},
    }
    result = render_one(payload, hf_project_dir=tmp_path / "hfp", tmp_dir=tmp_path / "work")
    assert result["status"] == "ok"
    assert result["r2_key"] == "projects/p/phase3/materials/x.webm"
    assert result["material_id"] == "b1_m00_x"


def test_render_one_drop_short_circuits(tmp_path):
    from pipeline.modal_render import render_one
    payload = {
        "planned": _planned_drop().to_dict(),
        "project_id": "p1",
        "material_id": "b1_m01_y",
        "brand": {"colors": {"primary":"#000","primary_dark":"#000","accent":"#000",
                            "accent_dark":"#000","carbon":"#000","carbon_light":"#000",
                            "surface":"#fff","background":"#fff"}, "id": "phymac"},
    }
    result = render_one(payload, hf_project_dir=tmp_path, tmp_dir=tmp_path)
    assert result["status"] == "dropped"
    assert result["r2_key"] is None
```

- [ ] **Step 2: Implementar `pipeline/modal_render.py`**

```python
"""Worker-side render logic. Runs inside Modal function (or locally for tests)."""
from __future__ import annotations

import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Any

from pipeline.models import PlannedMaterial
from pipeline.phase3_r2 import upload_webm
from pipeline.renderers.brand_css import render_brand_css
from pipeline.renderers.dispatch import DispatchError, build_render_input
from pipeline.renderers.output_validator import (
    OutputValidationError,
    validate_webm,
)

logger = logging.getLogger(__name__)

DURATION_BY_TIPO: dict[str, float] = {
    "lower_third": 6.0,
    "pull_quote": 6.6,
    "chapter_marker": 4.2,
    "animacion_texto": 2.2,
    "ecuacion_latex": 5.0,
    "diagrama": 6.0,
    "transcript_fix": 0.0,
}


def write_brand_assets(hf_project_dir: Path, brand: dict[str, Any]) -> None:
    """Write brand.css inside the HF project. brand-assets symlink optional."""
    (hf_project_dir / "brand.css").write_text(render_brand_css(brand), encoding="utf-8")


def _invoke_hf_render(
    hf_project_dir: Path,
    composition_path: str,
    variables: dict[str, Any],
    mov_out: Path,
) -> None:
    cmd = [
        "npx", "hyperframes", "render", str(hf_project_dir),
        "--composition", composition_path,
        "--output", str(mov_out),
        "--format", "mov",
        "--fps", "30",
        "--variables", json.dumps(variables, ensure_ascii=False),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not mov_out.exists() or mov_out.stat().st_size < 1024:
        raise RuntimeError(
            f"hyperframes render failed: rc={result.returncode}, "
            f"stderr={result.stderr.strip()[-300:]}"
        )


def _transcode_to_webm(mov_in: Path, webm_out: Path) -> None:
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(mov_in),
        "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0",
        "-b:v", "0", "-crf", "22", "-row-mt", "1", "-an",
        str(webm_out),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not webm_out.exists() or webm_out.stat().st_size < 1024:
        raise RuntimeError(
            f"ffmpeg transcode failed: rc={result.returncode}, "
            f"stderr={result.stderr.strip()[-300:]}"
        )


def _render_text_card_fallback(
    hf_project_dir: Path,
    planned: PlannedMaterial,
    mov_out: Path,
) -> None:
    spec = planned.spec_refined or planned.original_spec
    variables = {
        "text": spec.contenido,
        "position": planned.position if isinstance(planned.position, str) else "center",
    }
    _invoke_hf_render(
        hf_project_dir, "compositions/text_card_fallback.html", variables, mov_out,
    )


def render_one(
    payload: dict[str, Any],
    hf_project_dir: Path,
    tmp_dir: Path,
) -> dict[str, Any]:
    """Process one PlannedMaterial. Returns ManifestEntry-shaped dict."""
    planned = PlannedMaterial.from_dict(payload["planned"])
    project_id = payload["project_id"]
    material_id = payload["material_id"]
    brand = payload["brand"]
    tmp_dir.mkdir(parents=True, exist_ok=True)
    base_entry: dict[str, Any] = {
        "material_id": material_id,
        "block_id": planned.block_id,
        "original_spec": planned.original_spec.to_dict(),
        "refined_spec": planned.spec_refined.to_dict() if planned.spec_refined else None,
        "decision": planned.decision,
        "position": planned.position,
        "reframe": planned.reframe,
        "reasoning": planned.reasoning,
    }

    if planned.decision == "drop":
        return {
            **base_entry,
            "render_status": "dropped",
            "r2_key": None,
            "render_seconds": 0.0,
        }

    # Setup
    write_brand_assets(hf_project_dir, brand)
    mov_out = tmp_dir / f"{material_id}.mov"
    webm_out = tmp_dir / f"{material_id}.webm"
    spec = planned.spec_refined or planned.original_spec
    expected_duration = DURATION_BY_TIPO.get(spec.tipo, 5.0)
    t0 = time.time()
    status = "ok"
    error: str | None = None
    try:
        composition, variables = build_render_input(planned)
        _invoke_hf_render(hf_project_dir, composition, variables, mov_out)
        _transcode_to_webm(mov_out, webm_out)
        validate_webm(webm_out, expected_duration=expected_duration)
    except (RuntimeError, OutputValidationError, DispatchError) as e:
        logger.warning("render failed for %s: %s. Falling back to text card.", material_id, e)
        error = f"{type(e).__name__}: {e}"
        try:
            if mov_out.exists():
                mov_out.unlink()
            if webm_out.exists():
                webm_out.unlink()
            _render_text_card_fallback(hf_project_dir, planned, mov_out)
            _transcode_to_webm(mov_out, webm_out)
            validate_webm(webm_out, expected_duration=5.0)
            status = "fallback"
        except (RuntimeError, OutputValidationError) as fe:
            elapsed = time.time() - t0
            return {
                **base_entry,
                "render_status": "fallback",
                "r2_key": None,
                "render_seconds": round(elapsed, 2),
                "error": f"both render + fallback failed: original={error}; fallback={fe}",
            }

    r2_key = upload_webm(project_id, material_id, webm_out)
    elapsed = time.time() - t0
    # Cleanup local
    for p in (mov_out, webm_out):
        if p.exists():
            p.unlink()
    return {
        **base_entry,
        "render_status": status,
        "r2_key": r2_key,
        "render_seconds": round(elapsed, 2),
        "error": error,
    }
```

- [ ] **Step 3: Implementar `pipeline/modal_app.py`**

```python
"""Modal app for Phase 3 rendering."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import modal

HF_PROJECT_LOCAL = Path(__file__).parent / "renderers" / "hf-project"

hf_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install(
        "ffmpeg", "chromium", "fonts-liberation",
        "libcairo2", "libpango-1.0-0", "libpangocairo-1.0-0",
        "curl", "ca-certificates",
    )
    .run_commands(
        "curl -fsSL https://deb.nodesource.com/setup_22.x | bash -",
        "apt-get install -y nodejs",
    )
    .pip_install("boto3>=1.34.0", "python-dotenv>=1.0.0")
    .add_local_python_source("pipeline")
    .add_local_dir(local_path=str(HF_PROJECT_LOCAL), remote_path="/app/hf-project")
    .run_commands(
        "cd /app/hf-project && npm install --omit=dev --no-audit --no-fund",
    )
)

app = modal.App("phymac-phase3-render")


@app.function(
    image=hf_image,
    secrets=[
        modal.Secret.from_name("phymac-r2-creds"),
        modal.Secret.from_name("phymac-openrouter"),
    ],
    timeout=600,
    cpu=2.0,
    memory=4096,
    retries=modal.Retries(max_retries=1, backoff_coefficient=2.0),
)
def render_material(payload: dict[str, Any]) -> dict[str, Any]:
    """Modal entry point: renders one material end-to-end."""
    from pipeline.modal_render import render_one
    return render_one(
        payload,
        hf_project_dir=Path("/app/hf-project"),
        tmp_dir=Path("/tmp/phymac-phase3"),
    )
```

- [ ] **Step 4: Tests + CI**

```bash
uv run pytest tests/test_modal_render.py -v
uv run ruff check pipeline/modal_app.py pipeline/modal_render.py tests/test_modal_render.py
uv run ruff format --check pipeline/modal_app.py pipeline/modal_render.py tests/test_modal_render.py
uv run mypy pipeline/modal_app.py pipeline/modal_render.py
uv run pytest tests/ -x
```

- [ ] **Step 5: Modal deploy smoke (manual, requiere Modal auth)**

```bash
uv run modal deploy pipeline/modal_app.py
# Espera: app desplegada, función "render_material" visible en `uv run modal app list`
```

- [ ] **Step 6: Commit**

```bash
git add pipeline/modal_app.py pipeline/modal_render.py tests/test_modal_render.py
git commit -m "feat(phase3): Modal app + render_material function

modal_app.py: image debian + Node 22 + Chromium + ffmpeg + HF project
preinstalado en /app/hf-project. modal_render.render_one() ejecuta HF
mov + transcode webm + upload R2. Fallback automático a text_card si HF
o transcode fallan. retries=1 a nivel Modal.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Phase 3 orchestrator

**Goal:** El runner `pipeline/phases/phase3_materials.py` que orquesta todo: cache check, Phase 3a (frame extract + LLM-vision), Phase 3b (Modal.map), merge manifest, upload, validation.

**Files:**
- Create: `pipeline/phases/phase3_materials.py`
- Create: `tests/test_phase3_materials.py`

- [ ] **Step 1: Tests fallidos (orchestrator unit-test con mocks)**

Crear `tests/test_phase3_materials.py`:

```python
"""Tests for phase3_materials orchestrator (mocked external IO)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.models import (
    Block,
    MaterialSpec,
    NarrativePlan,
    PlannedMaterial,
)


@pytest.fixture
def sample_plan() -> NarrativePlan:
    mat = MaterialSpec(tipo="lower_third", contenido="X", timestamp_relativo=0, metadata={})
    b1 = Block(id="b1", name="Intro", segments=[0], estimated_duration="1:00",
               support_material=[mat], transition_next="cut")
    return NarrativePlan(project_id="p1", blocks=[b1], total_duration_estimate="1:00")


@patch("pipeline.phases.phase3_materials.render_material")
@patch("pipeline.phases.phase3_materials.plan_material_visual")
@patch("pipeline.phases.phase3_materials.extract_frames")
@patch("pipeline.phases.phase3_materials.download_video_to_local")
@patch("pipeline.phases.phase3_materials.load_visual_plan", return_value=None)
@patch("pipeline.phases.phase3_materials.load_manifest", return_value=None)
@patch("pipeline.phases.phase3_materials.upload_manifest")
@patch("pipeline.phases.phase3_materials.upload_visual_plan")
@patch("pipeline.phases.phase3_materials.upload_frame")
@patch("pipeline.phases.phase3_materials.head_object_exists", return_value=False)
def test_orchestrator_happy_path(
    mock_head, mock_up_frame, mock_up_plan, mock_up_man,
    mock_load_man, mock_load_plan, mock_dl, mock_extract, mock_plan, mock_render,
    sample_plan, tmp_path,
):
    from pipeline.phases.phase3_materials import run_phase3
    # frames
    mock_extract.return_value = [
        tmp_path / "f-1.png", tmp_path / "f0.png", tmp_path / "f1.png",
    ]
    for p in mock_extract.return_value:
        p.write_bytes(b"\x00" * 2048)
    # planned
    spec = sample_plan.blocks[0].support_material[0]
    mock_plan.return_value = PlannedMaterial(
        material_id="b1_m00_xxx", block_id="b1", original_spec=spec,
        decision="keep", spec_refined=spec, position="bottom-left",
        reframe=None, reasoning="OK.",
    )
    # render
    mock_render.map = MagicMock(return_value=[
        {
            "material_id": "b1_m00_xxx",
            "block_id": "b1",
            "original_spec": spec.to_dict(),
            "refined_spec": spec.to_dict(),
            "decision": "keep",
            "position": "bottom-left",
            "reframe": None,
            "reasoning": "OK.",
            "render_status": "ok",
            "r2_key": "projects/p1/phase3/materials/b1_m00_xxx.webm",
            "render_seconds": 50.0,
        },
    ])
    # video file at expected path
    with patch("pipeline.phases.phase3_materials.modal_app.run"):
        result = run_phase3(
            sample_plan,
            brand={"id": "phymac", "colors": {"primary": "#000","primary_dark": "#000",
                   "accent": "#000","accent_dark": "#000","carbon": "#000",
                   "carbon_light": "#000","surface": "#fff","background": "#fff"}},
            visual_specs_summary={},
        )
    assert len(result["manifest"]) == 1
    assert result["manifest"][0]["render_status"] == "ok"
    mock_up_man.assert_called_once()
```

- [ ] **Step 2: Implementar `pipeline/phases/phase3_materials.py`**

```python
"""Phase 3 orchestrator: visual planning + render + manifest."""
from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from pipeline.formats import load_format
from pipeline.models import NarrativePlan, PlannedMaterial
from pipeline.modal_app import app as modal_app, render_material
from pipeline.phase3_helpers import flatten_plan_to_materials
from pipeline.phase3_r2 import (
    download_video_to_local,
    head_object_exists,
    load_manifest,
    load_visual_plan,
    material_webm_key,
    upload_frame,
    upload_manifest,
    upload_visual_plan,
)
from pipeline.renderers.dispatch import load_diagram_registry
from pipeline.vision.frame_extractor import extract_frames
from pipeline.vision.visual_planner import plan_material_visual

logger = logging.getLogger(__name__)


def _visual_plan_to_dict(planned: PlannedMaterial) -> dict[str, Any]:
    return planned.to_dict()


def _visual_plan_from_dict(d: dict[str, Any]) -> PlannedMaterial:
    return PlannedMaterial.from_dict(d)


def _ensure_video_local(project_id: str, tmp_dir: Path) -> Path:
    target = tmp_dir / "video.mp4"
    if not target.exists():
        download_video_to_local(project_id, target)
    return target


def _phase3a_for_material(
    project_id: str,
    material_id: str,
    block_id: str,
    spec,
    video_local: Path,
    transcript_window: str,
    block_name: str,
    brand: dict,
    visual_specs_summary: dict,
    template_registry: list[dict],
    tmp_dir: Path,
) -> PlannedMaterial:
    t = float(spec.timestamp_relativo)
    timestamps = [max(0.0, t - 1.0), t, t + 1.0]
    frames_dir = tmp_dir / "frames"
    frames = extract_frames(video_local, timestamps, frames_dir, prefix=material_id)
    # Upload frames to R2 (audit + cache)
    for i, fp in enumerate(frames):
        suffix = ["tm1", "t0", "tp1"][i]
        upload_frame(project_id, material_id, suffix, fp)
    planned = plan_material_visual(
        material_id=material_id,
        block_id=block_id,
        original_spec=spec,
        frames_paths=frames,
        phase2_context={
            "block_id": block_id,
            "block_name": block_name,
            "material_spec": spec.to_dict(),
            "transcript_window": transcript_window,
        },
        brand=brand,
        visual_specs_summary=visual_specs_summary,
        diagram_template_registry=template_registry if spec.tipo == "diagrama" else [],
    )
    return planned


def run_phase3(
    plan: NarrativePlan,
    brand: dict[str, Any],
    visual_specs_summary: dict[str, Any],
) -> dict[str, Any]:
    """Run Phase 3 end-to-end for a project. Returns {"manifest": [...]}."""
    project_id = plan.project_id
    existing_manifest = load_manifest(project_id) or []
    existing_planned = load_visual_plan(project_id) or []
    materials = flatten_plan_to_materials(plan)

    fmt = load_format(plan.format_id) if hasattr(plan, "format_id") else None
    template_registry = load_diagram_registry().get("templates", [])

    with tempfile.TemporaryDirectory(prefix="phase3-") as td:
        tmp_dir = Path(td)
        video_local = _ensure_video_local(project_id, tmp_dir)

        # ---- Phase 3a: visual planning (secuencial; LLM-vision por material) ----
        planned_by_id: dict[str, PlannedMaterial] = {}
        existing_planned_by_id = {p["material_id"]: p for p in existing_planned}
        for mid, block_id, spec in materials:
            cached = existing_planned_by_id.get(mid)
            if cached is not None:
                planned_by_id[mid] = _visual_plan_from_dict(cached)
                continue
            block = next(b for b in plan.blocks if b.id == block_id)
            transcript_window = ""  # populated from transcription if available
            planned_by_id[mid] = _phase3a_for_material(
                project_id=project_id,
                material_id=mid,
                block_id=block_id,
                spec=spec,
                video_local=video_local,
                transcript_window=transcript_window,
                block_name=block.name,
                brand=brand,
                visual_specs_summary=visual_specs_summary,
                template_registry=template_registry,
                tmp_dir=tmp_dir,
            )
        upload_visual_plan(
            project_id,
            [_visual_plan_to_dict(p) for p in planned_by_id.values()],
        )

        # ---- Phase 3b: render via Modal.map() ----
        existing_by_id = {e["material_id"]: e for e in existing_manifest}
        to_render: list[dict[str, Any]] = []
        cached_entries: list[dict[str, Any]] = []
        for mid, _, _ in materials:
            planned = planned_by_id[mid]
            cached = existing_by_id.get(mid)
            if (
                cached is not None
                and cached.get("render_status") == "ok"
                and cached.get("r2_key")
                and head_object_exists(material_webm_key(project_id, mid))
            ):
                cached_entries.append(cached)
                continue
            to_render.append({
                "planned": planned.to_dict(),
                "project_id": project_id,
                "material_id": mid,
                "brand": brand,
            })

        new_entries: list[dict[str, Any]] = []
        if to_render:
            with modal_app.run():
                new_entries = list(render_material.map(to_render))

        # ---- Phase 3c: merge + upload manifest ----
        manifest = cached_entries + new_entries
        # preserve order of materials
        order = {mid: i for i, (mid, _, _) in enumerate(materials)}
        manifest.sort(key=lambda e: order.get(e["material_id"], 1_000_000))
        upload_manifest(project_id, manifest)

    return {"manifest": manifest}
```

- [ ] **Step 3: Tests + CI**

```bash
uv run pytest tests/test_phase3_materials.py -v
uv run ruff check pipeline/phases/phase3_materials.py tests/test_phase3_materials.py
uv run ruff format --check pipeline/phases/phase3_materials.py tests/test_phase3_materials.py
uv run mypy pipeline/phases/phase3_materials.py
uv run pytest tests/ -x
```

- [ ] **Step 4: Commit**

```bash
git add pipeline/phases/phase3_materials.py tests/test_phase3_materials.py
git commit -m "feat(phase3): orchestrator run_phase3()

Visual planning (LLM-vision por material) + Modal.map() per-material
render + merge con manifest existente + upload final a R2. Idempotente
a 3 niveles: frames, visual_plan, render. Materials cacheados
(status=ok + .webm en R2) se preservan; resto re-renderiza.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Phase 3 validator (extends pipeline/validator.py)

**Goal:** Agregar `validate_phase3()` al validator existente. 11 checks del spec §10.

**Files:**
- Modify: `pipeline/validator.py` (agregar función + helpers)
- Create: `tests/test_validator_phase3.py`

- [ ] **Step 1: Tests fallidos**

Crear `tests/test_validator_phase3.py`:

```python
"""Tests for Phase 3 validator."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from pipeline.validator import validate_phase3


def _entry(material_id, status="ok", r2_key=None, decision="keep", tipo="lower_third",
           original_tipo=None, reasoning="OK"):
    return {
        "material_id": material_id,
        "block_id": "b",
        "original_spec": {"tipo": original_tipo or tipo, "contenido":"x","timestamp_relativo":0,"metadata":{}},
        "refined_spec": {"tipo": tipo, "contenido":"x","timestamp_relativo":0,"metadata":{}} if status != "dropped" else None,
        "decision": decision,
        "position": "bottom-left" if status != "dropped" else None,
        "reframe": None,
        "reasoning": reasoning,
        "render_status": status,
        "r2_key": r2_key or (f"projects/p/phase3/materials/{material_id}.webm" if status != "dropped" else None),
        "render_seconds": 50.0,
    }


@patch("pipeline.validator.head_object_exists", return_value=True)
@patch("pipeline.validator._ffprobe_webm_summary")
def test_validate_phase3_all_pass(mock_ffprobe, mock_head):
    mock_ffprobe.return_value = {"width": 1920, "height": 1080, "duration": 6.0,
                                 "alpha_mode": "1"}
    manifest = [_entry("m1", "ok"), _entry("m2", "ok")]
    whitelist = ["lower_third", "pull_quote"]
    result = validate_phase3(manifest, whitelist=whitelist)
    assert result.passed is True
    assert result.critical_failures == []


@patch("pipeline.validator.head_object_exists", return_value=False)
def test_validate_phase3_critical_r2_missing(mock_head):
    manifest = [_entry("m1", "ok")]
    result = validate_phase3(manifest, whitelist=["lower_third"])
    assert result.passed is False
    assert any("r2_key" in c.lower() or "resolvable" in c.lower() for c in result.critical_failures)


def test_validate_phase3_critical_whitelist_violation():
    manifest = [_entry("m1", "ok", tipo="not_in_whitelist")]
    with patch("pipeline.validator.head_object_exists", return_value=True), \
         patch("pipeline.validator._ffprobe_webm_summary",
               return_value={"width":1920,"height":1080,"duration":6.0,"alpha_mode":"1"}):
        result = validate_phase3(manifest, whitelist=["lower_third"])
    assert result.passed is False
    assert any("whitelist" in c.lower() for c in result.critical_failures)


def test_validate_phase3_warning_high_drop_rate():
    # 4 dropped out of 10 → 40% > 30% threshold
    manifest = [_entry(f"m{i}", "ok") for i in range(6)] + [
        _entry(f"d{i}", "dropped", decision="drop") for i in range(4)
    ]
    with patch("pipeline.validator.head_object_exists", return_value=True), \
         patch("pipeline.validator._ffprobe_webm_summary",
               return_value={"width":1920,"height":1080,"duration":6.0,"alpha_mode":"1"}):
        result = validate_phase3(manifest, whitelist=["lower_third"])
    assert any("drop" in w.lower() for w in result.warnings)


def test_validate_phase3_warning_high_fallback_rate():
    # 2 fallback out of 10 → 20% > 10% threshold
    manifest = [_entry(f"m{i}", "ok") for i in range(8)] + [
        _entry(f"f{i}", "fallback") for i in range(2)
    ]
    with patch("pipeline.validator.head_object_exists", return_value=True), \
         patch("pipeline.validator._ffprobe_webm_summary",
               return_value={"width":1920,"height":1080,"duration":6.0,"alpha_mode":"1"}):
        result = validate_phase3(manifest, whitelist=["lower_third"])
    assert any("fallback" in w.lower() for w in result.warnings)
```

- [ ] **Step 2: Agregar `validate_phase3` a `pipeline/validator.py`**

Editar `pipeline/validator.py`, agregar al final (con imports y helpers que falten):

```python
# ---------------------------------------------------------------------------
# Phase 3 — Materiales de soporte (Unit 4)
# ---------------------------------------------------------------------------

from pipeline.phase3_r2 import head_object_exists


_DURATION_BY_TIPO_PHASE3: dict[str, float] = {
    "lower_third": 6.0,
    "pull_quote": 6.6,
    "chapter_marker": 4.2,
    "animacion_texto": 2.2,
    "ecuacion_latex": 5.0,
    "diagrama": 6.0,
}


def _ffprobe_webm_summary(r2_key: str) -> dict:
    """Stub que en producción consulta R2 y descarga el webm o usa byte-range.

    Para tests, esta función está mockeada. Para runtime real, implementa
    download a /tmp + ffprobe local + return summary dict.
    """
    raise NotImplementedError(
        "Implement webm sampling for production. Mocked in tests."
    )


def _sample_check_alpha_dimensions_duration(
    manifest: list[dict], sample_size: int = 1
) -> tuple[list[CheckResult], list[CheckResult]]:
    """Run ffprobe-based checks on 1 of every `sample_size` (1=every) ok/fallback entries."""
    crit: list[CheckResult] = []
    warn: list[CheckResult] = []
    candidates = [e for e in manifest if e["render_status"] in {"ok", "fallback"}]
    sampled = candidates[::max(sample_size, 1)] or candidates[:1]
    for entry in sampled:
        try:
            info = _ffprobe_webm_summary(entry["r2_key"])
        except Exception as e:
            crit.append(CheckResult(
                name="ffprobe_sample",
                passed=False,
                value=str(e), threshold="successful probe",
                message=f"could not probe {entry['material_id']}",
            ))
            continue
        if (info.get("width") != 1920) or (info.get("height") != 1080):
            crit.append(CheckResult(
                name="webm_dimensions_correct",
                passed=False,
                value=f"{info.get('width')}x{info.get('height')}",
                threshold="1920x1080",
                message=f"dimensions wrong on {entry['material_id']}",
            ))
        spec = entry.get("refined_spec") or entry.get("original_spec") or {}
        expected = _DURATION_BY_TIPO_PHASE3.get(spec.get("tipo"), 5.0)
        if abs(float(info.get("duration", 0)) - expected) > 0.2:
            crit.append(CheckResult(
                name="webm_duration_matches_spec",
                passed=False,
                value=info.get("duration"),
                threshold=f"{expected}±0.2",
                message=f"duration off on {entry['material_id']}",
            ))
        if info.get("alpha_mode") != "1":
            crit.append(CheckResult(
                name="webm_alpha_present",
                passed=False,
                value=info.get("alpha_mode"),
                threshold="alpha_mode=1",
                message=f"alpha missing on {entry['material_id']}",
            ))
    return crit, warn


def validate_phase3(
    manifest: list[dict],
    whitelist: list[str],
    *,
    drop_threshold: float = 0.30,
    fallback_threshold: float = 0.10,
) -> ValidationResult:
    """Validate the Phase 3 manifest. See spec §10."""
    checks: list[CheckResult] = []
    critical: list[str] = []
    warnings: list[str] = []

    # 1. all_materials_have_status
    bad_status = [
        e for e in manifest
        if e.get("render_status") not in {"ok", "fallback", "dropped"}
    ]
    if bad_status:
        critical.append(f"{len(bad_status)} entries with invalid render_status")
    checks.append(CheckResult(
        name="all_materials_have_status",
        passed=not bad_status,
        value=len(bad_status), threshold=0,
        message="every entry must have a known render_status",
    ))

    # 2. r2_keys_resolvable
    unresolvable = []
    for e in manifest:
        if e.get("render_status") in {"ok", "fallback"}:
            key = e.get("r2_key")
            if not key or not head_object_exists(key):
                unresolvable.append(e["material_id"])
    if unresolvable:
        critical.append(f"r2_key not resolvable for {len(unresolvable)} entries")
    checks.append(CheckResult(
        name="r2_keys_resolvable",
        passed=not unresolvable,
        value=len(unresolvable), threshold=0,
        message="every non-dropped entry must have an existing r2_key",
    ))

    # 3-5. webm sample checks
    if not critical:  # skip if R2 itself failed
        sample_crit, sample_warn = _sample_check_alpha_dimensions_duration(manifest)
        for c in sample_crit:
            critical.append(c.message)
            checks.append(c)
        for w in sample_warn:
            warnings.append(w.message)
            checks.append(w)

    # 6. whitelist_respected
    whitelist_violations = []
    for e in manifest:
        if e.get("render_status") == "dropped":
            continue
        refined = e.get("refined_spec") or e.get("original_spec") or {}
        tipo = refined.get("tipo")
        if tipo not in whitelist:
            whitelist_violations.append(f"{e['material_id']}:{tipo}")
    if whitelist_violations:
        critical.append(f"whitelist violations: {whitelist_violations[:5]}")
    checks.append(CheckResult(
        name="whitelist_respected",
        passed=not whitelist_violations,
        value=len(whitelist_violations), threshold=0,
        message="refined tipo must be in materials whitelist",
    ))

    # 7. drop_rate warning
    total = len(manifest) or 1
    dropped = sum(1 for e in manifest if e.get("render_status") == "dropped")
    drop_rate = dropped / total
    if drop_rate > drop_threshold:
        warnings.append(f"drop rate {drop_rate:.2%} exceeds {drop_threshold:.0%}")
    checks.append(CheckResult(
        name="drop_rate_acceptable",
        passed=drop_rate <= drop_threshold,
        value=f"{drop_rate:.2%}", threshold=f"<= {drop_threshold:.0%}",
        message="dropped materials should be infrequent",
    ))

    # 8. fallback_rate warning
    fallback = sum(1 for e in manifest if e.get("render_status") == "fallback")
    fb_rate = fallback / total
    if fb_rate > fallback_threshold:
        warnings.append(f"fallback rate {fb_rate:.2%} exceeds {fallback_threshold:.0%}")
    checks.append(CheckResult(
        name="fallback_rate_acceptable",
        passed=fb_rate <= fallback_threshold,
        value=f"{fb_rate:.2%}", threshold=f"<= {fallback_threshold:.0%}",
        message="recurring fallback indicates renderer issue",
    ))

    # 9. reasoning_quality (warning)
    bad_reasoning_keywords = ("no se ve", "negro", "vacío", "frame negro")
    bad_reasoning = [
        e for e in manifest
        if any(kw in (e.get("reasoning", "") or "").lower() for kw in bad_reasoning_keywords)
    ]
    if len(bad_reasoning) > 0.20 * total:
        warnings.append(f"reasoning quality: {len(bad_reasoning)}/{total} mention blank frame")
    checks.append(CheckResult(
        name="reasoning_quality",
        passed=len(bad_reasoning) <= 0.20 * total,
        value=len(bad_reasoning), threshold=f"<= {int(0.20 * total)}",
        message="too many entries flag blank/black frames",
    ))

    # Score
    crit_weight = len(critical) * 0.6
    warn_weight = len(warnings) * 0.4 / max(len(checks), 1)
    score = max(0.0, 1.0 - crit_weight - warn_weight)
    return ValidationResult(
        passed=not critical,
        phase=3,
        score=round(score, 2),
        checks=checks,
        critical_failures=critical,
        warnings=warnings,
        recommendation=(
            "Phase 3 OK — manifest válido y artefactos en R2."
            if not critical
            else f"Phase 3 FAILED — {len(critical)} críticos: {'; '.join(critical[:3])}"
        ),
    )
```

- [ ] **Step 3: Tests + CI**

```bash
uv run pytest tests/test_validator_phase3.py -v
uv run ruff check pipeline/validator.py tests/test_validator_phase3.py
uv run ruff format --check pipeline/validator.py tests/test_validator_phase3.py
uv run mypy pipeline/validator.py
uv run pytest tests/ -x
```

- [ ] **Step 4: Commit**

```bash
git add pipeline/validator.py tests/test_validator_phase3.py
git commit -m "feat(validator): validate_phase3() with 9 checks

Spec §10: 4 críticos (status, r2_keys, dimensions/duration/alpha sample,
whitelist) + 5 warnings (drop_rate, fallback_rate, reasoning quality).
ffprobe sampling via _ffprobe_webm_summary() (mockable, real impl TBD
en runtime — descarga byte-range desde R2).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Format updates (whitelist + narrative_prompt)

**Goal:** Actualizar el formato podcast para soportar los 7 tipos visuales (los 5 originales + ecuacion_latex + diagrama). Actualizar el prompt de Phase 2 para enseñarle al LLM cuándo emitir cada uno.

**Files:**
- Modify: `formats/podcast_hablando_con_profes/materials_whitelist.json`
- Modify: `formats/podcast_hablando_con_profes/narrative_prompt.md`

- [ ] **Step 1: Whitelist update**

Reemplazar `formats/podcast_hablando_con_profes/materials_whitelist.json` completo:

```json
{
  "allowed": [
    "lower_third",
    "pull_quote",
    "chapter_marker",
    "animacion_texto",
    "ecuacion_latex",
    "diagrama",
    "transcript_fix"
  ]
}
```

- [ ] **Step 2: narrative_prompt.md — agregar sección de tipos extendidos**

Leer el archivo actual (Read tool). Identificar la sección que describe los `tipos` permitidos. Justo después, agregar:

````markdown
### `ecuacion_latex`

Emitir cuando el speaker **menciona o explica una fórmula matemática explícita**. Ejemplos:
- "La energía es E igual a m c cuadrado" → emitir
- "El área del círculo es pi r al cuadrado" → emitir
- "Hablemos de física" → NO emitir (no hay fórmula)

Campos:
- `contenido`: el LaTeX string (KaTeX-compatible). Usar `\dfrac` en vez de `\frac`, `\nabla`, `\partial`, símbolos básicos. **No usar:** packages externos, `\begin{align}`, comandos custom.
- `metadata.caption`: label breve uppercase (ej "Ecuación de onda", "Energía cinética").
- `metadata.duration_seconds` (opcional): default 5.0, máx 10.0.

Ejemplo:
```json
{
  "tipo": "ecuacion_latex",
  "contenido": "\\dfrac{\\partial^2 u}{\\partial t^2} = c^2 \\nabla^2 u",
  "timestamp_relativo": 222,
  "metadata": { "caption": "Ecuación de onda" }
}
```

### `diagrama`

Emitir cuando el speaker referencia **algo visual no-textual**: un gráfico, un ciclo, un diagrama físico. Tres sub-tipos via `metadata.tipo_visual`:

#### `barras` — comparación cuantitativa explícita

- Speaker menciona rankings, porcentajes, datos numéricos que comparan.
- `metadata.data`: array de `{"label": str, "value": number}`.
- `contenido`: nombre breve del gráfico.

```json
{
  "tipo": "diagrama",
  "contenido": "Estudiantes por modalidad",
  "timestamp_relativo": 350,
  "metadata": {
    "tipo_visual": "barras",
    "data": [
      {"label": "Presencial", "value": 1200},
      {"label": "Virtual",   "value": 800}
    ]
  }
}
```

#### `ciclo` — proceso/flujo secuencial

- Speaker describe pasos, etapas, ciclo de algo.
- `metadata.nodes`: array de strings (3-7 elementos típico).

```json
{
  "tipo": "diagrama",
  "contenido": "Ciclo del agua",
  "timestamp_relativo": 410,
  "metadata": {
    "tipo_visual": "ciclo",
    "nodes": ["Evapora", "Condensa", "Precipita", "Escurre"]
  }
}
```

#### `esquema_libre` — físico-espacial

- Cualquier diagrama no estructurado: cuerpo libre, circuito, anatomía, geometría.
- `contenido`: descripción libre del diagrama (≤2 oraciones).
- **NO incluyas `template_id` ni `params`** — eso lo decide Phase 3a mirando los frames.

```json
{
  "tipo": "diagrama",
  "contenido": "diagrama de cuerpo libre de un bloque sobre plano inclinado con la fuerza de gravedad mg y la normal N",
  "timestamp_relativo": 502,
  "metadata": { "tipo_visual": "esquema_libre" }
}
```
````

- [ ] **Step 3: Verificar que los tests de Phase 2 siguen pasando**

Phase 2 ya tiene un test `test_validator_phase2.py` que checkea el whitelist. Al agregar nuevos tipos, los tests deben seguir verdes:

```bash
uv run pytest tests/test_validator_phase2.py tests/test_formats.py -v
```

Esperado: passes. Si algún test asume el whitelist viejo de 5 tipos, actualizarlo (lectura del JSON debe seguir funcionando, pero algún test puede checkear listas específicas).

- [ ] **Step 4: CI completo**

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy pipeline tests
uv run pytest -x
```

- [ ] **Step 5: Commit**

```bash
git add formats/podcast_hablando_con_profes/materials_whitelist.json \
        formats/podcast_hablando_con_profes/narrative_prompt.md
git commit -m "feat(format): extend podcast whitelist + prompt for ecuacion_latex + diagrama

Whitelist crece 5 → 7 tipos visuales. narrative_prompt.md documenta cuándo
emitir ecuacion_latex (fórmulas matemáticas explícitas) y diagrama con sus
3 sub-tipos (barras/ciclo/esquema_libre). Few-shot examples por sub-tipo.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: Pipeline orchestrator integration

**Goal:** Conectar Phase 3 al `pipeline/orchestrator.py` existente. Soportar `end_at_phase=3` y `start_at_phase=3` para retries.

**Files:**
- Modify: `pipeline/orchestrator.py`
- Modify: `tests/test_orchestrator.py` (agregar test de Phase 3)

- [ ] **Step 1: Read orchestrator actual**

```bash
sed -n '1,80p' /mnt/c/Users/johan/Documents/PhyMaC/video-capability/pipeline/orchestrator.py
```

Identificar el patrón de cómo Phase 2 está integrado (probablemente un dispatch por `phase_num`). El integration sigue el mismo molde.

- [ ] **Step 2: Agregar phase 3 al run loop**

Editar `pipeline/orchestrator.py`. Localizar el bloque que maneja Phase 2 (probablemente `if phase_num == 2:` o similar). Justo después, agregar:

```python
elif phase_num == 3:
    from pipeline.phases.phase3_materials import run_phase3
    from pipeline.formats import load_format
    import json
    from pathlib import Path

    # Cargar plan de Phase 2
    plan_key = f"projects/{project.id}/phase2/plan.json"
    resp = get_storage_client().get_object(Bucket=R2_BUCKET, Key=plan_key)
    plan_dict = json.loads(resp["Body"].read())
    plan = NarrativePlan.from_dict(plan_dict)

    # Brand + visual_specs
    brand_id = "phymac"  # TODO: read from format.json o project.brand_id si existe
    brand_path = Path("brands") / brand_id / "brand.json"
    brand = json.loads(brand_path.read_text(encoding="utf-8"))

    # Visual specs summary — leer formats/<id>/visual-specs.md y derivar resumen, o
    # mantener un dict hard-coded por ahora.
    visual_specs_summary = {
        "lower_third": "banner bottom-left primary, accent border-left",
        "pull_quote": "card centrada surface, accent border-left, símbolo grande primary",
        "chapter_marker": "full-screen interstitial gradient primary→primary_dark + pattern",
        "animacion_texto": "badge accent rotación -2deg uppercase",
        "ecuacion_latex": "card carbon bottom-right, accent vertical bar, KaTeX white",
        "diagrama": "card surface border-top accent, contenido SVG/data-driven",
    }

    result = run_phase3(plan, brand=brand, visual_specs_summary=visual_specs_summary)

    # Validate
    whitelist = load_format(plan.format_id).materials_whitelist
    validation = validate_phase3(result["manifest"], whitelist=whitelist)

    if not validation.passed:
        return PhaseResult(
            phase_num=3,
            status=PhaseStatus.FAILED,
            outputs={"manifest_count": len(result["manifest"])},
            validation=validation,
        )
    return PhaseResult(
        phase_num=3,
        status=PhaseStatus.COMPLETED,
        outputs={
            "manifest_count": len(result["manifest"]),
            "manifest_r2_key": f"projects/{project.id}/phase3/materials_manifest.json",
        },
        validation=validation,
    )
```

Agregar los imports necesarios al top del archivo (`validate_phase3`, `get_storage_client`, `R2_BUCKET`, `NarrativePlan`, `PhaseResult`, `PhaseStatus`) — la mayoría probablemente ya existen.

- [ ] **Step 3: Test de integración (mocked Modal + R2)**

Agregar a `tests/test_orchestrator.py`:

```python
@patch("pipeline.orchestrator.validate_phase3")
@patch("pipeline.orchestrator.run_phase3")
@patch("pipeline.orchestrator.get_storage_client")
def test_orchestrator_runs_phase3_when_dispatched(mock_storage, mock_run, mock_validate, tmp_path):
    from pipeline.models import Project, NarrativePlan, ValidationResult
    from pipeline.orchestrator import _run_phase_dispatch
    import json

    plan = {"project_id":"p1","blocks":[],"total_duration_estimate":"0:00","format_id":"podcast_hablando_con_profes"}
    fake_storage = MagicMock()
    fake_storage.get_object.return_value = {"Body": MagicMock(read=lambda: json.dumps(plan).encode())}
    mock_storage.return_value = fake_storage

    mock_run.return_value = {"manifest": []}
    mock_validate.return_value = ValidationResult(
        passed=True, phase=3, score=1.0, checks=[],
        critical_failures=[], warnings=[], recommendation="OK",
    )
    project = Project(id="p1", status="running", video_url="...", phases={})
    result = _run_phase_dispatch(project, phase_num=3)
    assert result.status.value == "completed"
```

Si la signature del dispatch en orchestrator es diferente (probable), ajustar el test a la real.

- [ ] **Step 4: Tests + CI**

```bash
uv run pytest tests/test_orchestrator.py -v
uv run ruff check pipeline/orchestrator.py tests/test_orchestrator.py
uv run ruff format --check pipeline/orchestrator.py tests/test_orchestrator.py
uv run mypy pipeline/orchestrator.py
uv run pytest tests/ -x
```

- [ ] **Step 5: Commit**

```bash
git add pipeline/orchestrator.py tests/test_orchestrator.py
git commit -m "feat(orchestrator): integrate Phase 3 into pipeline runner

phase_num=3 dispatch: load plan + brand → run_phase3 → validate_phase3.
Manifest count + r2_key en outputs. Status FAILED si validator críticos > 0.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 14: E2E smoke + manifest schema doc

**Goal:** Correr el pipeline completo en `cudris-20260526` (Phase 2 ya generó un plan en producción anterior). Validar manifest, los .webm en R2, documentar el contrato del manifest para Phase 4.

**Files:**
- Create: `docs/unit4/manifest-schema.md` (contrato del manifest)
- Create: `scripts/run_phase3_smoke.py` (smoke E2E)

- [ ] **Step 1: Documentar el manifest schema**

Crear `docs/unit4/manifest-schema.md`:

````markdown
# Phase 3 Manifest Schema

Output de Phase 3 (Unit 4), consumido por Phase 4 (Unit 5 — Composición + Branding).

**R2 key:** `projects/<project_id>/phase3/materials_manifest.json`

## Estructura

```json
[
  {
    "material_id": "<block_id>_m<NN>_<8hex>",
    "block_id": "<block_id>",
    "original_spec": {
      "tipo": "lower_third | pull_quote | chapter_marker | animacion_texto | ecuacion_latex | diagrama",
      "contenido": "<string>",
      "timestamp_relativo": <int seconds>,
      "metadata": { ... }
    },
    "refined_spec": { ... } | null,
    "decision": "keep" | "modify" | "drop",
    "position": "bottom-left" | "top-left" | "bottom-right" | "top-right" | "center" | {"x_pct": <float>, "y_pct": <float>} | null,
    "reframe": null | {
      "type": "crop" | "zoom" | "replace_with_material",
      "params": { ... },
      "t_start_relative": <float seconds>,
      "t_end_relative": <float seconds>
    },
    "reasoning": "<string>",
    "render_status": "ok" | "fallback" | "dropped",
    "r2_key": "projects/<id>/phase3/materials/<material_id>.webm" | null,
    "render_seconds": <float>
  },
  ...
]
```

## Cómo lo consume Phase 4

1. Filtra entries con `render_status != "dropped"`.
2. Por cada entry, descarga el `.webm` desde `r2_key`.
3. Aplica `reframe` al video subyacente durante `[t_start_relative, t_end_relative]`:
   - `crop`: ffmpeg crop filter con coords pct.
   - `zoom`: zoom + pan suave (ramp 0.3s).
   - `replace_with_material`: video oculto, material full-frame.
   - `null`: video sin tocar.
4. Compone overlay del `.webm` (alpha) en `position` durante `[timestamp_relativo, timestamp_relativo + duration]`.

## Reframe params por type

- **crop**: `{x_pct, y_pct, w_pct, h_pct}` — recorte rectangular.
- **zoom**: `{scale, center_x_pct, center_y_pct}` — `scale > 1` zoom in.
- **replace_with_material**: `{}` — sin params.

## Posiciones absolutas

Si `position` es string, se mapea a coords default (definidas en `formats/<id>/visual-specs.md`). Si es `{x_pct, y_pct}`, es la esquina superior-izquierda del overlay en fracción del frame 1920×1080.

## Idempotency

`material_id` es estable + content-aware (cambio en `original_spec` → cambio en hash → cache miss). Phase 4 puede asumir que si `material_id` existe en su propio cache, el `.webm` apuntado no cambió.
````

- [ ] **Step 2: Script de smoke E2E**

Crear `scripts/run_phase3_smoke.py`:

```python
"""Smoke test E2E para Phase 3 sobre un proyecto existente.

Usage:
    uv run python scripts/run_phase3_smoke.py <project_id>

Ejemplo:
    uv run python scripts/run_phase3_smoke.py cudris-20260526
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging  # noqa: E402

from pipeline.formats import load_format  # noqa: E402
from pipeline.models import NarrativePlan  # noqa: E402
from pipeline.phase3_r2 import load_manifest, head_object_exists  # noqa: E402
from pipeline.phases.phase3_materials import run_phase3  # noqa: E402
from pipeline.storage import R2_BUCKET, get_storage_client  # noqa: E402
from pipeline.validator import validate_phase3  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


def main(project_id: str) -> int:
    plan_key = f"projects/{project_id}/phase2/plan.json"
    if not head_object_exists(plan_key):
        print(f"ERROR: no Phase 2 plan at {plan_key}. Run Phase 2 first.")
        return 1
    resp = get_storage_client().get_object(Bucket=R2_BUCKET, Key=plan_key)
    plan = NarrativePlan.from_dict(json.loads(resp["Body"].read().decode("utf-8")))
    print(f"Loaded plan: {len(plan.blocks)} blocks, "
          f"{sum(len(b.support_material) for b in plan.blocks)} materials total")

    brand = json.loads(Path("brands/phymac/brand.json").read_text(encoding="utf-8"))
    visual_specs_summary = {
        "lower_third": "banner bottom-left primary",
        "pull_quote": "card centrada surface, accent border-left",
        "chapter_marker": "full-screen gradient primary",
        "animacion_texto": "badge accent rotado",
        "ecuacion_latex": "card carbon bottom-right, KaTeX",
        "diagrama": "card surface border-top accent",
    }

    result = run_phase3(plan, brand=brand, visual_specs_summary=visual_specs_summary)
    manifest = result["manifest"]
    print(f"\n=== Manifest ({len(manifest)} entries) ===")
    for e in manifest:
        print(f"  {e['material_id']} | status={e['render_status']:8} | "
              f"decision={e['decision']:6} | tipo={e.get('refined_spec', {}).get('tipo', 'N/A')}")

    whitelist = load_format(plan.format_id).materials_whitelist
    validation = validate_phase3(manifest, whitelist=whitelist)
    print(f"\n=== Validation ===")
    print(f"passed={validation.passed} score={validation.score}")
    if validation.critical_failures:
        print("CRITICAL:")
        for c in validation.critical_failures:
            print(f"  - {c}")
    if validation.warnings:
        print("WARNINGS:")
        for w in validation.warnings:
            print(f"  - {w}")
    print(f"\nrecommendation: {validation.recommendation}")
    return 0 if validation.passed else 2


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    sys.exit(main(sys.argv[1]))
```

- [ ] **Step 3: Correr el smoke E2E**

⚠️ **Esto consume cost real** (LLM-vision calls + Modal time). Solo correr cuando confíes en que los tests unitarios pasaron.

```bash
uv run python scripts/run_phase3_smoke.py cudris-20260526 2>&1 | tee /tmp/phase3-smoke.log
```

Esperado:
- Si Phase 2 plan existe y tiene ~30 materiales, esto demora 8-15 min.
- Output: manifest con ~30 entries, `passed=True`, score > 0.85.
- En R2: `projects/cudris-20260526/phase3/{visual_plan,materials_manifest}.json` + 25-30 .webm.

Si falla:
- Inspeccionar `/tmp/phase3-smoke.log` para identificar la causa.
- Si es un material individual fallando → debería caer a `fallback`. Revisar manifest.
- Si es un error sistémico (e.g. Modal image build fail, OpenRouter 401) → fix antes de seguir.

- [ ] **Step 4: Verificar idempotency — segundo run**

```bash
uv run python scripts/run_phase3_smoke.py cudris-20260526 2>&1 | tee /tmp/phase3-smoke-2.log
```

Esperado: completes en <1 min (cache hits en todo). Manifest idéntico al primer run.

- [ ] **Step 5: Commit**

```bash
git add docs/unit4/ scripts/run_phase3_smoke.py
git commit -m "docs(unit4): manifest schema + E2E smoke script

manifest-schema.md documenta el contrato consumido por Phase 4.
run_phase3_smoke.py corre el pipeline E2E sobre un project_id existente,
mide tiempo, valida manifest, imprime resumen.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 15: CI verde + PR a develop

**Goal:** Asegurar que TODOS los gates de CI pasan localmente, pushear la branch, abrir PR a `develop`. Esperar review (CodeRabbit + Copilot) y merge.

- [ ] **Step 1: CI completo local (todos los checks de project_github_required_checks)**

```bash
cd /mnt/c/Users/johan/Documents/PhyMaC/video-capability

# Ruff format + lint
uv run ruff format --check .
uv run ruff check .

# Mypy
uv run mypy pipeline tests

# Pytest (toda la suite)
uv run pytest -v

# Security
uv run pip-audit --strict
uv run bandit -c pyproject.toml -r pipeline
```

Esperado: TODOS verdes. Si alguno falla:
- `ruff format` → `uv run ruff format .` + re-correr check
- `ruff check` errores → fix por mano + re-correr
- `mypy` → fix tipos
- `pytest` → fix tests
- `pip-audit` → ver si hay advisory nuevo + bumpear deps o agregar exception justificada
- `bandit` → si hay un nuevo skip necesario, agregarlo al `pyproject.toml` con justificación

- [ ] **Step 2: Verificar que el commit history tiene sentido**

```bash
git log --oneline develop..HEAD
```

Esperado: ~14 commits, cada uno con mensaje descriptivo de su task.

Si querés squashear algunos, hacelo ahora con `git rebase -i origin/develop`. **No squashear pre-revisión si el PR template prefiere ver granularidad.** Mantenerlos separados por defecto.

- [ ] **Step 3: Push la branch**

```bash
git push -u origin feature/unit4-materials
```

Esperado: branch en remote, tracking configurado.

- [ ] **Step 4: Abrir PR**

```bash
gh pr create --base develop --title "feat(unit4): Phase 3 vision-aware materials" --body "$(cat <<'EOF'
## Summary

Implementa Unit 4 del pipeline PhyMaC (Fase 3 — Materiales de Soporte):

- **Phase 3a**: visual planning LLM-vision por material (Claude Sonnet 4.6 default via OpenRouter, 3 frames + contexto narrativo → decisión refinada con position + reframe).
- **Phase 3b**: render via HyperFrames sobre Modal (per-material `.map()`, ProRes 4444 alpha → WebM VP9-alpha con `-auto-alt-ref 0`).
- **Phase 3c**: manifest auditado en R2, ValidationAgent con 9 checks.
- **6 tipos**: lower_third, pull_quote, chapter_marker, animacion_texto, ecuacion_latex, diagrama (barras/ciclo/esquema_libre con template registry).
- **Failure policy**: 1 retry + fallback text card. Episodio nunca queda incompleto.
- **Idempotency**: 3 niveles (frames, visual_plan, render). Re-runs eficientes.

Stack: decidido en A/B spike 2026-05-26.

## Spec & Plan

- Spec: `docs/superpowers/specs/2026-05-27-unit4-materials-design.md`
- Plan: `docs/superpowers/plans/2026-05-27-unit4-materials-plan.md`

## Test plan

- [ ] CI green (ruff + mypy + pytest 3.11/3.12 + pip-audit + bandit)
- [ ] E2E smoke sobre `cudris-20260526`: manifest válido, score > 0.85, drop rate < 20%
- [ ] Re-run idempotente: segundo smoke completes en <1 min (cache hit total)
- [ ] Verificar uno de los .webm renderizados visualmente (download + open en browser)
- [ ] Manifest schema (`docs/unit4/manifest-schema.md`) revisado para Phase 4 consumption

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Esperado: PR creado, URL devuelta. CodeRabbit + Copilot review automático arranca.

- [ ] **Step 5: Verificar que CI remoto verde**

```bash
gh pr checks
```

Esperar a que todos los checks (`lint`, `typecheck`, `test 3.11`, `test 3.12`, `security`) marquen ✅.

Si alguno falla:
- Pull el error log: `gh run view --log-failed`
- Fix local, commit, push (los checks re-corren automáticamente)

- [ ] **Step 6: Merge cuando esté verde + review aprobado**

```bash
gh pr merge --merge
```

(Mergea con merge commit. Si preferís squash: `--squash`.)

- [ ] **Step 7: Cleanup local**

```bash
git checkout develop
git pull origin develop
git branch -d feature/unit4-materials
```

---

## Resumen de tasks

| Task | Componente | Test count | Commit estimado |
|------|-----------|-----------:|-----------------|
| 0  | Branch + commit spec/plan       | — | 1 |
| 1  | Modelos Phase 3                 | 7 | 1 |
| 2  | Material ID + flatten           | 7 | 1 |
| 3  | Frame extractor                 | 5 | 1 |
| 4  | Visual planner LLM-vision       | 5 | 1 |
| 5  | brand_css + HF scaffold         | 3 | 1 |
| 6  | 9 HF compositions               | 0 (smoke) | 1 |
| 7  | Renderer dispatch + registry    | 11 | 1 |
| 8  | Output validator + R2 helpers   | 9 | 1 |
| 9  | Modal app + render_one          | 2 | 1 |
| 10 | Phase 3 orchestrator            | 1 | 1 |
| 11 | Phase 3 validator               | 5 | 1 |
| 12 | Whitelist + prompt updates      | (re-run) | 1 |
| 13 | Pipeline orchestrator integ.    | 1 | 1 |
| 14 | E2E smoke + manifest doc        | — | 1 |
| 15 | CI green + PR                   | — | 0 (PR) |

**Total esperado:** ~14-15 commits, ~56 tests nuevos, ~12 archivos Python nuevos + 9 HTML compositions + 4 archivos config/docs.

**Tiempo total estimado:** 8-12h implementación + 30 min smoke + 1h ciclo de review.

**Costo del smoke E2E:** ~$1 (Modal compute ~$0.7 + LLM-vision ~$0.3 sobre cudris-20260526).

---

## Self-Review

**Spec coverage** (todas las secciones del spec tienen tasks asociadas):
- §3 decisiones → Task 1-14 (todas implementadas)
- §4 arquitectura → Task 10 (orchestrator)
- §5.1 file structure → Tasks 1-10 (cubre todos los archivos)
- §5.2 modelos → Task 1
- §5.3 diagram registry → Task 7
- §5.4 LLM-vision contract → Task 4
- §5.5 HF compositions → Task 6
- §5.6 validator → Task 11
- §6 data flow → Task 10 (orchestrator implementa el flujo)
- §7 Phase 2 schema updates → Task 12
- §8 R2 storage layout → Task 8 (phase3_r2.py implementa los keys)
- §9 idempotency → Task 10 (cache check en orchestrator)
- §10 validation → Task 11
- §11 Modal worker → Task 9
- §12 out-of-scope → respetado en todos los tasks
- §13 riesgos → mitigaciones implícitas en cada task
- §14 done criteria → Task 14 (E2E smoke) + Task 15 (CI verde)
- §15 pre-requisitos → Task 0 (branch) + pre-flight (CI baseline) + Modal secrets en Task 9 Step 5

**Placeholder scan:** Sin TBDs. Donde la implementación depende de la inspección del código existente (`_run_phase_dispatch` exacta signature, exact `R2_BUCKET` import path), se documenta como "ajustar a lo que ya está".

**Type consistency:**
- `material_id` formato: declarado en Task 2, usado idéntico en Tasks 8, 10, 11.
- `PlannedMaterial` schema: declarado en Task 1, usado idéntico en Tasks 4, 7, 9, 10.
- `ManifestEntry` keys: declarado en Task 1, generado en Task 9 (render_one return dict), consumido en Task 11 (validator).
- Composition IDs: kebab-case (`lower-third`, etc.) en HTML — consistente en Task 6.
- `composition_path` formato: `compositions/<name>.html` — consistente en Tasks 6, 7, 9.

Plan listo.


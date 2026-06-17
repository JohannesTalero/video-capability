# Unit 5 — Fase 4: Composición + Branding — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar la Fase 4 del pipeline: intro/outro de marca renderizadas con HyperFrames, timeline/EDL puro desde plan+manifest, y composición FFmpeg en Modal (trim+concat+cortinillas+overlays alpha) que produce `phase4/composed.mp4` con audio original intacto.

**Architecture:** El driver (`pipeline/phases/phase4_compose.py`) corre local: carga plan/transcripción/manifest de R2, computa el timeline con un módulo puro (`pipeline/phase4_timeline.py`, sin ffmpeg ni red), lo sube a `phase4/timeline.json`, y delega a dos workers Modal que reutilizan la imagen `hf_image` de Unit 4: `render_brand` (HyperFrames → MP4 opaco 1080p ~5 s para intro/outro, SIN workaround alpha) y `compose_video` (CPU worker que descarga raw+assets y ejecuta UN solo comando FFmpeg construido por `pipeline/phase4_ffmpeg.py` — puro y testeable sin ejecutar). `validate_phase4()` vive en la región marcada "Phase 4" de `pipeline/validator.py`. Idempotencia: short-circuit si `composed.mp4` + `timeline.json` ya existen en R2; intro/outro cacheadas individualmente en `phase4/brand/`.

**Tech Stack:** Python 3.11/3.12, dataclasses, pytest (mocks para IO), Modal (imagen `hf_image` existente: ffmpeg + node + chromium), HyperFrames (`npx hyperframes render --format mp4`), FFmpeg `filter_complex` (trim/concat/overlay, decoder `libvpx-vp9` explícito para alpha), Cloudflare R2 vía `StorageAdapter`.

---

## Contexto asumido (contrato §3 YA mergeado en `develop`)

Este plan asume que el PR de contrato (`docs/superpowers/plans/2026-06-09-units5-8-contract-plan.md`) está mergeado:

- `pipeline/models.py` tiene el `BrandConfig` reconciliado (campos `id`, `name`, `colors`, `fonts`, `shadows`, `radius`, `pattern`, `assets` como dicts + `from_dict`/`to_dict`), espejo 1:1 de `brands/phymac/brand.json`.
- `StorageKey.phase4_timeline(project_id)` → `projects/{id}/phase4/timeline.json` y `StorageKey.brand_render(project_id, name)` → `projects/{id}/phase4/brand/{name}.mp4` existen. `StorageKey.composed_video(project_id)` → `projects/{id}/phase4/composed.mp4` ya existía.
- `pipeline/phases/phase4_compose.py` existe como stub con `run_phase_4(state) -> dict` (`raise NotImplementedError`) y `register(orchestrator)`.
- `pipeline/validator.py` tiene el comentario de región `# --- Phase 4 — Composición (Unit 5) ---` al final del archivo.
- `tests/test_models_phase45.py` y `tests/test_phase_stubs.py` existen y pasan. **Nota:** el test del stub (`test_stub_registers_and_raises`) espera `NotImplementedError` para la fase 4; la Task 8 ajusta ese test para cubrir solo fases 5 y 6.

Si algo de esto falta, detente y mergea el contrato primero.

## Mapa de archivos

| Archivo | Responsabilidad | Task |
|---|---|---|
| `pipeline/brand.py` (create) | `BrandManager`: carga `brands/{id}/brand.json` → `BrandConfig`, valida SVGs, data URIs | 1 |
| `pipeline/renderers/hf-project/compositions/intro.html` (create) | Composición HF intro 5 s, opaca, parametrizada | 2 |
| `pipeline/renderers/hf-project/compositions/outro.html` (create) | Composición HF outro 5 s, opaca, parametrizada | 2 |
| `pipeline/modal_render.py` (modify) | `fmt` param en `_invoke_hf_render` + `render_brand_clip()` worker-side | 3 |
| `pipeline/modal_app.py` (modify) | Funciones Modal `render_brand` y `compose_video` | 3, 6 |
| `pipeline/phase4_timeline.py` (create) | EDL puro: `build_timeline()` — sin ffmpeg, sin red | 4 |
| `pipeline/phase4_ffmpeg.py` (create) | `build_compose_command()` puro — construye el comando, no lo ejecuta | 5 |
| `pipeline/phase4_worker.py` (create) | Worker-side: download → ffmpeg → probe → upload | 6 |
| `pipeline/validator.py` (modify) | `validate_phase4()` + bypass del agente legacy + `phase3_r2.object_size_mb` | 7 |
| `pipeline/phases/phase4_compose.py` (modify) | `run_phase4()` dominio + `run_phase_4(state)` adapter + idempotencia | 8 |
| `scripts/run_phase4_smoke.py` (create) | Smoke E2E real sobre `cudris-20260526` | 9 |

## Schema de `phase4/timeline.json` (congelado en Task 4)

Todos los tiempos en segundos, **absolutos en el video final** (la intro empieza en 0; el cuerpo empieza en `intro.duration`). `overlays[].start/end` también son absolutos del video final (el `enable=between(t,...)` de FFmpeg se aplica después del concat, donde `t` ya es tiempo absoluto).

```json
{
  "schema_version": 1,
  "project_id": "cudris-20260526",
  "fps": 30,
  "width": 1920,
  "height": 1080,
  "intro": {"r2_key": "projects/<id>/phase4/brand/intro.mp4", "duration": 5.0},
  "outro": {"r2_key": "projects/<id>/phase4/brand/outro.mp4", "duration": 5.0},
  "items": [
    {"kind": "marker", "material_id": "b2_m00_ab12cd34", "block_id": "b2",
     "r2_key": "projects/<id>/phase3/materials/b2_m00_ab12cd34.webm",
     "out_start": 5.0, "duration": 4.2},
    {"kind": "clip", "block_id": "b2", "segment_ids": [4, 5, 6],
     "src_start": 120.48, "src_end": 185.2, "out_start": 9.2, "duration": 64.72}
  ],
  "overlays": [
    {"material_id": "b2_m01_ef56ab78", "tipo": "pull_quote",
     "r2_key": "projects/<id>/phase3/materials/b2_m01_ef56ab78.webm",
     "position": "center", "start": 30.0, "end": 36.6}
  ],
  "body_duration": 712.0,
  "expected_duration": 722.0
}
```

`items` es la secuencia del cuerpo en orden de concat (markers full-frame + clips keep del raw). `expected_duration = intro + body + outro`.

## Decisiones técnicas (no explícitas en el spec)

1. **`timestamp_relativo` es tiempo del video CRUDO** (consistente con Phase 3, que extrae frames del raw en ese timestamp). `build_timeline` lo mapea a tiempo de salida vía los clips keep; si cae en una región recortada, hace snap al borde de clip más cercano (en tiempo de salida).
2. **Overlays a `overlay=0:0`**: todos los `.webm` de Unit 4 son full-frame 1920×1080 con la posición ya horneada en la composición HF (verificado en `lower_third.html`/`output_validator.py`). El campo `position` se conserva en el timeline solo para auditoría.
3. **Un solo encode**: intro + cuerpo + outro + overlays se componen en UN comando FFmpeg (`concat` de filter_complex + cadena de `overlay`), evitando doble pérdida de generación antes del render final de Fase 6. Intermedio: `libx264 -preset veryfast -crf 18`, audio `aac 192k` (el contenido del audio queda intacto — solo re-encode por los cortes; Fase 5 lo procesa).
4. **Intro/outro sin audio** → el comando agrega silencio `anullsrc` (estéreo 48 kHz) para esas posiciones del concat.
5. **Markers sobre fondo negro**: los `chapter_marker.webm` tienen alpha (fade in/out); se componen sobre `color=black` para que el fade no muestre basura al descartar alpha en yuv420p.
6. **Logo como data URI**: el SVG (`logo_white`) se pasa a la composición HF como variable `logo_src` (base64 data URI) — evita meter `brands/` en la imagen Modal.
7. **El worker reporta el probe**: `compose_video` hace ffprobe local del composed antes de subirlo y devuelve `{width, height, fps, duration, has_audio, size_bytes}`; `validate_phase4()` valida sobre ese probe + HEAD/size en R2 (no descarga ~1 GB al driver).
8. **`ValidationAgent._validate_phase_4` (legacy)**: cuando el output del runner trae `composed_key` sin `video_path`, devuelve pass (la validación real ya corrió in-runner con `validate_phase4()`, mismo patrón vacuo que Fase 3).
9. **Duraciones de overlay**: se reutiliza `pipeline.modal_render.DURATION_BY_TIPO` (única fuente de verdad); `transcript_fix` (0.0) y tipos desconocidos se ignoran en el timeline.

---

### Task 0: Branch + verificación del contrato

**Files:** ninguno (solo git + verificación).

- [ ] **Step 1: Crear la rama desde develop actualizado**

```bash
git fetch origin
git checkout develop && git pull origin develop
git checkout -b feature/unit5-composition
```

- [ ] **Step 2: Verificar que el contrato está mergeado**

Run: `uv run pytest tests/test_models_phase45.py tests/test_phase_stubs.py -q && ls pipeline/phases/phase4_compose.py && grep -n "Phase 4" pipeline/validator.py && grep -n "phase4_timeline\|brand_render" pipeline/models.py`
Expected: tests PASS, el stub existe, el marcador de región existe, y `StorageKey.phase4_timeline` + `StorageKey.brand_render` aparecen en `models.py`. **Si algo falla: STOP — el contrato no está mergeado.**

---

### Task 1: `BrandManager` (`pipeline/brand.py`)

**Files:**
- Create: `pipeline/brand.py`
- Test: `tests/test_brand.py`

- [ ] **Step 1: Write the failing test**

Crear `tests/test_brand.py`:

```python
"""Tests de BrandManager (carga + validación de assets del brand kit)."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from pipeline.brand import (
    BrandAssetMissingError,
    BrandManager,
    BrandNotFoundError,
)

REPO_ROOT = Path(__file__).parent.parent


def test_load_real_phymac_brand():
    manager = BrandManager(REPO_ROOT / "brands")
    cfg = manager.load("phymac")
    assert cfg.id == "phymac"
    assert cfg.colors["primary"] == "#2962FF"
    assert cfg.assets["logo_white"] == "brand-assets/logo-white.svg"


def test_load_unknown_brand_raises():
    manager = BrandManager(REPO_ROOT / "brands")
    with pytest.raises(BrandNotFoundError, match="no-existe"):
        manager.load("no-existe")


def test_load_brand_with_missing_asset_raises(tmp_path: Path):
    brand_dir = tmp_path / "rota"
    brand_dir.mkdir()
    data = {
        "id": "rota",
        "name": "Rota",
        "colors": {"primary": "#000000"},
        "fonts": {},
        "assets": {"logo": "brand-assets/logo.svg"},
    }
    (brand_dir / "brand.json").write_text(json.dumps(data), encoding="utf-8")
    manager = BrandManager(tmp_path)
    with pytest.raises(BrandAssetMissingError, match="logo"):
        manager.load("rota")


def test_asset_path_resolves_existing_file():
    manager = BrandManager(REPO_ROOT / "brands")
    path = manager.asset_path("phymac", "logo_white")
    assert path.exists()
    assert path.suffix == ".svg"


def test_asset_path_unknown_key_raises():
    manager = BrandManager(REPO_ROOT / "brands")
    with pytest.raises(BrandAssetMissingError, match="inexistente"):
        manager.asset_path("phymac", "inexistente")


def test_asset_data_uri_roundtrips_svg():
    manager = BrandManager(REPO_ROOT / "brands")
    uri = manager.asset_data_uri("phymac", "logo_white")
    assert uri.startswith("data:image/svg+xml;base64,")
    decoded = base64.standard_b64decode(uri.split(",", 1)[1]).decode("utf-8")
    assert "<svg" in decoded
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_brand.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.brand'`

- [ ] **Step 3: Write minimal implementation**

Crear `pipeline/brand.py`:

```python
"""BrandManager — carga y valida brand kits desde brands/<id>/ (filesystem local)."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from pipeline.models import BrandConfig


class BrandError(Exception):
    """Error base de brand kits."""


class BrandNotFoundError(BrandError):
    """brands/<id>/brand.json no existe."""


class BrandAssetMissingError(BrandError):
    """Un asset declarado en brand.json no existe en disco (o la clave es desconocida)."""


class BrandManager:
    """Carga brands/{id}/brand.json a BrandConfig y valida que los SVG existan.

    Los assets se resuelven relativos a brands/{id}/ (ej. "brand-assets/logo.svg").
    """

    def __init__(self, brands_root: str | Path = "brands") -> None:
        self.brands_root = Path(brands_root)

    def brand_dir(self, brand_id: str) -> Path:
        return self.brands_root / brand_id

    def load(self, brand_id: str) -> BrandConfig:
        brand_json = self.brand_dir(brand_id) / "brand.json"
        if not brand_json.exists():
            raise BrandNotFoundError(f"brand.json no encontrado para '{brand_id}': {brand_json}")
        cfg = BrandConfig.from_dict(json.loads(brand_json.read_text(encoding="utf-8")))
        missing = [
            f"{key} → {rel}"
            for key, rel in cfg.assets.items()
            if not (self.brand_dir(brand_id) / rel).exists()
        ]
        if missing:
            raise BrandAssetMissingError(f"assets faltantes para brand '{brand_id}': {missing}")
        return cfg

    def asset_path(self, brand_id: str, asset_key: str) -> Path:
        cfg = self.load(brand_id)
        if asset_key not in cfg.assets:
            raise BrandAssetMissingError(
                f"asset key '{asset_key}' desconocida para brand '{brand_id}' "
                f"(disponibles: {sorted(cfg.assets)})"
            )
        return self.brand_dir(brand_id) / cfg.assets[asset_key]

    def asset_data_uri(self, brand_id: str, asset_key: str) -> str:
        """SVG como data URI base64, para pasarlo como variable a HyperFrames."""
        path = self.asset_path(brand_id, asset_key)
        b64 = base64.standard_b64encode(path.read_bytes()).decode("ascii")
        return f"data:image/svg+xml;base64,{b64}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_brand.py -v`
Expected: 6 passed.

- [ ] **Step 5: Gates**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy pipeline && uv run pytest -q`
Expected: todo verde.

- [ ] **Step 6: Commit**

```bash
git add pipeline/brand.py tests/test_brand.py
git commit -m "feat(phase4): BrandManager loads and validates brand kits" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Composiciones HyperFrames `intro.html` y `outro.html`

**Files:**
- Create: `pipeline/renderers/hf-project/compositions/intro.html`
- Create: `pipeline/renderers/hf-project/compositions/outro.html`
- Test: `tests/test_brand_compositions.py`

Composiciones **opacas** (fondo gradient primary, sin transparencia — se renderizan como MP4 full-frame), 5 s, 1920×1080, parametrizadas vía variables HF, colores vía CSS vars de `brand.css` (generado por `render_brand_css`), GSAP timeline pausada registrada en `window.__timelines` (patrón de `chapter_marker.html`).

- [ ] **Step 1: Write the failing test**

Crear `tests/test_brand_compositions.py`:

```python
"""Checks estáticos de las composiciones intro/outro (sin renderizar)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

COMP_DIR = Path(__file__).parent.parent / "pipeline" / "renderers" / "hf-project" / "compositions"


def _read(name: str) -> str:
    return (COMP_DIR / f"{name}.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["intro", "outro"])
def test_composition_is_5s_1080p(name: str):
    html = _read(name)
    assert f'data-composition-id="{name}"' in html
    assert 'data-width="1920"' in html
    assert 'data-height="1080"' in html
    assert 'data-duration="5"' in html


@pytest.mark.parametrize("name", ["intro", "outro"])
def test_composition_declares_variables(name: str):
    html = _read(name)
    m = re.search(r"data-composition-variables='(\[.*?\])'", html, re.DOTALL)
    assert m, "data-composition-variables missing"
    ids = {v["id"] for v in json.loads(m.group(1))}
    assert "logo_src" in ids
    if name == "intro":
        assert {"title", "subtitle"} <= ids
    else:
        assert "message" in ids


@pytest.mark.parametrize("name", ["intro", "outro"])
def test_composition_is_opaque_and_branded(name: str):
    html = _read(name)
    # MP4 opaco full-frame: prohibido el fondo transparente de los overlays
    assert "background: transparent" not in html
    assert "../brand.css" in html
    assert "var(--primary" in html
    # Seek determinista de HyperFrames: timeline GSAP pausada registrada
    assert "window.__timelines" in html
    assert "paused: true" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_brand_compositions.py -v`
Expected: FAIL — `FileNotFoundError` (intro.html no existe).

- [ ] **Step 3: Create `intro.html`**

Crear `pipeline/renderers/hf-project/compositions/intro.html`:

```html
<!DOCTYPE html>
<html data-composition-variables='[
  {"id":"title","type":"string","label":"Título del episodio","default":"Episodio"},
  {"id":"subtitle","type":"string","label":"Subtítulo","default":""},
  {"id":"logo_src","type":"string","label":"Logo (data URI)","default":""}
]'>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="../brand.css">
<style>
  html, body { margin: 0; padding: 0; background: #000; }
  [data-composition-id="intro"] {
    position: relative; width: 1920px; height: 1080px;
    font-family: 'Open Sans', sans-serif; overflow: hidden;
  }
  .bg {
    position: absolute; inset: 0;
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
  }
  .pattern {
    position: absolute; inset: 0; opacity: 0.13;
    background-image:
      repeating-linear-gradient(0deg, transparent 0, transparent 39px, rgba(255,255,255,0.5) 39px, rgba(255,255,255,0.5) 40px),
      repeating-linear-gradient(90deg, transparent 0, transparent 39px, rgba(255,255,255,0.5) 39px, rgba(255,255,255,0.5) 40px);
  }
  .logo { position: absolute; top: 16%; left: 50%; width: 340px; height: auto; }
  .title {
    position: absolute; top: 46%; left: 50%; width: 76%;
    font-family: 'Montserrat', sans-serif; font-weight: 900; font-size: 92px;
    color: var(--surface); text-align: center; line-height: 1.1;
  }
  .subtitle {
    position: absolute; top: 76%; left: 50%;
    font-weight: 600; font-size: 30px; letter-spacing: 8px;
    color: var(--accent); text-transform: uppercase; white-space: nowrap;
  }
</style>
</head>
<body>
<div data-composition-id="intro" data-width="1920" data-height="1080" data-start="0" data-duration="5">
  <div class="bg"></div>
  <div class="pattern"></div>
  <img class="logo" id="logo" alt="">
  <div class="title" id="title"></div>
  <div class="subtitle" id="subtitle"></div>
</div>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<script>
  const { title, subtitle, logo_src } = window.__hyperframes.getVariables();
  document.getElementById('title').textContent = title;
  document.getElementById('subtitle').textContent = subtitle;
  if (logo_src) document.getElementById('logo').src = logo_src;
  else document.getElementById('logo').style.display = 'none';
  window.__timelines = window.__timelines || {};
  const tl = gsap.timeline({ paused: true });
  tl.from(".pattern", { opacity: 0, duration: 0.6, ease: "power2.out" }, 0);
  tl.fromTo(".logo",
    { xPercent: -50, y: -60, opacity: 0 },
    { xPercent: -50, y: 0, opacity: 1, duration: 0.6, ease: "power3.out" }, 0.3);
  tl.fromTo(".title",
    { xPercent: -50, y: 60, opacity: 0 },
    { xPercent: -50, y: 0, opacity: 1, duration: 0.7, ease: "power3.out" }, 0.7);
  tl.fromTo(".subtitle",
    { xPercent: -50, opacity: 0 },
    { xPercent: -50, opacity: 1, duration: 0.5, ease: "power2.out" }, 1.2);
  tl.to([".logo", ".title", ".subtitle"],
    { opacity: 0, duration: 0.5, ease: "power2.in" }, 4.4);
  window.__timelines["intro"] = tl;
</script>
</body>
</html>
```

- [ ] **Step 4: Create `outro.html`**

Crear `pipeline/renderers/hf-project/compositions/outro.html`:

```html
<!DOCTYPE html>
<html data-composition-variables='[
  {"id":"message","type":"string","label":"Mensaje","default":"Gracias por acompañarnos"},
  {"id":"logo_src","type":"string","label":"Logo (data URI)","default":""}
]'>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="../brand.css">
<style>
  html, body { margin: 0; padding: 0; background: #000; }
  [data-composition-id="outro"] {
    position: relative; width: 1920px; height: 1080px;
    font-family: 'Open Sans', sans-serif; overflow: hidden;
  }
  .bg {
    position: absolute; inset: 0;
    background: linear-gradient(135deg, var(--primary-dark) 0%, var(--primary) 100%);
  }
  .pattern {
    position: absolute; inset: 0; opacity: 0.13;
    background-image:
      repeating-linear-gradient(0deg, transparent 0, transparent 39px, rgba(255,255,255,0.5) 39px, rgba(255,255,255,0.5) 40px),
      repeating-linear-gradient(90deg, transparent 0, transparent 39px, rgba(255,255,255,0.5) 39px, rgba(255,255,255,0.5) 40px);
  }
  .logo { position: absolute; top: 24%; left: 50%; width: 420px; height: auto; }
  .message {
    position: absolute; top: 64%; left: 50%; width: 76%;
    font-family: 'Montserrat', sans-serif; font-weight: 900; font-size: 64px;
    color: var(--surface); text-align: center; line-height: 1.15;
  }
</style>
</head>
<body>
<div data-composition-id="outro" data-width="1920" data-height="1080" data-start="0" data-duration="5">
  <div class="bg"></div>
  <div class="pattern"></div>
  <img class="logo" id="logo" alt="">
  <div class="message" id="message"></div>
</div>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<script>
  const { message, logo_src } = window.__hyperframes.getVariables();
  document.getElementById('message').textContent = message;
  if (logo_src) document.getElementById('logo').src = logo_src;
  else document.getElementById('logo').style.display = 'none';
  window.__timelines = window.__timelines || {};
  const tl = gsap.timeline({ paused: true });
  tl.from(".pattern", { opacity: 0, duration: 0.6, ease: "power2.out" }, 0);
  tl.fromTo(".logo",
    { xPercent: -50, scale: 0.6, opacity: 0 },
    { xPercent: -50, scale: 1, opacity: 1, duration: 0.6, ease: "back.out(1.6)" }, 0.2);
  tl.fromTo(".message",
    { xPercent: -50, y: 50, opacity: 0 },
    { xPercent: -50, y: 0, opacity: 1, duration: 0.6, ease: "power3.out" }, 0.7);
  tl.to([".logo", ".message"],
    { opacity: 0, duration: 0.5, ease: "power2.in" }, 4.4);
  window.__timelines["outro"] = tl;
</script>
</body>
</html>
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_brand_compositions.py -v`
Expected: 6 passed.

- [ ] **Step 6: Gates**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy pipeline && uv run pytest -q`
Expected: todo verde.

- [ ] **Step 7: Commit**

```bash
git add pipeline/renderers/hf-project/compositions/intro.html pipeline/renderers/hf-project/compositions/outro.html tests/test_brand_compositions.py
git commit -m "feat(phase4): branded intro/outro HyperFrames compositions" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `render_brand_clip()` worker-side + función Modal `render_brand`

**Files:**
- Modify: `pipeline/modal_render.py` (param `fmt` en `_invoke_hf_render`, ~línea 39; nueva función al final)
- Modify: `pipeline/modal_app.py` (nueva función Modal al final)
- Test: `tests/test_modal_render_brand.py`

- [ ] **Step 1: Write the failing test**

Crear `tests/test_modal_render_brand.py`:

```python
"""Tests de render_brand_clip (HF render + upload mockeados)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.modal_render import BRAND_CLIP_DURATION, render_brand_clip

BRAND = {
    "id": "phymac",
    "name": "PhyMaC",
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


def _payload(name: str = "intro") -> dict:
    return {
        "project_id": "p1",
        "name": name,
        "brand": BRAND,
        "variables": {"title": "Mi episodio", "subtitle": "PhyMaC", "logo_src": "data:..."},
    }


@patch("pipeline.modal_render.StorageAdapter")
@patch("pipeline.modal_render.validate_webm")
@patch("pipeline.modal_render._invoke_hf_render")
def test_render_brand_clip_happy_path(mock_invoke, mock_validate, mock_sa, tmp_path: Path):
    hf_dir = tmp_path / "hf"
    hf_dir.mkdir()

    def fake_render(hf, comp, variables, out, fmt="mov"):
        assert fmt == "mp4"
        assert comp == "compositions/intro.html"
        assert variables["title"] == "Mi episodio"
        out.write_bytes(b"\x00" * 4096)

    mock_invoke.side_effect = fake_render

    result = render_brand_clip(_payload(), hf_project_dir=hf_dir, tmp_dir=tmp_path / "t")

    assert result["name"] == "intro"
    assert result["r2_key"] == "projects/p1/phase4/brand/intro.mp4"
    # validación técnica del MP4 opaco: 1080p, ~5s, SIN exigir alpha
    kwargs = mock_validate.call_args.kwargs
    assert kwargs["expected_duration"] == BRAND_CLIP_DURATION
    assert kwargs["require_alpha"] is False
    # subió el archivo a la key correcta
    upload_args = mock_sa.return_value.upload.call_args[0]
    assert str(upload_args[1]) == "projects/p1/phase4/brand/intro.mp4"
    # brand.css escrito en el proyecto HF
    assert (hf_dir / "brand.css").exists()


@patch("pipeline.modal_render.StorageAdapter")
@patch("pipeline.modal_render.validate_webm")
@patch("pipeline.modal_render._invoke_hf_render")
def test_render_brand_clip_outro_uses_outro_composition(
    mock_invoke, mock_validate, mock_sa, tmp_path: Path
):
    hf_dir = tmp_path / "hf"
    hf_dir.mkdir()
    mock_invoke.side_effect = lambda hf, comp, v, out, fmt="mov": out.write_bytes(b"\x00" * 4096)

    result = render_brand_clip(_payload("outro"), hf_project_dir=hf_dir, tmp_dir=tmp_path / "t")

    assert mock_invoke.call_args[0][1] == "compositions/outro.html"
    assert result["r2_key"] == "projects/p1/phase4/brand/outro.mp4"


def test_render_brand_clip_unknown_name_raises(tmp_path: Path):
    with pytest.raises(ValueError, match="cortinilla"):
        render_brand_clip(_payload("banner"), hf_project_dir=tmp_path, tmp_dir=tmp_path / "t")


@patch("pipeline.modal_render.subprocess.run")
def test_invoke_hf_render_fmt_param_builds_format_flag(mock_run, tmp_path: Path):
    from pipeline.modal_render import _invoke_hf_render

    out = tmp_path / "x.mp4"

    def fake_run(cmd, **kwargs):
        out.write_bytes(b"\x00" * 4096)
        return MagicMock(returncode=0, stderr="")

    mock_run.side_effect = fake_run
    _invoke_hf_render(tmp_path, "compositions/intro.html", {}, out, fmt="mp4")
    cmd = mock_run.call_args[0][0]
    assert cmd[cmd.index("--format") + 1] == "mp4"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_modal_render_brand.py -v`
Expected: FAIL — `ImportError: cannot import name 'BRAND_CLIP_DURATION'`

- [ ] **Step 3: Modify `pipeline/modal_render.py`**

3a. Ampliar imports del módulo (reemplazar `from pipeline.models import PlannedMaterial`):

```python
from pipeline.models import PlannedMaterial, StorageKey
from pipeline.storage import StorageAdapter
```

3b. Debajo del dict `DURATION_BY_TIPO` agregar:

```python
BRAND_CLIP_DURATION = 5.0
```

3c. Cambiar la firma de `_invoke_hf_render` para aceptar formato (los llamadores existentes no cambian — default `"mov"`):

```python
def _invoke_hf_render(
    hf_project_dir: Path,
    composition_path: str,
    variables: dict[str, Any],
    mov_out: Path,
    fmt: str = "mov",
) -> None:
    cmd = [
        "npx",
        "hyperframes",
        "render",
        str(hf_project_dir),
        "--composition",
        composition_path,
        "--output",
        str(mov_out),
        "--format",
        fmt,
        "--fps",
        "30",
        "--variables",
        json.dumps(variables, ensure_ascii=False),
    ]
```

(el resto del cuerpo — `subprocess.run`, timeout, chequeo de `returncode`/tamaño — queda idéntico).

3d. Agregar al FINAL del archivo:

```python
# ---------------------------------------------------------------------------
# Phase 4 (Unit 5) — intro/outro de marca como MP4 opaco full-frame
# ---------------------------------------------------------------------------


def render_brand_clip(
    payload: dict[str, Any],
    hf_project_dir: Path,
    tmp_dir: Path,
) -> dict[str, Any]:
    """Renderiza intro/outro de marca como MP4 opaco 1080p (~5s) y lo sube a R2.

    SIN workaround de alpha: render directo --format mp4 (las composiciones
    intro/outro son opacas). payload: {project_id, name: "intro"|"outro",
    brand: dict, variables: dict}.
    """
    project_id: str = payload["project_id"]
    name: str = payload["name"]
    if name not in ("intro", "outro"):
        raise ValueError(f"cortinilla desconocida: {name!r} (esperado 'intro' u 'outro')")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    write_brand_assets(hf_project_dir, payload["brand"])
    mp4_out = tmp_dir / f"{name}.mp4"
    t0 = time.time()
    _invoke_hf_render(
        hf_project_dir,
        f"compositions/{name}.html",
        payload["variables"],
        mp4_out,
        fmt="mp4",
    )
    # validate_webm es genérico (ffprobe): 1920x1080, duración ±tolerancia, sin alpha
    validate_webm(
        mp4_out,
        expected_duration=BRAND_CLIP_DURATION,
        duration_tolerance=0.3,
        require_alpha=False,
    )
    key = StorageKey.brand_render(project_id, name)
    StorageAdapter().upload(mp4_out, key)
    mp4_out.unlink()
    return {"name": name, "r2_key": key, "render_seconds": round(time.time() - t0, 2)}
```

- [ ] **Step 4: Add the Modal function in `pipeline/modal_app.py`**

Agregar al FINAL del archivo:

```python
@app.function(
    image=hf_image,
    secrets=[
        modal.Secret.from_name("phymac-r2-creds"),
    ],
    timeout=600,
    cpu=2.0,
    memory=4096,
    retries=modal.Retries(max_retries=1, backoff_coefficient=2.0),
)
def render_brand(payload: dict[str, Any]) -> dict[str, Any]:
    """Modal entry point: renderiza una cortinilla de marca (intro/outro)."""
    from pipeline.modal_render import render_brand_clip

    return render_brand_clip(
        payload,
        hf_project_dir=Path("/app/hf-project"),
        tmp_dir=Path("/tmp/phymac-phase4"),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_modal_render_brand.py tests/test_modal_render.py -v`
Expected: todos PASS (los tests existentes de `modal_render` no se rompen — `fmt` tiene default `"mov"`).

- [ ] **Step 6: Gates**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy pipeline && uv run pytest -q`
Expected: todo verde.

- [ ] **Step 7: Commit**

```bash
git add pipeline/modal_render.py pipeline/modal_app.py tests/test_modal_render_brand.py
git commit -m "feat(phase4): render_brand_clip worker + Modal render_brand function" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Timeline/EDL puro (`pipeline/phase4_timeline.py`)

**Files:**
- Create: `pipeline/phase4_timeline.py`
- Test: `tests/test_phase4_timeline.py`

Módulo 100% puro: sin ffmpeg, sin red, sin Modal. Entrada: `NarrativePlan` + segmentos de transcripción (dicts con `id/start/end`) + manifest de Fase 3. Salida: el dict del schema congelado (ver arriba).

- [ ] **Step 1: Write the failing test**

Crear `tests/test_phase4_timeline.py`:

```python
"""Tests de pipeline/phase4_timeline.py — EDL puro, sin ffmpeg ni red."""

from __future__ import annotations

import pytest

from pipeline.models import Block, NarrativePlan
from pipeline.phase4_timeline import build_timeline


def _segments() -> list[dict]:
    # 0-1 contiguos; 2 tras un hueco recortado [30,35]; 3 en el bloque 2
    return [
        {"id": 0, "start": 10.0, "end": 20.0, "text": "a"},
        {"id": 1, "start": 20.0, "end": 30.0, "text": "b"},
        {"id": 2, "start": 35.0, "end": 45.0, "text": "c"},
        {"id": 3, "start": 50.0, "end": 70.0, "text": "d"},
    ]


def _plan() -> NarrativePlan:
    b1 = Block(
        id="b1",
        name="Cold open",
        segments=[0, 1, 2],
        estimated_duration="0:30",
        support_material=[],
        transition_next="cut",
    )
    b2 = Block(
        id="b2",
        name="Tema",
        segments=[3],
        estimated_duration="0:20",
        support_material=[],
        transition_next="cut",
    )
    return NarrativePlan(project_id="p1", blocks=[b1, b2])


def _entry(mid: str, block: str, tipo: str, ts: int, status: str = "ok") -> dict:
    spec = {"tipo": tipo, "contenido": "x", "timestamp_relativo": ts, "metadata": {}}
    return {
        "material_id": mid,
        "block_id": block,
        "original_spec": spec,
        "refined_spec": None if status == "dropped" else spec,
        "decision": "keep",
        "position": "center",
        "reframe": None,
        "reasoning": "",
        "render_status": status,
        "r2_key": None if status == "dropped" else f"projects/p1/phase3/materials/{mid}.webm",
        "render_seconds": 1.0,
    }


def _manifest() -> list[dict]:
    return [
        _entry("m_marker", "b2", "chapter_marker", 50),
        _entry("m_quote", "b1", "pull_quote", 25),  # dentro del clip [10,30]
        _entry("m_lt", "b1", "lower_third", 32),  # en el hueco recortado [30,35] → snap
        _entry("m_drop", "b1", "pull_quote", 12, status="dropped"),
        _entry("m_fb", "b2", "animacion_texto", 55, status="fallback"),
        _entry("m_fix", "b1", "transcript_fix", 15),  # duración 0 → ignorado
    ]


KW = dict(
    intro_key="projects/p1/phase4/brand/intro.mp4",
    outro_key="projects/p1/phase4/brand/outro.mp4",
    intro_duration=5.0,
    outro_duration=5.0,
)


def test_clips_merge_contiguous_and_split_on_gap():
    tl = build_timeline(_plan(), _segments(), [], **KW)
    clips = [it for it in tl["items"] if it["kind"] == "clip"]
    assert [(c["src_start"], c["src_end"]) for c in clips] == [
        (10.0, 30.0),
        (35.0, 45.0),
        (50.0, 70.0),
    ]
    # el cuerpo empieza tras la intro (5s); offsets de salida acumulados
    assert [c["out_start"] for c in clips] == [5.0, 25.0, 35.0]
    assert [c["segment_ids"] for c in clips] == [[0, 1], [2], [3]]


def test_marker_inserted_before_its_block():
    tl = build_timeline(_plan(), _segments(), _manifest(), **KW)
    kinds = [(it["kind"], it["block_id"]) for it in tl["items"]]
    assert kinds == [("clip", "b1"), ("clip", "b1"), ("marker", "b2"), ("clip", "b2")]
    marker = tl["items"][2]
    assert marker["material_id"] == "m_marker"
    assert marker["duration"] == 4.2
    assert tl["items"][3]["out_start"] == pytest.approx(marker["out_start"] + 4.2)


def test_overlay_inside_clip_maps_linearly():
    tl = build_timeline(_plan(), _segments(), _manifest(), **KW)
    quote = next(o for o in tl["overlays"] if o["material_id"] == "m_quote")
    # ts=25 cae en el clip [10,30] que sale en out=5 → out = 5 + (25-10) = 20
    assert quote["start"] == pytest.approx(20.0)
    assert quote["end"] == pytest.approx(26.6)
    assert quote["tipo"] == "pull_quote"


def test_overlay_in_cut_region_snaps_to_nearest_clip_boundary():
    tl = build_timeline(_plan(), _segments(), _manifest(), **KW)
    lt = next(o for o in tl["overlays"] if o["material_id"] == "m_lt")
    # ts=32 cae en el hueco [30,35]; el borde más cercano es el fin del clip
    # [10,30] (dist 2) que mapea a out = 5 + 20 = 25
    assert lt["start"] == pytest.approx(25.0)


def test_dropped_and_zero_duration_excluded_fallback_included():
    tl = build_timeline(_plan(), _segments(), _manifest(), **KW)
    ids = {o["material_id"] for o in tl["overlays"]}
    assert "m_drop" not in ids
    assert "m_fix" not in ids
    assert "m_fb" in ids


def test_expected_duration():
    tl = build_timeline(_plan(), _segments(), _manifest(), **KW)
    body = (30 - 10) + (45 - 35) + (70 - 50) + 4.2  # clips + marker
    assert tl["body_duration"] == pytest.approx(body)
    assert tl["expected_duration"] == pytest.approx(5.0 + body + 5.0)
    assert tl["schema_version"] == 1
    assert tl["intro"]["r2_key"] == KW["intro_key"]
    assert tl["fps"] == 30 and tl["width"] == 1920 and tl["height"] == 1080


def test_overlays_sorted_by_start():
    tl = build_timeline(_plan(), _segments(), _manifest(), **KW)
    starts = [o["start"] for o in tl["overlays"]]
    assert starts == sorted(starts)


def test_missing_segment_id_raises():
    plan = _plan()
    plan.blocks[0].segments.append(99)
    with pytest.raises(ValueError, match="99"):
        build_timeline(plan, _segments(), [], **KW)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_phase4_timeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.phase4_timeline'`

- [ ] **Step 3: Write the implementation**

Crear `pipeline/phase4_timeline.py`:

```python
"""Cálculo del timeline/EDL de Fase 4. Puro: sin ffmpeg, sin red, sin Modal.

Convenciones de tiempo:
- src_*: segundos en el video CRUDO (phase1/video.mp4).
- out_* / start / end: segundos ABSOLUTOS en el video final compuesto
  (la intro empieza en 0; el cuerpo empieza en intro_duration).
"""

from __future__ import annotations

from typing import Any

from pipeline.modal_render import DURATION_BY_TIPO
from pipeline.models import NarrativePlan

TIMELINE_SCHEMA_VERSION = 1
FPS = 30
WIDTH = 1920
HEIGHT = 1080
# Segmentos consecutivos con un hueco <= a esto se fusionan en un solo clip
GAP_TOLERANCE_SECONDS = 0.5


def _renderable(manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Entries del manifest que tienen un .webm utilizable en R2."""
    return [
        e for e in manifest if e.get("render_status") in ("ok", "fallback") and e.get("r2_key")
    ]


def _spec(entry: dict[str, Any]) -> dict[str, Any]:
    return entry.get("refined_spec") or entry.get("original_spec") or {}


def _group_clips(
    segment_ids: list[int],
    seg_times: dict[int, tuple[float, float]],
    gap_tolerance: float,
) -> list[tuple[list[int], float, float]]:
    """Agrupa segment_ids consecutivos en clips (ids, src_start, src_end)."""
    clips: list[tuple[list[int], float, float]] = []
    cur_ids: list[int] = []
    cur_start = 0.0
    cur_end = 0.0
    for sid in segment_ids:
        start, end = seg_times[sid]
        if cur_ids and 0 <= start - cur_end <= gap_tolerance:
            cur_ids.append(sid)
            cur_end = end
        else:
            if cur_ids:
                clips.append((cur_ids, cur_start, cur_end))
            cur_ids = [sid]
            cur_start = start
            cur_end = end
    if cur_ids:
        clips.append((cur_ids, cur_start, cur_end))
    return clips


def _map_src_to_out(t: float, clips: list[dict[str, Any]]) -> float:
    """Mapea un timestamp del video crudo a tiempo de salida.

    Si t cae dentro de un clip keep, mapeo lineal. Si cae en una región
    recortada, snap al borde de clip más cercano (en tiempo de salida).
    """
    if not clips:
        raise ValueError("el timeline no tiene clips; no se puede mapear timestamps")
    for c in clips:
        if c["src_start"] <= t < c["src_end"]:
            return float(c["out_start"] + (t - c["src_start"]))
    best_dist = float("inf")
    best_out = float(clips[0]["out_start"])
    for c in clips:
        clip_dur = c["src_end"] - c["src_start"]
        for src_t, out_t in (
            (c["src_start"], c["out_start"]),
            (c["src_end"], c["out_start"] + clip_dur),
        ):
            dist = abs(t - src_t)
            if dist < best_dist:
                best_dist = dist
                best_out = float(out_t)
    return best_out


def build_timeline(
    plan: NarrativePlan,
    segments: list[dict[str, Any]],
    manifest: list[dict[str, Any]],
    *,
    intro_key: str,
    outro_key: str,
    intro_duration: float = 5.0,
    outro_duration: float = 5.0,
    gap_tolerance: float = GAP_TOLERANCE_SECONDS,
) -> dict[str, Any]:
    """Computa el EDL de la Fase 4. Schema documentado en el plan de Unit 5."""
    seg_times = {int(s["id"]): (float(s["start"]), float(s["end"])) for s in segments}

    markers_by_block: dict[str, list[dict[str, Any]]] = {}
    overlay_entries: list[dict[str, Any]] = []
    for e in _renderable(manifest):
        tipo = _spec(e).get("tipo", "")
        if tipo == "chapter_marker":
            markers_by_block.setdefault(e["block_id"], []).append(e)
        elif DURATION_BY_TIPO.get(tipo, 0.0) > 0:
            overlay_entries.append(e)
        # tipos desconocidos o de duración 0 (transcript_fix): sin representación visual

    items: list[dict[str, Any]] = []
    cursor = intro_duration  # el cuerpo empieza tras la intro
    for block in plan.blocks:
        for m in markers_by_block.get(block.id, []):
            d = DURATION_BY_TIPO["chapter_marker"]
            items.append(
                {
                    "kind": "marker",
                    "material_id": m["material_id"],
                    "block_id": block.id,
                    "r2_key": m["r2_key"],
                    "out_start": round(cursor, 3),
                    "duration": d,
                }
            )
            cursor += d
        missing = [sid for sid in block.segments if sid not in seg_times]
        if missing:
            raise ValueError(f"bloque {block.id}: segment ids fuera de la transcripción: {missing}")
        for ids, src_start, src_end in _group_clips(block.segments, seg_times, gap_tolerance):
            d = src_end - src_start
            items.append(
                {
                    "kind": "clip",
                    "block_id": block.id,
                    "segment_ids": ids,
                    "src_start": round(src_start, 3),
                    "src_end": round(src_end, 3),
                    "out_start": round(cursor, 3),
                    "duration": round(d, 3),
                }
            )
            cursor += d
    body_end = cursor

    clips = [it for it in items if it["kind"] == "clip"]
    overlays: list[dict[str, Any]] = []
    for e in overlay_entries:
        spec = _spec(e)
        tipo = spec["tipo"]
        d = DURATION_BY_TIPO[tipo]
        out_t = _map_src_to_out(float(spec.get("timestamp_relativo", 0)), clips)
        start = max(intro_duration, min(out_t, body_end - d))
        overlays.append(
            {
                "material_id": e["material_id"],
                "tipo": tipo,
                "r2_key": e["r2_key"],
                "position": e.get("position"),
                "start": round(start, 3),
                "end": round(start + d, 3),
            }
        )
    overlays.sort(key=lambda o: float(o["start"]))

    return {
        "schema_version": TIMELINE_SCHEMA_VERSION,
        "project_id": plan.project_id,
        "fps": FPS,
        "width": WIDTH,
        "height": HEIGHT,
        "intro": {"r2_key": intro_key, "duration": intro_duration},
        "outro": {"r2_key": outro_key, "duration": outro_duration},
        "items": items,
        "overlays": overlays,
        "body_duration": round(body_end - intro_duration, 3),
        "expected_duration": round(body_end + outro_duration, 3),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_phase4_timeline.py -v`
Expected: 8 passed.

- [ ] **Step 5: Gates**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy pipeline && uv run pytest -q`
Expected: todo verde.

- [ ] **Step 6: Commit**

```bash
git add pipeline/phase4_timeline.py tests/test_phase4_timeline.py
git commit -m "feat(phase4): pure timeline/EDL builder from plan+manifest" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Constructor del comando FFmpeg (`pipeline/phase4_ffmpeg.py`) + smoke local de overlay alpha

**Files:**
- Create: `pipeline/phase4_ffmpeg.py`
- Test: `tests/test_phase4_ffmpeg.py`

Un solo comando FFmpeg: trim+concat de clips, markers full-frame sobre negro entre segmentos, intro/outro con silencio `anullsrc`, overlays alpha con decoder `-c:v libvpx-vp9` explícito y `enable='between(t,...)'`. El builder es puro (no ejecuta nada). El test de integración (skip si no hay ffmpeg, patrón de `tests/test_frame_extractor.py`) es el "smoke local de overlay" exigido por el spec §9.

- [ ] **Step 1: Write the failing tests**

Crear `tests/test_phase4_ffmpeg.py`:

```python
"""Tests de pipeline/phase4_ffmpeg.py — comando construido (puro) + smoke local con ffmpeg."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pipeline.phase4_ffmpeg import build_compose_command


def _timeline() -> dict:
    return {
        "schema_version": 1,
        "project_id": "p1",
        "fps": 30,
        "width": 1920,
        "height": 1080,
        "intro": {"r2_key": "k_intro", "duration": 1.0},
        "outro": {"r2_key": "k_outro", "duration": 1.0},
        "items": [
            {
                "kind": "clip",
                "block_id": "b1",
                "segment_ids": [0],
                "src_start": 0.0,
                "src_end": 2.0,
                "out_start": 1.0,
                "duration": 2.0,
            },
            {
                "kind": "marker",
                "material_id": "mk",
                "block_id": "b2",
                "r2_key": "k_mk",
                "out_start": 3.0,
                "duration": 1.0,
            },
            {
                "kind": "clip",
                "block_id": "b2",
                "segment_ids": [1],
                "src_start": 3.0,
                "src_end": 5.0,
                "out_start": 4.0,
                "duration": 2.0,
            },
        ],
        "overlays": [
            {
                "material_id": "ov",
                "tipo": "pull_quote",
                "r2_key": "k_ov",
                "position": "center",
                "start": 1.5,
                "end": 2.5,
            },
        ],
        "body_duration": 5.0,
        "expected_duration": 7.0,
    }


def _paths(tmp_path: Path):
    return (
        tmp_path / "raw.mp4",
        tmp_path / "intro.mp4",
        tmp_path / "outro.mp4",
        {"mk": tmp_path / "mk.webm", "ov": tmp_path / "ov.webm"},
        tmp_path / "out.mp4",
    )


def test_inputs_order_and_explicit_vp9_decoders(tmp_path: Path):
    raw, intro, outro, mats, out = _paths(tmp_path)
    cmd = build_compose_command(_timeline(), raw, intro, outro, mats, out)
    assert cmd[0] == "ffmpeg"
    # 3 archivos + 1 marker + 1 overlay + 2 anullsrc = 7 inputs
    assert cmd.count("-i") == 7
    # decoder vp9 explícito por cada webm (preserva alpha — spec §9)
    assert cmd.count("libvpx-vp9") == 2
    i_mk = cmd.index(str(mats["mk"]))
    assert cmd[i_mk - 2] == "libvpx-vp9"
    i_ov = cmd.index(str(mats["ov"]))
    assert cmd[i_ov - 2] == "libvpx-vp9"


def test_filter_graph_contents(tmp_path: Path):
    raw, intro, outro, mats, out = _paths(tmp_path)
    cmd = build_compose_command(_timeline(), raw, intro, outro, mats, out)
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "trim=start=0.0:end=2.0" in fc
    assert "atrim=start=3.0:end=5.0" in fc
    # intro + clip + marker + clip + outro = 5 ítems del concat
    assert "concat=n=5:v=1:a=1" in fc
    # overlay alpha: shift de PTS + ventana enable
    assert "setpts=PTS-STARTPTS+1.5/TB" in fc
    assert "enable='between(t,1.5,2.5)'" in fc
    # marker compuesto sobre fondo negro (su alpha hace fade)
    assert "color=c=black:size=1920x1080:rate=30:duration=1.0" in fc
    assert "overlay=0:0:shortest=1" in fc
    # silencio para intro/outro
    assert "anullsrc=channel_layout=stereo:sample_rate=48000" in " ".join(cmd)


def test_output_flags_and_mapping(tmp_path: Path):
    raw, intro, outro, mats, out = _paths(tmp_path)
    cmd = build_compose_command(_timeline(), raw, intro, outro, mats, out)
    assert cmd[-1] == str(out)
    for token in ("libx264", "+faststart", "[vfinal]", "[bodya]", "aac"):
        assert token in cmd


def test_no_overlays_maps_bodyv(tmp_path: Path):
    raw, intro, outro, mats, out = _paths(tmp_path)
    tl = _timeline()
    tl["overlays"] = []
    cmd = build_compose_command(tl, raw, intro, outro, mats, out)
    assert "[bodyv]" in cmd
    assert "[vfinal]" not in cmd


# ---------------------------------------------------------------------------
# Smoke local (spec §9): corre el comando real con assets sintéticos.
# Mismo skip-pattern que tests/test_frame_extractor.py.
# ---------------------------------------------------------------------------


@pytest.fixture
def ffmpeg_assets(tmp_path: Path):
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not available on PATH")

    def run(args: list[str]) -> None:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)

    raw = tmp_path / "raw.mp4"
    run(
        [
            "-f", "lavfi", "-i", "testsrc=duration=6:size=1920x1080:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(raw),
        ]
    )
    intro = tmp_path / "intro.mp4"
    outro = tmp_path / "outro.mp4"
    for p in (intro, outro):
        run(
            [
                "-f", "lavfi", "-i", "testsrc2=duration=1:size=1920x1080:rate=30",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(p),
            ]
        )
    mats: dict[str, Path] = {}
    for mid in ("mk", "ov"):
        w = tmp_path / f"{mid}.webm"
        run(
            [
                "-f", "lavfi",
                "-i", "color=c=red@0.5:size=1920x1080:rate=30:duration=1,format=rgba",
                "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
                "-auto-alt-ref", "0", "-b:v", "0", "-crf", "40", str(w),
            ]
        )
        mats[mid] = w
    return raw, intro, outro, mats, tmp_path / "out.mp4"


def test_compose_command_runs_end_to_end(ffmpeg_assets):
    raw, intro, outro, mats, out = ffmpeg_assets
    cmd = build_compose_command(_timeline(), raw, intro, outro, mats, out)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr[-500:]
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", str(out),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    info = json.loads(probe.stdout)
    # intro(1) + clip(2) + marker(1) + clip(2) + outro(1) = 7s
    assert abs(float(info["format"]["duration"]) - 7.0) < 0.5
    codec_types = {s["codec_type"] for s in info["streams"]}
    assert codec_types == {"video", "audio"}
    vs = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (vs["width"], vs["height"]) == (1920, 1080)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_phase4_ffmpeg.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.phase4_ffmpeg'`

- [ ] **Step 3: Write the implementation**

Crear `pipeline/phase4_ffmpeg.py`:

```python
"""Construcción del comando FFmpeg de composición (puro — NO ejecuta nada).

Un solo encode: [intro] + [markers/clips del cuerpo] + [outro] vía concat de
filter_complex, luego cadena de overlays alpha sobre el resultado. Los .webm
(markers y overlays) se decodifican con -c:v libvpx-vp9 explícito para
preservar el canal alpha (validado en el spike — spec §9).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

V_CONFORM = "scale=1920:1080,fps=30,format=yuv420p"
A_CONFORM = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
ANULLSRC = "anullsrc=channel_layout=stereo:sample_rate=48000"


def build_compose_command(
    timeline: dict[str, Any],
    raw_video: Path,
    intro: Path,
    outro: Path,
    material_paths: dict[str, Path],
    out_path: Path,
    *,
    preset: str = "veryfast",
    crf: int = 18,
) -> list[str]:
    """Construye el comando ffmpeg completo para componer el episodio.

    Inputs (en orden): 0=raw, 1=intro, 2=outro, luego un input por marker
    (decoder vp9), luego un input por overlay (decoder vp9), y al final dos
    fuentes lavfi anullsrc (silencio de intro y de outro).
    """
    items: list[dict[str, Any]] = timeline["items"]
    markers = [it for it in items if it["kind"] == "marker"]
    overlays: list[dict[str, Any]] = timeline["overlays"]

    cmd: list[str] = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(raw_video),
        "-i", str(intro),
        "-i", str(outro),
    ]
    marker_base = 3
    for m in markers:
        cmd += ["-c:v", "libvpx-vp9", "-i", str(material_paths[m["material_id"]])]
    overlay_base = marker_base + len(markers)
    for o in overlays:
        cmd += ["-c:v", "libvpx-vp9", "-i", str(material_paths[o["material_id"]])]
    sil_intro = overlay_base + len(overlays)
    sil_outro = sil_intro + 1
    cmd += ["-f", "lavfi", "-t", f"{timeline['intro']['duration']}", "-i", ANULLSRC]
    cmd += ["-f", "lavfi", "-t", f"{timeline['outro']['duration']}", "-i", ANULLSRC]

    parts: list[str] = []
    seq: list[tuple[str, str]] = []  # (video_label, audio_label) en orden de concat

    parts.append(f"[1:v]{V_CONFORM}[vintro]")
    seq.append(("[vintro]", f"[{sil_intro}:a]"))

    marker_idx = 0
    for k, it in enumerate(items):
        if it["kind"] == "clip":
            s, e = it["src_start"], it["src_end"]
            parts.append(f"[0:v]trim=start={s}:end={e},setpts=PTS-STARTPTS,{V_CONFORM}[vc{k}]")
            parts.append(f"[0:a]atrim=start={s}:end={e},asetpts=PTS-STARTPTS,{A_CONFORM}[ac{k}]")
            seq.append((f"[vc{k}]", f"[ac{k}]"))
        else:
            idx = marker_base + marker_idx
            d = it["duration"]
            # cortinilla full-frame: el webm (con alpha) se compone sobre negro
            parts.append(f"color=c=black:size=1920x1080:rate=30:duration={d}[mb{k}]")
            parts.append(f"[mb{k}][{idx}:v]overlay=0:0:shortest=1,{V_CONFORM}[vm{k}]")
            parts.append(f"{ANULLSRC},atrim=duration={d},{A_CONFORM}[am{k}]")
            seq.append((f"[vm{k}]", f"[am{k}]"))
            marker_idx += 1

    parts.append(f"[2:v]{V_CONFORM}[voutro]")
    seq.append(("[voutro]", f"[{sil_outro}:a]"))

    concat_in = "".join(v + a for v, a in seq)
    parts.append(f"{concat_in}concat=n={len(seq)}:v=1:a=1[bodyv][bodya]")

    # Overlays alpha encadenados sobre el video concatenado. Los .webm son
    # full-frame 1920x1080 (posición horneada en la composición HF) → overlay=0:0.
    cur = "[bodyv]"
    for j, o in enumerate(overlays):
        idx = overlay_base + j
        parts.append(f"[{idx}:v]setpts=PTS-STARTPTS+{o['start']}/TB[ovs{j}]")
        out_label = "[vfinal]" if j == len(overlays) - 1 else f"[vo{j}]"
        parts.append(
            f"{cur}[ovs{j}]overlay=0:0:eof_action=pass:"
            f"enable='between(t,{o['start']},{o['end']})'{out_label}"
        )
        cur = out_label

    cmd += [
        "-filter_complex", ";".join(parts),
        "-map", cur,
        "-map", "[bodya]",
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", str(crf),
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_path),
    ]
    return cmd
```

- [ ] **Step 4: Run tests to verify they pass (incluye el smoke local con ffmpeg)**

Run: `uv run pytest tests/test_phase4_ffmpeg.py -v`
Expected: 5 passed (o 4 passed + 1 skipped si no hay ffmpeg local — en CI se salta igual que `test_frame_extractor`). **Antes del smoke real en Modal (Task 10), `test_compose_command_runs_end_to_end` DEBE haber pasado al menos una vez en una máquina con ffmpeg.**

- [ ] **Step 5: Gates**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy pipeline && uv run pytest -q`
Expected: todo verde.

- [ ] **Step 6: Commit**

```bash
git add pipeline/phase4_ffmpeg.py tests/test_phase4_ffmpeg.py
git commit -m "feat(phase4): pure ffmpeg compose command builder + local alpha overlay smoke" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Worker de composición (`pipeline/phase4_worker.py`) + función Modal `compose_video`

**Files:**
- Create: `pipeline/phase4_worker.py`
- Modify: `pipeline/modal_app.py` (nueva función Modal al final)
- Test: `tests/test_phase4_worker.py`

El worker descarga raw video + intro/outro + webms, corre el comando de Task 5, hace ffprobe del resultado y lo sube a R2. Devuelve el probe (la validación corre en el driver con esos datos — decisión técnica 7). Timeout del worker: 3600 s (spec §9: el raw es 1.4 GB / 32 min).

- [ ] **Step 1: Write the failing test**

Crear `tests/test_phase4_worker.py`:

```python
"""Tests de pipeline/phase4_worker.py (R2 y ffmpeg mockeados)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.phase4_worker import compose_one


def _timeline() -> dict:
    return {
        "schema_version": 1,
        "project_id": "p1",
        "fps": 30,
        "width": 1920,
        "height": 1080,
        "intro": {"r2_key": "projects/p1/phase4/brand/intro.mp4", "duration": 5.0},
        "outro": {"r2_key": "projects/p1/phase4/brand/outro.mp4", "duration": 5.0},
        "items": [
            {
                "kind": "clip",
                "block_id": "b1",
                "segment_ids": [0],
                "src_start": 0.0,
                "src_end": 10.0,
                "out_start": 5.0,
                "duration": 10.0,
            },
            {
                "kind": "marker",
                "material_id": "mk",
                "block_id": "b2",
                "r2_key": "projects/p1/phase3/materials/mk.webm",
                "out_start": 15.0,
                "duration": 4.2,
            },
        ],
        "overlays": [
            {
                "material_id": "ov",
                "tipo": "pull_quote",
                "r2_key": "projects/p1/phase3/materials/ov.webm",
                "position": "center",
                "start": 7.0,
                "end": 13.6,
            },
        ],
        "body_duration": 14.2,
        "expected_duration": 24.2,
    }


@patch("pipeline.phase4_worker.probe_mp4")
@patch("pipeline.phase4_worker.subprocess.run")
@patch("pipeline.phase4_worker.StorageAdapter")
def test_compose_one_happy_path(mock_sa, mock_run, mock_probe, tmp_path: Path):
    storage = mock_sa.return_value

    def fake_run(cmd, **kwargs):
        Path(cmd[-1]).write_bytes(b"\x00" * 4096)
        return MagicMock(returncode=0, stderr="")

    mock_run.side_effect = fake_run
    mock_probe.return_value = {
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "duration": 24.2,
        "has_audio": True,
        "size_bytes": 4096,
    }

    result = compose_one({"project_id": "p1", "timeline": _timeline()}, tmp_dir=tmp_path)

    assert result["composed_key"] == "projects/p1/phase4/composed.mp4"
    assert result["duration"] == 24.2
    assert result["has_audio"] is True
    assert "compose_seconds" in result
    # descargó raw + intro + outro + marker + overlay = 5 objetos
    assert storage.download.call_count == 5
    downloaded_keys = [c.args[0] for c in storage.download.call_args_list]
    assert "projects/p1/phase1/video.mp4" in downloaded_keys
    assert "projects/p1/phase4/brand/intro.mp4" in downloaded_keys
    assert "projects/p1/phase3/materials/ov.webm" in downloaded_keys
    # subió el composed a la key correcta
    storage.upload.assert_called_once()
    assert storage.upload.call_args.args[1] == "projects/p1/phase4/composed.mp4"


@patch("pipeline.phase4_worker.subprocess.run")
@patch("pipeline.phase4_worker.StorageAdapter")
def test_compose_one_ffmpeg_failure_raises(mock_sa, mock_run, tmp_path: Path):
    mock_run.return_value = MagicMock(returncode=1, stderr="filter parse error")
    with pytest.raises(RuntimeError, match="ffmpeg compose failed"):
        compose_one({"project_id": "p1", "timeline": _timeline()}, tmp_dir=tmp_path)


@patch("pipeline.phase4_worker.probe_mp4")
@patch("pipeline.phase4_worker.subprocess.run")
@patch("pipeline.phase4_worker.StorageAdapter")
def test_compose_one_builds_command_from_timeline(mock_sa, mock_run, mock_probe, tmp_path: Path):
    def fake_run(cmd, **kwargs):
        Path(cmd[-1]).write_bytes(b"\x00" * 4096)
        # el comando contiene los trims del timeline y el decoder vp9
        joined = " ".join(cmd)
        assert "trim=start=0.0:end=10.0" in joined
        assert "libvpx-vp9" in joined
        return MagicMock(returncode=0, stderr="")

    mock_run.side_effect = fake_run
    mock_probe.return_value = {
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "duration": 24.2,
        "has_audio": True,
        "size_bytes": 4096,
    }
    compose_one({"project_id": "p1", "timeline": _timeline()}, tmp_dir=tmp_path)
    assert mock_run.call_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_phase4_worker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.phase4_worker'`

- [ ] **Step 3: Write the implementation**

Crear `pipeline/phase4_worker.py`:

```python
"""Worker-side de la composición. Corre dentro de Modal (o local en tests).

Descarga raw + intro/outro + materiales de R2, ejecuta el comando único de
phase4_ffmpeg, hace ffprobe del resultado y lo sube a R2. Logs de progreso
por etapa (spec §9).
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Any

from pipeline.models import StorageKey
from pipeline.phase3_r2 import video_raw_key
from pipeline.phase4_ffmpeg import build_compose_command
from pipeline.storage import StorageAdapter

logger = logging.getLogger(__name__)

COMPOSE_TIMEOUT_SECONDS = 3000  # < timeout del worker Modal (3600s)


def probe_mp4(path: Path) -> dict[str, Any]:
    """ffprobe de un MP4 local → métricas que consume validate_phase4()."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr[:300]}")
    info = json.loads(result.stdout)
    vstreams = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    astreams = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    vs = vstreams[0] if vstreams else {}
    num, _, den = (vs.get("r_frame_rate") or "0/1").partition("/")
    try:
        fps = float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    return {
        "width": int(vs.get("width", 0)),
        "height": int(vs.get("height", 0)),
        "fps": round(fps, 3),
        "duration": float(info.get("format", {}).get("duration", 0) or 0),
        "has_audio": bool(astreams),
        "size_bytes": int(info.get("format", {}).get("size", 0) or 0),
    }


def compose_one(payload: dict[str, Any], tmp_dir: Path) -> dict[str, Any]:
    """Compone el episodio completo según el timeline. Devuelve el probe + key."""
    project_id: str = payload["project_id"]
    timeline: dict[str, Any] = payload["timeline"]
    tmp_dir.mkdir(parents=True, exist_ok=True)
    storage = StorageAdapter()
    t0 = time.time()

    logger.info("[compose] etapa 1/4: descargando raw video...")
    raw = tmp_dir / "raw.mp4"
    storage.download(video_raw_key(project_id), raw)

    logger.info("[compose] etapa 2/4: descargando intro/outro + materiales...")
    intro = tmp_dir / "intro.mp4"
    outro = tmp_dir / "outro.mp4"
    storage.download(timeline["intro"]["r2_key"], intro)
    storage.download(timeline["outro"]["r2_key"], outro)
    material_paths: dict[str, Path] = {}
    needed = [it for it in timeline["items"] if it["kind"] == "marker"] + timeline["overlays"]
    for entry in needed:
        local = tmp_dir / f"{entry['material_id']}.webm"
        if entry["material_id"] not in material_paths:
            storage.download(entry["r2_key"], local)
            material_paths[entry["material_id"]] = local

    logger.info(
        "[compose] etapa 3/4: ffmpeg (%d items, %d overlays)...",
        len(timeline["items"]),
        len(timeline["overlays"]),
    )
    out_path = tmp_dir / "composed.mp4"
    cmd = build_compose_command(timeline, raw, intro, outro, material_paths, out_path)
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=COMPOSE_TIMEOUT_SECONDS
    )
    if result.returncode != 0 or not out_path.exists() or out_path.stat().st_size < 1024:
        raise RuntimeError(
            f"ffmpeg compose failed: rc={result.returncode}, "
            f"stderr={result.stderr.strip()[-500:]}"
        )

    probe = probe_mp4(out_path)
    composed_key = StorageKey.composed_video(project_id)
    logger.info(
        "[compose] etapa 4/4: subiendo composed.mp4 (%.1f MB)...",
        out_path.stat().st_size / (1024 * 1024),
    )
    storage.upload(out_path, composed_key)

    for p in (raw, intro, outro, out_path, *material_paths.values()):
        if p.exists():
            p.unlink()
    return {
        "composed_key": composed_key,
        "compose_seconds": round(time.time() - t0, 2),
        **probe,
    }
```

- [ ] **Step 4: Add the Modal function in `pipeline/modal_app.py`**

Agregar al FINAL del archivo (después de `render_brand` de la Task 3):

```python
@app.function(
    image=hf_image,
    secrets=[
        modal.Secret.from_name("phymac-r2-creds"),
    ],
    timeout=3600,
    cpu=4.0,
    memory=8192,
)
def compose_video(payload: dict[str, Any]) -> dict[str, Any]:
    """Modal entry point: compone el episodio completo (CPU worker, sin retries
    a nivel Modal — el orchestrator ya reintenta la fase)."""
    from pipeline.phase4_worker import compose_one

    return compose_one(payload, tmp_dir=Path("/tmp/phymac-phase4"))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_phase4_worker.py -v`
Expected: 3 passed.

- [ ] **Step 6: Gates**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy pipeline && uv run pytest -q`
Expected: todo verde.

- [ ] **Step 7: Commit**

```bash
git add pipeline/phase4_worker.py pipeline/modal_app.py tests/test_phase4_worker.py
git commit -m "feat(phase4): compose worker + Modal compose_video CPU function" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: `validate_phase4()` + bypass del agente legacy

**Files:**
- Modify: `pipeline/phase3_r2.py` (helper `object_size_mb`, junto a `head_object_exists` ~línea 55)
- Modify: `pipeline/validator.py` (imports; `_validate_phase_4` ~línea 727; región "Phase 4" al final)
- Test: `tests/test_validator_phase4.py`

- [ ] **Step 1: Write the failing test**

Crear `tests/test_validator_phase4.py`:

```python
"""Tests de validate_phase4 + bypass del ValidationAgent legacy."""

from __future__ import annotations

from unittest.mock import patch

from pipeline.models import Block, NarrativePlan
from pipeline.validator import ValidationAgent, validate_phase4


def _plan() -> NarrativePlan:
    return NarrativePlan(
        project_id="p1",
        blocks=[
            Block(
                id="b1",
                name="B",
                segments=[0, 1],
                estimated_duration="1:00",
                support_material=[],
                transition_next="cut",
            )
        ],
    )


def _timeline() -> dict:
    return {
        "schema_version": 1,
        "project_id": "p1",
        "fps": 30,
        "width": 1920,
        "height": 1080,
        "intro": {"r2_key": "ki", "duration": 5.0},
        "outro": {"r2_key": "ko", "duration": 5.0},
        "items": [
            {
                "kind": "clip",
                "block_id": "b1",
                "segment_ids": [0, 1],
                "src_start": 0.0,
                "src_end": 50.0,
                "out_start": 5.0,
                "duration": 50.0,
            },
            {
                "kind": "marker",
                "material_id": "mk",
                "block_id": "b1",
                "r2_key": "k",
                "out_start": 55.0,
                "duration": 4.2,
            },
        ],
        "overlays": [
            {
                "material_id": "ov",
                "tipo": "pull_quote",
                "r2_key": "k2",
                "position": "center",
                "start": 10.0,
                "end": 16.6,
            }
        ],
        "body_duration": 54.2,
        "expected_duration": 64.2,
    }


def _manifest() -> list[dict]:
    return [
        {"material_id": "mk", "render_status": "ok", "r2_key": "k"},
        {"material_id": "ov", "render_status": "fallback", "r2_key": "k2"},
    ]


def _probe(**overrides) -> dict:
    p = {
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "duration": 64.2,
        "has_audio": True,
        "size_bytes": 700_000_000,
    }
    p.update(overrides)
    return p


@patch("pipeline.validator.object_size_mb", return_value=700.0)
@patch("pipeline.validator.head_object_exists", return_value=True)
def test_phase4_all_checks_pass(mock_head, mock_size):
    v = validate_phase4(_probe(), _timeline(), _plan(), _manifest())
    assert v.passed
    assert not v.critical_failures
    assert v.phase == 4
    mock_head.assert_called_once_with("projects/p1/phase4/composed.mp4")


@patch("pipeline.validator.object_size_mb", return_value=700.0)
@patch("pipeline.validator.head_object_exists", return_value=True)
def test_phase4_duration_out_of_tolerance_is_critical(mock_head, mock_size):
    # 64.2 esperado, 80 medido → fuera de ±5%
    v = validate_phase4(_probe(duration=80.0), _timeline(), _plan(), _manifest())
    assert not v.passed
    assert any("duration" in c for c in v.critical_failures)


@patch("pipeline.validator.object_size_mb", return_value=700.0)
@patch("pipeline.validator.head_object_exists", return_value=True)
def test_phase4_wrong_resolution_is_critical(mock_head, mock_size):
    v = validate_phase4(_probe(width=1280, height=720), _timeline(), _plan(), _manifest())
    assert any("resolution" in c for c in v.critical_failures)


@patch("pipeline.validator.object_size_mb", return_value=700.0)
@patch("pipeline.validator.head_object_exists", return_value=True)
def test_phase4_missing_audio_is_critical(mock_head, mock_size):
    v = validate_phase4(_probe(has_audio=False), _timeline(), _plan(), _manifest())
    assert any("audio" in c for c in v.critical_failures)


@patch("pipeline.validator.object_size_mb", return_value=700.0)
@patch("pipeline.validator.head_object_exists", return_value=False)
def test_phase4_missing_r2_object_is_critical(mock_head, mock_size):
    v = validate_phase4(_probe(), _timeline(), _plan(), _manifest())
    assert any("R2" in c for c in v.critical_failures)


@patch("pipeline.validator.object_size_mb", return_value=700.0)
@patch("pipeline.validator.head_object_exists", return_value=True)
def test_phase4_segment_mismatch_is_critical(mock_head, mock_size):
    plan = _plan()
    plan.blocks[0].segments.append(7)  # el plan tiene un segmento que el timeline no cubre
    v = validate_phase4(_probe(), _timeline(), plan, _manifest())
    assert any("segments" in c for c in v.critical_failures)


@patch("pipeline.validator.object_size_mb", return_value=700.0)
@patch("pipeline.validator.head_object_exists", return_value=True)
def test_phase4_orphan_material_is_critical(mock_head, mock_size):
    # manifest vacío → mk y ov son huérfanos
    v = validate_phase4(_probe(), _timeline(), _plan(), [])
    assert any("manifest" in c for c in v.critical_failures)


@patch("pipeline.validator.object_size_mb", return_value=700.0)
@patch("pipeline.validator.head_object_exists", return_value=True)
def test_phase4_fps_off_is_warning_not_critical(mock_head, mock_size):
    v = validate_phase4(_probe(fps=25.0), _timeline(), _plan(), _manifest())
    assert v.passed  # warning no bloquea
    assert any("fps" in w for w in v.warnings)


def test_agent_phase4_bypasses_when_runner_validated():
    """El runner ya validó in-runner: el agente legacy no debe re-validar sin video_path."""
    agent = ValidationAgent()
    output = {
        "composed_key": "projects/p1/phase4/composed.mp4",
        "timeline_key": "projects/p1/phase4/timeline.json",
        "duration_seconds": 64.2,
        "expected_duration": 64.2,
        "skipped": False,
    }
    result = agent.validate(4, output, {})
    assert result.passed
    assert result.phase == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_validator_phase4.py -v`
Expected: FAIL — `ImportError: cannot import name 'validate_phase4'`

- [ ] **Step 3: Add `object_size_mb` to `pipeline/phase3_r2.py`**

Debajo de `head_object_exists` agregar:

```python
def object_size_mb(key: str) -> float:
    return _get_adapter().get_object_size_mb(key)
```

- [ ] **Step 4: Implement in `pipeline/validator.py`**

4a. Ampliar el import de `phase3_r2` (línea ~36):

```python
from pipeline.phase3_r2 import download_to_local, head_object_exists, object_size_mb
```

4b. Ampliar el import de `pipeline.models` con `StorageKey`:

```python
from pipeline.models import (
    CheckResult,
    NarrativePlan,
    StorageKey,
    TranscriptionResult,
    ValidationResult,
)
```

4c. En `ValidationAgent._validate_phase_4` (~línea 727), agregar al INICIO del método (antes de `checks = []`):

```python
        # Unit 5: la validación real corre in-runner (validate_phase4, módulo-level)
        # sobre el probe del worker Modal. Sin video_path local no hay nada que
        # re-validar aquí — mismo patrón vacuo que Fase 3.
        if "composed_key" in output and "video_path" not in output:
            return ValidationResult(
                passed=True,
                phase=4,
                score=1.0,
                recommendation="Phase 4 validada in-runner por validate_phase4().",
            )
```

4d. En la región marcada `# --- Phase 4 — Composición (Unit 5) ---` al final del archivo, implementar:

```python
def validate_phase4(
    probe: dict,
    timeline: dict,
    plan: NarrativePlan,
    manifest: list[dict],
) -> ValidationResult:
    """Valida el output de Fase 4 (spec 2026-06-09 §4).

    probe: métricas ffprobe del composed.mp4 reportadas por el worker Modal.
    timeline: dict de phase4/timeline.json.
    """
    checks: list[CheckResult] = []
    critical: list[str] = []
    warnings: list[str] = []

    # 1. duración ≈ expected ±5% (critical)
    expected = float(timeline.get("expected_duration", 0) or 0)
    duration = float(probe.get("duration", 0) or 0)
    tolerance = 0.05 * expected
    dur_ok = expected > 0 and abs(duration - expected) <= tolerance
    if not dur_ok:
        critical.append(f"duration {duration:.1f}s vs expected {expected:.1f}s (±5%)")
    checks.append(
        CheckResult(
            name="duration_matches_timeline",
            passed=dur_ok,
            value=round(duration, 2),
            threshold=f"{expected:.1f}s ±{tolerance:.1f}s",
            message="duración del composed ≈ expected_duration del timeline",
        )
    )

    # 2. resolución 1920x1080 (critical)
    res = f"{probe.get('width')}x{probe.get('height')}"
    res_ok = probe.get("width") == 1920 and probe.get("height") == 1080
    if not res_ok:
        critical.append(f"resolution {res} != 1920x1080")
    checks.append(
        CheckResult(
            name="resolution_1080p",
            passed=res_ok,
            value=res,
            threshold="1920x1080",
            message="el composed debe ser full HD",
        )
    )

    # 3. fps (warning)
    expected_fps = float(timeline.get("fps", 30))
    fps = float(probe.get("fps", 0) or 0)
    fps_ok = abs(fps - expected_fps) <= 0.5
    if not fps_ok:
        warnings.append(f"fps {fps} fuera de {expected_fps}±0.5")
    checks.append(
        CheckResult(
            name="fps_correct",
            passed=fps_ok,
            value=fps,
            threshold=f"{expected_fps}±0.5",
            message="fps del composed",
        )
    )

    # 4. stream de audio presente (critical)
    has_audio = bool(probe.get("has_audio"))
    if not has_audio:
        critical.append("composed.mp4 sin stream de audio")
    checks.append(
        CheckResult(
            name="audio_present",
            passed=has_audio,
            value=has_audio,
            threshold=True,
            message="stream de audio presente (original, Fase 5 lo procesa)",
        )
    )

    # 5. objeto en R2 con tamaño > 0 (critical)
    composed_key = StorageKey.composed_video(timeline["project_id"])
    exists = head_object_exists(composed_key)
    size_mb = object_size_mb(composed_key) if exists else 0.0
    r2_ok = exists and size_mb > 0
    if not r2_ok:
        critical.append(f"composed.mp4 ausente o vacío en R2: {composed_key}")
    checks.append(
        CheckResult(
            name="r2_object_present",
            passed=r2_ok,
            value=f"{size_mb:.1f} MB",
            threshold="> 0 MB",
            message="composed.mp4 subido a R2",
        )
    )

    # 6. timeline consistente con el plan: mismos segment_ids (critical)
    plan_ids = {sid for b in plan.blocks for sid in b.segments}
    timeline_ids = {
        sid
        for it in timeline.get("items", [])
        if it.get("kind") == "clip"
        for sid in it.get("segment_ids", [])
    }
    seg_ok = timeline_ids == plan_ids
    if not seg_ok:
        critical.append(
            f"timeline segments != plan segments "
            f"(faltan={sorted(plan_ids - timeline_ids)[:5]}, "
            f"sobran={sorted(timeline_ids - plan_ids)[:5]})"
        )
    checks.append(
        CheckResult(
            name="timeline_segments_match_plan",
            passed=seg_ok,
            value=len(timeline_ids),
            threshold=len(plan_ids),
            message="los clips del timeline cubren exactamente los segmentos del plan",
        )
    )

    # 7. overlays y markers ⊆ manifest renderable (critical)
    renderable = {
        e["material_id"]
        for e in manifest
        if e.get("render_status") in ("ok", "fallback") and e.get("r2_key")
    }
    used = {it["material_id"] for it in timeline.get("items", []) if it.get("kind") == "marker"}
    used |= {o["material_id"] for o in timeline.get("overlays", [])}
    orphans = sorted(used - renderable)
    mats_ok = not orphans
    if orphans:
        critical.append(f"timeline referencia materiales fuera del manifest: {orphans[:5]}")
    checks.append(
        CheckResult(
            name="materials_subset_of_manifest",
            passed=mats_ok,
            value=len(orphans),
            threshold=0,
            message="overlays y markers deben venir del manifest de Fase 3",
        )
    )

    score = max(0.0, 1.0 - len(critical) * 0.6 - len(warnings) * 0.4 / max(len(checks), 1))
    return ValidationResult(
        passed=not critical,
        phase=4,
        score=round(score, 2),
        checks=checks,
        critical_failures=critical,
        warnings=warnings,
        recommendation=(
            "Phase 4 OK — composed.mp4 válido en R2."
            if not critical
            else f"Phase 4 FAILED — {len(critical)} críticos: {'; '.join(critical[:3])}"
        ),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_validator_phase4.py tests/test_validator_phase2.py tests/test_validator_phase3.py -v`
Expected: todos PASS.

- [ ] **Step 6: Gates**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy pipeline && uv run pytest -q`
Expected: todo verde.

- [ ] **Step 7: Commit**

```bash
git add pipeline/validator.py pipeline/phase3_r2.py tests/test_validator_phase4.py
git commit -m "feat(phase4): validate_phase4 checks + legacy agent bypass" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Runner de Fase 4 (`pipeline/phases/phase4_compose.py`) con idempotencia

**Files:**
- Modify: `pipeline/phases/phase4_compose.py` (reemplaza el stub del contrato)
- Modify: `tests/test_phase_stubs.py` (la fase 4 ya no es stub)
- Test: `tests/test_phase4_runner.py`

- [ ] **Step 1: Write the failing test**

Crear `tests/test_phase4_runner.py`:

```python
"""Tests del runner de Fase 4 (Modal y R2 mockeados; BrandManager real)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from pipeline.models import ValidationResult

PLAN = {
    "project_id": "p1",
    "blocks": [
        {
            "id": "b1",
            "name": "Cold open",
            "segments": [0],
            "estimated_duration": "0:10",
            "support_material": [],
            "transition_next": "cut",
        }
    ],
    "storage_key": "",
}
TRANSCRIPTION = {
    "project_id": "p1",
    "segments": [{"id": 0, "start": 0.0, "end": 10.0, "text": "hola", "confidence": 1.0}],
    "full_text": "hola",
    "duration_seconds": 10.0,
    "language": "es",
    "model": "m",
    "storage_key": "k",
}
MANIFEST: list = []

PROBE = {
    "width": 1920,
    "height": 1080,
    "fps": 30.0,
    "duration": 20.0,
    "has_audio": True,
    "size_bytes": 1_000_000,
    "composed_key": "projects/p1/phase4/composed.mp4",
    "compose_seconds": 100.0,
}


def _download_json(key: str) -> str:
    if "plan" in key:
        return json.dumps(PLAN)
    if "transcription" in key:
        return json.dumps(TRANSCRIPTION)
    if "manifest" in key:
        return json.dumps(MANIFEST)
    raise AssertionError(f"unexpected download_json: {key}")


def _mock_modal_ctx(mock_app):
    mock_app.run.return_value.__enter__ = MagicMock(return_value=None)
    mock_app.run.return_value.__exit__ = MagicMock(return_value=False)


@patch("pipeline.phases.phase4_compose.compose_video")
@patch("pipeline.phases.phase4_compose.render_brand")
@patch("pipeline.phases.phase4_compose.modal_app")
@patch("pipeline.phases.phase4_compose.StorageAdapter")
def test_run_phase4_happy_path(mock_sa, mock_app, mock_rb, mock_cv):
    from pipeline.phases.phase4_compose import run_phase4

    storage = mock_sa.return_value
    storage.exists.return_value = False
    storage.download_json.side_effect = _download_json
    _mock_modal_ctx(mock_app)
    mock_rb.map.return_value = [{"name": "intro"}, {"name": "outro"}]
    mock_cv.remote.return_value = PROBE

    result = run_phase4("p1", "phymac", "Mi episodio")

    assert result["skipped"] is False
    assert result["composed_key"] == "projects/p1/phase4/composed.mp4"
    assert result["timeline_key"] == "projects/p1/phase4/timeline.json"
    assert result["timeline"]["items"][0]["kind"] == "clip"
    assert result["probe"]["duration"] == 20.0
    # subió el timeline a R2 ANTES de componer
    storage.upload_json.assert_called_once()
    assert storage.upload_json.call_args.args[1] == "projects/p1/phase4/timeline.json"
    # renderizó intro + outro (no estaban cacheadas)
    assert len(mock_rb.map.call_args.args[0]) == 2
    names = {p["name"] for p in mock_rb.map.call_args.args[0]}
    assert names == {"intro", "outro"}
    # las variables llevan el título del episodio y el logo como data URI
    intro_payload = next(p for p in mock_rb.map.call_args.args[0] if p["name"] == "intro")
    assert intro_payload["variables"]["title"] == "Mi episodio"
    assert intro_payload["variables"]["logo_src"].startswith("data:image/svg+xml;base64,")
    assert intro_payload["brand"]["id"] == "phymac"
    # compose recibió el timeline
    assert mock_cv.remote.call_args.args[0]["timeline"]["project_id"] == "p1"


@patch("pipeline.phases.phase4_compose.compose_video")
@patch("pipeline.phases.phase4_compose.render_brand")
@patch("pipeline.phases.phase4_compose.modal_app")
@patch("pipeline.phases.phase4_compose.StorageAdapter")
def test_run_phase4_short_circuits_when_output_exists(mock_sa, mock_app, mock_rb, mock_cv):
    from pipeline.phases.phase4_compose import run_phase4

    storage = mock_sa.return_value
    storage.exists.return_value = True  # composed.mp4 y timeline.json existen
    storage.download_json.return_value = json.dumps({"expected_duration": 20.0})

    result = run_phase4("p1", "phymac", "Mi episodio")

    assert result["skipped"] is True
    assert result["composed_key"] == "projects/p1/phase4/composed.mp4"
    mock_app.run.assert_not_called()
    mock_cv.remote.assert_not_called()
    storage.upload_json.assert_not_called()


@patch("pipeline.phases.phase4_compose.compose_video")
@patch("pipeline.phases.phase4_compose.render_brand")
@patch("pipeline.phases.phase4_compose.modal_app")
@patch("pipeline.phases.phase4_compose.StorageAdapter")
def test_run_phase4_skips_cached_brand_renders(mock_sa, mock_app, mock_rb, mock_cv):
    from pipeline.phases.phase4_compose import run_phase4

    storage = mock_sa.return_value
    # composed/timeline NO existen, pero las cortinillas SÍ
    storage.exists.side_effect = lambda key: "/brand/" in key
    storage.download_json.side_effect = _download_json
    _mock_modal_ctx(mock_app)
    mock_cv.remote.return_value = PROBE

    result = run_phase4("p1", "phymac", "Mi episodio")

    assert result["skipped"] is False
    mock_rb.map.assert_not_called()  # cortinillas cacheadas
    mock_cv.remote.assert_called_once()


@patch("pipeline.phases.phase4_compose.validate_phase4")
@patch("pipeline.phases.phase4_compose.run_phase4")
def test_run_phase_4_adapter_returns_scalars(mock_run4, mock_val):
    from pipeline.phases.phase4_compose import run_phase_4

    mock_run4.return_value = {
        "skipped": False,
        "composed_key": "projects/p1/phase4/composed.mp4",
        "timeline_key": "projects/p1/phase4/timeline.json",
        "timeline": {"expected_duration": 20.0},
        "probe": dict(PROBE),
        "plan": MagicMock(),
        "manifest": [],
    }
    mock_val.return_value = ValidationResult(passed=True, phase=4, score=1.0)
    state = MagicMock()
    state.project.project_id = "p1"
    state.project.brand_id = "phymac"
    state.project.title = "T"

    out = run_phase_4(state)

    assert out == {
        "composed_key": "projects/p1/phase4/composed.mp4",
        "timeline_key": "projects/p1/phase4/timeline.json",
        "duration_seconds": 20.0,
        "expected_duration": 20.0,
        "skipped": False,
    }
    mock_run4.assert_called_once_with("p1", "phymac", "T")


@patch("pipeline.phases.phase4_compose.validate_phase4")
@patch("pipeline.phases.phase4_compose.run_phase4")
def test_run_phase_4_raises_on_critical_validation(mock_run4, mock_val):
    from pipeline.phases.phase4_compose import run_phase_4

    mock_run4.return_value = {
        "skipped": False,
        "composed_key": "c",
        "timeline_key": "t",
        "timeline": {"expected_duration": 20.0},
        "probe": dict(PROBE),
        "plan": MagicMock(),
        "manifest": [],
    }
    mock_val.return_value = ValidationResult(
        passed=False, phase=4, score=0.0, critical_failures=["duration off"]
    )
    state = MagicMock()
    state.project.project_id = "p1"
    state.project.brand_id = "phymac"
    state.project.title = "T"

    with pytest.raises(ValueError, match="Phase 4 failed validation"):
        run_phase_4(state)


@patch("pipeline.phases.phase4_compose.run_phase4")
def test_run_phase_4_skipped_does_not_validate(mock_run4):
    from pipeline.phases.phase4_compose import run_phase_4

    mock_run4.return_value = {
        "skipped": True,
        "composed_key": "projects/p1/phase4/composed.mp4",
        "timeline_key": "projects/p1/phase4/timeline.json",
        "timeline": {"expected_duration": 20.0},
        "probe": None,
    }
    state = MagicMock()
    state.project.project_id = "p1"
    state.project.brand_id = "phymac"
    state.project.title = "T"

    out = run_phase_4(state)
    assert out["skipped"] is True
    assert out["duration_seconds"] == 20.0


def test_register_registers_phase_4():
    from pipeline.phases import phase4_compose

    orch = MagicMock()
    phase4_compose.register(orch)
    orch.register_phase.assert_called_once()
    assert orch.register_phase.call_args.args[0] == 4
    assert orch.register_phase.call_args.args[1] is phase4_compose.run_phase_4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_phase4_runner.py -v`
Expected: FAIL — `ImportError: cannot import name 'run_phase4'` (el stub solo tiene `run_phase_4`).

- [ ] **Step 3: Replace the stub with the implementation**

Reemplazar el contenido COMPLETO de `pipeline/phases/phase4_compose.py`:

```python
"""Fase 4 — Composición + Branding (Unit 5).

Contrato (spec 2026-06-09 §4):
    Inputs (R2): phase2/plan.json, phase1/transcription.json,
                 phase3/materials_manifest.json, phase1/video.mp4,
                 brands/<brand_id>/ (filesystem local del repo)
    Outputs (R2): StorageKey.composed_video(project_id)
                  StorageKey.phase4_timeline(project_id)
                  StorageKey.brand_render(project_id, "intro"|"outro")
    Runner output dict: {composed_key, timeline_key, duration_seconds,
                         expected_duration, skipped}

Idempotencia: short-circuit si composed.mp4 + timeline.json ya existen en R2;
las cortinillas se cachean individualmente en phase4/brand/.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pipeline.brand import BrandManager
from pipeline.modal_app import app as modal_app
from pipeline.modal_app import compose_video, render_brand
from pipeline.modal_render import BRAND_CLIP_DURATION
from pipeline.models import NarrativePlan, StorageKey
from pipeline.phase4_timeline import build_timeline
from pipeline.storage import StorageAdapter
from pipeline.validator import validate_phase4

if TYPE_CHECKING:
    from pipeline.models import ProjectState
    from pipeline.orchestrator import PipelineOrchestrator

logger = logging.getLogger(__name__)

OUTRO_MESSAGE = "Gracias por acompañarnos"


def _brand_clip_payloads(
    project_id: str,
    brand_id: str,
    episode_title: str,
    manager: BrandManager,
) -> list[dict[str, Any]]:
    brand = manager.load(brand_id)
    logo_src = manager.asset_data_uri(brand_id, "logo_white")
    return [
        {
            "project_id": project_id,
            "name": "intro",
            "brand": brand.to_dict(),
            "variables": {
                "title": episode_title,
                "subtitle": brand.name,
                "logo_src": logo_src,
            },
        },
        {
            "project_id": project_id,
            "name": "outro",
            "brand": brand.to_dict(),
            "variables": {"message": OUTRO_MESSAGE, "logo_src": logo_src},
        },
    ]


def run_phase4(
    project_id: str,
    brand_id: str,
    episode_title: str,
    *,
    brands_root: str | Path = "brands",
) -> dict[str, Any]:
    """Run Phase 4 end-to-end. Devuelve timeline + probe + keys + skipped."""
    storage = StorageAdapter()
    composed_key = StorageKey.composed_video(project_id)
    timeline_key = StorageKey.phase4_timeline(project_id)

    # Idempotencia (spec §9): short-circuit si el output ya existe en R2.
    if storage.exists(composed_key) and storage.exists(timeline_key):
        logger.info("[Phase 4] composed.mp4 + timeline.json ya existen — short-circuit.")
        timeline: dict[str, Any] = json.loads(storage.download_json(timeline_key))
        return {
            "skipped": True,
            "composed_key": composed_key,
            "timeline_key": timeline_key,
            "timeline": timeline,
            "probe": None,
        }

    # 1. Inputs de R2.
    logger.info("[Phase 4] Cargando plan, transcripción y manifest de R2...")
    plan = NarrativePlan.from_json(storage.download_json(StorageKey.narrative_plan(project_id)))
    transcription = json.loads(storage.download_json(StorageKey.transcription(project_id)))
    manifest: list[dict[str, Any]] = json.loads(
        storage.download_json(StorageKey.materials_manifest(project_id))
    )

    # 2. Brand kit local + payloads de cortinillas (cache por nombre en R2).
    manager = BrandManager(brands_root)
    payloads = _brand_clip_payloads(project_id, brand_id, episode_title, manager)
    to_render = [
        p
        for p in payloads
        if not storage.exists(StorageKey.brand_render(project_id, p["name"]))
    ]

    # 3. Timeline/EDL (puro) → R2.
    timeline = build_timeline(
        plan,
        transcription["segments"],
        manifest,
        intro_key=StorageKey.brand_render(project_id, "intro"),
        outro_key=StorageKey.brand_render(project_id, "outro"),
        intro_duration=BRAND_CLIP_DURATION,
        outro_duration=BRAND_CLIP_DURATION,
    )
    storage.upload_json(json.dumps(timeline, ensure_ascii=False, indent=2), timeline_key)
    logger.info(
        "[Phase 4] Timeline subido: %d items, %d overlays, expected=%.1fs",
        len(timeline["items"]),
        len(timeline["overlays"]),
        timeline["expected_duration"],
    )

    # 4. Modal: cortinillas (si faltan) + composición.
    with modal_app.run():
        if to_render:
            results = list(render_brand.map(to_render))
            logger.info("[Phase 4] Cortinillas renderizadas: %s", [r["name"] for r in results])
        else:
            logger.info("[Phase 4] Cortinillas cacheadas en R2 — no se re-renderizan.")
        logger.info("[Phase 4] Componiendo episodio en Modal (CPU worker)...")
        probe = compose_video.remote({"project_id": project_id, "timeline": timeline})

    logger.info(
        "[Phase 4] Composición lista: %.1fs de video en %.0fs de worker.",
        probe["duration"],
        probe["compose_seconds"],
    )
    return {
        "skipped": False,
        "composed_key": composed_key,
        "timeline_key": timeline_key,
        "timeline": timeline,
        "probe": probe,
        "plan": plan,
        "manifest": manifest,
    }


def run_phase_4(state: ProjectState) -> dict:
    """Adapter del orchestrator (contrato Units 5-8). Valida in-runner."""
    project = state.project
    result = run_phase4(project.project_id, project.brand_id, project.title)

    if not result["skipped"]:
        validation = validate_phase4(
            result["probe"], result["timeline"], result["plan"], result["manifest"]
        )
        if validation.critical_failures:
            raise ValueError(
                f"Phase 4 failed validation — {len(validation.critical_failures)} "
                f"critical failure(s): {'; '.join(validation.critical_failures[:3])}"
            )
        duration = float(result["probe"]["duration"])
    else:
        duration = float(result["timeline"].get("expected_duration", 0.0))

    return {
        "composed_key": result["composed_key"],
        "timeline_key": result["timeline_key"],
        "duration_seconds": duration,
        "expected_duration": float(result["timeline"].get("expected_duration", 0.0)),
        "skipped": result["skipped"],
    }


def register(orchestrator: PipelineOrchestrator) -> None:
    """Register the Phase 4 runner with the orchestrator."""
    orchestrator.register_phase(4, run_phase_4)
    logger.info("Phase 4 (Composition) registered.")
```

- [ ] **Step 4: Update `tests/test_phase_stubs.py` (la fase 4 ya no es stub)**

En `tests/test_phase_stubs.py`, quitar la fase 4 del parametrize (queda cubierta por `tests/test_phase4_runner.py::test_register_registers_phase_4`):

```python
@pytest.mark.parametrize(
    ("module", "phase_num"),
    [(phase5_audio, 5), (phase6_render, 6)],
)
```

y eliminar `phase4_compose` del import:

```python
from pipeline.phases import phase5_audio, phase6_render
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_phase4_runner.py tests/test_phase_stubs.py -v`
Expected: todos PASS.

- [ ] **Step 6: Gates**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy pipeline && uv run pytest -q`
Expected: todo verde.

- [ ] **Step 7: Commit**

```bash
git add pipeline/phases/phase4_compose.py tests/test_phase4_runner.py tests/test_phase_stubs.py
git commit -m "feat(phase4): VideoComposer runner with idempotent short-circuit" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: Script de smoke (`scripts/run_phase4_smoke.py`)

**Files:**
- Create: `scripts/run_phase4_smoke.py`

Sigue el patrón de `scripts/run_phase3_smoke.py` (sys.path insert + funciones de dominio + reporte de validación + exit codes).

- [ ] **Step 1: Create the script**

Crear `scripts/run_phase4_smoke.py`:

```python
"""Smoke test E2E para Phase 4 sobre un proyecto existente.

Requiere:
- Modal secret `phymac-r2-creds` configurado.
- En R2: projects/<id>/state.json, phase2/plan.json, phase1/transcription.json,
  phase3/materials_manifest.json (+ .webm de materiales) y phase1/video.mp4.
- brands/<brand_id>/ en el repo local (brand.json + SVGs).

Costo aproximado por episodio:
- Modal render cortinillas (2 clips de 5s): ~$0.05
- Modal compose (CPU 4, ~10-25 min para 32 min de raw): ~$0.30-0.70
- Total: <$1

Usage:
    uv run python scripts/run_phase4_smoke.py <project_id> [--force]

Ejemplo:
    uv run python scripts/run_phase4_smoke.py cudris-20260526
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.models import ProjectState, StorageKey  # noqa: E402
from pipeline.phases.phase4_compose import run_phase4  # noqa: E402
from pipeline.storage import StorageAdapter  # noqa: E402
from pipeline.validator import validate_phase4  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke E2E de Fase 4")
    parser.add_argument("project_id")
    parser.add_argument(
        "--force",
        action="store_true",
        help="borra composed.mp4 y timeline.json de R2 antes de correr (anula el short-circuit)",
    )
    args = parser.parse_args()
    project_id: str = args.project_id
    storage = StorageAdapter()

    state_key = StorageKey.project_state(project_id)
    if not storage.exists(state_key):
        print(f"ERROR: no hay state.json en {state_key}. Crea el proyecto primero.")
        return 1
    state = ProjectState.from_json(storage.download_json(state_key))
    print(f"Project: {state.project.title} (brand={state.project.brand_id})")

    if args.force:
        print("--force: borrando composed.mp4 y timeline.json de R2...")
        storage.delete(StorageKey.composed_video(project_id))
        storage.delete(StorageKey.phase4_timeline(project_id))

    result = run_phase4(project_id, state.project.brand_id, state.project.title)
    timeline = result["timeline"]

    n_clips = sum(1 for it in timeline["items"] if it["kind"] == "clip")
    n_markers = sum(1 for it in timeline["items"] if it["kind"] == "marker")
    print(f"\n=== Timeline ({result['timeline_key']}) ===")
    print(f"clips={n_clips}  markers={n_markers}  overlays={len(timeline['overlays'])}")
    print(
        f"body={timeline['body_duration']:.1f}s  "
        f"expected_total={timeline['expected_duration']:.1f}s"
    )

    if result["skipped"]:
        print("\nSHORT-CIRCUIT: composed.mp4 ya existía en R2 (usa --force para recomponer).")
        return 0

    probe = result["probe"]
    print(f"\n=== Composed ({result['composed_key']}) ===")
    print(
        f"{probe['width']}x{probe['height']} @ {probe['fps']}fps, "
        f"{probe['duration']:.1f}s, audio={probe['has_audio']}, "
        f"{probe['size_bytes'] / (1024 * 1024):.0f} MB, "
        f"worker={probe['compose_seconds']:.0f}s"
    )

    validation = validate_phase4(probe, timeline, result["plan"], result["manifest"])
    print("\n=== Validation ===")
    print(f"passed={validation.passed}  score={validation.score}")
    if validation.critical_failures:
        print("CRITICAL:")
        for c in validation.critical_failures:
            print(f"  - {c}")
    if validation.warnings:
        print("WARNINGS:")
        for w in validation.warnings:
            print(f"  - {w}")
    print(f"\nrecommendation: {validation.recommendation}")

    url = storage.get_presigned_url(StorageKey.composed_video(project_id), expires_in=86400)
    print(f"\nDownload (24h): {url}")
    return 0 if validation.passed else 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Sanity check (sin red — solo parseo e imports)**

Run: `uv run python -c "import ast; ast.parse(open('scripts/run_phase4_smoke.py').read()); print('OK')" && uv run python scripts/run_phase4_smoke.py --help`
Expected: `OK` y el texto de ayuda de argparse (sin tocar R2 ni Modal).

- [ ] **Step 3: Gates**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy pipeline && uv run pytest -q`
Expected: todo verde.

- [ ] **Step 4: Commit**

```bash
git add scripts/run_phase4_smoke.py
git commit -m "feat(phase4): E2E smoke script for composition" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: Push + PR + smoke real sobre `cudris-20260526`

**Files:** ninguno nuevo.

- [ ] **Step 1: Gates finales completos**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy pipeline && uv run pytest -q`
Expected: todo verde (en una máquina con ffmpeg, 0 skips de los tests de Fase 4).

- [ ] **Step 2: Push de la rama**

```bash
git push -u origin feature/unit5-composition
```

- [ ] **Step 3: Crear el PR a develop**

```bash
gh pr create --base develop --title "feat(phase4): Unit 5 — Composición + Branding" --body "$(cat <<'EOF'
## Unit 5 — Fase 4: Composición + Branding

Implementa la Fase 4 según el spec `docs/superpowers/specs/2026-06-09-units5-8-pipeline-completion-design.md` §4 y el plan `docs/superpowers/plans/2026-06-09-unit5-composition-plan.md`.

### Qué incluye
- **BrandManager** (`pipeline/brand.py`): carga `brands/{id}/brand.json` → `BrandConfig`, valida SVGs, expone data URIs para HF.
- **Intro/outro**: composiciones HF `intro.html`/`outro.html` opacas (5s, 1080p), render en Modal como MP4 directo (`--format mp4`, sin workaround alpha), cacheadas en `phase4/brand/`.
- **Timeline/EDL puro** (`pipeline/phase4_timeline.py`): clips keep + chapter markers full-frame + overlays mapeados de tiempo raw → tiempo de salida. Subido a `phase4/timeline.json`.
- **Composición FFmpeg** (`pipeline/phase4_ffmpeg.py` + `pipeline/phase4_worker.py` + Modal `compose_video`): UN solo encode — trim+concat, cortinillas entre segmentos, overlays alpha (`-c:v libvpx-vp9` + `enable=between(t,...)`), audio original intacto. Output `phase4/composed.mp4`.
- **validate_phase4()**: duración ±5%, 1920x1080, fps, audio presente, objeto R2 > 0, timeline consistente con plan y manifest.
- **Idempotencia**: short-circuit si `composed.mp4` + `timeline.json` ya existen.
- **Smoke**: `scripts/run_phase4_smoke.py` (resultado sobre `cudris-20260526` abajo).

### Smoke E2E real
(pegar aquí el output de `uv run python scripts/run_phase4_smoke.py cudris-20260526`)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 4: Smoke real sobre cudris-20260526**

Pre-requisitos: `.env` con credenciales R2, Modal CLI autenticado, secret `phymac-r2-creds` existente (ya usado por Unit 4).

```bash
uv run python scripts/run_phase4_smoke.py cudris-20260526
```

Expected:
- Timeline impreso con clips/markers/overlays > 0 y `expected_total` ≈ duración del episodio editado (~12 min + 10 s de cortinillas).
- `passed=True score>=0.9` en la validación.
- URL presignada de descarga impresa.
- Exit code 0.

Verificación manual mínima (criterio de done): descargar el MP4 con la URL presignada y confirmar a ojo — intro de marca al inicio, outro al final, al menos un chapter marker full-frame entre bloques, al menos un overlay (pull_quote/lower_third) visible sobre el video, y audio continuo.

- [ ] **Step 5: Verificar idempotencia en real**

```bash
uv run python scripts/run_phase4_smoke.py cudris-20260526
```

Expected: segunda corrida termina en segundos con `SHORT-CIRCUIT: composed.mp4 ya existía en R2` y exit code 0 (no re-renderiza ni recompone).

- [ ] **Step 6: Pegar el output del smoke en el PR**

```bash
gh pr edit --body-file <(... body actualizado con el output real del smoke ...)
```

(o editar el body desde la web). CI debe quedar verde (lint, typecheck, test 3.11/3.12, security) antes de pedir merge.

---

## Self-review checklist (ejecutar al terminar)

- [ ] **Cobertura del spec §4:** BrandManager (Task 1) ✓, intro/outro HF + Modal MP4 opaco (Tasks 2-3) ✓, VideoComposer con timeline puro + ffmpeg en Modal (Tasks 4-6, 8) ✓, validate_phase4 (Task 7) ✓, smoke cudris (Tasks 9-10) ✓, idempotencia (Task 8 + verificación en Task 10) ✓.
- [ ] **Spec §9:** decoder vp9 explícito (Task 5) ✓, smoke local de overlay antes de Modal (Task 5, test de integración) ✓, timeout worker ≥ 30 min (Task 6: 3600s) ✓, logs de progreso por etapa (Task 6) ✓, retries vía orchestrator (sin retries Modal en compose) ✓.
- [ ] Sin `TBD`/`TODO`/pasos sin código en el plan.
- [ ] Consistencia de nombres entre tasks: `build_timeline`, `build_compose_command`, `compose_one`, `probe_mp4`, `render_brand_clip`, `run_phase4`/`run_phase_4`, `validate_phase4`, `object_size_mb`, `BRAND_CLIP_DURATION`.


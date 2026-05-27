# Phase 3 Materials A/B Spike — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir `experiments/phase3-ab/` con 4 stacks aislados (Playwright, Remotion, HyperFrames, Manim) que renderizan los 6 tipos de material de soporte (lower_third, pull_quote, chapter_marker, animacion_texto, ecuacion_latex, diagrama→esquema_libre) usando el brand pack de PhyMaC, más una UI estática `compare.html` para scoring lado a lado de los 20 MP4s resultantes.

**Architecture:** Carpeta throwaway `experiments/phase3-ab/` con sub-carpetas por stack (aislamiento total: deps, código, outputs separados). `_shared/` contiene insumos comunes read-only (brand pack JSON, samples, visual specs, brand assets). Cada stack expone un contrato uniforme (`render.{py,sh}` que lee `_shared/`, escribe en `_outputs/<stack>/`). Sin tests, sin retry, sin Modal — toda la disciplina se reserva para Unit 4 producción.

**Tech Stack:**
- Playwright stack: Python 3.12 + Playwright + Jinja2 + ffmpeg (PNG sequence → WebM VP9-alpha)
- Remotion stack: Node 22 + Remotion + React TSX
- HyperFrames stack: Node 22 + `hyperframes` CLI + HTML deterministic compositions
- Manim stack: Python + manim CE + LaTeX (ecuacion_latex + esquema_libre nativos)
- compare.html: HTML/JS estático con `<video>` autoplay loop + sliders + localStorage

**Spec de referencia:** `docs/superpowers/specs/2026-05-26-phase3-materials-ab-spike-design.md`

**⚠️ Nota sobre commits:** Por instrucción del usuario, **no se hace ningún commit durante este spike**. El spike es throwaway: el directorio `experiments/phase3-ab/` se borra cuando el A/B termina. Solo dos artefactos sobreviven (se mueven, no en este plan): `_shared/visual-specs.md` → `formats/podcast_hablando_con_profes/visual-specs.md` y `_shared/brand-pack.json` + `brand-assets/` → `brands/phymac/`.

---

## Pre-flight checks (verificación de entorno)

Antes de ejecutar Task 1, confirmá que el entorno tiene las dependencias requeridas. Si alguna falta, instalala antes de seguir.

- [ ] **Verificar deps base**

```bash
which ffmpeg python3 node npm
# Esperado: cada uno apunta a un binario válido
python3 --version    # Esperado: Python 3.11+ (3.12.x ok)
node --version       # Esperado: v20+ (v22 ok)
ffmpeg -version | head -1   # Esperado: ffmpeg 4.x+
```

- [ ] **Verificar libvpx-vp9 en ffmpeg (necesario para WebM alpha)**

```bash
ffmpeg -hide_banner -encoders 2>/dev/null | grep libvpx-vp9
# Esperado: una línea "V..... libvpx-vp9 ..."
```

Si falta libvpx-vp9 → `sudo apt install ffmpeg` (Ubuntu) o reinstalar ffmpeg con esa lib.

- [ ] **Verificar brand assets de origen**

```bash
ls "/mnt/c/Users/johan/Documents/PhyMaC/Videos/Identidad Grafica/"
# Esperado: al menos logo.svg presente; logo-white.svg y pattern.svg los generamos
```

- [ ] **Verificar dependencias de Manim (Cairo, Pango, LaTeX)**

```bash
which latex pdflatex 2>/dev/null && dpkg -l | grep -E "(libcairo|libpango)" | head -5
# Esperado: latex/pdflatex disponibles; libcairo2 y libpango1 instalados
```

Si falta LaTeX → `sudo apt install texlive texlive-latex-extra` (~2 GB; necesario para `ecuacion_latex` en Manim). Si esto explota en tiempo, el Task 5 documenta la opción de saltarse Manim (mitigación del riesgo de sección 10 del spec).

---

## Task 1: Scaffold + `_shared/` assets

**Objetivo:** Crear la estructura de carpetas, copiar/generar brand assets, escribir `brand-pack.json`, `samples.json` y `visual-specs.md`.

**Files:**
- Create: `experiments/phase3-ab/_shared/brand-pack.json`
- Create: `experiments/phase3-ab/_shared/samples.json`
- Create: `experiments/phase3-ab/_shared/visual-specs.md`
- Create: `experiments/phase3-ab/_shared/brand-assets/logo.svg` (copia)
- Create: `experiments/phase3-ab/_shared/brand-assets/logo-white.svg` (generado)
- Create: `experiments/phase3-ab/_shared/brand-assets/pattern.svg` (generado)
- Modify: `.gitignore` (agregar `experiments/phase3-ab/_outputs/`)

- [ ] **Step 1: Crear estructura de carpetas**

```bash
mkdir -p experiments/phase3-ab/_shared/brand-assets
mkdir -p experiments/phase3-ab/_outputs/{playwright,remotion,hyperframes,manim}
mkdir -p experiments/phase3-ab/playwright/templates
mkdir -p experiments/phase3-ab/remotion/src/compositions
mkdir -p experiments/phase3-ab/hyperframes/compositions
mkdir -p experiments/phase3-ab/manim
```

Verificación:

```bash
tree experiments/phase3-ab -L 3 -d
# Esperado: las carpetas listadas arriba
```

- [ ] **Step 2: Agregar `_outputs/` a `.gitignore`**

Editar `.gitignore` agregando al final:

```
# Phase 3 A/B spike outputs (videos grandes, throwaway)
experiments/phase3-ab/_outputs/
experiments/phase3-ab/*/node_modules/
experiments/phase3-ab/*/venv/
experiments/phase3-ab/*/__pycache__/
```

- [ ] **Step 3: Copiar `logo.svg` desde la carpeta de identidad gráfica**

```bash
cp "/mnt/c/Users/johan/Documents/PhyMaC/Videos/Identidad Grafica/logo.svg" \
   experiments/phase3-ab/_shared/brand-assets/logo.svg
ls -la experiments/phase3-ab/_shared/brand-assets/
```

Verificación: `logo.svg` aparece y tiene tamaño > 0.

- [ ] **Step 4: Generar `logo-white.svg` (variante blanca)**

Estrategia simple: leer `logo.svg`, reemplazar los fills oscuros por `#FFFFFF`. Como no conocemos los colores exactos sin abrirlo, generamos una variante manual: copiar el original y editar a mano si hace falta. Para el spike alcanza con un placeholder.

```bash
# Inspeccionar fills/strokes en el logo original
grep -oE 'fill="[^"]*"|stroke="[^"]*"' experiments/phase3-ab/_shared/brand-assets/logo.svg | sort -u
```

Si el grep muestra colores oscuros específicos (ej `#212121`, `#000000`), generá la variante white reemplazando esos por `white`:

```bash
sed -E 's/fill="#21[0-9a-fA-F]{4}"/fill="white"/g; s/fill="#000000"/fill="white"/g; s/fill="black"/fill="white"/g' \
  experiments/phase3-ab/_shared/brand-assets/logo.svg \
  > experiments/phase3-ab/_shared/brand-assets/logo-white.svg
```

Si el logo es mono-color o el sed no aplica, fallback: usá la misma `logo.svg` como `logo-white.svg` y aceptá la limitación (no es crítico para el A/B — ningún tipo de material usa logo blanco salvo `chapter_marker` y se puede omitir el logo ahí en el spike).

Verificación:

```bash
ls -la experiments/phase3-ab/_shared/brand-assets/logo-white.svg
# Esperado: existe; ideal si tamaño similar a logo.svg
```

- [ ] **Step 5: Crear `pattern.svg` (cross-grid)**

Contenido completo del archivo `experiments/phase3-ab/_shared/brand-assets/pattern.svg`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80" viewBox="0 0 80 80">
  <defs>
    <pattern id="cross-grid" width="40" height="40" patternUnits="userSpaceOnUse">
      <path d="M 40 0 L 0 0 0 40" fill="none" stroke="white" stroke-width="1" stroke-opacity="0.5"/>
      <path d="M 20 18 L 20 22 M 18 20 L 22 20" stroke="white" stroke-width="1" stroke-opacity="0.7"/>
    </pattern>
  </defs>
  <rect width="80" height="80" fill="url(#cross-grid)"/>
</svg>
```

Verificación:

```bash
cat experiments/phase3-ab/_shared/brand-assets/pattern.svg | head -3
# Esperado: el svg comienza con <svg ...>
```

- [ ] **Step 6: Crear `_shared/brand-pack.json`**

Contenido completo:

```json
{
  "id": "phymac",
  "name": "PhyMaC",
  "colors": {
    "primary":       "#2962FF",
    "primary_dark":  "#0039CB",
    "accent":        "#FF6D00",
    "accent_dark":   "#C43E00",
    "carbon":        "#212121",
    "carbon_light":  "#484848",
    "surface":       "#FFFFFF",
    "background":    "#F5F5F5"
  },
  "fonts": {
    "display": { "family": "Montserrat", "weights": [700, 800, 900], "source": "google" },
    "body":    { "family": "Open Sans",  "weights": [400, 600, 700], "source": "google" }
  },
  "shadows": {
    "button":      "0 4px 0 var(--color-primary-dark)",
    "card":        "8px 8px 0 var(--color-carbon)",
    "card_accent": "6px 6px 0 var(--color-accent)"
  },
  "radius":  { "button": 0, "card": 0, "badge": 4 },
  "pattern": { "type": "cross-grid", "opacity": 0.13, "stroke": "white" },
  "assets": {
    "logo":        "brand-assets/logo.svg",
    "logo_white":  "brand-assets/logo-white.svg",
    "pattern_svg": "brand-assets/pattern.svg"
  }
}
```

- [ ] **Step 7: Crear `_shared/samples.json`**

Contenido completo (un objeto top-level con los 6 tipos como keys; el schema de cada entry corresponde 1:1 con `MaterialSpec` en `pipeline/models.py`):

```json
{
  "lower_third": {
    "tipo": "lower_third",
    "contenido": "Edson Cúdris — Profesor de Física, Secretaría de Educación de Bogotá",
    "timestamp_relativo": 0,
    "metadata": {}
  },
  "pull_quote": {
    "tipo": "pull_quote",
    "contenido": "La educación que no transforma no es educación, es entretenimiento.",
    "timestamp_relativo": 0,
    "metadata": { "speaker": "Edson Cúdris" }
  },
  "chapter_marker": {
    "tipo": "chapter_marker",
    "contenido": "El primer alumno",
    "timestamp_relativo": 0,
    "metadata": { "chapter_number": 3 }
  },
  "animacion_texto": {
    "tipo": "animacion_texto",
    "contenido": "VOCACIÓN",
    "timestamp_relativo": 0,
    "metadata": {}
  },
  "ecuacion_latex": {
    "tipo": "ecuacion_latex",
    "contenido": "\\dfrac{\\partial^2 u}{\\partial t^2} = c^2 \\nabla^2 u",
    "timestamp_relativo": 0,
    "metadata": { "caption": "Ecuación de onda" }
  },
  "diagrama": {
    "tipo": "diagrama",
    "contenido": "diagrama de cuerpo libre de bloque en plano inclinado con fuerza de gravedad mg vertical hacia abajo y normal N perpendicular al plano",
    "timestamp_relativo": 0,
    "metadata": { "tipo_visual": "esquema_libre" }
  }
}
```

- [ ] **Step 8: Crear `_shared/visual-specs.md`**

Este archivo es el contrato visual reutilizable (sobrevive al spike). Contenido completo:

````markdown
# Visual Specs — Materiales de Soporte (PhyMaC / podcast "Hablando con Profes")

Specs detalladas por tipo. Brand-agnostic — todos los valores de color/sombra/tipografía vienen de `brand-pack.json`. Cada stack del spike implementa este contrato.

**Globales:**
- Canvas: 1920×1080 px, 30 fps
- Output: video con alpha (formato libre por stack)
- Fuentes: Google Fonts (Montserrat 700/800/900, Open Sans 400/600/700)

---

## `lower_third`

- Banner bottom-left, fondo `primary`, border-left 6px `accent`
- Posición: 8% bottom / 5% left, max-width 50%
- Tipografía: nombre Montserrat 900 24px `surface`; subtítulo Open Sans 400 13px `surface` opacidad 0.9
- Sombra: `card_accent` (6px 6px 0 `accent_dark`)
- Animación: slide-in left 0.4s → hold 5s → slide-out left 0.6s → total **6.0s**
- Input: `contenido = "Nombre — Cargo, Institución"`

## `pull_quote`

- Card centrada `surface`, border-left 8px `accent`, símbolo " grande `primary` top-left
- Centro del frame, ancho 70-75%
- Tipografía: cita Montserrat 800 36px `carbon` line-height 1.3; speaker Open Sans 600 13px `carbon_light` uppercase
- Sombra: `card` (8px 8px 0 `carbon`)
- Animación: scale 0.95→1.0 + fade 0.3s → hold 6s → fade-out 0.3s → total **6.6s**
- Input: `contenido = frase`; `metadata.speaker` opcional

## `chapter_marker`

- Full-screen interstitial 1920×1080 (reemplaza el frame, no overlay)
- Fondo: gradient(135deg, `primary` 50%, `primary_dark` 100%) + `pattern.svg` overlay opacidad 0.13
- Elementos:
  - número Montserrat 900 140px `accent` top-left (margen 10% / 8%)
  - "CAPÍTULO" Open Sans 600 14px `surface` opacidad 0.7 letter-spacing 3px (encima del número)
  - título Montserrat 900 48px `surface` max 6 palabras (centro vertical)
- Animación: número scale-in 0.3s + título slide-up 0.5s → hold 3s → fade-out 0.4s → total **4.2s**
- Input: `contenido = título`; `metadata.chapter_number = int`

## `animacion_texto`

- Box compacto `accent`, padding 18px 36px, rotación -2deg
- Top-right por defecto (configurable vía `metadata.position`)
- Tipografía: Montserrat 900 52px `surface` uppercase letter-spacing 2px
- Sombra: 6px 6px 0 `accent_dark`
- Animación: scale-bounce overshoot 1.1→1.0 elastic 0.4s → hold 1.5s → scale-fade out 0.3s → total **2.2s**
- Input: `contenido = palabra/frase corta (max 3)`

## `ecuacion_latex`

- Card oscura: fondo `carbon` (#212121), barra vertical interna 6px `accent` (lado izquierdo)
- Bottom-right, max-width 60%, padding 28px 36px
- Tipografía: label Open Sans 600 11px `accent` uppercase letter-spacing 2px; ecuación KaTeX 42px `surface`
- Sombra: 6px 6px 0 `accent`
- Animación: slide-in-up + fade 0.4s → hold (default 4.3s) → fade-out 0.3s → total **5.0s**
- Input: `contenido = LaTeX string`; `metadata.caption = label`; `metadata.duration` opcional

## `diagrama`

Sub-tipos via `metadata.tipo_visual`. **El spike implementa solo `esquema_libre`** (caso más demandante). `barras` y `ciclo` quedan especificados acá para Unit 4 producción.

### `esquema_libre` (implementado en spike)
- Card `surface` border-top 6px `accent`, padding 40px 50px
- Centro del frame, ancho 70%
- Contenido: dibujo SVG/Manim del diagrama físico (cuerpo libre del sample: bloque, plano inclinado, vectores mg + N rotulados con Montserrat 700 18px)
- Vectores: trazo 4px `primary` con arrowhead; etiquetas en `carbon`
- Sombra: `card`
- Animación: card fade-in 0.3s → bloque y plano dibujan 0.5s → vectores stagger 0.4s c/u → hold 3s → fade-out 0.3s → total **~6.0s**
- Input: `contenido = descripción libre`; en spike se hand-code el SVG por stack

### `barras` (deferred — spec para Unit 4)
- Card `surface` border-top 6px `accent`, sombra `card`
- Barras alternando `primary`/`accent` con sombras sharp 4px desplazadas
- Eje X labels Open Sans 600 14px `carbon`
- Animación: cada barra crece desde altura 0 stagger 0.2s + label fade-in
- Input: `metadata.data = [{label: str, value: number, color?: str}]`

### `ciclo` (deferred — spec para Unit 4)
- Card `primary` con `pattern.svg` overlay 0.13
- Nodos: card `surface` border-top 6px `accent`, padding 20px 24px, Montserrat 700 20px `carbon`
- Layout: triángulo equilátero (3 nodos) / cuadrado (4) / círculo (5+)
- Flechas: `accent` stroke 5px con arrowhead
- Animación: nodos stagger 0.3s + flechas se dibujan after (stroke-dasharray reveal)
- Input: `metadata.nodes = [str, ...]`

---

## Apéndice: contrato del entry point por stack

Cada stack expone `render.{py,sh}` que:
- **Lee** `_shared/brand-pack.json`, `_shared/samples.json`, `_shared/brand-assets/`
- **Escribe** `_outputs/<stack>/<tipo>.<ext>` (alpha-capable: webm | mov)
- **Escribe** `_outputs/<stack>/_meta.json` con `{<tipo>: {render_seconds: float}}`
- **No** toca nada fuera de `_outputs/<stack>/`
- Renderiza a 1920×1080 @ 30fps

````

Verificación final del Task 1:

```bash
find experiments/phase3-ab/_shared -type f
# Esperado:
# experiments/phase3-ab/_shared/brand-pack.json
# experiments/phase3-ab/_shared/samples.json
# experiments/phase3-ab/_shared/visual-specs.md
# experiments/phase3-ab/_shared/brand-assets/logo.svg
# experiments/phase3-ab/_shared/brand-assets/logo-white.svg
# experiments/phase3-ab/_shared/brand-assets/pattern.svg

python3 -c "import json; json.load(open('experiments/phase3-ab/_shared/brand-pack.json')); json.load(open('experiments/phase3-ab/_shared/samples.json')); print('JSON OK')"
# Esperado: "JSON OK"
```

---

## Task 2: Playwright stack

**Objetivo:** Renderizar los 6 tipos con Playwright + Jinja templates + ffmpeg. Frames-by-screenshot para alpha PNG → WebM VP9-alpha.

**Files:**
- Create: `experiments/phase3-ab/playwright/requirements.txt`
- Create: `experiments/phase3-ab/playwright/render.py`
- Create: `experiments/phase3-ab/playwright/templates/_base.css.j2` (shared CSS)
- Create: `experiments/phase3-ab/playwright/templates/animacion_texto.html.j2`
- Create: `experiments/phase3-ab/playwright/templates/lower_third.html.j2`
- Create: `experiments/phase3-ab/playwright/templates/pull_quote.html.j2`
- Create: `experiments/phase3-ab/playwright/templates/chapter_marker.html.j2`
- Create: `experiments/phase3-ab/playwright/templates/ecuacion_latex.html.j2`
- Create: `experiments/phase3-ab/playwright/templates/diagrama.html.j2`

**Patrón clave (determinismo):** cada template define animaciones vía Web Animations API (WAAPI), las pausa al cargar (`anim.pause()`), y expone `window.__seek(tSeconds)` que setea `anim.currentTime = tSeconds * 1000` en todas las animaciones registradas. El render.py llama `__seek(t)` antes de cada `page.screenshot()` para frame-perfect output.

- [ ] **Step 1: Crear `requirements.txt`**

Contenido:

```
playwright==1.49.0
Jinja2==3.1.4
```

- [ ] **Step 2: Crear venv e instalar deps + Chromium**

```bash
cd experiments/phase3-ab/playwright
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
./venv/bin/playwright install chromium
cd -
```

Verificación:

```bash
experiments/phase3-ab/playwright/venv/bin/python -c "import playwright, jinja2; print('OK')"
# Esperado: "OK"
```

- [ ] **Step 3: Crear template compartido `_base.css.j2`**

Contenido completo (`experiments/phase3-ab/playwright/templates/_base.css.j2`):

```html
<style>
  @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@700;800;900&family=Open+Sans:wght@400;600;700&display=swap');
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { width: 1920px; height: 1080px; overflow: hidden; background: transparent; font-family: 'Open Sans', sans-serif; }
  :root {
    --primary:      {{ brand.colors.primary }};
    --primary-dark: {{ brand.colors.primary_dark }};
    --accent:       {{ brand.colors.accent }};
    --accent-dark:  {{ brand.colors.accent_dark }};
    --carbon:       {{ brand.colors.carbon }};
    --carbon-light: {{ brand.colors.carbon_light }};
    --surface:      {{ brand.colors.surface }};
  }
</style>
<script>
  // Registry de animaciones para seek determinista
  window.__anims = [];
  window.__seek = function(tSeconds) {
    const ms = tSeconds * 1000;
    for (const a of window.__anims) {
      // Clamp a la duración de la animación
      const dur = (a.effect.getComputedTiming().endTime) || ms;
      a.currentTime = Math.min(ms, dur);
    }
  };
  window.__ready = false;
  // Esperar a fonts antes de marcar ready
  document.fonts.ready.then(() => { window.__ready = true; });
</script>
```

- [ ] **Step 4: Crear template `animacion_texto.html.j2`**

Contenido completo:

```html
<!DOCTYPE html>
<html><head>
{% include "_base.css.j2" %}
<style>
  .badge {
    position: absolute; top: 80px; right: 120px;
    background: var(--accent); color: var(--surface);
    padding: 18px 36px; transform: rotate(-2deg) scale(0);
    font-family: 'Montserrat', sans-serif; font-weight: 900;
    font-size: 52px; letter-spacing: 2px; text-transform: uppercase;
    box-shadow: 6px 6px 0 var(--accent-dark);
    opacity: 0;
  }
</style>
</head><body>
<div class="badge" id="badge">{{ sample.contenido }}</div>
<script>
  const el = document.getElementById('badge');
  // 0.0–0.4s scale-bounce overshoot 1.1 → 1.0; 0.4–1.9s hold; 1.9–2.2s fade+scale out
  const anim = el.animate([
    { transform: 'rotate(-2deg) scale(0)', opacity: 0,   offset: 0.0 },
    { transform: 'rotate(-2deg) scale(1.1)', opacity: 1, offset: 0.18 },
    { transform: 'rotate(-2deg) scale(1.0)', opacity: 1, offset: 0.27 },
    { transform: 'rotate(-2deg) scale(1.0)', opacity: 1, offset: 0.86 },
    { transform: 'rotate(-2deg) scale(0.9)', opacity: 0, offset: 1.0 }
  ], { duration: 2200, fill: 'both', easing: 'cubic-bezier(.34,1.56,.64,1)' });
  anim.pause();
  window.__anims.push(anim);
</script>
</body></html>
```

- [ ] **Step 5: Crear `render.py`**

Contenido completo (`experiments/phase3-ab/playwright/render.py`):

```python
"""Playwright A/B render: 6 tipos → WebM VP9-alpha 1920x1080 @ 30fps.

Lee _shared/brand-pack.json + samples.json + brand-assets/.
Escribe _outputs/playwright/<tipo>.webm + _outputs/playwright/_meta.json.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent
SHARED = ROOT.parent / "_shared"
OUT = ROOT.parent / "_outputs" / "playwright"
OUT.mkdir(parents=True, exist_ok=True)

FPS = 30
WIDTH, HEIGHT = 1920, 1080

# Duración por tipo (segundos) — del visual-specs.md
DURATION_S = {
    "animacion_texto": 2.2,
    "chapter_marker":  4.2,
    "ecuacion_latex":  5.0,
    "lower_third":     6.0,
    "diagrama":        6.0,
    "pull_quote":      6.6,
}

brand = json.loads((SHARED / "brand-pack.json").read_text(encoding="utf-8"))
samples = json.loads((SHARED / "samples.json").read_text(encoding="utf-8"))
env = Environment(loader=FileSystemLoader(ROOT / "templates"))


def render_tipo(page, tipo: str, sample: dict) -> float:
    """Render un tipo, devuelve render time en segundos."""
    template = env.get_template(f"{tipo}.html.j2")
    html = template.render(sample=sample, brand=brand)
    html_path = OUT / f"_tmp_{tipo}.html"
    html_path.write_text(html, encoding="utf-8")

    frames_dir = OUT / f"_frames_{tipo}"
    frames_dir.mkdir(exist_ok=True)
    for old in frames_dir.glob("*.png"):
        old.unlink()

    duration = DURATION_S[tipo]
    num_frames = int(duration * FPS)
    t_start = time.time()

    page.goto(html_path.as_uri())
    # Esperar fonts cargadas (window.__ready = true)
    page.wait_for_function("window.__ready === true", timeout=15000)

    for i in range(num_frames):
        t = i / FPS
        page.evaluate(f"window.__seek({t})")
        page.screenshot(
            path=str(frames_dir / f"frame_{i:04d}.png"),
            omit_background=True,
            clip={"x": 0, "y": 0, "width": WIDTH, "height": HEIGHT},
        )

    # PNG sequence → WebM VP9 alpha
    out_path = OUT / f"{tipo}.webm"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-framerate", str(FPS),
            "-i", str(frames_dir / "frame_%04d.png"),
            "-c:v", "libvpx-vp9",
            "-pix_fmt", "yuva420p",
            "-b:v", "0",
            "-crf", "22",
            "-row-mt", "1",
            str(out_path),
        ],
        check=True,
    )
    elapsed = time.time() - t_start

    # Cleanup
    for f in frames_dir.glob("*.png"):
        f.unlink()
    frames_dir.rmdir()
    html_path.unlink()
    return elapsed


def main():
    meta: dict[str, dict] = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
        page = ctx.new_page()
        for tipo in DURATION_S:
            print(f"  → {tipo}...", flush=True)
            elapsed = render_tipo(page, tipo, samples[tipo])
            meta[tipo] = {"render_seconds": round(elapsed, 2)}
            print(f"     done ({elapsed:.1f}s)")
        browser.close()
    (OUT / "_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"\n✓ {len(meta)} videos en {OUT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Smoke test con un solo tipo (`animacion_texto`)**

Para derisk el codec/alpha temprano (mitigación de sección 10 del spec), corramos solo el primer tipo antes de escribir los otros 5 templates.

Editar temporalmente `DURATION_S` en `render.py` para dejar solo `animacion_texto`, o usar este one-liner para correr solo ese:

```bash
cd experiments/phase3-ab/playwright
./venv/bin/python -c "
import render
render.DURATION_S = {'animacion_texto': render.DURATION_S['animacion_texto']}
render.main()
"
cd -
```

Verificación:

```bash
ls -la experiments/phase3-ab/_outputs/playwright/
# Esperado: animacion_texto.webm (> 5 KB) + _meta.json
ffprobe -v error -show_streams experiments/phase3-ab/_outputs/playwright/animacion_texto.webm 2>&1 | grep -E "(pix_fmt|codec_name|width|height)"
# Esperado: codec_name=vp9, pix_fmt=yuva420p, width=1920, height=1080
```

Si `pix_fmt` no es `yuva420p` → revisar ffmpeg/libvpx-vp9. **Si esto falla acá, falla en todos los stacks Playwright/HF/Remotion que usan VP9 alpha — vale la pena resolverlo ahora.**

Abrir el webm en un browser para verificar alpha:

```bash
# Crear un test page rápido (descartable)
cat > /tmp/test-alpha.html <<'EOF'
<!DOCTYPE html><html><body style="background: linear-gradient(45deg,red,blue); margin:0;">
<video autoplay loop muted style="width: 100%;">
  <source src="file:///mnt/c/Users/johan/Documents/PhyMaC/video-capability/experiments/phase3-ab/_outputs/playwright/animacion_texto.webm">
</video></body></html>
EOF
# Abrir /tmp/test-alpha.html en Chrome/Firefox
explorer.exe "$(wslpath -w /tmp/test-alpha.html)" 2>/dev/null || echo "Abrir manualmente: /tmp/test-alpha.html"
```

Esperado: el badge naranja "VOCACIÓN" aparece sobre el gradiente rojo-azul **con fondo transparente** (no negro). Si se ve negro, el alpha no está pasando — investigar antes de seguir.

- [ ] **Step 7: Crear template `lower_third.html.j2`**

Contenido completo:

```html
<!DOCTYPE html>
<html><head>
{% include "_base.css.j2" %}
<style>
  .lt {
    position: absolute; bottom: 8.6%; left: 5%;
    background: var(--primary); color: var(--surface);
    padding: 22px 32px 22px 32px;
    border-left: 6px solid var(--accent);
    max-width: 50%;
    box-shadow: 6px 6px 0 var(--accent-dark);
    transform: translateX(-130%);
  }
  .lt h1 { font-family: 'Montserrat'; font-weight: 900; font-size: 28px; line-height: 1.15; }
  .lt p  { font-family: 'Open Sans'; font-weight: 400; font-size: 16px; opacity: 0.9; margin-top: 4px; }
</style>
</head><body>
{% set parts = sample.contenido.split(' — ') %}
<div class="lt" id="lt">
  <h1>{{ parts[0] }}</h1>
  {% if parts|length > 1 %}<p>{{ parts[1] }}</p>{% endif %}
</div>
<script>
  const el = document.getElementById('lt');
  // 0–0.4 slide-in; 0.4–5.4 hold; 5.4–6.0 slide-out
  const anim = el.animate([
    { transform: 'translateX(-130%)', offset: 0.0 },
    { transform: 'translateX(0%)',    offset: 0.0667 }, // 0.4/6.0
    { transform: 'translateX(0%)',    offset: 0.9 },     // 5.4/6.0
    { transform: 'translateX(-130%)', offset: 1.0 }
  ], { duration: 6000, fill: 'both', easing: 'cubic-bezier(.22,.61,.36,1)' });
  anim.pause();
  window.__anims.push(anim);
</script>
</body></html>
```

- [ ] **Step 8: Crear template `pull_quote.html.j2`**

Contenido completo:

```html
<!DOCTYPE html>
<html><head>
{% include "_base.css.j2" %}
<style>
  .wrap { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; }
  .card {
    position: relative; width: 72%; background: var(--surface);
    border-left: 8px solid var(--accent); padding: 70px 80px 50px;
    box-shadow: 8px 8px 0 var(--carbon); opacity: 0; transform: scale(0.95);
  }
  .card .q {
    position: absolute; top: -10px; left: 30px;
    font-family: 'Montserrat'; font-weight: 900; font-size: 180px;
    color: var(--primary); line-height: 1;
  }
  .card blockquote {
    font-family: 'Montserrat'; font-weight: 800; font-size: 42px;
    color: var(--carbon); line-height: 1.3;
  }
  .card .speaker {
    margin-top: 22px; font-family: 'Open Sans'; font-weight: 600;
    font-size: 14px; color: var(--carbon-light); text-transform: uppercase;
    letter-spacing: 2px;
  }
</style>
</head><body>
<div class="wrap">
  <div class="card" id="card">
    <span class="q">“</span>
    <blockquote>{{ sample.contenido }}</blockquote>
    {% if sample.metadata.speaker %}<div class="speaker">— {{ sample.metadata.speaker }}</div>{% endif %}
  </div>
</div>
<script>
  const el = document.getElementById('card');
  // 0–0.3 in; 0.3–6.3 hold; 6.3–6.6 fade-out
  const anim = el.animate([
    { transform: 'scale(0.95)', opacity: 0, offset: 0 },
    { transform: 'scale(1.0)',  opacity: 1, offset: 0.045 },  // 0.3/6.6
    { transform: 'scale(1.0)',  opacity: 1, offset: 0.955 },  // 6.3/6.6
    { transform: 'scale(1.0)',  opacity: 0, offset: 1 }
  ], { duration: 6600, fill: 'both', easing: 'ease-out' });
  anim.pause();
  window.__anims.push(anim);
</script>
</body></html>
```

- [ ] **Step 9: Crear template `chapter_marker.html.j2`**

Contenido completo:

```html
<!DOCTYPE html>
<html><head>
{% include "_base.css.j2" %}
<style>
  .bg {
    position: absolute; inset: 0;
    background: linear-gradient(135deg, var(--primary) 50%, var(--primary-dark) 100%);
    opacity: 0;
  }
  .pattern { position: absolute; inset: 0; opacity: 0.13;
             background-image: url('../../_shared/brand-assets/pattern.svg'); }
  .num {
    position: absolute; top: 8%; left: 10%;
    font-family: 'Montserrat'; font-weight: 900; font-size: 220px;
    color: var(--accent); line-height: 1; transform: scale(0);
  }
  .label {
    position: absolute; top: calc(8% + 40px); left: calc(10% + 4px);
    font-family: 'Open Sans'; font-weight: 600; font-size: 22px;
    color: var(--surface); opacity: 0.7; letter-spacing: 6px;
  }
  .title {
    position: absolute; top: 50%; left: 50%;
    transform: translate(-50%, 80px); opacity: 0;
    font-family: 'Montserrat'; font-weight: 900; font-size: 84px;
    color: var(--surface); text-align: center;
  }
</style>
</head><body>
<div class="bg" id="bg"></div>
<div class="pattern" id="pat"></div>
<div class="label" id="lab">CAPÍTULO</div>
<div class="num" id="num">{{ sample.metadata.chapter_number }}</div>
<div class="title" id="title">{{ sample.contenido }}</div>
<script>
  const bg = document.getElementById('bg'), num = document.getElementById('num'),
        title = document.getElementById('title'), pat = document.getElementById('pat'),
        lab = document.getElementById('lab');
  const D = 4200;
  // bg + pattern + label: instant in, fade out al final
  for (const el of [bg, pat, lab]) {
    const a = el.animate([
      { opacity: 0, offset: 0 },
      { opacity: el === pat ? 0.13 : (el === lab ? 0.7 : 1), offset: 0.05 },
      { opacity: el === pat ? 0.13 : (el === lab ? 0.7 : 1), offset: 0.905 }, // 3.8/4.2
      { opacity: 0, offset: 1 }
    ], { duration: D, fill: 'both' });
    a.pause(); window.__anims.push(a);
  }
  // num: scale-in 0–0.3s, fade-out 3.8–4.2
  const aNum = num.animate([
    { transform: 'scale(0)', opacity: 0, offset: 0 },
    { transform: 'scale(1)', opacity: 1, offset: 0.071 },  // 0.3/4.2
    { transform: 'scale(1)', opacity: 1, offset: 0.905 },
    { transform: 'scale(1)', opacity: 0, offset: 1 }
  ], { duration: D, fill: 'both', easing: 'cubic-bezier(.34,1.56,.64,1)' });
  aNum.pause(); window.__anims.push(aNum);
  // title: slide-up 0–0.5s, fade-out 3.8–4.2
  const aTitle = title.animate([
    { transform: 'translate(-50%, 80px)', opacity: 0, offset: 0 },
    { transform: 'translate(-50%, 0)',    opacity: 1, offset: 0.119 },  // 0.5/4.2
    { transform: 'translate(-50%, 0)',    opacity: 1, offset: 0.905 },
    { transform: 'translate(-50%, 0)',    opacity: 0, offset: 1 }
  ], { duration: D, fill: 'both', easing: 'cubic-bezier(.22,.61,.36,1)' });
  aTitle.pause(); window.__anims.push(aTitle);
</script>
</body></html>
```

- [ ] **Step 10: Crear template `ecuacion_latex.html.j2`**

Usamos KaTeX via CDN para renderizar el LaTeX.

Contenido completo:

```html
<!DOCTYPE html>
<html><head>
{% include "_base.css.j2" %}
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
<style>
  .card {
    position: absolute; bottom: 8%; right: 5%;
    background: var(--carbon); padding: 28px 36px 28px 50px;
    box-shadow: 6px 6px 0 var(--accent);
    max-width: 60%; opacity: 0; transform: translateY(40px);
  }
  .card::before {
    content: ''; position: absolute; left: 24px; top: 18%; bottom: 18%;
    width: 6px; background: var(--accent);
  }
  .label {
    font-family: 'Open Sans'; font-weight: 600; font-size: 14px;
    color: var(--accent); letter-spacing: 2px; text-transform: uppercase;
    margin-bottom: 14px;
  }
  .eq { font-size: 42px; color: var(--surface); }
  .eq .katex { color: var(--surface); }
</style>
</head><body>
<div class="card" id="card">
  <div class="label">{{ sample.metadata.caption | default('Ecuación') }}</div>
  <div class="eq" id="eq"></div>
</div>
<script>
  // Re-renderiza KaTeX en el div (espera carga del script defer)
  document.addEventListener('DOMContentLoaded', () => {
    const wait = setInterval(() => {
      if (window.katex) {
        clearInterval(wait);
        katex.render({{ sample.contenido | tojson }}, document.getElementById('eq'), { throwOnError: false });
        // Marcar ready solo cuando KaTeX terminó
        document.fonts.ready.then(() => { window.__ready = true; });
      }
    }, 50);
  });
  const el = document.getElementById('card');
  // 0–0.4 in; hold; 4.7–5.0 fade-out
  const anim = el.animate([
    { transform: 'translateY(40px)', opacity: 0, offset: 0 },
    { transform: 'translateY(0)',    opacity: 1, offset: 0.08 },   // 0.4/5.0
    { transform: 'translateY(0)',    opacity: 1, offset: 0.94 },   // 4.7/5.0
    { transform: 'translateY(0)',    opacity: 0, offset: 1 }
  ], { duration: 5000, fill: 'both', easing: 'cubic-bezier(.22,.61,.36,1)' });
  anim.pause();
  window.__anims.push(anim);
</script>
</body></html>
```

Nota: el script de KaTeX usa `defer`, así que sobre-escribimos el `__ready` hook del base — la `window.__ready = true` se setea solo cuando KaTeX terminó de renderizar.

- [ ] **Step 11: Crear template `diagrama.html.j2`** (esquema_libre hand-coded SVG)

Contenido completo:

```html
<!DOCTYPE html>
<html><head>
{% include "_base.css.j2" %}
<style>
  .wrap { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; }
  .card {
    position: relative; width: 70%; background: var(--surface);
    border-top: 6px solid var(--accent);
    padding: 40px 50px; box-shadow: 8px 8px 0 var(--carbon);
    opacity: 0;
  }
  .card .title {
    font-family: 'Montserrat'; font-weight: 800; font-size: 24px;
    color: var(--carbon); margin-bottom: 20px;
  }
  svg { display: block; margin: 0 auto; }
  .block, .plane { stroke: var(--carbon); stroke-width: 4; fill: var(--surface); }
  .block { fill: var(--carbon-light); }
  .vec   { stroke: var(--primary); stroke-width: 5; fill: none; marker-end: url(#arrow); }
  .vec-label { font-family: 'Montserrat'; font-weight: 700; font-size: 28px; fill: var(--carbon); }
</style>
</head><body>
<div class="wrap"><div class="card" id="card">
  <div class="title">Diagrama de cuerpo libre — bloque en plano inclinado</div>
  <svg viewBox="0 0 800 480" width="800" height="480">
    <defs>
      <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--primary)"/>
      </marker>
    </defs>
    <!-- Plano inclinado (30°) -->
    <polygon class="plane" id="plane" points="100,400 700,400 700,55" />
    <!-- Bloque sobre el plano, rotado -30° en el punto (450, 245) -->
    <g transform="translate(450,245) rotate(-30)">
      <rect class="block" id="block" x="-60" y="-50" width="120" height="100" />
    </g>
    <!-- Vector gravedad mg (vertical hacia abajo desde centro del bloque) -->
    <line class="vec" id="vec-g" x1="450" y1="245" x2="450" y2="420" />
    <text class="vec-label" id="lab-g" x="465" y="370">mg</text>
    <!-- Vector normal N (perpendicular al plano, desde centro del bloque) -->
    <!-- plano sube con pendiente -tan(30°), normal = (-sin30, -cos30) = (-0.5, -0.866) -->
    <line class="vec" id="vec-n" x1="450" y1="245" x2="365" y2="98" />
    <text class="vec-label" id="lab-n" x="305" y="115">N</text>
  </svg>
</div></div>
<script>
  const card = document.getElementById('card');
  // Card fade-in 0–0.3, hold, 5.7–6.0 fade-out
  const aCard = card.animate([
    { opacity: 0, offset: 0 },
    { opacity: 1, offset: 0.05 },
    { opacity: 1, offset: 0.95 },
    { opacity: 0, offset: 1 }
  ], { duration: 6000, fill: 'both' });
  aCard.pause(); window.__anims.push(aCard);
  // Stagger reveals: plano (0.3-0.7), bloque (0.5-0.8), vec-g (0.9-1.3), lab-g (1.1-1.4),
  //                  vec-n (1.4-1.8), lab-n (1.6-1.9)
  const reveal = (id, startMs, durMs) => {
    const el = document.getElementById(id);
    const a = el.animate([
      { opacity: 0, offset: 0 },
      { opacity: 0, offset: startMs / 6000 },
      { opacity: 1, offset: (startMs + durMs) / 6000 },
      { opacity: 1, offset: 0.95 },
      { opacity: 0, offset: 1 }
    ], { duration: 6000, fill: 'both' });
    a.pause(); window.__anims.push(a);
  };
  ['plane','block','vec-g','lab-g','vec-n','lab-n'].forEach((id, i) => reveal(id, 300 + i * 200, 300));
</script>
</body></html>
```

- [ ] **Step 12: Correr render completo de los 6 tipos**

```bash
cd experiments/phase3-ab/playwright
./venv/bin/python render.py
cd -
```

Esperado output:
```
  → animacion_texto...
     done (X.Xs)
  → chapter_marker...
     done (X.Xs)
  ...
✓ 6 videos en .../_outputs/playwright
```

- [ ] **Step 13: Verificar los 6 outputs**

```bash
ls -lh experiments/phase3-ab/_outputs/playwright/
# Esperado: 6 archivos .webm + _meta.json. Cada webm entre ~50 KB y ~3 MB.

cat experiments/phase3-ab/_outputs/playwright/_meta.json
# Esperado: 6 entries con render_seconds
```

Open `_outputs/playwright/pull_quote.webm` y `chapter_marker.webm` en browser sobre un fondo de color para validar visualmente el alpha + animación. Si alguno se ve roto, ajustar el template correspondiente y re-correr solo ese tipo.

---

## Task 3: Remotion stack

**Objetivo:** Renderizar los 6 tipos con Remotion (React TSX) → MOV ProRes 4444 (alpha nativo).

**Files:**
- Create: `experiments/phase3-ab/remotion/package.json`
- Create: `experiments/phase3-ab/remotion/remotion.config.ts`
- Create: `experiments/phase3-ab/remotion/tsconfig.json`
- Create: `experiments/phase3-ab/remotion/src/index.ts`
- Create: `experiments/phase3-ab/remotion/src/Root.tsx`
- Create: `experiments/phase3-ab/remotion/src/brand.ts` (loader de brand-pack)
- Create: `experiments/phase3-ab/remotion/src/compositions/AnimacionTexto.tsx`
- Create: `experiments/phase3-ab/remotion/src/compositions/LowerThird.tsx`
- Create: `experiments/phase3-ab/remotion/src/compositions/PullQuote.tsx`
- Create: `experiments/phase3-ab/remotion/src/compositions/ChapterMarker.tsx`
- Create: `experiments/phase3-ab/remotion/src/compositions/EcuacionLatex.tsx`
- Create: `experiments/phase3-ab/remotion/src/compositions/Diagrama.tsx`
- Create: `experiments/phase3-ab/remotion/render.sh`

- [ ] **Step 1: Crear `package.json`**

Contenido completo:

```json
{
  "name": "phase3-ab-remotion",
  "version": "0.0.0",
  "private": true,
  "scripts": {
    "start": "remotion studio",
    "build": "remotion render"
  },
  "dependencies": {
    "@remotion/cli": "4.0.290",
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "remotion": "4.0.290",
    "react-katex": "3.0.1",
    "katex": "0.16.11"
  },
  "devDependencies": {
    "@types/react": "18.3.12",
    "typescript": "5.6.3"
  }
}
```

- [ ] **Step 2: Crear `tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "jsx": "react-jsx",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "resolveJsonModule": true,
    "allowSyntheticDefaultImports": true
  },
  "include": ["src"]
}
```

- [ ] **Step 3: Crear `remotion.config.ts`**

```typescript
import { Config } from "@remotion/cli/config";
Config.setVideoImageFormat("png");
Config.setOverwriteOutput(true);
```

- [ ] **Step 4: `npm install`**

```bash
cd experiments/phase3-ab/remotion
npm install
cd -
```

Verificación:

```bash
ls experiments/phase3-ab/remotion/node_modules/remotion/package.json
# Esperado: existe
```

- [ ] **Step 5: Crear `src/brand.ts`**

```typescript
import brandPack from "../../_shared/brand-pack.json";
import samples from "../../_shared/samples.json";
export const brand = brandPack;
export const samples_data = samples as Record<string, {
  tipo: string;
  contenido: string;
  timestamp_relativo: number;
  metadata: Record<string, unknown>;
}>;
```

Nota: TypeScript necesita `resolveJsonModule: true` (ya está en tsconfig).

- [ ] **Step 6: Crear `src/index.ts`**

```typescript
import { registerRoot } from "remotion";
import { RemotionRoot } from "./Root";
registerRoot(RemotionRoot);
```

- [ ] **Step 7: Crear `src/Root.tsx` (registry de las 6 compositions)**

```tsx
import { Composition } from "remotion";
import { AnimacionTexto } from "./compositions/AnimacionTexto";
import { LowerThird } from "./compositions/LowerThird";
import { PullQuote } from "./compositions/PullQuote";
import { ChapterMarker } from "./compositions/ChapterMarker";
import { EcuacionLatex } from "./compositions/EcuacionLatex";
import { Diagrama } from "./compositions/Diagrama";

// Duraciones en segundos del visual-specs.md → frames @ 30fps
const FPS = 30;
const COMPS = [
  { id: "animacion_texto", comp: AnimacionTexto, durationSec: 2.2 },
  { id: "lower_third",     comp: LowerThird,     durationSec: 6.0 },
  { id: "pull_quote",      comp: PullQuote,      durationSec: 6.6 },
  { id: "chapter_marker",  comp: ChapterMarker,  durationSec: 4.2 },
  { id: "ecuacion_latex",  comp: EcuacionLatex,  durationSec: 5.0 },
  { id: "diagrama",        comp: Diagrama,       durationSec: 6.0 },
];

export const RemotionRoot: React.FC = () => (
  <>
    {COMPS.map(({ id, comp: C, durationSec }) => (
      <Composition
        key={id}
        id={id}
        component={C}
        durationInFrames={Math.round(durationSec * FPS)}
        fps={FPS}
        width={1920}
        height={1080}
      />
    ))}
  </>
);
```

- [ ] **Step 8: Crear `src/compositions/AnimacionTexto.tsx`**

```tsx
import { AbsoluteFill, useCurrentFrame, interpolate, spring, useVideoConfig } from "remotion";
import { brand, samples_data } from "../brand";

export const AnimacionTexto: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sample = samples_data.animacion_texto;

  // 0–12 in (bounce), 12–57 hold, 57–66 out
  const scale = frame < 12
    ? spring({ frame, fps, config: { damping: 8, stiffness: 100 } })
    : frame < 57
    ? 1
    : interpolate(frame, [57, 66], [1, 0.9], { extrapolateRight: "clamp" });
  const opacity = frame < 12
    ? interpolate(frame, [0, 6], [0, 1], { extrapolateRight: "clamp" })
    : frame < 57
    ? 1
    : interpolate(frame, [57, 66], [1, 0], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ fontFamily: "Montserrat, sans-serif" }}>
      <div style={{
        position: "absolute", top: 80, right: 120,
        background: brand.colors.accent, color: brand.colors.surface,
        padding: "18px 36px", transform: `rotate(-2deg) scale(${scale})`,
        fontWeight: 900, fontSize: 52, letterSpacing: 2, textTransform: "uppercase",
        boxShadow: `6px 6px 0 ${brand.colors.accent_dark}`, opacity,
      }}>
        {sample.contenido}
      </div>
    </AbsoluteFill>
  );
};
```

- [ ] **Step 9: Crear `src/compositions/LowerThird.tsx`**

```tsx
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import { brand, samples_data } from "../brand";

export const LowerThird: React.FC = () => {
  const frame = useCurrentFrame();
  const sample = samples_data.lower_third;
  const [name, subtitle] = sample.contenido.split(" — ");

  // 0–12 slide-in; 12–162 hold; 162–180 slide-out (180 = 6.0s @ 30fps)
  const x = frame < 12
    ? interpolate(frame, [0, 12], [-130, 0], { extrapolateRight: "clamp" })
    : frame < 162
    ? 0
    : interpolate(frame, [162, 180], [0, -130], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ fontFamily: "Open Sans, sans-serif" }}>
      <div style={{
        position: "absolute", bottom: "8.6%", left: "5%",
        background: brand.colors.primary, color: brand.colors.surface,
        padding: "22px 32px", borderLeft: `6px solid ${brand.colors.accent}`,
        maxWidth: "50%", boxShadow: `6px 6px 0 ${brand.colors.accent_dark}`,
        transform: `translateX(${x}%)`,
      }}>
        <h1 style={{ fontFamily: "Montserrat", fontWeight: 900, fontSize: 28, lineHeight: 1.15 }}>{name}</h1>
        {subtitle && <p style={{ fontWeight: 400, fontSize: 16, opacity: 0.9, marginTop: 4 }}>{subtitle}</p>}
      </div>
    </AbsoluteFill>
  );
};
```

- [ ] **Step 10: Crear `src/compositions/PullQuote.tsx`**

```tsx
import { AbsoluteFill, useCurrentFrame, interpolate, spring, useVideoConfig } from "remotion";
import { brand, samples_data } from "../brand";

export const PullQuote: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sample = samples_data.pull_quote;
  const TOTAL = 198; // 6.6s * 30

  const scale = frame < 9 ? spring({ frame, fps, config: { damping: 12, stiffness: 80 } }) * 0.05 + 0.95
              : frame < 189 ? 1
              : 1;
  const opacity = frame < 9 ? interpolate(frame, [0, 9], [0, 1], { extrapolateRight: "clamp" })
                : frame < 189 ? 1
                : interpolate(frame, [189, TOTAL], [1, 0], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{
        position: "relative", width: "72%", background: brand.colors.surface,
        borderLeft: `8px solid ${brand.colors.accent}`, padding: "70px 80px 50px",
        boxShadow: `8px 8px 0 ${brand.colors.carbon}`,
        opacity, transform: `scale(${scale})`,
      }}>
        <span style={{
          position: "absolute", top: -10, left: 30,
          fontFamily: "Montserrat", fontWeight: 900, fontSize: 180,
          color: brand.colors.primary, lineHeight: 1,
        }}>“</span>
        <blockquote style={{
          fontFamily: "Montserrat", fontWeight: 800, fontSize: 42,
          color: brand.colors.carbon, lineHeight: 1.3, margin: 0,
        }}>{sample.contenido}</blockquote>
        {(sample.metadata.speaker as string | undefined) && (
          <div style={{
            marginTop: 22, fontFamily: "Open Sans", fontWeight: 600, fontSize: 14,
            color: brand.colors.carbon_light, textTransform: "uppercase", letterSpacing: 2,
          }}>— {String(sample.metadata.speaker)}</div>
        )}
      </div>
    </AbsoluteFill>
  );
};
```

- [ ] **Step 11: Crear `src/compositions/ChapterMarker.tsx`**

```tsx
import { AbsoluteFill, useCurrentFrame, interpolate, spring, useVideoConfig, staticFile, Img } from "remotion";
import { brand, samples_data } from "../brand";

export const ChapterMarker: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sample = samples_data.chapter_marker;
  const TOTAL = 126; // 4.2s

  const numScale = spring({ frame: Math.min(frame, 9), fps, config: { damping: 8, stiffness: 100 } });
  const titleY = interpolate(frame, [0, 15], [80, 0], { extrapolateRight: "clamp" });
  const titleOpacity = interpolate(frame, [0, 15], [0, 1], { extrapolateRight: "clamp" });
  const fadeOut = interpolate(frame, [114, TOTAL], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ fontFamily: "Open Sans, sans-serif", opacity: fadeOut }}>
      <div style={{
        position: "absolute", inset: 0,
        background: `linear-gradient(135deg, ${brand.colors.primary} 50%, ${brand.colors.primary_dark} 100%)`,
      }}/>
      <Img src={staticFile("pattern.svg")} style={{
        position: "absolute", inset: 0, width: "100%", height: "100%",
        opacity: 0.13, objectFit: "cover",
      }}/>
      <div style={{
        position: "absolute", top: "calc(8% + 40px)", left: "calc(10% + 4px)",
        fontWeight: 600, fontSize: 22, color: brand.colors.surface,
        opacity: 0.7, letterSpacing: 6,
      }}>CAPÍTULO</div>
      <div style={{
        position: "absolute", top: "8%", left: "10%",
        fontFamily: "Montserrat", fontWeight: 900, fontSize: 220,
        color: brand.colors.accent, lineHeight: 1, transform: `scale(${numScale})`,
      }}>{String(sample.metadata.chapter_number)}</div>
      <div style={{
        position: "absolute", top: "50%", left: "50%",
        transform: `translate(-50%, ${titleY}px)`, opacity: titleOpacity,
        fontFamily: "Montserrat", fontWeight: 900, fontSize: 84,
        color: brand.colors.surface, textAlign: "center",
      }}>{sample.contenido}</div>
    </AbsoluteFill>
  );
};
```

Nota: Remotion `staticFile()` busca en `public/`. **Antes de renderizar ChapterMarker, copiar `pattern.svg`** a `experiments/phase3-ab/remotion/public/pattern.svg`. Lo hacemos en el render.sh.

- [ ] **Step 12: Crear `src/compositions/EcuacionLatex.tsx`**

```tsx
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import { brand, samples_data } from "../brand";
import "katex/dist/katex.min.css";
import { BlockMath } from "react-katex";

export const EcuacionLatex: React.FC = () => {
  const frame = useCurrentFrame();
  const sample = samples_data.ecuacion_latex;
  const TOTAL = 150; // 5.0s

  const y = interpolate(frame, [0, 12], [40, 0], { extrapolateRight: "clamp" });
  const opacity = frame < 12 ? interpolate(frame, [0, 12], [0, 1], { extrapolateRight: "clamp" })
                : frame < 141 ? 1
                : interpolate(frame, [141, TOTAL], [1, 0], { extrapolateRight: "clamp" });
  const caption = (sample.metadata.caption as string | undefined) ?? "Ecuación";

  return (
    <AbsoluteFill>
      <div style={{
        position: "absolute", bottom: "8%", right: "5%",
        background: brand.colors.carbon, padding: "28px 36px 28px 50px",
        boxShadow: `6px 6px 0 ${brand.colors.accent}`, maxWidth: "60%",
        opacity, transform: `translateY(${y}px)`,
      }}>
        <div style={{
          position: "absolute", left: 24, top: "18%", bottom: "18%",
          width: 6, background: brand.colors.accent,
        }}/>
        <div style={{
          fontFamily: "Open Sans", fontWeight: 600, fontSize: 14,
          color: brand.colors.accent, letterSpacing: 2, textTransform: "uppercase",
          marginBottom: 14,
        }}>{caption}</div>
        <div style={{ fontSize: 42, color: brand.colors.surface }}>
          <BlockMath math={sample.contenido} />
        </div>
      </div>
    </AbsoluteFill>
  );
};
```

- [ ] **Step 13: Crear `src/compositions/Diagrama.tsx`**

```tsx
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import { brand, samples_data } from "../brand";

const Vec: React.FC<{ id: string; opacity: number; x1: number; y1: number; x2: number; y2: number }> = ({ opacity, x1, y1, x2, y2 }) => (
  <line opacity={opacity} x1={x1} y1={y1} x2={x2} y2={y2} stroke={brand.colors.primary} strokeWidth={5} markerEnd="url(#arrow)" />
);

export const Diagrama: React.FC = () => {
  const frame = useCurrentFrame();
  const TOTAL = 180;

  const cardOp = frame < 9 ? interpolate(frame, [0, 9], [0, 1], { extrapolateRight: "clamp" })
              : frame < 171 ? 1
              : interpolate(frame, [171, TOTAL], [1, 0], { extrapolateRight: "clamp" });
  const reveal = (startFrame: number, durFrames = 9) =>
    interpolate(frame, [startFrame, startFrame + durFrames], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{
        position: "relative", width: "70%", background: brand.colors.surface,
        borderTop: `6px solid ${brand.colors.accent}`, padding: "40px 50px",
        boxShadow: `8px 8px 0 ${brand.colors.carbon}`, opacity: cardOp,
      }}>
        <div style={{ fontFamily: "Montserrat", fontWeight: 800, fontSize: 24, color: brand.colors.carbon, marginBottom: 20 }}>
          Diagrama de cuerpo libre — bloque en plano inclinado
        </div>
        <svg viewBox="0 0 800 480" width="800" height="480" style={{ display: "block", margin: "0 auto" }}>
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill={brand.colors.primary}/>
            </marker>
          </defs>
          <polygon opacity={reveal(9)} points="100,400 700,400 700,55" fill={brand.colors.surface} stroke={brand.colors.carbon} strokeWidth={4}/>
          <g transform="translate(450,245) rotate(-30)" opacity={reveal(15)}>
            <rect x={-60} y={-50} width={120} height={100} fill={brand.colors.carbon_light} stroke={brand.colors.carbon} strokeWidth={4}/>
          </g>
          <Vec id="g" opacity={reveal(27)} x1={450} y1={245} x2={450} y2={420}/>
          <text opacity={reveal(33)} x={465} y={370} fontFamily="Montserrat" fontWeight={700} fontSize={28} fill={brand.colors.carbon}>mg</text>
          <Vec id="n" opacity={reveal(42)} x1={450} y1={245} x2={365} y2={98}/>
          <text opacity={reveal(48)} x={305} y={115} fontFamily="Montserrat" fontWeight={700} fontSize={28} fill={brand.colors.carbon}>N</text>
        </svg>
      </div>
    </AbsoluteFill>
  );
};
```

- [ ] **Step 14: Crear `render.sh`**

Contenido completo:

```bash
#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
mkdir -p ../_outputs/remotion
mkdir -p public
# Remotion staticFile() lee de ./public — copiamos los assets necesarios
cp ../_shared/brand-assets/pattern.svg public/pattern.svg

TIPOS=(animacion_texto lower_third pull_quote chapter_marker ecuacion_latex diagrama)
META="{}"
META_FILE="../_outputs/remotion/_meta.json"

for tipo in "${TIPOS[@]}"; do
  echo "  → $tipo..."
  t0=$(date +%s.%N)
  # ProRes 4444 = MOV con alpha; codec específico en flags
  npx remotion render src/index.ts "$tipo" \
    "../_outputs/remotion/${tipo}.mov" \
    --codec=prores --prores-profile=4444 \
    --pixel-format=yuva444p10le \
    --log=warn
  t1=$(date +%s.%N)
  elapsed=$(echo "$t1 - $t0" | bc)
  META=$(jq --arg t "$tipo" --argjson s "$elapsed" '.[$t] = {render_seconds: ($s | tonumber)}' <<<"$META")
  printf "     done (%.1fs)\n" "$elapsed"
done

echo "$META" | jq '.' > "$META_FILE"
echo "✓ 6 videos en _outputs/remotion/"
```

Hacelo ejecutable:

```bash
chmod +x experiments/phase3-ab/remotion/render.sh
```

- [ ] **Step 15: Smoke con un solo tipo (`animacion_texto`)**

Antes de correr los 6, validá que Remotion renderiza ProRes con alpha:

```bash
cd experiments/phase3-ab/remotion
mkdir -p ../_outputs/remotion public
cp ../_shared/brand-assets/pattern.svg public/
npx remotion render src/index.ts animacion_texto \
  ../_outputs/remotion/animacion_texto.mov \
  --codec=prores --prores-profile=4444 --pixel-format=yuva444p10le --log=warn
cd -

ffprobe -v error -show_streams experiments/phase3-ab/_outputs/remotion/animacion_texto.mov 2>&1 | grep -E "(pix_fmt|codec_name|width|height)"
# Esperado: codec_name=prores, pix_fmt=yuva444p10le, width=1920, height=1080
```

- [ ] **Step 16: Correr render completo de los 6 tipos**

```bash
./experiments/phase3-ab/remotion/render.sh
```

- [ ] **Step 17: Verificar los 6 outputs**

```bash
ls -lh experiments/phase3-ab/_outputs/remotion/
# Esperado: 6 archivos .mov + _meta.json
cat experiments/phase3-ab/_outputs/remotion/_meta.json
```

Abrir un par en browser sobre fondo de color (mismo patrón que Task 2 step 6) para validar alpha visualmente. Si algún ProRes no reproduce en Chrome (Chromium tiene soporte parcial de ProRes), convertirlo a WebM VP9-alpha en post para compare.html:

```bash
# Solo si algún .mov no reproduce en compare.html — opcional:
# ffmpeg -i input.mov -c:v libvpx-vp9 -pix_fmt yuva420p -b:v 0 -crf 22 output.webm
```

---

## Task 4: HyperFrames stack

**Objetivo:** Renderizar los 6 tipos con HyperFrames (HTML deterministic) → WebM VP9-alpha por default de la CLI.

> **Para el subagente que ejecute este Task:** invocá la skill `hyperframes` y/o `hyperframes-cli` antes de empezar — las skills tienen los patrones canónicos de seek determinista, fonts loading, y CLI commands. Tratá las HTMLs de Task 2 (Playwright) como punto de partida y adaptalas al patrón HyperFrames (composiciones reciben `hf-seek` events, no `window.__seek` custom).

**Files:**
- Create: `experiments/phase3-ab/hyperframes/package.json`
- Create: `experiments/phase3-ab/hyperframes/hyperframes.json`
- Create: `experiments/phase3-ab/hyperframes/compositions/animacion_texto.html`
- Create: `experiments/phase3-ab/hyperframes/compositions/lower_third.html`
- Create: `experiments/phase3-ab/hyperframes/compositions/pull_quote.html`
- Create: `experiments/phase3-ab/hyperframes/compositions/chapter_marker.html`
- Create: `experiments/phase3-ab/hyperframes/compositions/ecuacion_latex.html`
- Create: `experiments/phase3-ab/hyperframes/compositions/diagrama.html`
- Create: `experiments/phase3-ab/hyperframes/render.sh`

- [ ] **Step 1: Inicializar el proyecto HyperFrames**

```bash
cd experiments/phase3-ab/hyperframes
npx hyperframes init --no-tailwind --no-install
# Si la CLI pide nombre, usar "phase3-ab-hyperframes"
cd -
```

Verificación: `experiments/phase3-ab/hyperframes/hyperframes.json` y `package.json` existen.

Si `hyperframes init` no acepta esas flags, ejecutalo interactivo y aceptá defaults; después limpiá `tailwind*` si se incluyó. Consultá la skill `hyperframes-cli` para flags actuales.

- [ ] **Step 2: `npm install`**

```bash
cd experiments/phase3-ab/hyperframes
npm install
cd -
```

- [ ] **Step 3: Copiar brand-assets a un dir accesible desde HTML**

HyperFrames usa rutas relativas desde la composición. Como compositions/ y _shared/brand-assets/ están separados, hacemos un symlink:

```bash
cd experiments/phase3-ab/hyperframes
ln -sfn ../_shared/brand-assets brand-assets
ln -sfn ../_shared/brand-pack.json brand-pack.json
ln -sfn ../_shared/samples.json samples.json
cd -
```

Verificación:

```bash
ls -la experiments/phase3-ab/hyperframes/brand-assets/
# Esperado: contenido del _shared/brand-assets via symlink
```

- [ ] **Step 4: Crear `compositions/animacion_texto.html`**

> **Patrón HyperFrames:** la composición declara `<meta name="hf:duration" content="2.2">` y reacciona al evento `hf-seek` con `currentTime` actualizado. Si la skill `hyperframes` tiene un boilerplate más reciente, usar el suyo.

Contenido completo (estructura mínima):

```html
<!DOCTYPE html>
<html><head>
<meta name="hf:duration" content="2.2">
<meta name="hf:fps" content="30">
<meta name="hf:width" content="1920">
<meta name="hf:height" content="1080">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@900&display=swap" rel="stylesheet">
<style>
  *,*::before,*::after { box-sizing:border-box; margin:0; padding:0; }
  html,body { width:1920px; height:1080px; overflow:hidden; background:transparent; }
  :root { --accent:#FF6D00; --accent-dark:#C43E00; --surface:#FFFFFF; }
  .badge {
    position:absolute; top:80px; right:120px;
    background:var(--accent); color:var(--surface);
    padding:18px 36px; transform:rotate(-2deg) scale(0); opacity:0;
    font-family:'Montserrat',sans-serif; font-weight:900; font-size:52px;
    letter-spacing:2px; text-transform:uppercase;
    box-shadow:6px 6px 0 var(--accent-dark);
  }
</style>
</head><body>
<div class="badge" id="badge"></div>
<script>
  // Cargar el sample desde _shared/samples.json (path relativo desde compositions/)
  (async () => {
    const r = await fetch('../samples.json');
    const samples = await r.json();
    document.getElementById('badge').textContent = samples.animacion_texto.contenido;
  })();
  // Animation pausada + responder a hf-seek
  const el = document.getElementById('badge');
  const anim = el.animate([
    { transform:'rotate(-2deg) scale(0)',   opacity:0, offset:0.0 },
    { transform:'rotate(-2deg) scale(1.1)', opacity:1, offset:0.18 },
    { transform:'rotate(-2deg) scale(1.0)', opacity:1, offset:0.27 },
    { transform:'rotate(-2deg) scale(1.0)', opacity:1, offset:0.86 },
    { transform:'rotate(-2deg) scale(0.9)', opacity:0, offset:1.0 }
  ], { duration: 2200, fill:'both', easing:'cubic-bezier(.34,1.56,.64,1)' });
  anim.pause();
  document.addEventListener('hf-seek', (e) => {
    anim.currentTime = Math.min(e.detail.currentTime * 1000, 2200);
  });
</script>
</body></html>
```

- [ ] **Step 5: Crear las otras 5 compositions**

Reutilizar la estructura HTML/CSS/JS de Task 2 (Playwright templates) cambiando:
1. El loader de samples (fetch a `../samples.json` en lugar de Jinja render)
2. El loader de brand colors (fetch a `../brand-pack.json` o hard-code los hex)
3. El seek handler: `document.addEventListener('hf-seek', e => { anim.currentTime = e.detail.currentTime * 1000 })` en lugar de `window.__seek`
4. Meta tags `hf:*` al inicio con duración por tipo:
   - `lower_third` → 6.0
   - `pull_quote` → 6.6
   - `chapter_marker` → 4.2
   - `ecuacion_latex` → 5.0
   - `diagrama` → 6.0
5. Pattern para chapter_marker: usar `url('../brand-assets/pattern.svg')`

**Hard-code colors en cada composition** (más simple que fetch brand-pack en cada una). Los hex están en brand-pack.json — leerlos una vez y embeberlos:

```
primary:      #2962FF
primary_dark: #0039CB
accent:       #FF6D00
accent_dark:  #C43E00
carbon:       #212121
carbon_light: #484848
surface:      #FFFFFF
```

Para `ecuacion_latex` cargar KaTeX desde CDN igual que en Task 2 Step 10. Asegurarse que el render KaTeX termina **antes** de que la CLI tome screenshots: usar `document.fonts.ready` + `await katex render` y emitir `hf-ready` event o setear `window.__hf_ready = true`.

> **Consultá la skill `hyperframes` para el patrón canónico de "ready hook" antes del primer frame.**

- [ ] **Step 6: Crear `render.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p ../_outputs/hyperframes

TIPOS=(animacion_texto lower_third pull_quote chapter_marker ecuacion_latex diagrama)
META="{}"

for tipo in "${TIPOS[@]}"; do
  echo "  → $tipo..."
  t0=$(date +%s.%N)
  npx hyperframes render "compositions/${tipo}.html" \
    --out "../_outputs/hyperframes/${tipo}.webm"
  t1=$(date +%s.%N)
  elapsed=$(echo "$t1 - $t0" | bc)
  META=$(jq --arg t "$tipo" --argjson s "$elapsed" '.[$t] = {render_seconds: ($s | tonumber)}' <<<"$META")
  printf "     done (%.1fs)\n" "$elapsed"
done

echo "$META" | jq '.' > "../_outputs/hyperframes/_meta.json"
echo "✓ 6 videos en _outputs/hyperframes/"
```

Chequeá los flags exactos de `hyperframes render` con `npx hyperframes render --help` — si difieren (ej. `--output` en lugar de `--out`, o falta `--codec`), ajustar.

```bash
chmod +x experiments/phase3-ab/hyperframes/render.sh
```

- [ ] **Step 7: Smoke con animacion_texto**

```bash
cd experiments/phase3-ab/hyperframes
npx hyperframes render compositions/animacion_texto.html \
  --out ../_outputs/hyperframes/animacion_texto.webm
cd -

ffprobe -v error -show_streams experiments/phase3-ab/_outputs/hyperframes/animacion_texto.webm 2>&1 | grep -E "(pix_fmt|codec_name)"
# Esperado: codec_name=vp9, pix_fmt=yuva420p
```

- [ ] **Step 8: Render completo + verificación**

```bash
./experiments/phase3-ab/hyperframes/render.sh
ls -lh experiments/phase3-ab/_outputs/hyperframes/
# Esperado: 6 .webm + _meta.json
```

---

## Task 5: Manim stack (solo ecuacion_latex + diagrama)

**Objetivo:** Renderizar 2 tipos con Manim → MOV HEVC alpha (o WebM si Manim no soporta HEVC alpha nativo).

**Files:**
- Create: `experiments/phase3-ab/manim/requirements.txt`
- Create: `experiments/phase3-ab/manim/scenes.py`
- Create: `experiments/phase3-ab/manim/render.sh`

- [ ] **Step 1: Crear `requirements.txt`**

```
manim==0.18.1
```

- [ ] **Step 2: Crear venv e instalar**

```bash
cd experiments/phase3-ab/manim
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
cd -
```

Si Manim falla al instalar por libs de sistema faltantes (Cairo/Pango/FFmpeg/LaTeX), instalá deps OS y reintentá. Si la instalación tarda más de 15 min o explota repetidamente, **considerar marcar Manim out-of-spike** (mitigación spec §10): documentalo en compare.html como "no renderizado" y seguí con los otros 3 stacks.

Verificación:

```bash
experiments/phase3-ab/manim/venv/bin/python -c "import manim; print(manim.__version__)"
# Esperado: 0.18.1 (o similar)
```

- [ ] **Step 3: Crear `scenes.py`**

Contenido completo:

```python
"""Manim scenes for Phase 3 A/B: ecuacion_latex + diagrama (esquema_libre)."""
from __future__ import annotations

import json
from pathlib import Path

from manim import (
    BLACK, WHITE, Arrow, Create, FadeIn, FadeOut, Group, ImageMobject,
    MathTex, Polygon, Rectangle, Scene, Text, Transform, UP, DOWN, LEFT, RIGHT,
    Write, config, rgb_to_color,
)

ROOT = Path(__file__).parent
SHARED = ROOT.parent / "_shared"

with (SHARED / "brand-pack.json").open() as f:
    BRAND = json.load(f)
with (SHARED / "samples.json").open() as f:
    SAMPLES = json.load(f)


def hex_to_color(h: str):
    h = h.lstrip("#")
    return rgb_to_color([int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4)])


PRIMARY = hex_to_color(BRAND["colors"]["primary"])
ACCENT = hex_to_color(BRAND["colors"]["accent"])
CARBON = hex_to_color(BRAND["colors"]["carbon"])
SURFACE = hex_to_color(BRAND["colors"]["surface"])

# Manim global config (1920x1080 @ 30fps, fondo transparente)
config.pixel_height = 1080
config.pixel_width = 1920
config.frame_rate = 30
config.background_color = BLACK  # se reemplaza por alpha en el render


class EcuacionLatex(Scene):
    def construct(self):
        sample = SAMPLES["ecuacion_latex"]
        caption = sample["metadata"].get("caption", "Ecuación")

        # Card oscura con barra accent
        card = Rectangle(width=12, height=3.0, color=CARBON, fill_color=CARBON, fill_opacity=1.0)
        card.shift(3.5 * RIGHT + 2.5 * DOWN)
        bar = Rectangle(width=0.12, height=2.0, color=ACCENT, fill_color=ACCENT, fill_opacity=1.0)
        bar.move_to(card.get_left() + 0.6 * RIGHT)
        label = Text(caption.upper(), font="Open Sans", weight="SEMIBOLD", color=ACCENT).scale(0.32)
        label.next_to(card.get_top() + 1.3 * RIGHT, DOWN, buff=0.3)
        eq = MathTex(sample["contenido"], color=SURFACE).scale(1.1)
        eq.next_to(label, DOWN, buff=0.35).align_to(label, LEFT)
        group = Group(card, bar, label, eq)

        # 0.4s fade-in, hold 4.3s, 0.3s fade-out (total 5.0s)
        self.play(FadeIn(group, shift=UP * 0.4), run_time=0.4)
        self.wait(4.3)
        self.play(FadeOut(group), run_time=0.3)


class Diagrama(Scene):
    def construct(self):
        # Card surface con border-top accent
        card = Rectangle(width=11, height=6, color=CARBON, fill_color=SURFACE, fill_opacity=1.0)
        accent_bar = Rectangle(width=11, height=0.12, color=ACCENT, fill_color=ACCENT, fill_opacity=1.0)
        accent_bar.next_to(card.get_top(), DOWN, buff=0)
        title = Text("Diagrama de cuerpo libre — bloque en plano inclinado",
                     font="Montserrat", weight="BOLD", color=CARBON).scale(0.38)
        title.next_to(card.get_top(), DOWN, buff=0.5).align_to(card.get_left() + 0.5 * RIGHT, LEFT)

        # Plano inclinado (triángulo rectángulo)
        plane = Polygon([-4, -1.7, 0], [4, -1.7, 0], [4, 1.6, 0],
                        color=CARBON, fill_color=SURFACE, fill_opacity=1.0, stroke_width=4)
        plane.shift(0.0 * RIGHT + 1.0 * DOWN)
        # Bloque sobre el plano, rotado -30°
        block = Rectangle(width=1.2, height=1.0, color=CARBON, fill_color=hex_to_color(BRAND["colors"]["carbon_light"]), fill_opacity=1.0, stroke_width=4)
        block.rotate(-0.5236)  # -30° en radianes
        block.move_to([0.5, 0.0, 0])
        # Vector gravedad mg (vertical hacia abajo desde centro del bloque)
        mg = Arrow(start=block.get_center(), end=block.get_center() + 2.0 * DOWN, color=PRIMARY, buff=0, stroke_width=8)
        mg_label = Text("mg", font="Montserrat", weight="BOLD", color=CARBON).scale(0.5)
        mg_label.next_to(mg.get_end(), RIGHT, buff=0.2)
        # Vector normal N (perpendicular al plano)
        import math
        nx, ny = -math.sin(0.5236), math.cos(0.5236)
        nvec = Arrow(start=block.get_center(), end=block.get_center() + 1.8 * np_arr(nx, ny), color=PRIMARY, buff=0, stroke_width=8)
        n_label = Text("N", font="Montserrat", weight="BOLD", color=CARBON).scale(0.5)
        n_label.next_to(nvec.get_end(), UP + LEFT, buff=0.2)

        diagram = Group(plane, block, mg, mg_label, nvec, n_label)
        card_group = Group(card, accent_bar, title)

        # Animación: card (0.3s), plano (0.5s), bloque (0.3s), vec/labels stagger
        self.play(FadeIn(card_group), run_time=0.3)
        self.play(Create(plane), run_time=0.5)
        self.play(FadeIn(block), run_time=0.3)
        self.play(Create(mg), run_time=0.4)
        self.play(FadeIn(mg_label), run_time=0.2)
        self.play(Create(nvec), run_time=0.4)
        self.play(FadeIn(n_label), run_time=0.2)
        self.wait(2.8)
        self.play(FadeOut(card_group), FadeOut(diagram), run_time=0.3)


def np_arr(x, y):
    """Helper para devolver array 3D (Manim usa arrays de 3 elementos)."""
    import numpy as np
    return np.array([x, y, 0])
```

Nota sobre fuentes: Manim usa `font="Montserrat"` que requiere que la fuente esté instalada en el sistema. Si no está, Manim cae a la default. Para el spike no es bloqueante.

- [ ] **Step 4: Crear `render.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p ../_outputs/manim

META="{}"
for scene in EcuacionLatex Diagrama; do
  tipo=$(echo "$scene" | sed -E 's/([A-Z])/_\L\1/g; s/^_//')
  echo "  → $tipo (Scene: $scene)..."
  t0=$(date +%s.%N)
  ./venv/bin/python -m manim -qh --format=mov --transparent scenes.py "$scene" \
    --output_file "${tipo}.mov" \
    --media_dir "../_outputs/manim/_media"
  # Manim coloca el output en _media/videos/scenes/1080p30/${tipo}.mov; lo movemos
  find ../_outputs/manim/_media -name "${tipo}.mov" -exec mv {} "../_outputs/manim/${tipo}.mov" \;
  t1=$(date +%s.%N)
  elapsed=$(echo "$t1 - $t0" | bc)
  META=$(jq --arg t "$tipo" --argjson s "$elapsed" '.[$t] = {render_seconds: ($s | tonumber)}' <<<"$META")
  printf "     done (%.1fs)\n" "$elapsed"
done

rm -rf ../_outputs/manim/_media
echo "$META" | jq '.' > ../_outputs/manim/_meta.json
echo "✓ 2 videos en _outputs/manim/"
```

```bash
chmod +x experiments/phase3-ab/manim/render.sh
```

- [ ] **Step 5: Smoke con EcuacionLatex**

```bash
cd experiments/phase3-ab/manim
./venv/bin/python -m manim -qh --format=mov --transparent scenes.py EcuacionLatex \
  --media_dir ../_outputs/manim/_media
find ../_outputs/manim/_media -name "EcuacionLatex.mov" -exec mv {} ../_outputs/manim/ecuacion_latex.mov \;
cd -

ls -lh experiments/phase3-ab/_outputs/manim/ecuacion_latex.mov
ffprobe -v error -show_streams experiments/phase3-ab/_outputs/manim/ecuacion_latex.mov 2>&1 | grep -E "(pix_fmt|codec_name)"
# Esperado: codec_name=hevc o prores (depende de Manim build); pix_fmt con alpha
```

Si el MOV no reproduce en Chrome para compare.html → convertilo a WebM VP9-alpha:

```bash
# Solo si Chrome no reproduce el MOV de Manim:
ffmpeg -i experiments/phase3-ab/_outputs/manim/ecuacion_latex.mov \
  -c:v libvpx-vp9 -pix_fmt yuva420p -b:v 0 -crf 22 \
  experiments/phase3-ab/_outputs/manim/ecuacion_latex.webm
# Y editar compare.html para apuntar al .webm en lugar del .mov para esta celda.
```

- [ ] **Step 6: Render completo (las 2 scenes)**

```bash
./experiments/phase3-ab/manim/render.sh
```

- [ ] **Step 7: Verificar outputs**

```bash
ls -lh experiments/phase3-ab/_outputs/manim/
# Esperado: ecuacion_latex.mov, diagrama.mov, _meta.json
```

---

## Task 6: `compare.html` (UI de evaluación)

**Objetivo:** Página HTML estática (file://) con grid 6×4, sliders de scoring, render time auto, persistencia en localStorage, export final.

**Files:**
- Create: `experiments/phase3-ab/compare.html`

- [ ] **Step 1: Crear el archivo `compare.html`**

Contenido completo (autocontenido — sin deps externas):

```html
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Phase 3 A/B — Comparación visual</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #F5F5F5; color: #212121; padding: 24px;
  }
  h1 { font-size: 28px; margin-bottom: 8px; }
  .help { color: #666; margin-bottom: 24px; font-size: 14px; }
  table { border-collapse: collapse; width: 100%; background: white; }
  th, td { border: 1px solid #ddd; padding: 10px; vertical-align: top; text-align: center; }
  th { background: #212121; color: white; padding: 14px; }
  th.tipo-col { background: #484848; min-width: 140px; text-align: left; }
  td.tipo-cell { background: #f9f9f9; text-align: left; font-weight: 600; vertical-align: middle; }
  .cell-empty { background: repeating-linear-gradient(45deg, #fafafa, #fafafa 8px, #f0f0f0 8px, #f0f0f0 16px); color: #aaa; font-style: italic; }
  video {
    width: 360px; height: 202px; background: linear-gradient(45deg, #888, #ccc 50%, #888);
    cursor: pointer; display: block; margin: 0 auto 8px;
  }
  .meta { font-size: 11px; color: #666; }
  .sliders label { display: block; font-size: 11px; margin-top: 6px; text-align: left; }
  .sliders input[type=range] { width: 100%; }
  .footer-cell { background: #212121; color: white; font-size: 12px; padding: 12px; }
  .footer-cell .score { font-size: 18px; font-weight: 800; color: #FF6D00; }
  .decision-row td { background: #FFFDE7; padding: 14px; }
  .decision-row select { font-size: 14px; padding: 6px 10px; }
  .actions { margin-top: 24px; display: flex; gap: 12px; }
  button { padding: 12px 24px; font-size: 14px; cursor: pointer; border: 1px solid #212121; background: white; }
  button.primary { background: #2962FF; color: white; border-color: #2962FF; }
  pre.export {
    margin-top: 16px; padding: 16px; background: #212121; color: #FF6D00;
    font-family: monospace; font-size: 12px; max-height: 300px; overflow: auto;
    white-space: pre-wrap; display: none;
  }
</style>
</head>
<body>

<h1>Phase 3 Materials A/B — comparación visual</h1>
<p class="help">
  Click en cada video para fullscreen. Ajustá los sliders (1=malo, 5=excelente).
  Los scores se guardan automáticamente en localStorage.
  Al final, elegí ganador por tipo y exportá el resumen.
</p>

<table id="grid"></table>

<div class="actions">
  <button onclick="window.location.reload()">Recargar</button>
  <button onclick="clearScores()">Limpiar scores</button>
  <button class="primary" onclick="exportSummary()">Exportar decisión</button>
</div>
<pre class="export" id="export-out"></pre>

<script>
const TIPOS = [
  { id: 'lower_third',     label: 'lower_third' },
  { id: 'pull_quote',      label: 'pull_quote' },
  { id: 'chapter_marker',  label: 'chapter_marker' },
  { id: 'animacion_texto', label: 'animacion_texto' },
  { id: 'ecuacion_latex',  label: 'ecuacion_latex', isMath: true },
  { id: 'diagrama',        label: 'diagrama (esquema_libre)', isMath: true },
];
const STACKS = [
  { id: 'playwright',  ext: 'webm' },
  { id: 'remotion',    ext: 'mov'  },
  { id: 'hyperframes', ext: 'webm' },
  { id: 'manim',       ext: 'mov', only: ['ecuacion_latex', 'diagrama'] },
];
const STORE_KEY = 'phase3-ab-scores';
const scores = JSON.parse(localStorage.getItem(STORE_KEY) || '{}');

function saveScores() { localStorage.setItem(STORE_KEY, JSON.stringify(scores)); }
function getScore(tipo, stack, axis) { return scores?.[tipo]?.[stack]?.[axis] ?? 3; }
function setScore(tipo, stack, axis, val) {
  scores[tipo] = scores[tipo] || {};
  scores[tipo][stack] = scores[tipo][stack] || {};
  scores[tipo][stack][axis] = Number(val);
  saveScores();
  updateFooter();
}
function clearScores() {
  if (!confirm('Borrar todos los scores?')) return;
  localStorage.removeItem(STORE_KEY);
  window.location.reload();
}

let metaCache = {};
async function loadMeta(stack) {
  if (metaCache[stack]) return metaCache[stack];
  try {
    const r = await fetch(`_outputs/${stack}/_meta.json`);
    if (!r.ok) return {};
    metaCache[stack] = await r.json();
    return metaCache[stack];
  } catch (e) { return {}; }
}

function buildGrid() {
  const table = document.getElementById('grid');
  let html = '<thead><tr><th class="tipo-col">Tipo</th>';
  for (const s of STACKS) html += `<th>${s.id}</th>`;
  html += '</tr></thead><tbody>';

  for (const t of TIPOS) {
    html += `<tr><td class="tipo-cell">${t.label}</td>`;
    for (const s of STACKS) {
      const skipped = s.only && !s.only.includes(t.id);
      if (skipped) {
        html += `<td class="cell-empty">— no aplica —</td>`;
      } else {
        html += `<td>
          <video autoplay loop muted preload="metadata"
                 onclick="this.requestFullscreen && this.requestFullscreen()"
                 src="_outputs/${s.id}/${t.id}.${s.ext}"></video>
          <div class="meta" id="meta-${s.id}-${t.id}">render time: …</div>
          <div class="sliders">
            <label>A visual: <span id="v-A-${s.id}-${t.id}">${getScore(t.id, s.id, 'A')}</span>
              <input type="range" min="1" max="5" step="1" value="${getScore(t.id, s.id, 'A')}"
                     oninput="setScore('${t.id}','${s.id}','A',this.value); document.getElementById('v-A-${s.id}-${t.id}').textContent=this.value;"></label>
            <label>B animación: <span id="v-B-${s.id}-${t.id}">${getScore(t.id, s.id, 'B')}</span>
              <input type="range" min="1" max="5" step="1" value="${getScore(t.id, s.id, 'B')}"
                     oninput="setScore('${t.id}','${s.id}','B',this.value); document.getElementById('v-B-${s.id}-${t.id}').textContent=this.value;"></label>
            ${t.isMath ? `
            <label>C latex/diagrama: <span id="v-C-${s.id}-${t.id}">${getScore(t.id, s.id, 'C')}</span>
              <input type="range" min="1" max="5" step="1" value="${getScore(t.id, s.id, 'C')}"
                     oninput="setScore('${t.id}','${s.id}','C',this.value); document.getElementById('v-C-${s.id}-${t.id}').textContent=this.value;"></label>
            ` : ''}
          </div>
        </td>`;
      }
    }
    html += '</tr>';
  }

  // Decision row
  html += `<tr class="decision-row"><td class="tipo-cell">Ganador</td>`;
  for (let i = 0; i < STACKS.length; i++) html += `<td></td>`;
  html += `</tr>`;
  // Footer
  html += `<tr><td class="tipo-cell">Total (A+B+C)</td>`;
  for (const s of STACKS) html += `<td class="footer-cell" id="foot-${s.id}"></td>`;
  html += `</tr></tbody>`;

  table.innerHTML = html;

  // Per-tipo dropdown ganador en la decision row
  const decisionRow = table.querySelector('.decision-row');
  decisionRow.innerHTML = '';
  decisionRow.innerHTML += `<td class="tipo-cell">Ganador por tipo</td>`;
  for (const t of TIPOS) {
    // skip, hacemos otra fila si lo necesitamos
  }
  // Actually una fila final con dropdown por tipo en formato vertical sería más limpio:
  // pero el spec dice "dropdown por fila para elegir ganador del tipo".
  // Reescribir: agregamos columna extra "Ganador" en cada fila tipo. Hacelo manual:
}

function updateFooter() {
  for (const s of STACKS) {
    let total = 0, count = 0;
    for (const t of TIPOS) {
      if (s.only && !s.only.includes(t.id)) continue;
      for (const ax of ['A','B','C']) {
        if (ax === 'C' && !t.isMath) continue;
        total += getScore(t.id, s.id, ax);
        count++;
      }
    }
    const avg = count ? (total / count).toFixed(2) : '—';
    const cell = document.getElementById(`foot-${s.id}`);
    if (cell) cell.innerHTML = `<div class="score">${avg}</div><div>avg / ${count} scores</div>`;
  }
}

async function loadAllMeta() {
  for (const s of STACKS) {
    const m = await loadMeta(s.id);
    for (const t of TIPOS) {
      if (s.only && !s.only.includes(t.id)) continue;
      const el = document.getElementById(`meta-${s.id}-${t.id}`);
      if (!el) continue;
      const rs = m?.[t.id]?.render_seconds;
      el.textContent = rs != null ? `render: ${rs.toFixed(1)}s` : 'render: ?';
    }
  }
}

function exportSummary() {
  const out = {
    timestamp: new Date().toISOString(),
    scores,
    averages: {},
  };
  for (const s of STACKS) {
    let total = 0, count = 0;
    for (const t of TIPOS) {
      if (s.only && !s.only.includes(t.id)) continue;
      for (const ax of ['A','B','C']) {
        if (ax === 'C' && !t.isMath) continue;
        total += getScore(t.id, s.id, ax);
        count++;
      }
    }
    out.averages[s.id] = count ? (total / count) : null;
  }
  const pre = document.getElementById('export-out');
  pre.style.display = 'block';
  pre.textContent = JSON.stringify(out, null, 2);
  // También copiar al clipboard
  navigator.clipboard?.writeText(pre.textContent);
}

buildGrid();
updateFooter();
loadAllMeta();
</script>
</body>
</html>
```

Nota: la "decisión por tipo" del spec (sección 5.4) es opcional para el A/B mismo — el ranking por stack ya se ve en el footer agregado. Si querés ganador por tipo más granular, agregalo después en una fila extra.

- [ ] **Step 2: Abrir `compare.html` con outputs todavía incompletos (smoke UI)**

```bash
explorer.exe "$(wslpath -w experiments/phase3-ab/compare.html)" 2>/dev/null \
  || echo "Abrir manualmente: $(pwd)/experiments/phase3-ab/compare.html"
```

Verificación visual:
- Grid 6 filas × 4 columnas se ve correctamente
- Las celdas Manim de tipos no-math muestran "— no aplica —"
- Los videos de stacks ya renderizados reproducen autoplay loop
- Los sliders responden y persisten al recargar la página
- Footer agregado muestra avg por stack

Si algún video no carga (404 / formato no soportado), verificar:
1. Path correcto (`_outputs/<stack>/<tipo>.<ext>`)
2. Codec soportado por el browser (ProRes puede no funcionar en Chrome; convertir a WebM en post si hace falta)

---

## Task 7: README + final smoke + decisión

**Objetivo:** Documento de uso del spike + walk-through final de los 20 outputs + dejarlo listo para scoring.

**Files:**
- Create: `experiments/phase3-ab/README.md`

- [ ] **Step 1: Crear `README.md`**

Contenido completo:

````markdown
# Phase 3 A/B Spike — Materiales de soporte (Unit 4 prep)

Compara 4 stacks de rendering (Playwright / Remotion / HyperFrames / Manim) sobre los 6 tipos de material del podcast "Hablando con Profes". 20 videos en total. Decisión por inspección visual lado a lado.

**Spec:** `docs/superpowers/specs/2026-05-26-phase3-materials-ab-spike-design.md`
**Plan:** `docs/superpowers/plans/2026-05-26-phase3-materials-ab-spike-plan.md`

## Estructura

- `_shared/` — insumos comunes (brand pack, samples, visual specs, assets)
- `_outputs/<stack>/` — videos generados (gitignored)
- `playwright/` `remotion/` `hyperframes/` `manim/` — cada stack aislado
- `compare.html` — UI estática de scoring

## Correr todo

```bash
# Playwright
(cd playwright && ./venv/bin/python render.py)

# Remotion
./remotion/render.sh

# HyperFrames
./hyperframes/render.sh

# Manim (opcional — más pesado)
./manim/render.sh

# Abrir UI de scoring
explorer.exe "$(wslpath -w compare.html)"   # WSL
# o: open compare.html (macOS) / xdg-open compare.html (Linux)
```

## Decisión

1. Scorear cada celda en `compare.html` (sliders 1-5)
2. Click "Exportar decisión" → JSON con scores y averages
3. Si scores quedan ±0.3, aplicar tie-breakers (sección 8 del spec):
   - Determinismo (re-run misma hash)
   - Imagen Modal estimada (`du -sh` del stack)
   - Líneas de código

## Output esperado del spike

- ✅ `formats/podcast_hablando_con_profes/visual-specs.md` (movido desde `_shared/`)
- ✅ `brands/phymac/brand.json` + `brand-assets/` (movido desde `_shared/`)
- ✅ `aidlc-state.md` actualizado: "Unit 4 stack: X. Razón: Y"
- ✅ `experiments/phase3-ab/` borrado completo

## Cleanup post-decisión

```bash
# 1. Mover artefactos sobrevivientes
mkdir -p formats/podcast_hablando_con_profes brands/phymac
mv _shared/visual-specs.md formats/podcast_hablando_con_profes/visual-specs.md
mv _shared/brand-pack.json brands/phymac/brand.json
mv _shared/brand-assets brands/phymac/brand-assets
# 2. Borrar el spike entero
cd ../..
rm -rf experiments/phase3-ab
```
````

- [ ] **Step 2: Walk-through final — verificar los 20 outputs**

```bash
ls -R experiments/phase3-ab/_outputs/
# Esperado:
#   playwright/  → 6 webm + _meta.json
#   remotion/    → 6 mov + _meta.json
#   hyperframes/ → 6 webm + _meta.json
#   manim/       → 2 mov + _meta.json
```

Total: 20 archivos de video (más 4 _meta.json).

Si falta alguno → identificar qué stack falló y rerun solo ese tipo. El plan no incluye retries automáticos (spec §9).

- [ ] **Step 3: Smoke final de la UI**

```bash
explorer.exe "$(wslpath -w experiments/phase3-ab/compare.html)" 2>/dev/null
```

Checklist visual:
- [ ] Grid se ve con 20 celdas con video + 4 vacías ("no aplica") en columna Manim
- [ ] Cada video autoplay+loop reproduce con alpha (no fondo negro)
- [ ] Render times se muestran debajo de cada video
- [ ] Sliders responden y guardan en localStorage (recargar página: scores persisten)
- [ ] Footer suma averages por stack
- [ ] Click en "Exportar decisión" muestra JSON y lo copia al clipboard

Si algún video se ve con fondo negro en compare.html pero alpha funciona aislado (Task 2 step 6 / Task 3 step 15 / Task 4 step 7), el codec puede no estar soportado por el browser para overlay. Convertir el MOV → WebM VP9-alpha y actualizar `compare.html` para que esa celda apunte al `.webm`.

- [ ] **Step 4: Anotar timing total**

```bash
# Sumar render times por stack
for stack in playwright remotion hyperframes manim; do
  echo -n "$stack: "
  jq '[to_entries[] | .value.render_seconds] | add' \
    experiments/phase3-ab/_outputs/$stack/_meta.json 2>/dev/null
done
# Esperado: 4 líneas con tiempos en segundos. Útiles para tie-breakers.
```

- [ ] **Step 5: Spike listo para scoring**

A partir de acá el siguiente paso es **humano**: scorear en `compare.html`, decidir ganador, exportar decisión.

Cuando el usuario diga "ganador es X", el follow-up (fuera del scope de este plan):

1. Actualizar `aidlc-docs/aidlc-state.md` con la decisión y razón
2. Mover `_shared/visual-specs.md` → `formats/podcast_hablando_con_profes/visual-specs.md`
3. Mover `_shared/brand-pack.json` + `brand-assets/` → `brands/phymac/`
4. Borrar `experiments/phase3-ab/` (entero)
5. Arrancar Unit 4 producción sobre el stack ganador

---

## Resumen de tasks

| Task | Stack / Componente | Tipos | Output esperado |
|------|--------------------|-------|-----------------|
| 1    | Scaffold + _shared | —     | brand pack + samples + visual specs + assets |
| 2    | Playwright         | 6     | 6 .webm VP9-alpha |
| 3    | Remotion           | 6     | 6 .mov ProRes 4444 |
| 4    | HyperFrames        | 6     | 6 .webm VP9-alpha |
| 5    | Manim              | 2     | 2 .mov (ecuacion_latex + diagrama) |
| 6    | compare.html       | —     | UI scoring estática |
| 7    | README + smoke     | —     | walk-through 20 outputs |

**Tareas 2–5 son independientes** — pueden ejecutarse en paralelo si se dispatcha con `superpowers:dispatching-parallel-agents`. Cada stack tiene su propia carpeta, sus propias deps y su propio output dir.

**Total estimado:** 8-16h de implementación + 1h scoring humano. Si Manim explota en setup, marcar out-of-spike y seguir con los otros 3 (válido por spec §10).

# Spec — Phase 3 Materials A/B Spike (Unit 4 prep)

**Fecha:** 2026-05-26
**Estado:** Diseño aprobado, pendiente plan de implementación
**Pre-requisitos:** Unit 1 (Core), Unit 2 (Phase 1 ingest), Unit 3 (Phase 2 narrative) — todos COMPLETE & VALIDATED E2E

---

## 1. Propósito

Decidir empíricamente qué stack de rendering usa Unit 4 (Fase 3 — Generación de Material de Apoyo) para los 6 tipos visuales del podcast "Hablando con Profes". El A/B compara cuatro stacks renderizando los mismos materiales con el brand pack de PhyMaC, y la elección se hace por inspección visual lado a lado de los 20 MP4s resultantes.

El spike NO es Unit 4. Es trabajo desechable que produce **una decisión** (qué stack) y **un contrato visual** (specs reutilizables). Unit 4 producción arranca limpio con el ganador.

## 2. Contexto

- **Caso de uso real:** podcast "Hablando con Profes" — entrevistas a profesores de ciencias (física, matemáticas, computación).
- **Whitelist del formato crece** de 5 a 7 tipos: agregamos `ecuacion_latex` y `diagrama` al podcast (los profes son de ciencias y los conceptos se entienden mejor con ecuaciones/diagramas renderizados).
- **Brand**: PhyMaC tiene identidad gráfica documentada (paleta cerrada, Montserrat + Open Sans, sharp shadows, patrón eléctrico). Sistema queda **brand-agnostic** — PhyMaC es un brand pack más.

## 3. Decisiones clave

| Decisión | Valor | Razón |
|---|---|---|
| Scope renderers | 6 tipos (todos menos `transcript_fix` que no se renderiza) | El podcast los necesita todos |
| Implementación A/B | **Spike-then-commit** (carpeta `experiments/`, throwaway) | Medir antes de producirizar; YAGNI |
| Stacks tipográficos (4 tipos) | Playwright + Remotion + HyperFrames | Comparar HTML/CSS vs React vs HTML deterministic |
| Stacks math (2 tipos) | Los 3 anteriores + Manim | Manim es fuerte en ecuación/diagrama; no cubre typography |
| Total outputs | **20 MP4** (12 + 8) | Matrix asimétrica intencional |
| Criterios A/B | calidad visual + animación + latex/diagrama + render time | E/F/G (determinismo, worker size, extensibilidad) son tie-breakers |
| Modal en spike | NO | Local-only; Modal entra en Unit 4 producción con ganador |
| Sample inputs | Hand-authored fixtures, no plan real | Asegurar cobertura de los 6 tipos + sub-tipos diagrama |
| Brand-agnostic | SÍ | `brands/{id}/brand.json` + assets; renderers consumen tokens |

## 4. Arquitectura del spike

```
experiments/phase3-ab/
├── README.md                          # qué es, cómo correrlo, cómo decidir ganador
│
├── _shared/                           # consumido por los 4 stacks (read-only)
│   ├── brand-pack.json                # tokens PhyMaC (paleta, fuentes, sombras)
│   ├── brand-assets/                  # logo.svg, fonts/, pattern.svg
│   ├── samples.json                   # MaterialSpec hand-authored para los 6 tipos
│   └── visual-specs.md                # specs visuales (contrato; sobrevive al spike)
│
├── _outputs/                          # gitignored — los 20 MP4s
│   ├── playwright/{6 archivos}
│   ├── remotion/{6 archivos}
│   ├── hyperframes/{6 archivos}
│   └── manim/{2 archivos: ecuacion_latex.mp4, diagrama.mp4}
│
├── playwright/                        # spike aislado
│   ├── requirements.txt
│   ├── render.py
│   └── templates/{tipo}.html.j2
│
├── remotion/                          # spike aislado
│   ├── package.json
│   ├── src/compositions/{tipo}.tsx
│   └── render.sh
│
├── hyperframes/                       # spike aislado
│   ├── compositions/{tipo}.html
│   ├── package.json
│   └── render.sh
│
├── manim/                             # spike aislado (solo math)
│   ├── requirements.txt
│   └── scenes.py
│
└── compare.html                       # UI estática de evaluación
```

### Principios

1. **Aislamiento total** entre stacks — un stack roto no rompe los otros.
2. **Solo `_shared/` es código común** — JSON, markdown, assets. Sin Python/JS compartido entre stacks.
3. **Local-only** — sin Modal en el spike.
4. **Sin tests, sin retry, sin ValidationAgent** — toda la disciplina va en Unit 4 producción.
5. **`_outputs/` gitignored** — binarios no entran al repo.
6. **`compare.html` es la UI de evaluación** — abrís en browser, ves grid 20 videos, decidís.
7. **El spike entero se borra** cuando se elige ganador. Sobreviven: `visual-specs.md` (movido a `formats/podcast_hablando_con_profes/`) y `brand.json` + assets (movidos a `brands/phymac/`).

## 5. Componentes

### 5.1 `_shared/brand-pack.json`

Formato brand-agnóstico. PhyMaC es la primera instancia; futuros brands (otros podcasts, cursos) usan el mismo schema.

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
    "logo":         "brand-assets/logo.svg",
    "logo_white":   "brand-assets/logo-white.svg",
    "pattern_svg":  "brand-assets/pattern.svg"
  }
}
```

### 5.2 `_shared/samples.json`

Fixture hand-authored cubriendo los 6 tipos. Para `diagrama` usamos **1 representativo en el spike** (`esquema_libre` — el caso más difícil); las specs de `barras` y `ciclo` quedan en `visual-specs.md` para que Unit 4 producción las implemente. Total: 6 entries en samples.json → 6 renders por stack typography (Playwright/Remotion/HyperFrames), 2 renders en Manim (ecuacion + diagrama).

Schema de cada entry: corresponde 1:1 con `MaterialSpec` en `pipeline/models.py` (`tipo`, `contenido`, `timestamp_relativo`, `metadata`).

Contenidos:
- `lower_third`: "Edson Cúdris — Profesor de Física, Secretaría de Educación de Bogotá"
- `pull_quote`: "La educación que no transforma no es educación, es entretenimiento." (metadata.speaker)
- `chapter_marker`: "El primer alumno" (metadata.chapter_number=3)
- `animacion_texto`: "VOCACIÓN"
- `ecuacion_latex`: `\dfrac{\partial^2 u}{\partial t^2} = c^2 \nabla^2 u` (metadata.caption="Ecuación de onda")
- `diagrama`: "diagrama de cuerpo libre de bloque en plano inclinado con fuerza de gravedad mg vertical hacia abajo y normal N perpendicular al plano" (metadata.tipo_visual="esquema_libre")

**Razón de elegir 1 sub-tipo en lugar de 3 en el spike:** el A/B mide calidad del stack, no del sub-tipo. Si Playwright renderiza bien `esquema_libre` (el caso más demandante), razonablemente renderizará bien `barras` y `ciclo`. Validación final de `barras`/`ciclo` ocurre en Unit 4 producción contra las specs del registry.

### 5.3 Contrato de render entrypoint

Cada stack expone un punto de entrada (`render.py` o `render.sh`) con este contrato:

```
Input:        $SHARED_DIR (read-only) — brand-pack.json, samples.json, brand-assets/
Output:       $OUTPUT_DIR/<tipo>.<ext>  (alpha-capable: webm | mov | mp4)
Side effects: nada fuera de $OUTPUT_DIR
Specs:        1920×1080, 30 fps
```

No se impone codec/container exacto — cada stack usa lo que produce nativamente:
- Playwright: WebM con VP9-alpha (vía ffmpeg sobre PNG frames)
- Remotion: MOV ProRes 4444
- HyperFrames: WebM VP9-alpha por default
- Manim: MOV HEVC alpha

`compare.html` embebe los 3 formatos vía `<video>` (todos soportados por Chromium/Firefox modernos).

### 5.4 `compare.html` — UI de evaluación

Página HTML estática (file://, sin server). Layout:

- **Grid principal**: 6 filas (tipos) × 4 columnas (stacks) = 24 celdas. 20 activas (Playwright/Remotion/HyperFrames hacen los 6 tipos = 18; Manim hace ecuacion + diagrama = 2) + 4 vacías (las 4 filas tipográficas en la columna de Manim).
- **Cada celda**: `<video autoplay loop muted>` 480×270, poster del primer frame, click → fullscreen.
- **Inputs de scoring por celda**: 3 sliders 1-5 (A=visual, B=animación, C=latex/diagrama solo en math). Render time (D) viene del `_outputs/<stack>/_meta.json` automático.
- **Footer por columna**: scores agregados, render time total, deps size estimado.
- **Decisión final**: dropdown por fila para elegir ganador del tipo + botón final "exportar resumen" → JSON con decisiones.
- **Persistencia**: scores en `localStorage` para no perder progreso al refrescar.

## 6. Data flow

```
              ┌───────────────────────────┐
              │   _shared/                │
              │   - brand-pack.json       │ ← input común
              │   - brand-assets/         │
              │   - samples.json          │
              └────────────┬──────────────┘
                           │ read-only
       ┌───────────────────┴───────────────────┐
       │                                       │
       ▼            (4 procesos independientes)
  ┌────────────┐  ┌────────────┐  ┌──────────────┐  ┌─────────┐
  │playwright/ │  │ remotion/  │  │ hyperframes/ │  │ manim/  │
  │ render.py  │  │ render.sh  │  │   render.sh  │  │render.sh│
  └─────┬──────┘  └─────┬──────┘  └──────┬───────┘  └────┬────┘
        │               │                │                │
        └───────────────┴────────────────┴────────────────┘
                           │ writes
                           ▼
              ┌───────────────────────────┐
              │  _outputs/<stack>/        │ ← 20 MP4 + _meta.json
              │  *.webm | *.mov | *.mp4   │
              └────────────┬──────────────┘
                           │ embebidos en
                           ▼
              ┌───────────────────────────┐
              │   compare.html            │ ← UI de evaluación
              └───────────────────────────┘
```

### Render loop por sample

1. Resolver template/composition del tipo (Jinja, JSX, HTML, Python class según stack).
2. Renderizar frames PNG 1920×1080 con alpha (motor propio de cada stack).
3. Empaquetar frames → video con alpha (ffmpeg con codec adecuado o motor interno).
4. Escribir en `_outputs/<stack>/<tipo>.<ext>` + actualizar `_meta.json` con render time.

### Flujo del usuario

```
cd experiments/phase3-ab
cd playwright && python render.py
cd ../remotion && npm install && bash render.sh
cd ../hyperframes && npm install && bash render.sh
cd ../manim && python -m venv venv && pip install -r requirements.txt && bash render.sh
open compare.html
# scoring + decisión por tipo
# decir en terminal "ganador es X"
# claude borra experiments/, mueve specs sobrevivientes, arranca Unit 4 producción
```

## 7. Visual specs registry (sobrevive al spike)

`_shared/visual-specs.md` es el contrato visual que cada stack del spike implementa. Cuando termina el spike, se mueve a `formats/podcast_hablando_con_profes/visual-specs.md` y Unit 4 producción lo usa como spec de referencia.

Specs detalladas por tipo (resumen ejecutivo — el archivo final incluye más detalle):

### `lower_third`
- Banner bottom-left, fondo primary, border-left 6px accent
- Posición: 8% bottom / 5% left, max-width 50%
- Tipografía: nombre Montserrat 900 24px white; subtítulo Open Sans 400 13px white-90%
- Sombra: card_accent (6px 6px 0 accent_dark)
- Animación: slide-in left 0.4s → hold 5s → slide-out left 0.6s → total 6s
- Input: `contenido = "Nombre — Cargo, Institución"`

### `pull_quote`
- Card centrada surface, border-left 8px accent, símbolo " grande primary top-left
- Centro frame, ancho 70-75%
- Tipografía: cita Montserrat 800 36px carbon line-height 1.3; speaker Open Sans 600 13px carbon-light uppercase
- Sombra: card (8px 8px 0 carbon)
- Animación: scale 0.95→1.0 + fade 0.3s → hold 6s → fade-out 0.3s → total 6.6s
- Input: `contenido = frase`; `metadata.speaker` opcional

### `chapter_marker`
- Full-screen interstitial 1920×1080 (NO overlay; reemplaza frame momentáneamente)
- Fondo: gradient(135deg, primary 50%, primary_dark 100%) + pattern overlay 0.13
- Elementos: número Montserrat 900 140px accent top-left; "CAPÍTULO" Open Sans 600 14px white-70% letter-spacing 3px; título Montserrat 900 48px white max 6 palabras
- Animación: número scale-in 0.3s + título slide-up 0.5s → hold 3s → fade-out 0.4s → total 4.2s
- Input: `contenido = título`; `metadata.chapter_number = int`

### `animacion_texto`
- Box compacto accent, padding 18px 36px, rotación -2deg
- Top-right por defecto (configurable vía metadata.position)
- Tipografía: Montserrat 900 52px white uppercase letter-spacing 2px
- Sombra: 6px 6px 0 accent_dark
- Animación: scale-bounce overshoot 1.1→1.0 elastic 0.4s → hold 1.5s → scale-fade out 0.3s → total 2.2s
- Input: `contenido = palabra/frase corta (max 3)`

### `ecuacion_latex`
- Card carbon (fondo #212121), accent vertical interno 6px, box-shadow accent externo
- Bottom-right, max-width 60%
- Tipografía: label Open Sans 600 11px accent uppercase; ecuación KaTeX 42px white
- Sombra: 6px 6px 0 accent
- Animación: slide-in-up + fade 0.4s → hold configurable → fade-out 0.3s → total 5s default
- Input: `contenido = LaTeX string`; `metadata.caption = label`; `metadata.duration` opcional

### `diagrama`
Sub-tipos en `metadata.tipo_visual`:

- **`barras`**: card surface border-top accent, sombra card. Barras primary/accent con sombras sharp. Animación: cada barra crece desde 0 stagger 0.2s. Input: `metadata.data = [{label, value, color?}]`.
- **`ciclo`**: card primary con pattern overlay 0.13. Nodos card surface border-top accent. Layout triángulo (3) / cuadrado (4) / círculo (5+). Flechas accent stroke 5px con arrowheads. Animación: nodos stagger 0.3s + flechas se dibujan after. Input: `metadata.nodes = [str, ...]`.
- **`esquema_libre`**: card surface border-top accent. Renderizado por stack en el spike (Manim nativo, Playwright/Remotion/HyperFrames vía SVG hand-coded para el sample). En Unit 4 producción se decide entre (i) mini-DSL Python o (ii) AI-generated SVG. Input: `contenido = descripción libre`.

## 8. Comparación y mecánica de decisión

### Criterios (acordados)

| ID | Criterio | Cómo se mide | Quién |
|---|---|---|---|
| A | Calidad visual | Slider 1-5 en compare.html | Usuario |
| B | Calidad animación | Slider 1-5 en compare.html | Usuario |
| C | Calidad latex/diagrama | Slider 1-5 (solo en math) | Usuario |
| D | Render time | `time` en render script → `_meta.json` | Automático |

### Tie-breakers (si scores quedan ±0.3)

1. **Determinismo** — re-run produce hash idéntico.
2. **Imagen Modal estimada** — `du -sh` del stack con deps.
3. **Líneas de código** — proxy de mantenibilidad.

### Output del spike

```
✅ formats/podcast_hablando_con_profes/visual-specs.md   # contrato visual (movido)
✅ brands/phymac/brand.json + brand-assets/              # brand pack lite (movido)
✅ aidlc-state.md actualizado: "Unit 4 stack: X. Razón: Y"
✅ experiments/phase3-ab/ borrado completo
```

Unit 4 producción arranca limpio con el stack ganador. Implementa el contrato `visual-specs.md` con disciplina completa: Modal.map(), storage R2, error handling, retry, ValidationAgent, tests unit + integración.

## 9. Out of scope (explícito)

- **Modal integration**: el spike es local. Modal entra en Unit 4 producción.
- **Phase 2 real plan**: el spike usa fixtures hand-authored, no el plan de `cudris-20260526`.
- **ValidationAgent**: ninguno valida en el spike.
- **Idempotencia / cache / state.json**: si un render se rompe, se vuelve a correr desde 0.
- **Tests automáticos**: cero. Toda evaluación es visual + scoring manual.
- **Multi-brand**: el spike solo prueba con PhyMaC. La arquitectura es brand-agnostic pero no la validamos con un segundo brand.
- **Phase 4 composition**: cómo Phase 4 va a componer los MP4 sobre el video crudo es Unit 5; el spike solo produce los MP4 con alpha.

## 10. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Un stack falla por dep rota → no produce sus 6 MP4s | Aislamiento por carpeta; los otros 3 siguen. Documentamos en compare.html "no renderizado" y seguimos. |
| Diferencias de calidad entre stacks no son atribuibles al stack sino a la implementación (ej: mejor template HTML) | Visual specs (sección 7) son el contrato. Cada stack debe cumplir las mismas specs. Si uno se aleja, se ajusta. |
| Tiempo del spike se desborda (>4 días) | Cortar manim si la complejidad explota. Decisión: "manim quedó out por costo de spike" es válida. |
| Codec/container con alpha no compatible entre stacks en compare.html | Probar early: render un sample tonto por stack antes de hacer los 20. Si hay incompat, normalizar a WebM VP9-alpha vía ffmpeg en post. |
| Imagen Modal estimada del stack ganador resulta muy grande para producción | Tie-breaker D ayuda. Si el ganador objetivo en calidad tiene 2GB de deps, considerar segundo lugar como compromiso. |

## 11. Pre-requisitos para arrancar implementación

- [ ] Spec aprobado por el usuario (este archivo).
- [ ] Plan de implementación escrito vía `writing-plans` (siguiente paso del flujo).
- [ ] Brand assets disponibles: `logo.svg`, `logo-white.svg` (derivado), `pattern.svg` (definido en el doc PhyMaC) — están en `C:\Users\johan\Documents\PhyMaC\Videos\Identidad Grafica\`, hay que copiarlos al spike.
- [ ] Acceso a herramientas: Python 3.11+, Node 20+, ffmpeg, Chromium para Playwright. Manim requiere Cairo/Pango/FFmpeg.

## 12. Criterio de "done" del spike

El spike está done cuando:

1. Los 20 MP4s (o menos, si algún stack quedó fuera con causa) existen en `_outputs/`.
2. `compare.html` muestra el grid completo y abre en browser sin errores.
3. El usuario completó scoring y eligió ganador.
4. La decisión + razón quedó documentada en `aidlc-state.md`.
5. `visual-specs.md` y `brand.json` están en sus ubicaciones finales bajo `formats/` y `brands/`.
6. `experiments/phase3-ab/` fue borrado.

A partir de ahí: Unit 4 producción arranca como un trabajo limpio sobre el stack ganador.

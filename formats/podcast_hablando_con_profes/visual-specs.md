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

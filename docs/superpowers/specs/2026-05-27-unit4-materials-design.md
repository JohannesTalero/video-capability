# Spec — Unit 4: Phase 3 Materiales de Soporte (vision-aware)

**Fecha:** 2026-05-27
**Estado:** Diseño aprobado por el usuario tras brainstorming. Pendiente plan de implementación.
**Pre-requisitos:** Unit 1 (Core + R2), Unit 2 (Phase 1 ingest), Unit 3 (Phase 2 narrative) — todos COMPLETE & VALIDATED E2E. A/B spike Phase 3 — COMPLETE (stack ganador: HyperFrames).

---

## 1. Propósito

Unit 4 implementa la Fase 3 del pipeline PhyMaC: tomar el plan narrativo de Phase 2 (lista de bloques con `support_material[]`), inspeccionar visualmente los frames del video crudo donde caería cada material, refinar la decisión narrativa según el contexto visual, y producir los assets renderizados (`.webm` con alpha 1920×1080 @ 30fps) más instrucciones de reframe para Phase 4.

**Diferencia clave vs el spike:** el spike rendereó materiales hand-authored en local. Unit 4 producción es vision-aware (mira el video crudo), corre sobre Modal con paralelismo `.map()`, persiste todo en R2, y produce un manifest auditado consumido por Phase 4.

## 2. Contexto

- **Caso de uso real:** podcast "Hablando con Profes" — episodio piloto `cudris-20260526` ya tiene Phase 1 + Phase 2 ejecutadas.
- **Stack de rendering:** HyperFrames (decidido en A/B spike 2026-05-26). Render via `--format mov` (ProRes `yuva444p12le`) + `ffmpeg` transcode a WebM VP9-alpha con `-auto-alt-ref 0`.
- **Whitelist crece:** se agregan `ecuacion_latex` y `diagrama` a la whitelist del podcast (5 → 7 tipos visuales).
- **Brand pack:** `brands/phymac/brand.json` + `brand-assets/` ya instalados.
- **Visual specs canónicas:** `formats/podcast_hablando_con_profes/visual-specs.md` (contrato visual de cada tipo).
- **AIDLC:** Unit 4 es el cuarto de 8 unidades del plan de construcción.

## 3. Decisiones clave (aprobadas en brainstorming)

| Decisión | Valor | Razón |
|---|---|---|
| Scope v1 | 6 tipos completos: lower_third, pull_quote, chapter_marker, animacion_texto, ecuacion_latex, diagrama | Cobertura total desde día 1; episodios reales lo necesitan |
| Estrategia esquema_libre | Templates + keywords con registry | Determinístico, brand-consistent. Phase 3a mapea descripción libre → template_id + params via LLM-vision. Fallback text card si no match |
| Templates iniciales v1 | `bloque_inclinado` (1 template) | Cubre caso Cudris; nuevos templates se agregan episodio a episodio |
| Granularidad Modal | Per-material `.map()` | Máximo throughput, idempotency granular, fallas aisladas |
| Failure policy | 1 retry + fallback text card | Episodio nunca queda incompleto; manifest reporta tasa de fallback |
| Frame analysis | LLM-vision por material (default `anthropic/claude-sonnet-4-6` via OpenRouter) | Permite refinar Phase 2 según frame real; costo aceptable (~$0.30/episodio) |
| Latitud de Phase 3a | Puede modify/drop materiales, NO puede agregar | Mantiene Phase 2 como autoridad narrativa; Phase 3a solo refina visualmente |
| Reframe instructions | Producidas por Phase 3a, consumidas por Phase 4 | Decoupling: Unit 4 decide; Unit 5 ejecuta |
| Cache levels | 3: frames extraídos, visual_plan, materials rendered | Re-runs eficientes si Phase 2 plan no cambia |
| Out-of-scope | Phase 4 composition, transcript_fix execution, multi-brand, audio en webm | Cada uno tiene su propia Unit |

## 4. Arquitectura

```
Phase 2 plan (R2: projects/<id>/phase2/plan.json)        Video raw (R2: projects/<id>/phase1/video.mp4)
        │                                                              │
        └──────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │  pipeline/phases/phase3_materials.py — orchestrator                    │
  │                                                                        │
  │  1. Cargar plan + format + brand pack + existing manifest (si hay)     │
  │  2. flatten_plan_to_materials() → List[(material_id, MaterialSpec)]    │
  │  3. Phase 3a — Visual planning (LLM-vision por material):              │
  │       ├─ ffmpeg extract frames @ [t-1s, t, t+1s] → R2 phase3/frames/   │
  │       ├─ LLM-vision call: PlanContext + 3 frames + brand + tmpl reg    │
  │       └─ Output: List[PlannedMaterial] → R2 phase3/visual_plan.json    │
  │  4. Filtrar planned por cache (skip si .webm existe + status=ok)       │
  │  5. Phase 3b — Render: Modal.map(render_material, payloads)            │
  │       └─ Cada call: HF render mov + transcode webm + upload R2         │
  │  6. Merge manifests (cached + recién renderizados)                     │
  │  7. ValidationAgent.validate_phase3(manifest, plan)                    │
  │  8. Upload final manifest → R2 phase3/materials_manifest.json          │
  └────────────────────────────────────────────────────────────────────────┘
                               │
                               ▼ por material en paralelo (Modal.map)
  ┌────────────────────────────────────────────────────────────────────────┐
  │  Modal function: render_material(payload)                              │
  │  Image: Python 3.12 + Node 22 + Chromium + ffmpeg + hyperframes        │
  │                                                                        │
  │  1. Si decision="drop" → manifest entry dropped, return                 │
  │  2. Dispatch renderer por tipo                                         │
  │  3. Inyectar contenido + metadata + position en composition variables  │
  │  4. npx hyperframes render . --composition ... --format mov            │
  │  5. ffmpeg transcode mov → webm VP9-alpha (-auto-alt-ref 0 -an)        │
  │  6. Validar output técnico (alpha, dims, duration)                     │
  │  7. Si error en cualquier paso → Modal retry 1×; si falla otra vez,    │
  │     render text card fallback                                          │
  │  8. Upload a R2: projects/<id>/phase3/materials/<material_id>.webm     │
  │  9. Return ManifestEntry                                               │
  └────────────────────────────────────────────────────────────────────────┘
```

### Principios arquitectónicos

1. **Separation of concerns:** Phase 2 = narrativa, Phase 3a = visual planning, Phase 3b = render, Phase 4 = composición. Cada uno escribe a R2 su contrato de salida.
2. **Idempotency por material_id estable.** Re-runs después de cambios parciales solo regeneran lo que cambió.
3. **Resilient by default:** retries automáticos (Modal), fallback text card, drop allowed (con threshold de validación).
4. **Audit trail:** todo se guarda en R2 (frames extraídos, visual_plan con reasoning, manifest con original + refined spec).
5. **Modal centralizado:** el orchestrator nunca ejecuta Chrome/HF — solo dispatcha a Modal.

## 5. Componentes

### 5.1 Estructura de archivos nueva

```
pipeline/
├── phases/
│   └── phase3_materials.py             # orchestrator
├── renderers/
│   ├── __init__.py                     # public API: render_material()
│   ├── dispatch.py                     # build_render_input() por tipo
│   ├── fallback.py                     # text card generator
│   ├── brand_css.py                    # render brand.json → brand.css
│   ├── output_validator.py             # checks técnicos del .webm
│   ├── diagram_templates/
│   │   └── registry.json               # template registry
│   └── hf-project/                     # HyperFrames project compartido
│       ├── package.json
│       ├── hyperframes.json
│       ├── index.html                  # stub
│       ├── brand.css                   # generado por brand_css.py
│       ├── brand-assets/               # symlink a brands/<id>/brand-assets
│       └── compositions/
│           ├── lower_third.html
│           ├── pull_quote.html
│           ├── chapter_marker.html
│           ├── animacion_texto.html
│           ├── ecuacion_latex.html
│           ├── diagrama_barras.html
│           ├── diagrama_ciclo.html
│           ├── diagrama_bloque_inclinado.html
│           └── text_card_fallback.html
├── vision/
│   ├── __init__.py
│   ├── frame_extractor.py              # ffmpeg wrapper
│   ├── visual_planner.py               # LLM-vision Phase 3a
│   └── prompts/
│       └── visual_planner_system.md    # prompt cargado en runtime
├── validators/
│   └── phase3_validator.py
├── modal_app.py                        # Modal app + render_material function
└── modal_render.py                     # render_one() — runs in worker
```

### 5.2 Modelos de datos (extiende `pipeline/models.py`)

```python
@dataclass
class PlannedMaterial:
    """Output de Phase 3a — la versión final del material con decisión visual."""
    material_id: str
    block_id: str
    original_spec: MaterialSpec         # tal como salió de Phase 2
    decision: str                       # "keep" | "modify" | "drop"
    spec_refined: MaterialSpec | None   # None si decision="drop"
    position: str | dict | None         # "bottom-left" o {x_pct, y_pct}
    reframe: dict | None                # {type, params, t_start_relative, t_end_relative}
    reasoning: str                      # razón en español

@dataclass
class RenderResult:
    material_id: str
    status: str                         # "ok" | "fallback" | "dropped"
    r2_key: str | None                  # None si dropped
    render_seconds: float
    error: str | None                   # populated si fallback

@dataclass
class ManifestEntry:
    material_id: str
    block_id: str
    original_spec: dict                 # MaterialSpec serializado
    refined_spec: dict | None
    decision: str
    position: str | dict | None
    reframe: dict | None
    reasoning: str
    render_status: str
    r2_key: str | None
    render_seconds: float
```

### 5.3 Diagram template registry (`pipeline/renderers/diagram_templates/registry.json`)

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

### 5.4 LLM-vision contract (Phase 3a)

**Input (multimodal message a OpenRouter):**

```
SYSTEM: pipeline/vision/prompts/visual_planner_system.md (cargado en runtime)

USER:
  [image_1: frame_t-1.png]
  [image_2: frame_t.png]
  [image_3: frame_t+1.png]
  
  Context JSON:
  {
    "phase2_context": {
      "block_id": "...",
      "block_name": "...",
      "material_spec": { "tipo":"...", "contenido":"...", "metadata":{...}, "timestamp_relativo": int },
      "transcript_window": "...texto del transcript ±5s..."
    },
    "brand": { /* colors + fuentes resumido */ },
    "visual_specs_summary": { /* posiciones default y carácter visual por tipo */ },
    "diagram_template_registry": [ /* solo si tipo=diagrama esquema_libre */ ]
  }
```

**Output JSON (strict, retry 1× si malformed):**

```json
{
  "decision": "keep" | "modify" | "drop",
  "spec_refined": {
    "tipo": "...",
    "contenido": "...",
    "timestamp_relativo": 222,
    "metadata": { /* tipo-specific */ }
  },
  "position": "bottom-left" | "top-right" | { "x_pct": 0.05, "y_pct": 0.85 },
  "reframe": null | {
    "type": "crop" | "zoom" | "replace_with_material",
    "params": { /* tipo-específico */ },
    "t_start_relative": 220.5,
    "t_end_relative": 226.5
  },
  "reasoning": "Speaker centrado, fondo libre, lower-third bottom-left no obstruye."
}
```

Cuando `decision="drop"`: `spec_refined=null`, `position=null`, `reframe=null`.

### 5.5 HyperFrames compositions

Cada `.html` declara variables con `data-composition-variables` y usa `window.__hyperframes.getVariables()` para leerlas. Estructura mínima:

```html
<html data-composition-variables='[ /* schema */ ]'>
<head>
  <link rel="stylesheet" href="../brand.css">
  <style>/* CSS scoped al composition-id */</style>
</head>
<body>
  <div data-composition-id="..." data-width="1920" data-height="1080" data-start="0" data-duration="N">
    <!-- content -->
  </div>
  <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
  <script>
    const vars = window.__hyperframes.getVariables();
    // ... aplicar vars al DOM ...
    window.__timelines = window.__timelines || {};
    const tl = gsap.timeline({ paused: true });
    // tweens (gsap.from para entrance, gsap.to para exit)
    window.__timelines["..."] = tl;
  </script>
</body>
</html>
```

Pattern canónico de la skill `hyperframes` — patrón viejo `window.__hf` está prohibido (vimos en spike que no funciona).

### 5.6 ValidationAgent.validate_phase3()

Schema validator de manifest + checks técnicos vía ffprobe + sampling. Detalles en sección "Validación" abajo.

## 6. Data flow

```
Phase 2 plan + Video raw
        │
        ▼
1. flatten_plan_to_materials()
   - Genera material_id estable (block_id + idx + content_hash[:8])
   - Output: [(material_id, MaterialSpec, block_id), ...]
        │
        ▼
2. Phase 3a — Visual planning
   Por cada material:
     a. extract_frames(video_url, [t-1, t, t+1]) → 3 PNGs
        - Cache: si frames ya existen en R2 phase3/frames/, skip
     b. build_vision_prompt_payload(material, frames, brand, specs, templates)
     c. POST OpenRouter (vision model) con multimodal message
     d. Parse + validate JSON output
        - Si malformed: 1 retry con feedback
        - Si vuelve a fallar: decision="keep" con position default por tipo
   Output: List[PlannedMaterial] → upload phase3/visual_plan.json
        │
        ▼
3. Build Modal payloads
   Por cada PlannedMaterial con decision != "drop":
     payload = {
       "planned": PlannedMaterial.to_dict(),
       "project_id": "...",
       "material_id": "...",
       "brand": brand_dict,
       "format_id": "podcast_hablando_con_profes"
     }
        │
        ▼
4. Modal.map(render_material, payloads)
   En paralelo, cada worker:
     a. ensure brand.css + brand-assets en /app/hf-project
     b. dispatch.build_render_input(planned) → (composition_path, variables)
     c. npx hyperframes render . --composition ... --variables ... --format mov
     d. ffmpeg transcode → .webm
     e. validate_output(.webm, planned) — alpha, dims, duration
     f. Si fail: render_text_card_fallback(planned)
     g. upload_r2(.webm, "projects/<id>/phase3/materials/<material_id>.webm")
     h. Return ManifestEntry
        │
        ▼
5. Merge manifest + upload
   - Materials cached + recién renderizados
   - Materials dropped (entry sin r2_key)
   - Upload: phase3/materials_manifest.json
        │
        ▼
6. ValidationAgent.validate_phase3()
   - Crítico falla → invalidar manifest + visual_plan, marcar phase FAILED
   - Warnings → log + permitir continuar
        │
        ▼
7. Result returned al Orchestrator
   - Phase 4 (Unit 5) lee phase3/materials_manifest.json
```

## 7. Phase 2 schema updates (necesarios)

### 7.1 `formats/podcast_hablando_con_profes/materials_whitelist.json`

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

### 7.2 MaterialSpec metadata schemas que Phase 2 emite

| tipo | contenido | metadata requerida | metadata opcional |
|---|---|---|---|
| `lower_third` | `"Nombre — Cargo, Institución"` | — | — |
| `pull_quote` | frase | — | `speaker: str` |
| `chapter_marker` | título | `chapter_number: int` | — |
| `animacion_texto` | ≤3 palabras | — | — |
| `ecuacion_latex` | LaTeX string | `caption: str` | `duration_seconds: float` |
| `diagrama` (barras) | nombre del gráfico | `tipo_visual: "barras", data: [{label, value}]` | `color_overrides` |
| `diagrama` (ciclo) | nombre del flujo | `tipo_visual: "ciclo", nodes: [str]` | — |
| `diagrama` (esquema_libre) | descripción libre | `tipo_visual: "esquema_libre"` | — (template lo asigna Phase 3a) |
| `transcript_fix` | corrección | (segmento target) | — |

**Phase 2 NO emite** `position` ni `reframe` — eso es Phase 3a.

### 7.3 `formats/podcast_hablando_con_profes/narrative_prompt.md` updates

Secciones nuevas:
- **Cuándo emitir `ecuacion_latex`:** speaker explica/cita una fórmula matemática explícita. Limitar a fórmulas KaTeX-compatibles. Lista de comandos LaTeX soportados.
- **Cuándo emitir `diagrama`:** referencias a algo visual no-textual.
- **Cómo elegir `tipo_visual`:**
  - `barras`: comparación cuantitativa explícita (rankings, porcentajes, datos).
  - `ciclo`: proceso/flujo secuencial (pasos, ciclo de algo).
  - `esquema_libre`: cualquier otra cosa física/espacial (físico-mecánica, anatomía, etc.).
- **Few-shot examples** para cada tipo nuevo.

## 8. Storage layout (R2)

```
projects/<project_id>/
├── phase1/
│   ├── transcription.json
│   ├── audio.wav
│   └── video.mp4                       # video raw original
├── phase2/
│   └── plan.json
├── phase3/
│   ├── frames/                         # 3 frames por material (debug + cache)
│   │   └── <material_id>_t{-1,0,+1}.png
│   ├── visual_plan.json                # Phase 3a output
│   ├── materials/                      # .webm por material no-dropped
│   │   └── <material_id>.webm
│   └── materials_manifest.json         # Phase 3c output (autoritativo)
└── phase3_validation.json
```

`<material_id>` = `f"{block_id}_m{idx:02d}_{content_hash[:8]}"`

## 9. Idempotency

3 niveles de cache verificados por phase3 orchestrator:

1. **Frames cache** — `phase3/frames/<material_id>_t{N}.png`. Skip ffmpeg extract si existe.
2. **Visual plan cache** — `phase3/visual_plan.json`. Si existe + sus materials matchean los del Phase 2 actual por material_id, skip Phase 3a entera. Si solo algunos materials matchean, Phase 3a corre solo para los nuevos/modificados.
3. **Render cache** — `phase3/materials/<material_id>.webm`. Skip render si existe + manifest dice `status=ok`.

**Auto-invalidación post-validation-fail:** si `validate_phase3()` retorna críticos, borrar `materials_manifest.json` + `visual_plan.json` en R2 antes del retry. Los `.webm` que pasan checks técnicos quedan (re-uso oportunista).

## 10. Validación (ValidationAgent.validate_phase3)

| Check | Tipo | Lógica |
|---|---|---|
| `manifest_exists_and_valid` | crítico | `materials_manifest.json` en R2, parseable, schema válido |
| `all_materials_have_status` | crítico | Cada entry tiene `render_status ∈ {ok, fallback, dropped}` |
| `r2_keys_resolvable` | crítico | Para `status ∈ {ok, fallback}`: HEAD a R2 confirma existencia |
| `webm_alpha_present` | crítico | Sample (1 de cada 5): ffprobe muestra `alpha_mode=1` |
| `webm_dimensions_correct` | crítico | Sample: 1920×1080 |
| `webm_duration_matches_spec` | crítico | Sample: duration ±0.2s del valor declarado por tipo |
| `whitelist_respected` | crítico | `spec_refined.tipo ∈ materials_whitelist.allowed` |
| `drop_rate_acceptable` | warning | `count(dropped) / count(total) ≤ 0.30` (validador del sistema; el episodio piloto debe estar bajo 0.20 — ver §14) |
| `fallback_rate_acceptable` | warning | `count(fallback) / count(total) ≤ 0.10` |
| `reasoning_quality` | warning | `reasoning` no contiene "no se ve / negro / vacío" en >20% de materiales |
| `reframe_consistency` | warning | Cada `reframe.t_*_relative` cae dentro del rango del material |

Score: 1.0 - (sum_weights críticos fallados / total_weights_críticos) * 0.6 - (warnings_fallados / total_warnings) * 0.4.
Recommendation strings en español (igual patrón que validator de Phase 2).

## 11. Modal worker

### 11.1 Image

- Base: `modal.Image.debian_slim(python_version="3.12")`
- apt: `ffmpeg`, `chromium`, `fonts-liberation`, `libcairo2`, `libpango-1.0-0`, `libpangocairo-1.0-0`, `curl`, `ca-certificates`
- Node 22 vía NodeSource
- pip: `boto3`, `python-dotenv`
- `add_local_dir(pipeline/renderers/hf-project, /app/hf-project)`
- `npm install` + warmup HF (render una composition tonta para cachear fonts)

### 11.2 Función

```python
@app.function(
    image=hf_image,
    secrets=[modal.Secret.from_name("phymac-r2-creds"), modal.Secret.from_name("phymac-openrouter")],
    timeout=600,
    cpu=2.0,
    memory=4096,
    retries=modal.Retries(max_retries=1, backoff_coefficient=2.0),
)
def render_material(payload: dict) -> dict:
    return render_one(payload)
```

### 11.3 Material ID

```python
def compute_material_id(block_id: str, idx_in_block: int, material_spec: MaterialSpec) -> str:
    content_hash = hashlib.sha256(
        f"{material_spec.tipo}|{material_spec.contenido}|"
        f"{json.dumps(material_spec.metadata, sort_keys=True)}".encode()
    ).hexdigest()[:8]
    return f"{block_id}_m{idx_in_block:02d}_{content_hash}"
```

### 11.4 Cost estimation (por episodio típico ~30 materiales)

- Modal render: 30 × 80s × $0.000150/CPU·s × 2 CPUs ≈ $0.72
- LLM-vision (Claude Sonnet 4.6 con 3 imágenes/material): ~$0.20-0.40
- LLM Phase 2 (already in Phase 2 budget)
- **Total Unit 4**: ~$1/episodio

## 12. Out-of-scope explícito

- **Phase 4 composition** (cómo se aplican overlays + reframes al video): Unit 5.
- **transcript_fix execution** (aplicación al audio): Unit 6.
- **Multi-brand A/B**: un proyecto = un brand.
- **Custom diagram templates por episodio dynamic**: v1 ship con `bloque_inclinado` solo. Más templates = PR manual.
- **Audio en los .webm**: visuals puros con alpha.
- **Live preview / Studio UI**: HF Studio disponible localmente para devs, no expuesto en Unit 8 frontend.
- **Detección automática de cambios en video raw**: invalidación de cache de Phase 3 es manual si el video cambia.
- **Cost cap por episodio**: ValidationAgent flagea post-hoc, no hay budget guardrail proactivo.

## 13. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Cold start de Modal image (Node + Chrome) | Warmup render en `run_commands` de la image; Modal mantiene containers ~5-10 min |
| LLM-vision retorna JSON malformed | Validación + 1 retry con feedback del error; fallback a `decision="keep"` con position default por tipo |
| HF crashea por LaTeX malformado (ecuacion_latex) | `throwOnError: false` en KaTeX render + validación de output (.webm > 0 bytes, duration > 0); si falla → fallback text card |
| Template `bloque_inclinado` no calza con descripción del Phase 2 | Phase 3a usa `fits_well` del registry como guía; si no match, fallback text card con `contenido` como string |
| Drop rate >30% | Validator warning; revisar prompts de Phase 3a / Phase 2 |
| Modal worker OOM / timeout | `cpu=2, memory=4096, timeout=600` configurados; chapter_marker (más pesado) probado en spike (~87s) |
| Frame extraction lento si video grande | ffmpeg con `-ss` antes de `-i` (seek rápido); frames cacheados en R2 |
| Tipos diagrama (barras/ciclo) sin data válida | Validación de schema antes de render; si malformed → fallback text card |
| Episodio cambia + Phase 3 ya corrió | material_id incluye content_hash → cambia → cache miss natural |

## 14. Criterio de "done" del Unit

Unit 4 está done cuando:

1. ✅ El flujo E2E corre sobre `cudris-20260526`: Phase 1 → Phase 2 → **Phase 3** → manifest válido + 30+ .webm en R2.
2. ✅ ValidationAgent passes (cero críticos, score > 0.85).
3. ✅ Re-run idempotente: segundo run de Phase 3 sobre mismo proyecto skip-eando todos los stages (cache hit completo).
4. ✅ Frame extraction funciona correctamente para video MP4 estándar (1920×1080 o 1080×1920).
5. ✅ Drop rate < 20% en el episodio piloto.
6. ✅ CI verde: ruff + mypy + pytest (3.11 + 3.12) + pip-audit + bandit.
7. ✅ Manifest format documentado para que Unit 5 (Phase 4) lo consuma sin sorpresas.
8. ✅ README de Unit 4 actualizado con ejemplos de uso + troubleshooting.

## 15. Pre-requisitos para arrancar implementación

- [x] Spec aprobado (este archivo).
- [ ] Plan de implementación escrito vía `superpowers:writing-plans`.
- [ ] Branch `feature/unit4-materials` creada (siguiendo `project_github_branch_strategy.md`).
- [ ] CI baseline verificado (los checks actuales pasan en `develop`).
- [ ] Modal token + R2 creds disponibles como Modal secrets: `phymac-r2-creds`, `phymac-openrouter`.
- [ ] Acceso al video `cudris-20260526.mp4` en R2 para tests E2E.

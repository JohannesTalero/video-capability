# Units 5–8 — Completar el pipeline (Fases 4–6 + UI iter. 1)

**Fecha:** 2026-06-09
**Estado:** Aprobado por el usuario (diseño por secciones, brainstorming 2026-06-09)
**Contexto previo:** Units 1–4 COMPLETE & VALIDATED E2E (proyecto de referencia `cudris-20260526`). Unit 4 mergeada en PR #8; stack de materiales = HyperFrames.

## 1. Alcance y decisiones del usuario

| Decisión | Valor |
|---|---|
| Alcance de la ronda | U5 + U6 + U8 (iteración 1) en paralelo; U7 secuencial al final |
| Alcance de UI (U8) | Solo iteración 1: ProjectAPI + Upload/Transcription/PlanEditor con tablas editables |
| Validación | Smoke E2E real sobre `cudris-20260526` por cada unit (como en Units 2–4) |
| Intro/outro | Generadas con HyperFrames desde el brand kit (`brands/phymac/`); **sin música** en esta ronda |
| Orquestación | Enfoque A: PR de contrato primero, luego 3 worktrees paralelos, merges ordenados |

## 2. Análisis de paralelización

**Paralelizable:**
- U5 ∥ U8: archivos 100% disjuntos (`pipeline/phases/phase4_compose.py` + `pipeline/brand.py` vs `pipeline/api.py` + `webapp/`).
- U6 ∥ U5 (solo desarrollo): `AudioProcessor` opera sobre un archivo genérico; unit tests con fixtures sintéticos. Su smoke real espera el output de U5.

**No paralelizable:**
- U7: integración E2E; requiere U5 y U6 mergeadas.
- Smoke real de U6 antes del merge+smoke de U5.
- Merges simultáneos de U5/U6 sin contrato previo (archivos calientes: `models.py`, `validator.py`).

## 3. PR de contrato compartido (paso 0, secuencial)

Un PR pequeño a `develop` que congela interfaces antes del trabajo paralelo:

1. **`pipeline/models.py`:**
   - Reconciliar `BrandConfig` con el schema real de `brands/phymac/brand.json` (creado por el spike): `colors` con `primary/primary_dark/accent/accent_dark/carbon/carbon_light/surface/background`, `fonts` con `display/body` + weights + source, `shadows`, `radius`, `pattern`, `assets` solo SVG (`logo`, `logo_white`, `pattern_svg`). Eliminar los campos `intro`/`outro`/`lower_third`/`cortinillas` de `BrandAssets` (la intro/outro ahora se generan).
   - Agregar `Phase5AudioResult`: `project_id`, `storage_key`, `loudness_in_lufs`, `loudness_out_lufs`, `true_peak_dbtp`, `noise_reduction_applied: bool`, `duration_seconds`, `process_time_seconds`.
   - `Phase4RenderResult` y `RenderConfig` ya existen y cubren Fases 4 y 6.
2. **`StorageKey`:** agregar `phase4_timeline(project_id)` → `projects/{id}/phase4/timeline.json` y `brand_render(project_id, name)` → `projects/{id}/phase4/brand/{name}.mp4` (intro/outro renderizadas). `composed_video`, `audio_processed_video`, `final_video` ya existen.
3. **Stubs de fases:** `pipeline/phases/phase4_compose.py`, `phase5_audio.py`, `phase6_render.py` siguiendo el patrón real de Fases 1–3: cada módulo expone una función de dominio (`run_phase4(plan, manifest, visual_plan, brand, ...) -> dict`) más un `register(orchestrator)` que registra el adapter `run_phase_n(state: ProjectState) -> dict`. En el contrato: docstring con inputs/outputs congelados y body `raise NotImplementedError`. Cada unit rellena exclusivamente su archivo.
4. **`pipeline/validator.py`:** comentarios de sección (`# --- Phase 4 (Unit 5) ---` etc.) marcando la región donde cada unit agrega su `validate_phaseN()`. Conflictos de merge → triviales o nulos.
5. **Contrato de API para U8:** sección 7 de este spec; el agente de UI no toca archivos de U5/U6.

## 4. Unit 5 — Fase 4: Composición + Branding

**`BrandManager`** (`pipeline/brand.py`): carga `brands/{id}/brand.json`, valida existencia de assets SVG, expone brand kit tipado (`BrandConfig` reconciliado). Reutiliza `pipeline/renderers/brand_css.py` para CSS vars de HyperFrames.

**Intro/outro:** composiciones HyperFrames `intro.html` y `outro.html` en `pipeline/renderers/hf-project/compositions/`, parametrizadas (título del episodio, logo, pattern, colores). Render en Modal reutilizando `modal_render.py`, como **MP4 opaco full-frame 1080p** (sin workaround de alpha). Duración ~5 s cada una. Se suben a `phase4/brand/`.

**`VideoComposer`** (`pipeline/phases/phase4_compose.py`, Modal CPU worker):
1. Lee de R2: plan narrativo, `materials_manifest.json`, `visual_plan.json`.
2. Computa el **timeline/EDL** → `phase4/timeline.json`: segmentos keep del video crudo, posición y ventana temporal de cada overlay (relativos al video editado), ubicación de chapter markers.
3. FFmpeg: trim + concat de segmentos; `chapter_marker` **full-frame entre segmentos** (cortinilla); `pull_quote`/`lower_third`/`animacion_texto` como **overlays con alpha** (`filter_complex overlay` + `enable=between(t,...)`) en la posición del visual planner.
4. Concat: intro + cuerpo + outro. Audio original intacto (Fase 5 lo procesa).
5. Output: `phase4/composed.mp4` + `phase4/timeline.json`. Checkpoint phase_4.

**`validate_phase4()`:** duración ≈ Σ segmentos keep + intro/outro + markers (±5 %); resolución 1920×1080; fps correcto; stream de audio presente; objeto en R2 con tamaño > 0; `timeline.json` parseable y consistente con el plan (mismos segment_ids, overlays ⊆ manifest).

**Smoke real:** `cudris-20260526` completo → episodio editado (~12 min) compuesto en R2.

## 5. Unit 6 — Fase 5: Audio

**`AudioProcessor`** (`pipeline/phases/phase5_audio.py`, Modal worker):
1. Input `phase4/composed.mp4` → extrae audio WAV 48 kHz.
2. **DeepFilterNet** (pip `deepfilternet`) para limpieza de ruido; CPU suficiente.
3. **loudnorm 2-pass** (FFmpeg) a **-14 LUFS** integrado, true peak ≤ -1 dBTP.
4. Remux audio procesado + video con `-c:v copy` → `phase5/audio_processed.mp4`. Checkpoint phase_5.
5. Sin música de fondo en esta ronda.

**`validate_phase5()`:** loudness integrado -14 ±1 LUFS (medido con `loudnorm print_format=json`); true peak < -1 dBTP; duración = input ±0.1 s; stream de video intacto (codec/resolución); tamaño > 0.

**Desarrollo:** en paralelo con U5 vía fixtures sintéticos (tonos + ruido generados con ffmpeg en tests). **Smoke real espera el merge+smoke de U5.**

## 6. Unit 7 — Fase 6: Render Final + Checkpoints (secuencial, al final)

**`VideoRenderer`** (`pipeline/phases/phase6_render.py`):
1. Input `phase5/audio_processed.mp4` → render final con `RenderConfig` (libx264 CRF 18 preset slow, AAC 192k, 1080p, `+faststart`).
2. Output `final/video.mp4` + URL presignada de descarga. Checkpoint phase_6 → proyecto `completed`.
3. Verificar reanudación 1→6 (`scripts/resume_pipeline.py` + orchestrator).

**`validate_phase6()`:** codec h264 + AAC; 1080p; moov atom al inicio; duración = phase5 ±0.1 s; URL descargable (HEAD 200).

**E2E completo:** cudris por todo el pipeline (resume desde fase 4 aprovecha checkpoints de 1–3). Criterio de done original: video final descargable; interrupción en Fase 4 reanuda sin repetir Fases 1–3.

## 7. Unit 8 — UI iteración 1 (ProjectAPI + Next.js básica)

**`ProjectAPI`** (`pipeline/api.py`, FastAPI, uvicorn local):
- `POST /projects` — crea proyecto, devuelve URL presignada R2 para upload directo desde browser.
- `POST /projects/{id}/phases/{n}/run` — dispara fase N en background (BackgroundTasks → orchestrator).
- `GET /projects/{id}` — estado completo desde `state.json`.
- `GET /projects/{id}/transcription` — transcripción con timestamps.
- `GET /projects/{id}/plan` / `PUT /projects/{id}/plan` — leer/editar plan narrativo; el PUT invalida checkpoints de fases ≥ 3.
- CORS habilitado para el dev server de Next.js.

**`webapp/`** (Next.js App Router, dev local): **Upload** (crear proyecto + subir a R2 con progreso), **Transcription** (tabla de segmentos), **PlanEditor** (tabla editable de bloques/segmentos/materiales + aprobar → correr siguiente fase). Sin drag & drop ni preview (iteración 2, post-U7).

## 8. Plan de ejecución

| Paso | Qué | Cómo |
|---|---|---|
| 0 | PR contrato | Secuencial, PR pequeño a develop |
| 1 | U5, U6, U8 en paralelo | 3 subagentes en worktrees aislados, cada uno con plan TDD propio |
| 2 | Merge U5 → smoke real cudris | PR + CI + smoke antes de aprobar |
| 3 | Merge U6 → smoke real | PR + CI + smoke (consume output de U5) |
| 4 | Merge U8 | PR + CI + verificación manual del flujo en browser |
| 5 | U7 → E2E completo | PR + E2E cudris con reanudación |
| 6 | Actualizar `aidlc-state.md` | PR final |

Cada unit: TDD, CI verde (ruff/mypy/pytest 3.11+3.12/security), smoke E2E real, PR a develop (nunca commit directo a develop), CodeRabbit como review automático.

## 9. Manejo de errores y riesgos

- **Overlays alpha en FFmpeg:** los `.webm` VP9 con alpha de Unit 4 requieren `-c:v libvpx-vp9` como decoder explícito para preservar alpha en `filter_complex`. Validado en el spike; el plan de U5 incluye un test de humo local de overlay antes del run en Modal.
- **Duración de composición en Modal:** el video crudo es 1.4 GB / 32 min; el worker descarga, corta y re-encodea. Timeout del worker dimensionado (≥ 30 min) y logs de progreso por etapa.
- **DeepFilterNet falla o degrada la voz:** `noise_reduction_applied=false` como fallback (solo loudnorm) con warning en la validación, no crítico.
- **Retries:** mismas reglas del orchestrator (MAX_PHASE_RETRIES, pausa al agotar).
- **Idempotencia:** cada fase hace short-circuit si su output ya existe en R2 (patrón de Fases 1–3).

## 10. Testing

- Unit tests por módulo (TDD): timeline/EDL puro (sin ffmpeg), brand manager, comandos ffmpeg construidos (sin ejecutar), API con TestClient, parsers de loudnorm JSON.
- Tests que requieren ffmpeg: marcados con el skip-pattern existente de CI (como `test_frame_extractor`).
- Smokes E2E reales por unit sobre `cudris-20260526` (sección 8).

# AI-DLC State Tracking

## Project Information
- **Project Name**: PhyMaC Video Auto-Edit Pipeline
- **Project Type**: Greenfield
- **Start Date**: 2026-05-21T00:00:00Z
- **Current Stage**: INCEPTION - Workspace Detection → Requirements Analysis

## Workspace State
- **Existing Code**: No (solo documentación de plan)
- **Reverse Engineering Needed**: No (Greenfield)
- **Workspace Root**: C:\Users\johan\Documents\PhyMaC\video-capability
- **Key Reference Doc**: pipeline-phymac-plan.md

## Stack Decisions (Pre-confirmed by user)
- **Backend compute**: Python + Modal.com (GPU workers)
- **Transcription**: OpenAI Whisper (large-v3)
- **Narrative AI**: Anthropic Claude API
- **Video processing**: FFmpeg
- **Animations**: Remotion (React)
- **Frontend**: Next.js (Vercel)
- **Storage**: Cloudflare R2 / AWS S3

## Code Location Rules
- **Application Code**: C:\Users\johan\Documents\PhyMaC\video-capability\ (workspace root)
- **Documentation**: aidlc-docs/ only
- **Structure patterns**: See units-generation and code-generation stages

## Extension Configuration
- **security-baseline**: OPTED OUT (personal/small team project, speed priority)
- **property-based-testing**: OPTED OUT (MVP stage, unit tests sufficient)

## Stage Progress

### 🔵 INCEPTION PHASE
- [x] Workspace Detection — COMPLETE
- [x] Reverse Engineering — SKIPPED (Greenfield)
- [x] Requirements Analysis — COMPLETE
- [x] User Stories — SKIPPED (herramienta interna, single user)
- [x] Workflow Planning — COMPLETE
- [x] Application Design — COMPLETE
- [x] Units Generation — COMPLETE
- [x] ValidationAgent Design — COMPLETE (agregado como componente transversal)

### 🟢 CONSTRUCTION PHASE (8 unidades)
- [x] Unit 1: Core Pipeline + Storage Layer — COMPLETE
- [x] Unit 2: Fase 1 — Ingesta & Transcripción — COMPLETE & VALIDATED E2E
  - Primer test real: video `Cudris_sin_reverb.mp4` (32.8 min, 1.42 GB) → 494 segmentos, 27,654 chars, español, score 1.00
  - Modal GPU: ~9 min total (build imagen + cold start + Whisper large-v3), transcripción real 6:16
  - Project ID: `cudris-20260526` — transcription JSON en R2: `projects/cudris-20260526/phase1/transcription.json`
  - Fix aplicado: envolver `transcribe_on_modal.remote()` en `with app.run():` (Modal moderno exige contexto para apps efímeras desde scripts)
  - Bugs menores resueltos (post-validación): (1) `orchestrator.run()` ahora acepta `end_at_phase`, `run_phase1.py` pasa `end_at_phase=1`; (2) outputs widening a `dict[str, Any]` con filtro JSON-scalar (str|int|float|bool|None); (3) Phase 1 idempotente — short-circuit si transcription_key existe, skip download/extract/upload si artefactos ya presentes. Retry post-fix tarda 2s vs 9+ min antes.
- [x] Unit 3: Fase 2 — Plan Narrativo — COMPLETE & VALIDATED E2E
  - Arquitectura `format_id` operativa: nuevo módulo `pipeline/formats.py` con `load_format()` cacheado; carpeta `formats/podcast_hablando_con_profes/` con `format.json` + `narrative_prompt.md` + `materials_whitelist.json`
  - `Project` ganó campo `format_id` (backward compat via `DEFAULT_FORMAT_ID` env var)
  - `MaterialSpec` ganó campo `metadata: dict` para soportar `transcript_fix` y futuras extensiones
  - Phase 2 runner (`pipeline/phases/phase2_narrative.py`) con idempotencia + auto-invalidación de cache en retries post-validation-fail
  - Validator refactorizado con 4 críticas (has_blocks, segment_ids_valid, no_duplicate_segments, material_tipos_in_whitelist) + 5 warnings (pull_quote_count, lower_third_count, duration_in_range, cold_open_structure, llm_coherence)
  - **Regla especial cold-open ↔ chapter overlap**: el primer bloque ("Cold open") puede compartir segments con sus capítulos naturales (teaser intencional); cualquier otro duplicado es crítico
  - 14 unit tests pasan (4 `test_formats.py` + 10 `test_validator_phase2.py`)
  - Smoke test E2E sobre `cudris-20260526`: PASS (score 0.78, 0 críticos). Plan generado por `openai/gpt-oss-120b:free`: 7 bloques, 29 segments, cold open con frases contraintuitivas "ley" y "homo sapiens", capítulos con nombres narrativos coincidentes con el plan editado a mano
  - Modelo default cambiado de `google/gemini-2.0-flash-exp:free` (deprecated, 404) a `openai/gpt-oss-120b:free`
  - Calidad de output del modelo free: estructuralmente válida pero conservadora en cortes (episodio sale 12 min vs target 22-32 min). Para producción usar modelo paid (Sonnet/GPT-4) via `LLM_MODEL_PLANNER` env var.
- [ ] Unit 4: Fase 3 — Generación de Materiales
- [ ] Unit 5: Fase 4 — Composición + Branding
- [ ] Unit 6: Fase 5 — Audio Processing
- [ ] Unit 7: Fase 6 — Render Final + Checkpoints
- [ ] Unit 8: UI Next.js Frontend
- [ ] Build and Test

### 🟡 OPERATIONS PHASE
- [ ] Operations — PLACEHOLDER

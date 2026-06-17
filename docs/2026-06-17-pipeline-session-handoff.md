# Handoff — Sesión 2026-06-17 (Fases 1-3 en 3 videos + producción Sonnet 4.6)

Resumen para retomar el trabajo (Fase 4+) en una sesión/asistente aparte.

## Qué se hizo

1. **Seguridad (CI verde):** bump `aiohttp 3.13.5→3.14.1`, `pip 26.1.1→26.1.2`; se ignora en CI el `CVE-2025-3000` de torch (sin fix upstream, ataque local vía `torch.jit.script` que el pipeline nunca expone).
2. **Modelo de producción:** planner/validator/vision → `anthropic/claude-sonnet-4-6` (antes free `openai/gpt-oss-120b:free`). En `pipeline/config.py` y `.env`.
3. **Se corrieron Fases 1-3** sobre los 3 videos de `Content_base` (formato `podcast_hablando_con_profes`).

### Bugs encontrados y corregidos al correr con el modelo real
| # | Fix | Commit |
|---|---|---|
| 1 | Claude envuelve JSON en ```` ```json ````; `strip_code_fence()` centralizado en `pipeline/llm.py`, usado en phase2 + 3 sitios del validator + visual_planner | `b49bbc9` |
| 2 | El modelo usaba el timestamp (s) como `segment_id`; formato de tabla desambiguado `seg=<id> \| t=<ini>-<fin>s` + coherence check `max_tokens` 256→1024 | `8197699` |
| 3 | `MAX_PHASE_RETRIES` 3→5 (robustez ante slips del LLM) | `62c28e4` |
| 4 | Fase 3 leía el video crudo de una key hardcodeada `phase1/video.mp4`; ahora usa `video_original_key` real (`input/<archivo>`) | `e5c642f` |
| 5 | `scripts/seed_brand.py` — sube el brand pack a R2 (Fase 3 lo requiere) | `89c80a5` |
| 6 | Validar materiales en `fallback` contra la duración del card fallback (5.0s), no la del tipo | `f1a910e` |

Todos los commits están en la rama **`feature/llm-prod-models`** (incluye el de seguridad `4bcd2a7`). Gates verdes: ruff + format + mypy + ~100 tests.

## Estado del pipeline (proyectos en R2, bucket `phymac-pipeline`)

| Proyecto | Video | F1 transcripción | F2 plan | F3 materiales |
|---|---|---|---|---|
| `diaz-20260617`   | Diaz_final.mp4 (49.6 min) | ✅ 1022 seg | ✅ 9 bloques | ✅ 43 materiales (score 1.00) |
| `cudris-20260617` | Cudris_sin_reverb.mp4 (32.8 min) | ✅ 777 seg | ✅ 9 bloques | ✅ 46 materiales (score 1.00) |
| `dji-20260617`    | DJI_…video-003.mp4 (40.3 min) | ✅ 895 seg | ✅ 10 bloques | ✅ 53 materiales (score 1.00) |

**Los 3 videos completaron Fases 1-3 con validación score 1.00.**

Artefactos por proyecto en R2:
- `projects/<id>/phase1/transcription.json`
- `projects/<id>/phase2/plan.json`
- `projects/<id>/phase3/materials_manifest.json` + `phase3/materials/*.webm` + `phase3/frames/*.png`
- `projects/<id>/state.json` (checkpoint del orquestador)
- Brand: `brands/phymac/brand.json` + `brands/phymac/brand-assets/*.svg`

## Cómo ver el avance

```bash
# Estado de fases de un proyecto (lee state.json de R2):
uv run python scripts/resume_pipeline.py --project-id diaz-20260617 --status

# Inspeccionar artefactos directamente: cualquier cliente S3/R2 sobre projects/<id>/...
```

> El run de Fase 3 corre en background vía `/tmp/phymac_run/driver_p3.sh`; logs en
> `/tmp/phymac_run/*_p3b.log` (efímeros — se pierden al reiniciar). La fuente de
> verdad persistente es R2 (`state.json` + artefactos).

## Cómo compartir / handoff al otro asistente

1. **Código:** `git push -u origin feature/llm-prod-models` y abrir PR a `develop`
   (sigue la estrategia de ramas del repo). Eso comparte los 8 fixes + este doc.
2. **Datos:** los 3 `project_id` de arriba — el otro asistente los retoma con
   `scripts/run_phase4_*` (cuando exista) o `resume_pipeline.py --project-id <id> --from-phase 4`.
3. **Plan de Fase 4:** ver `docs/superpowers/plans/2026-06-09-unit5-composition-plan.md`
   (composición + branding: intro/outro HyperFrames, timeline/EDL, FFmpeg en Modal).

## Notas para Fase 4+
- El modelo por defecto ya es Sonnet 4.6 (override con env `LLM_MODEL_*`).
- El brand pack ya está sembrado en R2 (`scripts/seed_brand.py` si se necesita re-sembrar).
- Los manifests de Fase 3 incluyen materiales con `render_status` `ok`/`fallback`/`dropped`;
  Fase 4 debería usar las duraciones reales del probe, no asumir `DURATION_BY_TIPO` para fallbacks.

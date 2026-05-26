# Units of Work
# PhyMaC Video Auto-Edit Pipeline

**Total de unidades**: 8  
**Estrategia**: Construcción secuencial respetando dependencias. Cada unidad es verificable de forma independiente antes de avanzar.

---

## Secuencia de Construcción

```
Unit 1 → Unit 2 → Unit 3 → Unit 4 → Unit 5 → Unit 6 → Unit 7
                                ↑
                           Unit 8 (UI) se construye en paralelo con Unit 3-4
```

---

## Unit 1 — Core Pipeline + Storage Layer

**Prioridad**: CRÍTICA · construir primero  
**Día objetivo**: Día 1 (mañana)  
**Duración estimada**: 2-3 horas

**Qué incluye**:
- `StorageAdapter` — abstracción R2/S3 (boto3 / r2 SDK)
- `PipelineOrchestrator` — máquina de estados, checkpoint save/load, retry loop (x2 reintentos → pausa)
- `ValidationAgent` — esqueleto + validadores técnicos base (FFprobe, pydub). Cada fase agrega sus validadores específicos.
- `models.py` — todos los dataclasses compartidos (TranscriptionResult, NarrativePlan, ValidationResult, etc.)
- `config.py` — variables de entorno, constantes
- `projects/{id}/state.json` — esquema de estado del proyecto
- Script CLI mínimo: `run_pipeline.py --project-id X --from-phase N`
- Setup de Modal.com: `modal setup`, token, primer app deployada

**Criterio de done**:
- `StorageAdapter.upload()` y `.download()` funcionando contra R2/S3 real
- `PipelineOrchestrator` puede guardar y cargar checkpoints
- Modal app deployada y callable desde local

**Componentes**: `StorageAdapter`, `PipelineOrchestrator`, `ValidationAgent` (base), `models.py`, `config.py`  
**Archivos**: `pipeline/storage.py`, `pipeline/orchestrator.py`, `pipeline/validator.py`, `pipeline/models.py`, `pipeline/config.py`, `scripts/run_pipeline.py`

---

## Unit 2 — Fase 1: Ingesta & Transcripción

**Prioridad**: CRÍTICA  
**Día objetivo**: Día 1 (tarde)  
**Duración estimada**: 2-3 horas  
**Depende de**: Unit 1

**Qué incluye**:
- `VideoIngestor` completo en Modal GPU Worker
- FFmpeg: extracción de audio del video MP4/MOV
- Whisper large-v3 self-hosted en Modal
- Guardado de transcripción en R2/S3
- Checkpoint phase_1 = completed
- Script CLI: `run_phase1.py --video path/al/video.mp4 --title "Mi Video"`

**Criterio de done**:
> Subís el video real de PhyMaC (> 30 min) y en < 10 minutos tenés la transcripción con timestamps impresa en terminal / guardada en R2/S3.

**Componentes**: `VideoIngestor`  
**Archivos**: `pipeline/phases/phase1_ingest.py`, `scripts/run_phase1.py`

---

## Unit 3 — Fase 2: Plan Narrativo (Claude API)

**Prioridad**: Alta  
**Día objetivo**: Día 2 (mañana)  
**Duración estimada**: 3-4 horas  
**Depende de**: Unit 1, Unit 2

**Qué incluye**:
- `NarrativePlanner` completo
- Sistema de prompts para Claude API (prompt engineering del plan narrativo)
- Parser y validador del JSON de respuesta de Claude
- Manejo de errores: si Claude devuelve JSON malformado → retry con prompt de corrección
- Guardado del plan en R2/S3
- Checkpoint phase_2 = completed
- Script CLI: `run_phase2.py --project-id X` (lee transcripción aprobada de storage)

**Criterio de done**:
> Dada la transcripción del video real, Claude genera un plan narrativo completo con bloques identificados, segmentos a conservar, y material de apoyo sugerido. El JSON es válido y parseable.

**Componentes**: `NarrativePlanner`  
**Archivos**: `pipeline/phases/phase2_plan.py`, `pipeline/prompts/narrative_planner.py`, `scripts/run_phase2.py`

---

## Unit 4 — Fase 3: Generación Paralela de Materiales

**Prioridad**: Alta  
**Día objetivo**: Día 3  
**Duración estimada**: 4-5 horas  
**Depende de**: Unit 1, Unit 3

**Qué incluye**:
- `MaterialGenerator` con dispatcher Modal.map()
- `LatexRenderer`: MathJax → Puppeteer headless → PNG → FFmpeg → MP4 con alpha
- `DiagramRenderer`: Matplotlib → SVG → FFmpeg → MP4 con alpha
- `AnimationRenderer`: Remotion → MP4 con alpha (requiere Node.js en el worker)
- Todos los outputs son MP4 con canal alpha (formato estándar para composición)
- Guardado de materiales en `projects/{id}/materials/` en R2/S3
- Checkpoint phase_3 = completed

**Criterio de done**:
> Dado un plan aprobado con 5–10 items de material, todos los MP4 generados en paralelo en < 5 minutos y disponibles en R2/S3.

**Componentes**: `MaterialGenerator`, `LatexRenderer`, `DiagramRenderer`, `AnimationRenderer`  
**Archivos**: `pipeline/phases/phase3_materials.py`, `pipeline/renderers/latex_renderer.py`, `pipeline/renderers/diagram_renderer.py`, `pipeline/renderers/animation_renderer.py`

---

## Unit 5 — Fase 4: Composición + Sistema de Branding Multi-marca

**Prioridad**: Alta  
**Día objetivo**: Día 4 (mañana)  
**Duración estimada**: 4-5 horas  
**Depende de**: Unit 1, Unit 4, assets PhyMaC disponibles

**Qué incluye**:
- `BrandManager` completo: load config JSON, validar assets, proveer paths
- `brands/phymac/config.json` y assets de PhyMaC en R2/S3 ← inventariar antes de este día
- `VideoComposer` completo: apply_cuts, overlay_materials, insert_transitions, apply_branding
- Pipeline FFmpeg orquestado en Modal CPU Worker
- Checkpoint phase_4 = completed

**Prerrequisito externo**: Tener los assets de PhyMaC inventariados y subidos a storage antes de este día.

**Criterio de done**:
> El video crudo de PhyMaC, cortado y con materiales de apoyo superpuestos, con intro/outro y branding aplicado, listo para procesamiento de audio.

**Componentes**: `BrandManager`, `VideoComposer`  
**Archivos**: `pipeline/brand.py`, `pipeline/phases/phase4_compose.py`, `brands/phymac/config.json`

---

## Unit 6 — Fase 5: Procesamiento de Audio

**Prioridad**: Media  
**Día objetivo**: Día 4 (tarde)  
**Duración estimada**: 2-3 horas  
**Depende de**: Unit 5

**Qué incluye**:
- `AudioProcessor`: clean_noise (DeepFilter), normalize_volume (FFmpeg loudnorm), mix_audio
- DeepFilter instalado en Modal Worker (pip install deepfilternet)
- Normalización a -14 LUFS (estándar YouTube)
- Mix con música si el usuario provee un archivo (ducking automático: voz 85%, música 15%)
- Checkpoint phase_5 = completed

**Criterio de done**:
> El audio del video compuesto suena limpio, con volumen normalizado, sin ruido de fondo perceptible.

**Componentes**: `AudioProcessor`  
**Archivos**: `pipeline/phases/phase5_audio.py`

---

## Unit 7 — Fase 6: Render Final + Sistema de Checkpoints Completo

**Prioridad**: Alta  
**Día objetivo**: Día 5 (mañana)  
**Duración estimada**: 3-4 horas  
**Depende de**: Units 1-6 (integración completa)

**Qué incluye**:
- `VideoRenderer`: render final 1080p (libx264 CRF 18, AAC 192k, preset slow)
- Upload del video final a R2/S3 con URL de descarga
- `PipelineOrchestrator` completo con todos los checkpoints integrados end-to-end
- Script de reanudación: `resume_pipeline.py --project-id X --from-phase N`
- Test de integración completo: video real de PhyMaC por todo el pipeline

**Criterio de done**:
> El video real de PhyMaC (> 30 min) procesado end-to-end en < 4 horas. Video final 1080p descargable. Si se interrumpe en Fase 4 y se reanuda, completa sin repetir Fases 1-3.

**Componentes**: `VideoRenderer`, `PipelineOrchestrator` (versión completa)  
**Archivos**: `pipeline/phases/phase6_render.py`, `scripts/resume_pipeline.py`

---

## Unit 8 — UI Frontend (Next.js)

**Prioridad**: Alta (pero no bloquea el pipeline)  
**Día objetivo**: Día 2 (básica), Día 5 (completa)  
**Duración estimada**: 6-8 horas total  
**Depende de**: `ProjectAPI` (que depende de Unit 1)

**Iteración 1 — Día 2** (básica, desbloquea revisión de transcripción y plan):
- `ProjectAPI` (FastAPI): endpoints de creación, estado, aprobación
- `WebUI` pantallas mínimas: Upload + TranscriptionView + PlanEditorView
- Sin drag & drop todavía, solo tablas editables

**Iteración 2 — Día 5** (completa):
- Drag & drop en PlanEditor
- PreviewView con player de video y timeline
- DownloadView con estado del render
- Polling de estado en tiempo real (polling cada 3s o WebSocket)

**Criterio de done (Día 2)**:
> Podés subir un video desde el browser, ver la transcripción y editar el plan narrativo.

**Criterio de done (Día 5)**:
> Pipeline completo operado 100% desde el browser: upload → transcripción → plan → preview → descarga.

**Componentes**: `ProjectAPI`, `WebUI`, `TranscriptionEditor`, `PlanEditor`  
**Archivos**: `pipeline/api.py`, `webapp/` (estructura Next.js completa)

---

## Resumen de Unidades

| Unit | Nombre | Día | Horas est. | Depende de | Verificable sin UI |
|------|-------|-----|-----------|-----------|-------------------|
| 1 | Core + Storage | Día 1 AM | 2-3h | — | ✅ Script CLI |
| 2 | Fase 1 Transcripción | Día 1 PM | 2-3h | U1 | ✅ Script CLI |
| 3 | Fase 2 Plan Narrativo | Día 2 AM | 3-4h | U1, U2 | ✅ Script CLI |
| 4 | Fase 3 Materiales | Día 3 | 4-5h | U1, U3 | ✅ Script CLI |
| 5 | Fase 4 Composición | Día 4 AM | 4-5h | U1, U4 | ✅ Script CLI |
| 6 | Fase 5 Audio | Día 4 PM | 2-3h | U5 | ✅ Script CLI |
| 7 | Fase 6 Render + Checkpoints | Día 5 AM | 3-4h | U1-U6 | ✅ Script CLI |
| 8 | UI Next.js | Día 2 + Día 5 | 6-8h total | U1 (API) | ❌ Necesita API |

**Total estimado**: 26-35 horas de desarrollo (~5 días)

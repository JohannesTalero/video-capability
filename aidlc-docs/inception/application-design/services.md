# Services
# PhyMaC Video Auto-Edit Pipeline

---

## Arquitectura de Servicios

El sistema tiene tres capas de servicios que se coordinan a través del `PipelineOrchestrator`:

```
┌─────────────────────────────────────────────────────────┐
│                    WebUI (Next.js)                       │
│         [Upload] [Editor] [Preview] [Download]           │
└────────────────────┬────────────────────────────────────┘
                     │ HTTP REST
┌────────────────────▼────────────────────────────────────┐
│                  ProjectAPI (FastAPI)                     │
│         Stateless · Valida requests · Retorna JSON        │
└────────────────────┬────────────────────────────────────┘
                     │ Python calls
┌────────────────────▼────────────────────────────────────┐
│              PipelineOrchestrator                         │
│   Coordina fases · Checkpoints · Retry · Estado          │
│                                                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ Phase 1  │ │ Phase 2  │ │ Phase 3  │ │ Phase 4+ │  │
│  │Ingestor  │ │Narrative │ │Material  │ │Composer  │  │
│  │          │ │Planner   │ │Generator │ │+Audio    │  │
│  │(Modal GPU│ │(Claude   │ │(Modal    │ │+Renderer │  │
│  │ Worker)  │ │  API)    │ │ .map())  │ │(Modal    │  │
│  └──────────┘ └──────────┘ └──────────┘ │ CPU)     │  │
│                                          └──────────┘  │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│             Servicios de Soporte                          │
│   ┌────────────────┐   ┌──────────────────────────────┐ │
│   │ StorageAdapter │   │       BrandManager            │ │
│   │  (R2 / S3)     │   │  (config JSON por marca)     │ │
│   └────────────────┘   └──────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## Service 1: TranscriptionService

**Patrón**: Async Job (fire and poll)  
**Ejecución**: Modal.com GPU Worker

Responsabilidad: recibir el video, procesarlo de forma asíncrona en Modal, y devolver el resultado.

```
Usuario sube video
      │
      ▼
ProjectAPI recibe el archivo → lo sube a R2/S3
      │
      ▼
PipelineOrchestrator.run(project_id, start_from_phase=1)
      │
      ▼
VideoIngestor.ingest() ejecuta en Modal GPU:
  1. FFmpeg extrae audio
  2. Whisper large-v3 transcribe
  3. Resultado guardado en R2/S3
  4. Checkpoint guardado: phase_1 = completed
      │
      ▼
Frontend polling GET /projects/{id} hasta status = "phase_1_complete"
      │
      ▼
Usuario ve transcripción editable en browser
```

---

## Service 2: NarrativePlanningService

**Patrón**: Request-Response con aprobación humana  
**Ejecución**: Modal.com Worker + Claude API (external)

```
Usuario aprueba transcripción (PUT /projects/{id}/transcription)
      │
      ▼
PipelineOrchestrator.run(start_from_phase=2)
      │
      ▼
NarrativePlanner.generate_plan():
  1. Construye prompt con transcripción
  2. Llama a Claude API (claude-sonnet)
  3. Parsea JSON de respuesta
  4. Valida estructura del plan
  5. Guarda plan en R2/S3
  6. Checkpoint: phase_2 = completed
      │
      ▼
Usuario edita y aprueba el plan en PlanEditor (POST /projects/{id}/phase/2/approve)
```

---

## Service 3: MaterialGenerationService

**Patrón**: Parallel Fan-Out  
**Ejecución**: N workers en Modal.com simultáneos (Modal.map())

```
Usuario aprueba plan narrativo
      │
      ▼
PipelineOrchestrator.run(start_from_phase=3)
      │
      ▼
MaterialGenerator.generate_all(plan):
  │
  ├── Worker A: LatexRenderer.render(bloque_1.material[0])
  ├── Worker B: DiagramRenderer.render(bloque_1.material[1])
  ├── Worker C: AnimationRenderer.render(bloque_2.material[0])
  ├── Worker D: LatexRenderer.render(bloque_3.material[0])
  └── ... (todos en paralelo)
      │
      ▼  (cuando todos completan)
  Todos los MP4 subidos a R2/S3
  Checkpoint: phase_3 = completed
```

---

## Service 4: CompositionService

**Patrón**: Sequential Pipeline (FFmpeg)  
**Ejecución**: Modal.com CPU Worker (4 cores)

```
PipelineOrchestrator.run(start_from_phase=4)
      │
      ▼
BrandManager.load("phymac") → BrandConfig
      │
      ▼
VideoComposer.compose():
  1. apply_cuts()          → video_cut.mp4
  2. overlay_materials()   → video_with_material.mp4
  3. insert_transitions()  → video_with_transitions.mp4
  4. apply_branding()      → video_branded.mp4
  5. Checkpoint: phase_4 = completed
```

---

## Service 5: AudioProcessingService

**Patrón**: Sequential Pipeline  
**Ejecución**: Modal.com Worker

```
PipelineOrchestrator.run(start_from_phase=5)
      │
      ▼
AudioProcessor.process(video_branded.mp4, music_path=None):
  1. clean_noise()         → video_clean_audio.mp4
  2. normalize_volume()    → video_normalized.mp4
  3. mix_audio() si hay música provista por usuario
  4. Checkpoint: phase_5 = completed
```

---

## Service 6: RenderService

**Patrón**: Long-Running Job  
**Ejecución**: Modal.com CPU Worker (8 cores, timeout 30 min)

```
PipelineOrchestrator.run(start_from_phase=6)
      │
      ▼
VideoRenderer.render(config=RenderConfig(1080p, CRF18)):
  1. FFmpeg render final (libx264, AAC 192k)
  2. upload_final() → R2/S3
  3. Genera presigned URL
  4. Checkpoint: phase_6 = completed · project = DONE
      │
      ▼
Usuario ve video listo en UI con link de descarga
```

---

## Service 7: CheckpointService (transversal)

**Patrón**: State Machine  
**Ejecución**: Embebido en PipelineOrchestrator

Cada proyecto tiene un estado persistido en storage (`projects/{id}/state.json`):

```json
{
  "project_id": "my-proyecto-phymac",
  "title": "Ondas Electromagnéticas — Episodio 12",
  "brand_id": "phymac",
  "created_at": "2026-05-21T00:00:00Z",
  "current_phase": 3,
  "phases": {
    "1": {"status": "completed", "completed_at": "...", "outputs": {"transcription": "s3://..."}},
    "2": {"status": "completed", "completed_at": "...", "outputs": {"plan": "s3://..."}},
    "3": {"status": "running",   "started_at": "..."},
    "4": {"status": "pending"},
    "5": {"status": "pending"},
    "6": {"status": "pending"}
  }
}
```

Reanudar desde una fase que falló:
```bash
python pipeline.py resume --project-id my-proyecto-phymac --from-phase 3
```

---

## Service 8: BrandService (transversal)

**Patrón**: Configuration as Code  
**Ejecución**: Python module, sin worker propio

Estructura en storage:
```
brands/
  phymac/
    config.json          ← colores, fuentes, nombres de assets
    logo.png             ← con alpha
    intro.mp4
    outro.mp4
    cortinilla_concepto.mp4
    cortinilla_datos.mp4
    lower_third.svg      ← template con variables {{title}}, {{name}}
  otra_marca/
    config.json
    ...
```

Para agregar una nueva marca: crear la carpeta con sus assets y su `config.json`. Sin cambio de código.

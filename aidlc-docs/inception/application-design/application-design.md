# Application Design — Consolidado
# PhyMaC Video Auto-Edit Pipeline

**Versión**: 1.0 · **Fecha**: 2026-05-21

---

## Vista General del Sistema

```
┌──────────────────────────────────────────────────────────────────┐
│                         FRONTEND                                  │
│   Next.js · Vercel (o self-hosted)                               │
│                                                                   │
│  [UploadScreen] → [TranscriptionView] → [PlanEditorView]         │
│                                    → [PreviewView] → [Download]  │
└──────────────────────────┬───────────────────────────────────────┘
                           │ HTTP REST
┌──────────────────────────▼───────────────────────────────────────┐
│                       ProjectAPI                                  │
│   FastAPI · Modal.com (o Railway)                                │
│   Stateless · Valida requests · Coordina con Orchestrator        │
└──────────────────────────┬───────────────────────────────────────┘
                           │ Python calls
┌──────────────────────────▼───────────────────────────────────────┐
│                  PipelineOrchestrator                             │
│   Gestiona el ciclo de vida del proyecto                         │
│   Checkpoints · Retry · Estado persistido en storage             │
│                                                                   │
│  ┌────────────┐ ┌────────────┐ ┌──────────────┐ ┌────────────┐ │
│  │VideoIngestor│ │Narrative  │ │Material      │ │VideoComposer│ │
│  │            │ │Planner    │ │Generator     │ │AudioProcessor│ │
│  │Whisper GPU │ │Claude API │ │Modal.map()   │ │VideoRenderer│ │
│  │Modal Worker│ │Modal Work.│ │N Workers     │ │Modal Worker │ │
│  └────────────┘ └────────────┘ └──────────────┘ └────────────┘ │
│                                                                   │
│  ┌──────────────────────┐   ┌──────────────────────────────────┐ │
│  │   StorageAdapter     │   │       BrandManager               │ │
│  │  Cloudflare R2 / S3  │   │  Multi-marca · Config JSON       │ │
│  └──────────────────────┘   └──────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
                           │
                     External APIs
              Claude API · Whisper (self-hosted)
```

---

## Resumen de Componentes (13 en total)

| # | Componente | Capa | Responsabilidad |
|---|-----------|------|----------------|
| 1 | `VideoIngestor` | Backend · Modal GPU | Upload → extracción de audio → Whisper → transcripción |
| 2 | `TranscriptionEditor` | Frontend · Next.js | Editor inline de transcripción |
| 3 | `NarrativePlanner` | Backend · Modal + Claude API | Genera plan narrativo estructurado |
| 4 | `PlanEditor` | Frontend · Next.js | Tabla editable + drag & drop de bloques |
| 5 | `MaterialGenerator` | Backend · Modal (paralelo) | Genera materiales de apoyo en paralelo |
| 6 | `BrandManager` | Backend · Python module | Config multi-marca, assets de identidad |
| 7 | `VideoComposer` | Backend · Modal CPU | Ensamblaje FFmpeg: cortes + overlays + branding |
| 8 | `AudioProcessor` | Backend · Modal | Limpieza + normalización + mezcla |
| 9 | `VideoRenderer` | Backend · Modal CPU | Render final 1080p + upload a storage |
| 10 | `PipelineOrchestrator` | Backend · Python | Coordina fases, checkpoints, retry |
| 11 | `StorageAdapter` | Backend · Python module | Abstracción R2/S3 |
| 12 | `ProjectAPI` | Backend · FastAPI | REST API → frontend |
| 13 | `WebUI` | Frontend · Next.js | Interfaz completa (upload → preview → descarga) |

---

## Estructura de Directorios del Proyecto (target)

```
video-capability/
│
├── pipeline/                        # Backend Python
│   ├── orchestrator.py              # PipelineOrchestrator
│   ├── storage.py                   # StorageAdapter
│   ├── brand.py                     # BrandManager
│   │
│   ├── phases/
│   │   ├── phase1_ingest.py         # VideoIngestor (Modal GPU)
│   │   ├── phase2_plan.py           # NarrativePlanner (Claude API)
│   │   ├── phase3_materials.py      # MaterialGenerator (Modal.map)
│   │   ├── phase4_compose.py        # VideoComposer (FFmpeg)
│   │   ├── phase5_audio.py          # AudioProcessor (DeepFilter)
│   │   └── phase6_render.py         # VideoRenderer (FFmpeg)
│   │
│   ├── renderers/                   # Sub-renderers para materiales
│   │   ├── latex_renderer.py        # MathJax → MP4
│   │   ├── diagram_renderer.py      # Matplotlib → MP4
│   │   └── animation_renderer.py    # Remotion → MP4
│   │
│   ├── api.py                       # ProjectAPI (FastAPI)
│   ├── models.py                    # Dataclasses compartidas
│   └── config.py                    # Variables de entorno, constantes
│
├── webapp/                          # Frontend Next.js
│   ├── app/
│   │   ├── page.tsx                 # Home / lista de proyectos
│   │   ├── projects/
│   │   │   ├── new/page.tsx         # Upload screen
│   │   │   └── [id]/
│   │   │       ├── page.tsx         # Estado del proyecto
│   │   │       ├── transcription/   # TranscriptionView
│   │   │       ├── plan/            # PlanEditorView
│   │   │       ├── preview/         # PreviewView
│   │   │       └── download/        # DownloadView
│   │   └── api/                     # API routes (proxy al backend)
│   └── components/
│       ├── VideoUploader.tsx
│       ├── TranscriptionEditor.tsx
│       ├── PlanEditor.tsx
│       ├── VideoPlayer.tsx
│       └── Timeline.tsx
│
├── brands/                          # Assets de identidad por marca
│   └── phymac/
│       ├── config.json
│       ├── logo.png
│       ├── intro.mp4
│       ├── outro.mp4
│       └── cortinillas/
│
├── scripts/                         # CLI para Día 1 (antes de UI completa)
│   ├── run_phase1.py
│   ├── run_phase2.py
│   └── resume_pipeline.py
│
└── aidlc-docs/                      # Documentación AIDLC (este directorio)
```

---

## Contratos de Datos entre Fases (resumen)

```
Fase 1 output → Fase 2 input:
  TranscriptionResult { segments: [{id, start, end, text}], full_text, duration }

Fase 2 output → Fase 3 input:
  NarrativePlan { blocks: [{id, name, segments[], support_material[], transition}] }

Fase 3 output → Fase 4 input:
  list[MaterialAsset] { block_id, storage_path, duration, has_alpha }

Fase 4 output → Fase 5 input:
  path: str  (video compuesto en storage)

Fase 5 output → Fase 6 input:
  path: str  (video con audio procesado en storage)

Fase 6 output → Usuario:
  RenderResult { download_url, file_size_mb, duration_seconds }
```

---

## Sistema de Checkpoints

Cada fase escribe su resultado en `projects/{project_id}/state.json` antes de retornar. Si algo falla en Fase N, el usuario ejecuta `resume_pipeline.py --from-phase N` y el sistema retoma desde ahí, cargando los outputs de las fases anteriores desde storage.

---

## Sistema Multi-Marca

```
brands/{brand_id}/config.json:
{
  "brand_id": "phymac",
  "display_name": "PhyMaC",
  "colors": {
    "primary": "#1A1A2E",
    "secondary": "#E94560",
    "accent": "#0F3460",
    "text": "#FFFFFF"
  },
  "fonts": {
    "heading": "Space Grotesk",
    "body": "Inter"
  },
  "assets": {
    "logo": "brands/phymac/logo.png",
    "intro": "brands/phymac/intro.mp4",
    "outro": "brands/phymac/outro.mp4",
    "cortinilla_concepto": "brands/phymac/cortinillas/concepto.mp4",
    "lower_third": "brands/phymac/lower_third.svg"
  }
}
```

Agregar una nueva marca = crear `brands/nueva_marca/config.json` + sus assets. Sin cambio de código.

---

## Referencias a documentos detallados

- [components.md](./components.md) — Definición completa de los 13 componentes
- [component-methods.md](./component-methods.md) — Firmas de métodos y tipos de datos
- [services.md](./services.md) — Patrones de servicio y flujos de datos por fase
- [component-dependency.md](./component-dependency.md) — Matriz de dependencias y comunicación

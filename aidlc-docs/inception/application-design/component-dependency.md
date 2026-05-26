# Component Dependency Map
# PhyMaC Video Auto-Edit Pipeline

---

## Matriz de Dependencias

| Componente | Depende de | Es usado por |
|-----------|-----------|-------------|
| `VideoIngestor` | `StorageAdapter` | `PipelineOrchestrator` |
| `NarrativePlanner` | `StorageAdapter` | `PipelineOrchestrator` |
| `MaterialGenerator` | `StorageAdapter` | `PipelineOrchestrator` |
| `BrandManager` | `StorageAdapter` | `VideoComposer` |
| `VideoComposer` | `StorageAdapter`, `BrandManager` | `PipelineOrchestrator` |
| `AudioProcessor` | `StorageAdapter` | `PipelineOrchestrator` |
| `VideoRenderer` | `StorageAdapter` | `PipelineOrchestrator` |
| `PipelineOrchestrator` | `StorageAdapter`, todos los workers | `ProjectAPI` |
| `StorageAdapter` | R2/S3 (externo) | Todos los componentes backend |
| `ProjectAPI` | `PipelineOrchestrator` | `WebUI` |
| `WebUI` | `ProjectAPI` | Usuario final |
| `TranscriptionEditor` | `ProjectAPI` | Usuario final |
| `PlanEditor` | `ProjectAPI` | Usuario final |

---

## Flujo de Datos por Fase

```
[Usuario]
    │ upload video + título
    ▼
[WebUI] ──────────────────────────────── POST /projects ──────────▶ [ProjectAPI]
                                                                          │
                                                         run(phase=1)     │
                                                                          ▼
                                                              [PipelineOrchestrator]
                                                                          │
                                                                          ├──▶ [VideoIngestor]
                                                                          │         │ MP4/MOV
                                                                          │         ├──▶ FFmpeg (audio)
                                                                          │         └──▶ Whisper GPU
                                                                          │              │
                                                                          │         [StorageAdapter]
                                                                          │              │ save transcription
                                                                          │    checkpoint(phase=1, done)
                                                                          │
[WebUI] ◀──── polling GET /projects/{id} ◀──── [ProjectAPI] ◀────────────┤
    │ muestra transcripción
    │ usuario edita + aprueba
    │ PUT /projects/{id}/transcription
    ▼
[ProjectAPI] ─── run(phase=2) ──▶ [PipelineOrchestrator]
                                          │
                                          ├──▶ [NarrativePlanner]
                                          │         └──▶ Claude API (externo)
                                          │              │ NarrativePlan JSON
                                          │         [StorageAdapter] save plan
                                          │    checkpoint(phase=2, done)
                                          │
[WebUI] ◀─ plan generado ──[ProjectAPI] ◀┤
    │ usuario edita plan + aprueba
    │ POST /projects/{id}/phase/2/approve
    ▼
[ProjectAPI] ─── run(phase=3) ──▶ [PipelineOrchestrator]
                                          │
                                          └──▶ [MaterialGenerator]
                                                   │ Modal.map() - paralelo
                                                   ├── Worker: LatexRenderer
                                                   ├── Worker: DiagramRenderer
                                                   └── Worker: AnimationRenderer
                                                        │ MP4 con alpha × N
                                                   [StorageAdapter] save materials
                                              checkpoint(phase=3, done)
                                                          │
                                    ──run(phase=4)──▶ [VideoComposer]
                                                   │
                                                   ├──▶ [BrandManager].load("phymac")
                                                   │         └──▶ [StorageAdapter] get assets
                                                   │    BrandConfig
                                                   │
                                                   └──▶ FFmpeg pipeline:
                                                        apply_cuts → overlay → transitions → branding
                                                        [StorageAdapter] save composed video
                                              checkpoint(phase=4, done)
                                                          │
                                    ──run(phase=5)──▶ [AudioProcessor]
                                                   DeepFilter + normalize + mix
                                                   [StorageAdapter] save audio-processed
                                              checkpoint(phase=5, done)
                                                          │
                                    ──run(phase=6)──▶ [VideoRenderer]
                                                   FFmpeg render 1080p
                                                   [StorageAdapter] upload final
                                              checkpoint(phase=6, done) · PROJECT DONE
                                                          │
[WebUI] ◀── download URL ──[ProjectAPI] ◀────────────────┘
    │ usuario descarga video final
```

---

## Comunicación entre Componentes

| Tipo | Protocolo | Entre |
|------|-----------|-------|
| Frontend ↔ Backend | HTTP REST + JSON | WebUI ↔ ProjectAPI |
| Orquestador → Workers | Python function call (Modal remote call) | PipelineOrchestrator → Workers |
| Workers → Storage | S3-compatible SDK (boto3 o r2) | Todos los workers ↔ StorageAdapter |
| Worker → External AI | HTTPS REST | NarrativePlanner → Claude API |
| Estado entre fases | JSON en storage (checkpoint) | PipelineOrchestrator ↔ StorageAdapter |

---

## Dependencias Externas

| Servicio externo | Usado por | Criticidad | Fallback |
|-----------------|-----------|-----------|---------|
| Anthropic Claude API | NarrativePlanner | Alta (Fase 2 bloqueante) | Sin fallback — Fase 2 manual si falla |
| OpenAI Whisper (self-hosted en Modal) | VideoIngestor | Alta (Fase 1 bloqueante) | whisper.cpp local como fallback |
| Modal.com (compute) | Todos los workers | Crítica | Ejecución local (sin GPU para Whisper) |
| Cloudflare R2 / AWS S3 | StorageAdapter | Crítica | Sin fallback — storage es esencial |
| ElevenLabs | (futuro: efectos de sonido) | Baja | No se usa en MVP |

---

## Acoplamiento y Puntos de Extensión

**Bajo acoplamiento** (bien):
- `StorageAdapter` desacopla el proveedor de storage → cambiar R2 por S3 = 1 archivo
- `BrandManager` desacopla el sistema de marca → nueva marca = nueva carpeta, sin código
- `ProjectAPI` desacopla el frontend del backend → puede cambiarse el frontend sin tocar workers

**Puntos de extensión identificados**:
- `MaterialGenerator` → agregar nuevo tipo de material = nuevo renderer, sin tocar el dispatcher
- `BrandManager` → nueva marca = config.json + assets, sin cambio de código
- `AudioProcessor` → agregar generación de música = nuevo método `generate_music()`, sin romper el pipeline
- `VideoRenderer` → agregar output de Reel/Short = nuevo método `render_short()` con config diferente

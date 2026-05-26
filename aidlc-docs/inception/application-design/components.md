# Components
# PhyMaC Video Auto-Edit Pipeline

---

## Componentes del Sistema

### 1. `VideoIngestor`
**Capa**: Backend · Modal.com Worker  
**Responsabilidad**: Recibir el archivo de video subido por el usuario, extraer el audio, enviarlo a Whisper y devolver la transcripción con timestamps.

Interfaces:
- Input: archivo de video (MP4/MOV), `project_id`, `project_title`
- Output: `TranscriptionResult` (segmentos con timestamps + texto completo)
- Almacena audio extraído y transcripción en storage (R2/S3)

---

### 2. `TranscriptionEditor`
**Capa**: Frontend · Next.js  
**Responsabilidad**: Presentar la transcripción al usuario en formato editable inline. Permitir correcciones antes de proceder al plan narrativo.

Interfaces:
- Input: `TranscriptionResult`
- Output: `ApprovedTranscription` (transcripción revisada y aprobada por el usuario)

---

### 3. `NarrativePlanner`
**Capa**: Backend · Modal.com Worker + Anthropic Claude API  
**Responsabilidad**: Recibir la transcripción aprobada y generar automáticamente el plan narrativo: segmentación en bloques, decisiones de corte, material de apoyo sugerido por bloque, transiciones.

Interfaces:
- Input: `ApprovedTranscription`
- Output: `NarrativePlan` (JSON estructurado con bloques, segmentos, material, transiciones)

---

### 4. `PlanEditor`
**Capa**: Frontend · Next.js  
**Responsabilidad**: Presentar el plan narrativo en una UI editable (tabla con drag & drop de bloques). Permitir al usuario editar, reordenar, eliminar y aprobar el plan.

Interfaces:
- Input: `NarrativePlan`
- Output: `ApprovedNarrativePlan`

---

### 5. `MaterialGenerator`
**Capa**: Backend · Modal.com Workers (paralelos)  
**Responsabilidad**: Generar todos los clips de material de apoyo en paralelo usando Modal.map(). Cada worker produce un tipo de material (ecuación LaTeX, diagrama, animación Remotion).

Sub-componentes:
- `LatexRenderer` — ecuaciones LaTeX → PNG/MP4 con alpha (MathJax + Puppeteer)
- `DiagramRenderer` — diagramas científicos → SVG → MP4 con alpha (Matplotlib)
- `AnimationRenderer` — animaciones de texto → MP4 con alpha (Remotion)

Interfaces:
- Input: `ApprovedNarrativePlan`
- Output: lista de `MaterialAsset` (paths en storage + metadata por item)

---

### 6. `BrandManager`
**Capa**: Backend · Python module (importado por otros componentes)  
**Responsabilidad**: Gestionar el sistema de identidad visual multi-marca. Cargar la configuración de una marca específica y proveer acceso a sus assets (colores, fuentes, logo, intro/outro, cortinillas).

Interfaces:
- Input: `brand_id` (string, ej: `"phymac"`)
- Output: `BrandConfig` (colores hex, fuentes, paths a assets en storage)

Design multi-marca:
- Cada marca vive en `brands/{brand_id}/` en storage
- Config JSON por marca: `brands/{brand_id}/config.json`
- Agregar una nueva marca = nueva carpeta + config.json, sin cambio de código

---

### 7. `VideoComposer`
**Capa**: Backend · Modal.com Worker (CPU intensivo)  
**Responsabilidad**: Ensamblar el video final usando FFmpeg: aplicar cortes al video crudo, insertar materiales de apoyo en los timestamps correctos, agregar cortinillas entre bloques, aplicar branding (logo, lower thirds, intro/outro).

Interfaces:
- Input: `ApprovedNarrativePlan`, lista de `MaterialAsset`, `BrandConfig`, path al video crudo
- Output: path al video compuesto (sin render final)

---

### 8. `AudioProcessor`
**Capa**: Backend · Modal.com Worker (GPU opcional)  
**Responsabilidad**: Limpiar el audio del video (DeepFilter), normalizar volumen de la voz, mezclar con música de fondo provista por el usuario (ducking automático).

Interfaces:
- Input: video compuesto, path a música de fondo (opcional, provista por usuario)
- Output: video con audio procesado

---

### 9. `VideoRenderer`
**Capa**: Backend · Modal.com Worker (CPU 8 cores)  
**Responsabilidad**: Render final del video en 1080p con preset YouTube (libx264 CRF 18, AAC 192kbps). Subir el resultado a storage y notificar al usuario.

Interfaces:
- Input: video con audio procesado, `render_config` (resolución, calidad, formato)
- Output: path al video final en storage, `RenderResult` (metadata del archivo final)

---

### 10. `PipelineOrchestrator`
**Capa**: Backend · Python (Modal.com o local)  
**Responsabilidad**: Coordinar la ejecución secuencial de todas las fases del pipeline. Gestionar el sistema de checkpoints (guardar estado al completar cada fase, permitir reanudar desde cualquier fase). Manejar reintentos y notificaciones de error.

Interfaces:
- Input: `project_id`, `start_from_phase` (para reanudar), config del proyecto
- Output: actualización continua del estado del proyecto (`ProjectState`)

Estado por proyecto:
```json
{
  "project_id": "...",
  "title": "...",
  "phases": {
    "phase_1": {"status": "completed", "output_path": "..."},
    "phase_2": {"status": "completed", "output_path": "..."},
    "phase_3": {"status": "pending"},
    ...
  },
  "current_phase": 3,
  "created_at": "...",
  "updated_at": "..."
}
```

---

### 11. `StorageAdapter`
**Capa**: Backend · Python module  
**Responsabilidad**: Abstracción sobre el proveedor de storage (Cloudflare R2 o AWS S3). Todos los componentes usan esta interfaz — cambiar de proveedor = cambiar solo este módulo.

Interfaces:
- `upload(local_path, remote_key) → remote_url`
- `download(remote_key, local_path)`
- `get_url(remote_key) → presigned_url`
- `exists(remote_key) → bool`
- `delete(remote_key)`

---

### 12. `ProjectAPI`
**Capa**: Backend · API REST (FastAPI o Flask en Modal)  
**Responsabilidad**: Exponer endpoints HTTP para que el frontend pueda crear proyectos, consultar estado, aprobar fases y descargar outputs. Intermediario entre la UI y el PipelineOrchestrator.

Endpoints principales:
- `POST /projects` — crear proyecto
- `GET /projects/{id}` — estado actual del proyecto
- `POST /projects/{id}/approve/{phase}` — aprobar una fase
- `GET /projects/{id}/download` — URL de descarga del video final

---

### 13. `ValidationAgent`
**Capa**: Backend · Python module (transversal — llamado por PipelineOrchestrator después de cada fase)  
**Responsabilidad**: Validar el output de cada fase antes de guardar el checkpoint y avanzar. Combina métricas técnicas (FFprobe, pydub, Pydantic) con Claude Vision para detección de errores visuales.

Comportamiento:
- **2 reintentos automáticos** si la validación falla
- Si falla el tercer intento → **pausa el proyecto y notifica al usuario**
- Genera un `ValidationResult` con score de confianza, lista de checks, fallas críticas y advertencias

Validadores por fase:
- Fase 1: Whisper confidence scores, cobertura de transcripción, duración (FFprobe)
- Fase 2: JSON schema (Pydantic), coherencia narrativa (Claude texto)
- Fase 3: Integridad de MP4 con alpha (FFprobe), contenido visual correcto (Claude Vision)
- Fase 4: Composición visual — 3 frames analizados (Claude Vision + FFprobe)
- Fase 5: Volumen, clipping, reducción de ruido (pydub + FFprobe)
- Fase 6: Codec, resolución, reproducibilidad (FFprobe completo)

Costo de validación: ~$0.20 por video (principalmente Claude Vision en Fases 3 y 4).

---

### 14. `WebUI`
**Capa**: Frontend · Next.js  
**Responsabilidad**: Interfaz web completa para el usuario. Contiene: upload de video, visualización de transcripción, editor de plan, preview de video, timeline por bloques, panel de descarga. (Disponible desde Día 2 — Día 1 puede usarse CLI).

Sub-componentes de UI:
- `UploadScreen` — drag & drop + barra de progreso
- `TranscriptionView` — editor inline
- `PlanEditorView` — tabla editable + drag & drop
- `PreviewView` — player de video + timeline
- `DownloadView` — estado final + link de descarga

# Requirements Document
# PhyMaC Video Auto-Edit Pipeline

**Versión**: 1.0  
**Fecha**: 2026-05-21  
**Tipo de request**: New Project (Greenfield)  
**Scope**: System-wide — pipeline de 6 fases con compute cloud, UI web y storage  
**Complejidad**: Alta — múltiples servicios distribuidos, procesamiento GPU, orquestación de workers

---

## Intent Analysis

**Request original**: Construir un sistema que automatice la postproducción de videos educativos de PhyMaC, reduciendo el tiempo de edición de 3 días a 3–4 horas por video.

**Request type**: New Project  
**Scope**: Multi-component system (compute workers + orchestrator + UI + storage + brand system)  
**Complexity**: High — distributed pipeline con fases interdependientes, GPU processing, multi-tenant brand support

---

## Estrategia de construcción

**Enfoque iterativo por fases funcionales**: Cada fase del pipeline se construye de manera que sea completamente ejecutable y verificable de forma independiente antes de construir la siguiente. No se avanza a la siguiente fase hasta que la anterior funcione end-to-end.

```
Día 1 → Fase 1 funcional (upload + transcripción completa)
Día 2 → Fase 2 funcional (plan narrativo Claude API)
        + UI completa (editor, timeline, preview)
Día 3 → Fase 3 funcional (generación paralela de materiales)
Día 4 → Fases 4 + 5 funcionales (composición + audio)
Día 5 → Fase 6 funcional (render + entrega) + integración completa
```

---

## Requisitos Funcionales

### RF-01: Ingesta y Transcripción (Fase 1)
- El sistema acepta upload de archivos MP4 y MOV
- Soporta videos de 20 minutos a 1 hora de duración
- Extrae el audio del video y lo envía a Whisper large-v3
- Devuelve transcripción con timestamps por segmento en < 10 minutos
- La transcripción es editable en el browser antes de proceder
- El proyecto se identifica por un **título manual** ingresado por el usuario al crear
- **Criterio de done**: Subís un video MP4/MOV, escribís un título, y en < 10 min ves la transcripción editada en el browser

### RF-02: Plan Narrativo y Cortes (Fase 2)
- Claude API analiza la transcripción y genera automáticamente:
  - Segmentación narrativa (intro, bloques de contenido, cierre)
  - Lista de segmentos a conservar/cortar con justificación
  - Material de apoyo sugerido por bloque (tipo + contenido)
  - Transiciones entre bloques
- El plan se presenta en UI editable (tabla + drag & drop de bloques)
- El usuario aprueba el plan antes de proceder a Fase 3
- **Criterio de done**: Plan narrativo completo generado y aprobable en < 5 min de procesamiento

### RF-03: Generación de Material de Apoyo (Fase 3)
- Generación en paralelo de todos los materiales del plan aprobado:
  - Ecuaciones LaTeX → PNG/MP4 con canal alpha
  - Diagramas científicos → SVG → MP4 con canal alpha
  - Animaciones de texto → Remotion → MP4 con canal alpha
- Todos los outputs en MP4 con canal alpha para composición
- Los materiales se almacenan en R2/S3 con path por proyecto
- **Criterio de done**: 10 materiales de apoyo generados en paralelo en < 5 min

### RF-04: Composición y Branding (Fase 4)
- FFmpeg ensambla: video cortado + materiales de apoyo + assets de identidad PhyMaC
- Assets de identidad reutilizables: intro/outro MP4, cortinillas, logo PNG, lower thirds SVG
- El sistema de branding es **multi-marca**: cada marca tiene su propio conjunto de assets
- En el MVP: marca PhyMaC. Arquitectura preparada para agregar más marcas sin refactor
- **Criterio de done**: Video compuesto con branding completo PhyMaC, listo para preview

### RF-05: Procesamiento de Audio (Fase 5)
- Limpieza de ruido de fondo (DeepFilter o similar)
- Normalización de volumen de la voz
- **La música de fondo la provee el usuario** — el sistema NO genera música automáticamente
- Mezcla final: voz limpia + música provista por usuario (ducking automático)
- **Criterio de done**: Audio del video final limpio, normalizado y mezclado

### RF-06: Preview, Revisión y Render Final (Fase 6)
- Preview del video ensamblado directamente en el browser
- Timeline visual por bloques con timestamps
- Ajustes rápidos antes del render final (regenerar bloque, cambiar asset)
- Render final en Modal.com (1080p, preset YouTube, libx264 CRF 18)
- Output entregado a R2/S3, descargable desde la UI
- Output MVP: **un solo video MP4 final** (extensión a múltiples cortes en iteraciones futuras)
- **Criterio de done**: Video final 1080p descargable desde la UI

### RF-07: Sistema de Checkpoints y Resiliencia
- Cada fase guarda su estado y outputs al completarse
- Si una fase falla, el usuario puede **reanudar desde esa fase** sin perder el trabajo anterior
- Estado del proyecto persiste entre sesiones
- Las fases completadas no se re-ejecutan a menos que el usuario lo pida explícitamente

### RF-08: UI — Día 2 en adelante
- Día 1: CLI/scripts suficiente para verificar funcionamiento
- Día 2+: UI completa con:
  - Upload con drag & drop + barra de progreso
  - Editor de transcripción inline
  - Editor del plan narrativo (tabla + drag & drop de bloques)
  - Timeline visual por bloques
  - Preview de video en el browser
  - Panel de ajustes rápidos antes del render

---

## Requisitos No Funcionales

### RNF-01: Performance
- Transcripción de 1h de audio: < 10 minutos (Whisper large-v3 en GPU Modal)
- Generación de plan narrativo: < 2 minutos (Claude API)
- Generación de 10 materiales de apoyo en paralelo: < 5 minutos
- Composición final: < 20 minutos (Modal CPU 4-8 cores)
- Render 1080p de 1h de video: < 30 minutos

### RNF-02: Costo
- Target: **$3–5 USD por video** de 20–60 minutos
- Breakdown máximo permitido:
  - Whisper (OpenAI): < $0.15
  - Claude API: < $0.80
  - Modal compute: < $2.50
  - Storage R2/S3: < $0.15
  - ElevenLabs (efectos opcionales): < $0.50

### RNF-03: Escalabilidad de Marca (Multi-tenant)
- El sistema de assets de identidad visual es parametrizable por marca
- Cada marca tiene: colores (hex), fuentes, logo PNG, intro/outro MP4, cortinillas MP4, config JSON
- Agregar una nueva marca = agregar una carpeta de assets + un archivo de config JSON
- No se requiere cambio de código para onboardear nuevas marcas

### RNF-04: Formatos de Entrada
- MP4 (H.264/H.265)
- MOV (Apple QuickTime)
- Duración soportada: 20 minutos a 1 hora
- Resolución de entrada: cualquier resolución (el sistema escala al output target)
- Output: 1080p, 30fps, libx264, CRF 18, audio AAC 192kbps

### RNF-05: Resiliencia
- Checkpoints automáticos al completar cada fase
- Retry automático de operaciones atómicas (máx 3 intentos)
- Si falla tras retries: pausa en esa fase, notifica al usuario, permite reanudar
- Los archivos intermedios se preservan hasta que el usuario elimine el proyecto

### RNF-06: Stack Técnico Confirmado
- **Compute**: Modal.com (GPU para transcripción, CPU para composición/render)
- **Transcripción**: OpenAI Whisper large-v3 (self-hosted en Modal)
- **AI narrativa**: Anthropic Claude API (claude-sonnet o claude-haiku según latencia)
- **Video processing**: FFmpeg
- **Animaciones**: Remotion (React → MP4)
- **Audio cleanup**: DeepFilter (Python, Modal)
- **Frontend**: Next.js (deploy flexible: Vercel, Railway, o self-hosted)
- **Storage**: Cloudflare R2 o AWS S3 (abstraído detrás de interfaz común)
- **Efectos de sonido** (opcional): ElevenLabs API ← única API key disponible al inicio

### RNF-07: API Keys — Estado actual
| Servicio | Estado |
|----------|--------|
| ElevenLabs | ✅ Disponible |
| OpenAI (Whisper) | ⏳ Pendiente de configurar |
| Anthropic (Claude) | ⏳ Pendiente de configurar |
| Modal.com | ⏳ Pendiente de configurar |
| Cloudflare R2 / AWS S3 | ⏳ Pendiente de configurar |

**Impacto**: El Día 1 puede comenzar con Whisper ejecutado localmente (sin Modal) mientras se configuran las cuentas. Fase 2 requiere Anthropic API key.

---

## Video de Testing

- Video real de PhyMaC disponible, duración > 30 minutos
- Se usará para validación end-to-end de cada fase
- Criterio de éxito final: ese video procesado en < 4 horas con calidad publicable

---

## Assets de Identidad PhyMaC — Estado

El usuario tiene **algunos assets disponibles**. Antes del Día 4 (Fase 4 - Composición), se necesitan:

| Asset | Estado |
|-------|--------|
| Logo PNG (con alpha) | Por confirmar |
| Intro video MP4 | Por confirmar |
| Outro video MP4 | Por confirmar |
| Cortinillas MP4 (con alpha) | Por confirmar |
| Paleta de colores (hex) | Por confirmar |
| Fuentes tipográficas | Por confirmar |

> **Acción requerida antes de Día 4**: Inventariar qué assets existen y cuáles hay que crear.

---

## Dependencias entre Fases

```
Fase 1 (Transcripción)
    └─→ Fase 2 (Plan Narrativo) — depende de: transcripción aprobada
            └─→ Fase 3 (Generación Materiales) — depende de: plan aprobado
                    └─→ Fase 4 (Composición) — depende de: materiales + assets PhyMaC
                            └─→ Fase 5 (Audio) — depende de: video compuesto
                                    └─→ Fase 6 (Render) — depende de: audio procesado
```

Cada fase es un checkpoint independiente. Se puede reanudar desde cualquier fase.

---

## Lo que queda explícitamente FUERA del scope inicial

1. Generación automática de música de fondo (el usuario la provee)
2. Múltiples formatos de output simultáneos (reel, short) — iteración futura
3. Colaboración multi-usuario — sistema single-user para Johannes
4. Integración directa con YouTube/Instagram para publicar — iteración futura
5. Generación de thumbnails automáticos — iteración futura

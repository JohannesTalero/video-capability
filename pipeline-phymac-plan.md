# Pipeline de Postproducción PhyMaC — Plan de Construcción

> Objetivo: Reducir de 3 días a ~4-6 horas por video.
> Stack: Modal.com + Whisper + Claude API + Remotion + FFmpeg + Next.js
> Modelo de costo: Pay-per-use. Estimado $5–20 USD por video.

---

## Visión General del Pipeline

```
Video Crudo
    │
    ▼
[FASE 1] Ingesta & Transcripción          ← 80% automático
    │
    ▼
[FASE 2] Plan Narrativo & Cortes          ← 60% automático, 40% revisión manual
    │
    ▼
[FASE 3] Generación de Material de Apoyo  ← 90% automático (paralelo)
    │
    ▼
[FASE 4] Composición & Identidad Visual   ← 95% automático
    │
    ▼
[FASE 5] Audio & Identidad Sonora         ← 70% automático
    │
    ▼
[FASE 6] Render & Entrega                 ← 100% automático
    │
    ▼
Video Final
```

---

## FASE 1 — Ingesta & Transcripción

**Tiempo actual:** ~1-2 horas manuales
**Tiempo objetivo:** ~15 minutos (espera de procesamiento)
**Automatización:** 90%

### Qué hace esta fase
El usuario sube el video crudo desde la app web. El sistema extrae el audio, lo manda a Whisper, y devuelve una transcripción con timestamps por segmento.

### Construcción (Día 1 del sprint)

**Frontend — Next.js (Vercel)**
- Upload component con drag & drop
- Barra de progreso en tiempo real (polling al backend)
- Vista previa de la transcripción con editor inline para correcciones manuales

**Backend — Modal.com**
```python
# Job de transcripción
@app.function(gpu="any", timeout=600)
def transcribir_video(video_path: str):
    import whisper
    model = whisper.load_model("large-v3")
    result = model.transcribe(video_path, language="es")
    return {
        "segments": result["segments"],  # [{start, end, text}, ...]
        "full_text": result["text"]
    }
```

**Salida de la fase:**
```json
{
  "segments": [
    {"id": 1, "start": 0.0, "end": 45.2, "text": "Hoy vamos a ver..."},
    {"id": 2, "start": 45.2, "end": 120.8, "text": "El concepto de..."}
  ],
  "duracion_total": 3240
}
```

### Punto de impacto en tiempo
Antes: transcribir manualmente o esperar servicio lento. Ahora: Whisper large-v3 procesa 1 hora de audio en ~4-6 minutos en Modal GPU. **Ahorro estimado: 45-90 minutos.**

### Lo que sigue siendo manual
Revisar la transcripción en el editor inline (~5-10 min). Vale la pena porque el plan narrativo depende de su calidad.

---

## FASE 2 — Plan Narrativo & Cortes

**Tiempo actual:** ~3-4 horas (el día 2 entero, en gran parte)
**Tiempo objetivo:** ~30-45 minutos (revisión del plan generado)
**Automatización:** 65%

### Qué hace esta fase
Con la transcripción como input, Claude API genera automáticamente:
- Segmentación narrativa del video (intro, bloques de contenido, cierre)
- Plan de cortes: qué segmentos conservar, cuáles cortar, en qué orden
- Para cada segmento: qué material de apoyo necesita (ecuación, diagrama, captura, animación)
- Sugerencias de cortinillas entre bloques

### Construcción (Día 1-2 del sprint)

**Prompt al LLM:**
```
Eres un editor de video educativo especializado en física y matemáticas.
Tienes la transcripción de un video de PhyMaC con timestamps.

Tu tarea:
1. Identifica los bloques narrativos naturales (intro, concepto 1, concepto 2..., cierre)
2. Para cada bloque: indica qué segmentos de la transcripción incluir (por ID)
3. Para cada bloque: propone qué material de apoyo visual generaría más claridad
   (tipo: ecuacion_latex | diagrama | captura_pantalla | animacion_texto)
4. Propone transiciones entre bloques

Devuelve JSON estructurado.
```

**Salida de la fase:**
```json
{
  "bloques": [
    {
      "id": "bloque_1",
      "nombre": "Introducción al concepto",
      "segmentos": [1, 2, 3],
      "duracion_estimada": "00:02:15",
      "material_apoyo": [
        {"tipo": "ecuacion_latex", "contenido": "F = ma", "timestamp_relativo": 30},
        {"tipo": "diagrama", "descripcion": "diagrama de fuerzas sobre bloque", "timestamp_relativo": 90}
      ],
      "transicion_siguiente": "cortinilla_concepto"
    }
  ]
}
```

**UI — Editor del Plan:**
- Vista de tabla: cada bloque con sus segmentos, duración, y material de apoyo propuesto
- Drag & drop para reordenar bloques
- Editar/eliminar material de apoyo sugerido
- Botón "Aprobar y generar" → dispara Fase 3

### Punto de impacto en tiempo
Antes: Ver el video completo, tomar notas, decidir estructura, planificar qué mostrar — todo manual. Ahora: el LLM hace el 65% de ese trabajo; tú revisás y ajustás. **Ahorro estimado: 2-3 horas.**

### Lo que sigue siendo manual
La revisión del plan (~20-30 min). Es inevitable — sos vos el que conoce la intención pedagógica. Pero es revisar en lugar de crear desde cero.

---

## FASE 3 — Generación de Material de Apoyo (paralela)

**Tiempo actual:** El día 3 entero (~6-8 horas). El nodo más doloroso.
**Tiempo objetivo:** ~20-40 minutos de render en paralelo. Tú no hacés nada.
**Automatización:** 95%

### Qué hace esta fase
Toma el plan aprobado de Fase 2 y genera en paralelo todos los clips de material de apoyo. Cada bloque corre en su propio worker en Modal.

### Construcción (Día 2 del sprint)

**Arquitectura paralela en Modal:**
```python
@app.function(timeout=300)
def generar_material_bloque(bloque: dict) -> list[str]:
    resultados = []
    for item in bloque["material_apoyo"]:
        if item["tipo"] == "ecuacion_latex":
            path = renderizar_ecuacion_latex(item["contenido"])
        elif item["tipo"] == "diagrama":
            path = generar_diagrama(item["descripcion"])
        elif item["tipo"] == "animacion_texto":
            path = renderizar_remotion(item)
        resultados.append(path)
    return resultados

# Lanzar todos los bloques en paralelo
@app.function()
def generar_todo(plan: dict):
    # .map() de Modal ejecuta en paralelo automáticamente
    resultados = list(
        generar_material_bloque.map(plan["bloques"])
    )
    return resultados
```

**Generadores por tipo de material:**

| Tipo | Herramienta | Formato salida | Tiempo estimado |
|------|-------------|----------------|-----------------|
| Ecuación LaTeX | MathJax → Puppeteer → PNG/MP4 | MP4 con alpha | ~10s por ecuación |
| Diagrama de física | Matplotlib/D3 → SVG → MP4 | MP4 con alpha | ~15s por diagrama |
| Animación de texto | Remotion (React) | MP4 con alpha | ~30s por animación |
| Captura de pantalla | Descripción → Playwright | PNG | ~5s |

**Clave: todos los outputs son MP4 con canal alpha** para poder componerlos sobre el video en Fase 4 sin fondo blanco.

### Punto de impacto en tiempo
Antes: crear cada elemento manualmente en After Effects, Canva, o similar — uno por uno. Ahora: 10 elementos en 10 workers, corriendo al mismo tiempo. Si cada uno tarda 30s, todos están listos en 30s. **Ahorro estimado: 4-6 horas.**

### Lo que sigue siendo manual
Nada en esta fase. Si el material generado no te gusta, lo ajustás en Fase 2 (el plan) y regenerás.

---

## FASE 4 — Composición & Identidad Visual

**Tiempo actual:** ~2 horas (parte del día 2-3)
**Tiempo objetivo:** ~15-20 minutos de render automático
**Automatización:** 95%

### Qué hace esta fase
FFmpeg toma: el video cortado + el material de apoyo generado + los assets de identidad de PhyMaC (logo, fuentes, colores, cortinillas) → y ensambla el video final con branding completo.

### Construcción (Día 2-3 del sprint)

**Script de composición FFmpeg:**
```python
@app.function(cpu=4, memory=8192)
def componer_video(segmentos_cortados, materiales, identidad):
    # 1. Aplicar cortes al video crudo
    video_cortado = aplicar_cortes(segmentos_cortados)
    
    # 2. Para cada bloque, overlay del material de apoyo en el timestamp correcto
    video_con_material = overlay_materiales(video_cortado, materiales)
    
    # 3. Insertar cortinillas entre bloques (assets Remotion pre-renderizados)
    video_con_cortinillas = insertar_cortinillas(video_con_material, identidad)
    
    # 4. Aplicar lower third con nombre del tema (template de marca)
    video_branded = aplicar_identidad(video_con_cortinillas, identidad)
    
    return video_branded
```

**Assets de identidad que se suben UNA vez y se reusan siempre:**
- Intro/outro de PhyMaC (MP4)
- Cortinillas entre segmentos (MP4 con alpha)
- Lower thirds template (SVG con variables)
- Paleta de colores y fuentes (JSON de configuración)
- Logo (PNG con alpha)

### Punto de impacto en tiempo
Antes: ensamblar manualmente en editor de video, cuadrar timestamps, aplicar branding en cada elemento. Ahora: proceso completamente automático. **Ahorro estimado: 1.5-2 horas.**

### Lo que sigue siendo manual
Si querés un ajuste muy específico de composición, lo hacés en la UI de revisión (Fase 5 preview) antes del render final.

---

## FASE 5 — Audio & Identidad Sonora

**Tiempo actual:** ~2-3 horas
**Tiempo objetivo:** ~20 minutos (revisión)
**Automatización:** 70%

### Qué hace esta fase
Procesamiento de audio del video + generación de música de fondo y efectos de sonido complementarios basados en el contenido.

### Construcción (Día 3 del sprint)

**Procesamiento automático de audio:**
```python
@app.function(gpu="any")
def procesar_audio(video_path: str, plan_sonoro: dict):
    # 1. Limpieza de audio: eliminar ruido de fondo
    audio_limpio = limpiar_ruido(video_path)  # DeepFilter o similar
    
    # 2. Normalización de volumen
    audio_normalizado = normalizar_volumen(audio_limpio)
    
    # 3. Generar música de fondo según mood del bloque
    for bloque in plan_sonoro["bloques"]:
        musica = generar_musica_fondo(
            mood=bloque["mood"],  # "explicativo", "introductorio", "conclusivo"
            duracion=bloque["duracion"]
        )  # ElevenLabs Sound Effects o Suno API
    
    # 4. Mezcla final: voz principal + música de fondo (ducking automático)
    audio_final = mezclar(audio_normalizado, musicas, ratio_voz=0.85)
    
    return audio_final
```

**El plan sonoro lo genera Claude en Fase 2** junto con el plan visual — ya sabe la duración y el mood de cada bloque.

**ElevenLabs para efectos sonoros** (ya tenés el plugin instalado en Cowork): generar transiciones de audio, efectos para cuando aparece una ecuación, etc.

### Punto de impacto en tiempo
Antes: limpiar audio manualmente, buscar música, cuadrar volúmenes. Ahora: automático. **Ahorro estimado: 1.5-2 horas.**

### Lo que sigue siendo manual
Revisión del mix de audio (~15-20 min). El ducking automático es bueno pero no perfecto — hay momentos donde querés ajustar manualmente.

---

## FASE 6 — Preview, Revisión & Render Final

**Tiempo actual:** ~1-2 horas (render + revisión + ajustes)
**Tiempo objetivo:** ~20-30 minutos
**Automatización:** 80%

### Qué hace esta fase
Preview del video completo ensamblado. Interfaz de revisión para ajustes finales. Render en alta calidad en Modal y entrega al storage.

### UI de Preview & Revisión

```
┌─────────────────────────────────────────┐
│  Preview del video                      │
│  [████████████░░░░░░░░░] 00:04:32      │
├─────────────────────────────────────────┤
│  Timeline por bloques:                  │
│  [Intro][Bloque 1][Trans][Bloque 2]... │
├─────────────────────────────────────────┤
│  Ajustes rápidos:                       │
│  □ Regenerar material bloque 2          │
│  □ Cambiar cortinilla en 00:02:15       │
│  □ Ajustar volumen música               │
├─────────────────────────────────────────┤
│         [Aprobar y Renderizar]          │
└─────────────────────────────────────────┘
```

### Render final en Modal

```python
@app.function(cpu=8, memory=16384, timeout=1800)
def render_final(proyecto_id: str, config: dict):
    # Render en 1080p o 4K según configuración
    # FFmpeg con preset de calidad para YouTube
    output_path = f"s3://phymac-videos/{proyecto_id}/final.mp4"
    
    ffmpeg_cmd = [
        "ffmpeg", "-i", video_ensamblado,
        "-c:v", "libx264", "-preset", "slow",
        "-crf", "18",  # Alta calidad
        "-c:a", "aac", "-b:a", "192k",
        output_path
    ]
    # ...
    return output_path
```

### Punto de impacto en tiempo
Antes: render local (bloquea tu máquina, tarda más), revisión, ajustes, re-render. Ahora: render en cloud mientras hacés otra cosa, revisás el resultado directo en la app. **Ahorro estimado: 1-1.5 horas.**

---

## Plan de Construcción: Los 3 Días

### DÍA 1 — Infraestructura base + Fase 1 completa

**Objetivo del día:** Subir un video, obtener transcripción, ver el resultado en el browser.

| Bloque | Tarea | Tiempo estimado |
|--------|-------|-----------------|
| Mañana | Setup: Modal account, proyecto Next.js, S3/R2 bucket | 1.5h |
| Mañana | Job de transcripción en Modal con Whisper | 1.5h |
| Tarde | UI de upload + barra de progreso + viewer de transcripción | 2h |
| Tarde | Editor inline de transcripción (correcciones manuales) | 1h |
| Tarde | Test end-to-end: subir video real de PhyMaC | 1h |

**Criterio de éxito del día 1:** Subís un video y en ~10 minutos tenés la transcripción con timestamps en el browser, editable.

---

### DÍA 2 — Fase 2 + Fase 3 (el corazón del sistema)

**Objetivo del día:** Dado un plan aprobado, generar todo el material de apoyo en paralelo.

| Bloque | Tarea | Tiempo estimado |
|--------|-------|-----------------|
| Mañana | Integración Claude API → generación del plan narrativo | 2h |
| Mañana | UI del editor del plan (tabla editable, drag & drop básico) | 2h |
| Tarde | Generadores de material: ecuaciones LaTeX → MP4 alpha | 1.5h |
| Tarde | Generadores de material: Remotion para animaciones de texto | 1.5h |
| Tarde | Orquestación paralela en Modal (.map()) | 1h |

**Criterio de éxito del día 2:** Aprobás un plan y en ~5 minutos tenés todos los materiales de apoyo generados y disponibles en S3.

---

### DÍA 3 — Fases 4, 5, 6 + Composición final

**Objetivo del día:** De materiales generados a video final exportado.

| Bloque | Tarea | Tiempo estimado |
|--------|-------|-----------------|
| Mañana | Script FFmpeg de composición: cortes + overlays + cortinillas | 2h |
| Mañana | Sistema de assets de identidad PhyMaC (upload único, reuso siempre) | 1h |
| Tarde | Procesamiento de audio: limpieza + normalización + mezcla | 1.5h |
| Tarde | UI de preview + timeline por bloques + ajustes rápidos | 1.5h |
| Tarde | Render final en Modal + entrega a S3 | 1h |

**Criterio de éxito del día 3:** Procesás el mismo video que tomó 3 días, en menos de 6 horas, con la app completa.

---

## Resumen de Impacto en Tiempo

| Fase | Antes | Después | Ahorro |
|------|-------|---------|--------|
| Transcripción | 45-90 min | 15 min (espera) | ~75 min |
| Plan narrativo & cortes | 3-4 horas | 30-45 min (revisión) | ~3 horas |
| Material de apoyo | 6-8 horas | 40 min (render paralelo) | ~6.5 horas |
| Composición visual | 2 horas | 20 min (render) | ~1.5 horas |
| Audio | 2-3 horas | 20 min (revisión) | ~2 horas |
| Render & revisión final | 1-2 horas | 30 min | ~1.5 horas |
| **TOTAL** | **~3 días** | **~3-4 horas** | **~85% reducción** |

---

## Costo Operativo por Video (estimado)

| Servicio | Uso | Costo USD |
|----------|-----|-----------|
| Whisper API (OpenAI) | 1h de audio | $0.10 |
| Claude API (plan narrativo) | ~5k tokens | $0.50 |
| Modal compute (transcripción) | GPU 6 min | $0.20 |
| Modal compute (generación paralela) | 4 workers × 5 min | $0.80 |
| Modal compute (composición + render) | CPU 8 cores × 20 min | $1.20 |
| ElevenLabs (efectos sonoros) | ~10 efectos | $0.50 |
| R2/S3 storage | ~5GB por video | $0.10 |
| **TOTAL** | | **~$3.40 USD por video** |

Para 12 videos: **~$41 USD total.** Vs 36 días de tu tiempo.

---

## Prerrequisitos antes del Día 1

- [ ] Cuenta en Modal.com (free tier)
- [ ] API key OpenAI (Whisper)
- [ ] API key Anthropic (Claude)
- [ ] Cuenta Cloudflare R2 o AWS S3
- [ ] Node.js + Python instalados localmente
- [ ] Assets de identidad PhyMaC listos (logo, colores, fuentes, intro/outro MP4)

---

## Lo que sigue siendo manual (y por qué está bien)

1. **Revisión de transcripción (5-10 min):** Necesaria. La calidad del plan depende de ella.
2. **Revisión del plan narrativo (20-30 min):** Necesaria. Vos decidís la intención pedagógica.
3. **Revisión del audio mix (15-20 min):** Recomendada. El oído humano detecta lo que el algoritmo no.
4. **Revisión del preview final (10-15 min):** Recomendada. Control de calidad antes de publicar.

**Total de tiempo manual por video: ~60-75 minutos.** El resto lo hace la máquina.

# Validation System Design
# PhyMaC Video Auto-Edit Pipeline

**Decisión**: Componente transversal agregado post-Application Design.  
**Trigger**: Observación crítica del usuario — el pipeline necesita validar su propio output para garantizar calidad sin intervención humana constante.

---

## Comportamiento global

```
Phase ejecuta
     │
     ▼
ValidationAgent.validate(phase, output)
     │
     ├── PASS → checkpoint(phase, done) → siguiente fase
     │
     └── FAIL → retry (intento 2)
                    │
                    ├── PASS → checkpoint(phase, done) → siguiente fase
                    │
                    └── FAIL → retry (intento 3)
                                   │
                                   ├── PASS → checkpoint(phase, done) → siguiente fase
                                   │
                                   └── FAIL → PAUSA
                                              notifica al usuario
                                              espera decisión: [corregir / continuar igual / abortar]
```

**Retries**: máximo 2 reintentos automáticos → si falla el tercer intento, pausa y notifica.  
**Cada reintento**: re-ejecuta la fase completa con los mismos inputs.

---

## Componente: `ValidationAgent`

**Capa**: Backend · Python module (llamado por PipelineOrchestrator después de cada fase)  
**Motor**: combinación de métricas técnicas + Claude Vision API (según la fase)

```python
class ValidationAgent:
    def validate(self, phase: int, output: PhaseOutput, context: ProjectContext) -> ValidationResult:
        """Punto de entrada principal. Delega al validador específico de la fase."""

    def validate_phase_1(self, result: TranscriptionResult) -> ValidationResult:
    def validate_phase_2(self, plan: NarrativePlan, transcription: TranscriptionResult) -> ValidationResult:
    def validate_phase_3(self, materials: list[MaterialAsset]) -> ValidationResult:
    def validate_phase_4(self, video_path: str, plan: ApprovedNarrativePlan) -> ValidationResult:
    def validate_phase_5(self, video_path: str) -> ValidationResult:
    def validate_phase_6(self, render_result: RenderResult) -> ValidationResult:

@dataclass
class ValidationResult:
    passed: bool
    phase: int
    score: float                    # 0.0 → 1.0
    checks: list[CheckResult]       # detalle de cada verificación
    critical_failures: list[str]    # lo que bloqueó el pipeline
    warnings: list[str]             # problemas menores que no bloquean
    recommendation: str             # qué hacer si falló
```

---

## Validaciones por Fase

### Fase 1 — Transcripción

**Herramientas**: FFprobe, análisis de Whisper confidence scores, heurísticas de texto

| Check | Herramienta | Criterio de PASS |
|-------|-------------|-----------------|
| Duración audio == duración transcripción | FFprobe vs timestamps | Diferencia < 5% |
| Cobertura de transcripción | Whisper segments | > 90% del audio tiene texto asignado |
| Confianza promedio de Whisper | Whisper word-level confidence | Media > 0.7 |
| Segmentos con texto vacío o muy corto | Análisis de segments | < 5% de segments son `""` o < 3 chars |
| Idioma detectado | Whisper language detection | `"es"` o `"es-*"` |

**Qué hace si falla**: re-transcribe con temperatura diferente (0.0 → 0.2 en retry) o con un modelo más pequeño para cruzar.

---

### Fase 2 — Plan Narrativo

**Herramientas**: validación de JSON schema + Claude Vision (análisis de coherencia)

| Check | Herramienta | Criterio de PASS |
|-------|-------------|-----------------|
| JSON válido y con schema correcto | Pydantic validator | 100% campos requeridos presentes |
| Todos los segment IDs del plan existen en la transcripción | Lookup en TranscriptionResult | 0 IDs huérfanos |
| Duración total del plan ≈ duración del video | Suma de duraciones de bloques | Diferencia < 10% |
| Al menos 1 bloque generado | Conteo | `len(blocks) >= 1` |
| Material de apoyo tiene tipo válido | Enum check | Solo tipos permitidos |
| Coherencia narrativa (Claude) | Claude API (texto) | Claude confirma que el plan tiene sentido con la transcripción |

**Prompt de coherencia a Claude**:
```
Tengo una transcripción de un video educativo y un plan narrativo generado automáticamente.
¿El plan narrativo divide el contenido de forma coherente?
¿Los bloques identificados tienen sentido temático?
Responde: {"coherent": true/false, "issues": [...], "confidence": 0.0-1.0}
```

---

### Fase 3 — Materiales de Apoyo

**Herramientas**: FFprobe para video, Claude Vision para validación visual

| Check | Herramienta | Criterio de PASS |
|-------|-------------|-----------------|
| Todos los materiales del plan fueron generados | Conteo | `len(generated) == len(planned)` |
| Cada MP4 tiene canal alpha | FFprobe streams | `codec_name: png` o `pix_fmt: yuva420p` |
| Duración > 0 | FFprobe duration | > 0.5 segundos |
| El archivo no está corrupto | FFprobe probe | Exit code 0 |
| Contenido visual correcto (Claude Vision) | Claude API vision | Claude confirma que la ecuación/diagrama es legible y correcto |

**Prompt de validación visual a Claude**:
```
Esta imagen es un clip de material de apoyo generado para un video educativo de física/matemáticas.
Tipo esperado: {spec.tipo}. Contenido esperado: {spec.contenido}.
¿El contenido es legible? ¿Es correcto matemáticamente? ¿Hay errores de render obvios?
Responde: {"readable": bool, "correct": bool, "issues": [...]}
```

**Muestreo**: no valida todos los materiales con visión — toma el frame del medio de cada MP4 y lo analiza. Para 10 materiales → 10 llamadas a Claude Vision (~$0.10 extra).

---

### Fase 4 — Composición

**Herramientas**: FFprobe + Claude Vision sobre frames clave del video compuesto

| Check | Herramienta | Criterio de PASS |
|-------|-------------|-----------------|
| Video compuesto tiene audio + video streams | FFprobe | Ambos streams presentes |
| Duración ≈ suma de bloques del plan | FFprobe vs plan | Diferencia < 5% |
| Resolución correcta | FFprobe | `width >= 1280` |
| El frame del inicio no está en negro (intro aplicado) | FFprobe thumbnails | Frame 0.5s no es negro puro |
| El frame del final no está en negro (outro aplicado) | FFprobe thumbnails | Frame -0.5s no es negro puro |
| Composición visual correcta — muestra de 3 frames (Claude Vision) | Claude API vision | No hay overlays fuera de pantalla, texto legible, branding visible |

**Prompt para frames**:
```
Este es un frame de un video educativo de PhyMaC ya compuesto.
¿El branding es visible? ¿Hay elementos visuales fuera de pantalla?
¿Hay artefactos visuales obvios (corrupción, glitches)?
Responde: {"branding_visible": bool, "layout_ok": bool, "artifacts": [...]}
```

---

### Fase 5 — Audio

**Herramientas**: FFprobe + pyaudioanalysis / pydub para análisis de espectro

| Check | Herramienta | Criterio de PASS |
|-------|-------------|-----------------|
| Stream de audio presente | FFprobe | Audio stream existe |
| Volumen promedio en rango correcto | pydub dBFS | Entre -20 dBFS y -8 dBFS |
| Sin clipping detectado | pydub | Picos < 0 dBFS en > 99% de frames |
| Ruido de fondo reducido | Comparación de RMS antes/después | RMS en segmentos de silencio reducido > 50% |
| Duración audio == duración video | FFprobe | Diferencia < 0.1 segundos |

**Nota**: Esta fase NO usa Claude Vision — métricas técnicas son suficientes y más precisas para audio.

---

### Fase 6 — Render Final

**Herramientas**: FFprobe completo

| Check | Herramienta | Criterio de PASS |
|-------|-------------|-----------------|
| Codec de video: libx264 | FFprobe | `codec_name: h264` |
| Resolución: 1920x1080 | FFprobe | Exacto |
| Frame rate: 30fps | FFprobe | `r_frame_rate: 30/1` |
| Codec de audio: aac | FFprobe | `codec_name: aac` |
| Bitrate de audio ≥ 192k | FFprobe | `bit_rate >= 192000` |
| Archivo reproducible end-to-end | FFprobe -v error | Exit code 0, sin errores |
| Tamaño de archivo razonable | stat | Entre 100MB y 8GB para 20-60 min |
| URL de descarga accesible | HTTP HEAD request | Status 200 |

---

## Integración con PipelineOrchestrator

```python
# En PipelineOrchestrator.run_phase():

def run_phase(self, phase_num: int, max_retries: int = 3) -> bool:
    for attempt in range(1, max_retries + 1):
        output = self.execute_phase(phase_num)
        result = self.validator.validate(phase_num, output, self.context)
        
        if result.passed:
            self.save_checkpoint(phase_num, output, result)
            return True
        
        if attempt < max_retries:
            logger.warning(f"Phase {phase_num} validation failed (attempt {attempt}). Retrying...")
            logger.warning(f"Issues: {result.critical_failures}")
            continue
        
        # Falló 3 veces → pausa
        self.pause_project(phase_num, result)
        self.notify_user(
            f"Phase {phase_num} failed after {max_retries} attempts.\n"
            f"Critical issues: {result.critical_failures}\n"
            f"Recommendation: {result.recommendation}\n"
            f"Run: resume_pipeline.py --project-id {self.project_id} --from-phase {phase_num}"
        )
        return False
```

---

## Costo adicional de validación

| Fase | Motor | Costo estimado por video |
|------|-------|--------------------------|
| Fase 1 | FFprobe + heurísticas | $0.00 |
| Fase 2 | Pydantic + Claude (texto) | ~$0.05 |
| Fase 3 | FFprobe + Claude Vision (N frames) | ~$0.10 |
| Fase 4 | FFprobe + Claude Vision (3 frames) | ~$0.05 |
| Fase 5 | FFprobe + pydub | $0.00 |
| Fase 6 | FFprobe | $0.00 |
| **Total validación** | | **~$0.20 por video** |

Costo total ajustado: $3.40 + $0.20 = **~$3.60 por video** (dentro del target de $3–5).

---

## Nueva Unidad de Trabajo

Este componente se agrega como **Unit 1b** (parte de Unit 1 — Core):

```
Unit 1 — Core Pipeline + Storage Layer + ValidationAgent base
  ├── StorageAdapter
  ├── PipelineOrchestrator (con retry loop integrado)
  ├── ValidationAgent (esqueleto + validadores técnicos básicos)
  └── models.py actualizado con ValidationResult
```

Los validadores específicos de cada fase (incluidos los de Claude Vision) se implementan junto con la fase correspondiente (Unit 2 trae el validador de Fase 1, Unit 3 trae el validador de Fase 2, etc.).

# Diseño: Phase 2 — Plan Narrativo & Cortes

**Fecha**: 2026-05-26
**Estado**: Pendiente de aprobación
**AIDLC Unit**: Unit 3
**Depende de**: Phase 1 (Ingesta & Transcripción) — completada y validada E2E con video `Cudris_sin_reverb.mp4` (cudris-20260526)

---

## 1. Objetivo

Tomar la transcripción JSON producida por Phase 1 y generar, vía LLM (OpenRouter), un **plan narrativo estructurado** que un editor humano revisará antes de disparar Phase 3. El plan describe:

- Cómo segmentar el episodio editado en bloques (cold open + capítulos + cierre).
- Qué segmentos de la transcripción cruda usar en cada bloque y en qué orden de playback.
- Qué material gráfico de apoyo (lower thirds, pull quotes, chapter markers, animaciones de texto, correcciones de transcripción) acompaña cada bloque y cuándo aparece.

**Formato implementado en esta iteración**: `podcast_hablando_con_profes` solamente. La arquitectura `format_id` queda en el código para que futuros formatos (clase, tutorial, anuncio) se enchufen sin refactor.

## 2. Non-goals

- No se hace UI de revisión del plan (eso es Unit 8).
- No se generan los assets gráficos finales — eso es Phase 3.
- No se editan los segmentos de audio/video internamente (no L-cuts, no trim_start_ms). Cortes son IMPLÍCITOS: si un segmento no aparece en ningún bloque, queda fuera.
- No se construyen VO bridges del host entre capítulos (eso requiere regrabación, va en Phase 5).
- No se hace intro/outro PhyMaC pregrabado (eso es branding, Phase 4).

## 3. Referencias

- **Plan editorial manual del Cudris** (32:45 brutos → 24-27 min final): `C:\Users\johan\Documents\PhyMaC\Videos\Cudris\plan\Propuesta.md` — 717 líneas, hand-edited. Estructura: cold open (gancho movido del minuto 30 al inicio), presentación del invitado, 6 capítulos narrativos, cierre. Sirve como referencia de calidad para validar el output del LLM.
- **Design / Brand kit del Cudris**: `C:\Users\johan\Documents\PhyMaC\Videos\Cudris\plan\design.md` — paleta, tipografía, reglas de animación por capítulo.
- **Plan general del pipeline**: `pipeline-phymac-plan.md` (sección "FASE 2").
- **Memoria de proyecto**: `[[project-podcast-use-case]]` — confirma que el primer caso real es podcast, no clase.

## 4. Arquitectura

### 4.1 Nuevos archivos

```
pipeline/
  formats.py                              ← NUEVO (módulo central de formatos)
  phases/
    phase2_narrative.py                   ← NUEVO (Phase 2 runner)

formats/                                  ← NUEVA carpeta en la raíz del repo
  podcast_hablando_con_profes/
    format.json                           ← metadata: id, name, version, description
    narrative_prompt.md                   ← system prompt para LLM_MODEL_PLANNER
    materials_whitelist.json              ← {"allowed": [...]}

scripts/
  run_phase2.py                           ← NUEVO (CLI espejo de run_phase1.py)

tests/
  test_formats.py                         ← NUEVO (unit tests del loader)
  test_validator_phase2.py                ← NUEVO (unit tests de _validate_phase_2)
```

### 4.2 Archivos modificados

- `pipeline/models.py`: añadir `format_id` a `Project`; añadir `metadata: dict` opcional a `MaterialSpec`.
- `pipeline/validator.py`: `_validate_phase_2` carga whitelist desde `FormatConfig` y aplica nuevas reglas.
- `pipeline/config.py`: añadir `DEFAULT_FORMAT_ID = "podcast_hablando_con_profes"`.
- `pipeline/orchestrator.py`: `create_project()` acepta `format_id` parámetro.

## 5. Schemas

### 5.1 Cambio mínimo a `Project`

```python
@dataclass
class Project:
    project_id: str
    title: str
    brand_id: str
    format_id: str             # NUEVO — e.g. "podcast_hablando_con_profes"
    video_original_key: str
    created_at: str
    updated_at: str
    current_phase: int
    status: ProjectStatus
```

Backward compat: proyectos existentes en R2 cargados via `ProjectState.from_json()` que no tengan `format_id` reciben `DEFAULT_FORMAT_ID` automáticamente.

### 5.2 Cambio mínimo a `MaterialSpec`

```python
@dataclass
class MaterialSpec:
    tipo: str                  # del whitelist del formato
    contenido: str
    timestamp_relativo: int    # segundos desde el inicio del bloque
    metadata: dict[str, Any] = field(default_factory=dict)  # NUEVO
```

`metadata` permite estructurar datos extra sin proliferar tipos. Ejemplo `transcript_fix`:

```json
{
  "tipo": "transcript_fix",
  "contenido": "Usme",
  "timestamp_relativo": 47,
  "metadata": {"segment_id": 5, "original": "Uzme", "corrected": "Usme"}
}
```

### 5.3 Nuevo módulo `pipeline/formats.py`

```python
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import json

FORMATS_ROOT = Path(__file__).parent.parent / "formats"

@dataclass(frozen=True)
class FormatConfig:
    format_id: str
    name: str
    version: str
    description: str
    narrative_prompt: str
    materials_whitelist: list[str]

class FormatNotFoundError(Exception):
    pass

@lru_cache(maxsize=16)
def load_format(format_id: str) -> FormatConfig:
    """Load formats/<id>/ from disk. Cached in memory."""
    base = FORMATS_ROOT / format_id
    if not base.exists():
        raise FormatNotFoundError(f"Unknown format_id: {format_id}")
    meta = json.loads((base / "format.json").read_text())
    prompt = (base / "narrative_prompt.md").read_text()
    whitelist = json.loads((base / "materials_whitelist.json").read_text())["allowed"]
    return FormatConfig(
        format_id=format_id,
        name=meta["name"],
        version=meta["version"],
        description=meta["description"],
        narrative_prompt=prompt,
        materials_whitelist=whitelist,
    )
```

## 6. Formato `podcast_hablando_con_profes`

### 6.1 `formats/podcast_hablando_con_profes/format.json`

```json
{
  "format_id": "podcast_hablando_con_profes",
  "name": "Podcast — Hablando con Profes",
  "version": "1.0",
  "description": "Entrevistas a profesores sobre vocación, métodos y visión de la educación. Marca PhyMaC, formato podcast video. Duración objetivo: 25-30 min sobre crudos de 30-60 min."
}
```

### 6.2 `formats/podcast_hablando_con_profes/materials_whitelist.json`

```json
{
  "allowed": [
    "lower_third",
    "pull_quote",
    "chapter_marker",
    "animacion_texto",
    "transcript_fix"
  ]
}
```

### 6.3 `formats/podcast_hablando_con_profes/narrative_prompt.md`

```markdown
# Editor narrativo — Podcast "Hablando con Profes"

## Rol

Eres el editor narrativo de "Hablando con Profes", un podcast de PhyMaC
donde profesores son entrevistados sobre su vocación, métodos, anécdotas
y visión de la educación. Tu trabajo es tomar la transcripción cruda de
la entrevista y producir un plan editorial estructurado que un editor
humano revisará antes de cortar el video.

## Contexto del formato

- Duración objetivo del episodio final: 25-30 minutos.
- Audio crudo de entrada: 30-60 minutos.
- El invitado lleva el peso conversacional; el host pregunta y guía.
- Audiencia: docentes y público interesado en educación.
- Tono: cálido, reflexivo, sin azúcar artificial.
- La conversación es el contenido principal — sé conservador con los cortes,
  solo eliminá muletillas largas, silencios, repeticiones obvias o tangentes
  claramente off-topic.

## Output

Devuelve un JSON con la estructura indicada al final. NO incluyas comentarios,
explicaciones, ni texto fuera del JSON.

## Estructura del episodio

1. **Cold open** (primer bloque, name: "Cold open")
   - Contiene EXACTAMENTE 3 segmentos. Cada segmento es una frase contraintuitiva
     del invitado, escogida porque desafía una suposición común sobre enseñar.
   - "Contraintuitiva" = afirmación que un docente promedio probablemente
     cuestionaría al primer escuchar (ejemplos: "el ajedrez no era para enseñar
     matemáticas", "si la ley lo permitiera, quitaría cálculo y física",
     "no existe la ecuación de estado del homo sapiens").
   - Cada frase puede escucharse aislada y tener sentido en menos de 15 segundos.
   - Pueden venir de cualquier parte de la grabación (probablemente del último
     tercio, donde el invitado ya entró en confianza y sintetiza).
   - Sin transición ni context-setting — son 3 golpes secos consecutivos.
   - Cualquiera de los 3 puede luego reaparecer en su capítulo natural; el cold
     open es una "promesa" del episodio, no un spoiler.
   - support_material para este bloque: opcional `animacion_texto` (palabra
     clave por frase). NO incluyas `chapter_marker` aquí.

2. **Presentación del invitado** (segundo bloque, name: "Presentación")
   - 1-2 segmentos donde el invitado dice su nombre, cargo, institución.
   - support_material: 1 `lower_third` con "Nombre — Cargo, Institución".

3. **Capítulos temáticos** (3-7 bloques, names narrativos)
   - Cada capítulo es una unidad temática coherente.
   - Nombres deben ser narrativos, no descriptivos: "El error de creer que la
     universidad te preparó", no "Reflexión sobre formación universitaria".
   - support_material[0] de cada capítulo: 1 `chapter_marker` con título breve
     (máx 6 palabras), `timestamp_relativo: 0`.
   - support_material adicional: `pull_quote` para frases citables fuertes
     (<25 palabras), `animacion_texto` para palabras clave (máx 1 por capítulo).

4. **Cierre** (último bloque, name: "Cierre")
   - 1-3 segmentos con la reflexión final del invitado.
   - support_material: opcional `pull_quote` con la frase de cierre.

## Reglas duras

1. SOLO referenciá `segment_id` que aparezcan en la transcripción de entrada.
2. Un mismo `segment_id` NO puede aparecer en dos bloques distintos.
3. El orden de `segments[]` dentro de un bloque ES el orden de playback.
   Podés agrupar segmentos no contiguos por tema (e.g. `[12, 13, 45, 46]`)
   si la coherencia narrativa lo justifica.
4. El orden de `blocks[]` ES el orden del episodio final. El cold open va primero.
5. Cortes son IMPLÍCITOS: cualquier segmento no incluido en ningún bloque queda
   fuera del video final.
6. Material de apoyo: usá SOLO estos tipos:
   - `lower_third` — banner inferior con nombre/cargo del invitado.
     Contenido: "Nombre — Cargo, Institución". Máx 2 por episodio.
   - `pull_quote` — cita textual destacada (<25 palabras).
     Contenido: la cita exacta. Sin límite duro, pero más de 10 dispara warning.
   - `chapter_marker` — título de capítulo entre bloques.
     Contenido: título breve (máx 6 palabras). `timestamp_relativo: 0`.
   - `animacion_texto` — palabra clave animada en pantalla.
     Contenido: la palabra/frase corta. Máx 1 por bloque.
   - `transcript_fix` — corrección de un artefacto de Whisper.
     Contenido: el texto corregido. metadata: `{"segment_id": int,
     "original": "texto whisper", "corrected": "texto correcto"}`.
     Usar cuando notes nombres propios mal transcritos, palabras inexistentes
     en español, o palabras que claramente son artefactos (e.g. "Uzme" → "Usme",
     "Jerez" → "ajedrez", "zapiens" → "sapiens").

## Output schema

{
  "blocks": [
    {
      "id": "block_N",
      "name": "string en español",
      "segments": [int, ...],
      "estimated_duration": "MM:SS",
      "support_material": [
        {
          "tipo": "lower_third" | "pull_quote" | "chapter_marker" |
                  "animacion_texto" | "transcript_fix",
          "contenido": "string",
          "timestamp_relativo": int,
          "metadata": {}
        }
      ],
      "transition_next": "corte_directo" | "fade" | "cortinilla_capitulo"
    }
  ]
}

## Input que recibirás

Una tabla en texto plano con la transcripción:

[id]  [start→end]  texto del segmento

Ejemplo:
[0]  [0.0→17.76]  Mi nombre es Edson Cúdris, soy docente de la Secretaría...
[1]  [17.76→32.10]  Empecé en el aula hace 23 años en la localidad de Uzme...
```

## 7. Phase 2 runner (`pipeline/phases/phase2_narrative.py`)

### 7.1 Algoritmo

```
def run_phase_2(state: ProjectState) -> dict:
    project_id = state.project.project_id
    format_id  = state.project.format_id
    storage    = StorageAdapter()
    plan_key   = StorageKey.narrative_plan(project_id)  # NUEVO en StorageKey

    # 1. Idempotencia
    if storage.exists(plan_key):
        plan = NarrativePlan.from_json(storage.download_json(plan_key))
        return {"plan_key": plan_key, "plan": plan,
                "block_count": len(plan.blocks), ...}

    # 2. Cargar formato + transcripción
    fmt = load_format(format_id)
    transcription_key = StorageKey.transcription(project_id)
    transcription = TranscriptionResult.from_json(storage.download_json(transcription_key))

    # 3. Construir mensajes para LLM
    transcript_table = _format_transcript(transcription.segments)
    messages = [
        {"role": "system", "content": fmt.narrative_prompt},
        {"role": "user",   "content": transcript_table},
    ]

    # 4. Llamada LLM
    client = get_llm_client()
    response = client.chat.completions.create(
        model=LLM_MODEL_PLANNER,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.4,
    )
    plan_json = response.choices[0].message.content

    # 5. Parsear y validar estructura
    plan_dict = json.loads(plan_json)
    plan = NarrativePlan(
        project_id=project_id,
        blocks=[Block.from_dict(b) for b in plan_dict["blocks"]],
        storage_key=plan_key,
    )

    # 6. Persistir
    storage.upload_json(plan.to_json(), plan_key)

    return {
        "plan_key": plan_key,
        "plan": plan,
        "block_count": len(plan.blocks),
        "total_segments_used": sum(len(b.segments) for b in plan.blocks),
        "format_id": format_id,
    }
```

Las claves persisted en `PhaseState.outputs` (post-fix de orchestrator): `plan_key`, `block_count`, `total_segments_used`, `format_id` (todas JSON-scalars). `plan` se pasa al ValidationAgent via context pero no se persiste en outputs.

### 7.2 Idempotencia

Mismo patrón que Phase 1 (post-fix): short-circuit al inicio si `plan_key` existe en R2. Para forzar regeneración, borrar `narrative_plan.json` de R2.

### 7.3 Storage key

Nueva en `StorageKey`:

```python
@staticmethod
def narrative_plan(project_id: str) -> str:
    return f"projects/{project_id}/phase2/narrative_plan.json"
```

### 7.4 Registro con orchestrator

Misma técnica que Phase 1:

```python
def register(orchestrator) -> None:
    orchestrator.register_phase(2, run_phase_2)
```

## 8. Cambios a `validator.py`

`_validate_phase_2` se rehace para usar `FormatConfig`:

```python
def _validate_phase_2(self, output, context):
    plan = output.get("plan")
    transcription = context.get("transcription")
    state = context["state"]
    fmt = load_format(state.project.format_id)
    whitelist = set(fmt.materials_whitelist)
    checks = []

    # CRÍTICAS — bloquean pipeline si fallan
    checks.append(self._check_has_blocks(plan))
    checks.append(self._check_segment_ids_valid(plan, transcription))
    checks.append(self._check_no_duplicate_segments(plan))           # NUEVA
    checks.append(self._check_material_tipos_in_whitelist(plan, whitelist))

    # WARNINGS — no bloquean
    checks.append(self._check_pull_quote_count(plan, max_warn=10))   # NUEVA
    checks.append(self._check_lower_third_count(plan, max_warn=2))   # NUEVA
    checks.append(self._check_duration_in_range(plan, low=22*60, high=32*60))
    checks.append(self._check_cold_open_structure(plan))             # NUEVA
    checks.append(self._claude_coherence_check(plan, transcription))

    critical_names = [
        "has_blocks", "segment_ids_valid",
        "no_duplicate_segments", "material_tipos_in_whitelist",
    ]
    warning_names = [
        "pull_quote_count", "lower_third_count", "duration_in_range",
        "cold_open_structure", "llm_coherence",
    ]
    return self._build_result(2, checks, critical_names, warning_names)
```

Reglas nuevas:

- **`no_duplicate_segments`**: cada `segment_id` debe aparecer máx 1 vez sumando todos los `blocks[].segments`. **Critical** — duplicar segments rompería el playback.
- **`pull_quote_count`**: cuenta total de `MaterialSpec` con `tipo == "pull_quote"`. Si > 10 → warning.
- **`lower_third_count`**: si > 2 → warning. El prompt instruye al LLM con este límite; el validator lo refuerza como soft check.
- **`cold_open_structure`**: el primer bloque debe llamarse exactamente "Cold open" y tener exactamente 3 segmentos. Si no, **warning** (no critical) — el LLM podría no respetar siempre la regla y el editor humano puede ajustar en Phase 8 UI, mejor no bloquear el pipeline por esto.

## 9. CLI `scripts/run_phase2.py`

Espejo de `run_phase1.py` (post-fix), pasando `end_at_phase=2`:

```python
state = orchestrator.run(
    project_id=project_id,
    start_from_phase=2,
    end_at_phase=2,
    skip_validation=args.skip_validation,
)
```

`run_phase1.py` ya valida que Phase N-1 esté completa, así que requerir Phase 1 completed antes de Phase 2 lo da gratis el orchestrator (`_validate_start_phase`).

## 10. Testing

### Unit tests (rápidos, sin red)

- `test_formats.py::test_load_podcast_format` — carga `podcast_hablando_con_profes`, verifica campos no vacíos, narrative_prompt > 1000 chars, whitelist contiene los 5 tipos.
- `test_formats.py::test_load_unknown_format_raises` — `load_format("does-not-exist")` → `FormatNotFoundError`.
- `test_validator_phase2.py::test_validates_clean_plan` — plan correcto → passed=True.
- `test_validator_phase2.py::test_duplicate_segment_critical` — segment_id repetido entre 2 bloques → critical.
- `test_validator_phase2.py::test_invalid_tipo_critical` — tipo fuera de whitelist → critical.
- `test_validator_phase2.py::test_pull_quote_excess_warning_only` — 15 pull_quotes → warning, NO critical.
- `test_validator_phase2.py::test_cold_open_wrong_count_warning` — primer bloque con 2 o 4 segmentos → warning.

### Integration test (manual, con LLM real)

```bash
python scripts/run_phase2.py --project-id cudris-20260526
```

Tras ejecución exitosa:

1. Descargar `projects/cudris-20260526/phase2/narrative_plan.json` de R2.
2. Comparar el cold open generado con el del plan manual (`/Videos/Cudris/plan/Propuesta.md`). El gancho manual era 1 frase; el LLM debería proponer 3 (cambio intencional).
3. Inspeccionar capítulos: ¿los nombres son narrativos? ¿están en orden razonable? ¿chapter_markers presentes?
4. Buscar `transcript_fix` para "Uzme", "Jerez", "zapiens" → debería detectarlos.
5. Verificar duración estimada total entre 22 y 32 min.

## 11. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| LLM devuelve JSON inválido | `response_format={"type": "json_object"}` + try/except con re-prompt vía orchestrator retry |
| LLM ignora la regla de 3 segmentos en cold open | `cold_open_structure` warning + revisión humana en Phase 8 UI |
| Gemini Flash free rate-limit en testing | Switchear `LLM_MODEL_PLANNER` env var a paid model (anthropic/claude-sonnet-4.5 o openai/gpt-4o) |
| Transcripción demasiado larga para context window | 32 min = ~30K chars = ~7K tokens; Gemini Flash soporta 1M. Bajo riesgo. Si llega a pasar, recortar la `text` de cada segment a 500 chars al construir la tabla. |
| Reordenamiento del LLM genera discontinuidad audio difícil de oír | Aceptado en esta versión. Editor humano revisa en Phase 8. Si se vuelve problema, agregar warning si bloque atraviesa gap > 5 min. |
| `transcript_fix` falsos positivos (LLM "corrige" nombres válidos) | Validator no rechaza fixes; editor humano confirma en UI. |

## 12. Open questions (no bloquean implementación)

- ¿Cómo se versionan los formatos? Si `narrative_prompt.md` cambia, ¿se regeneran planes existentes? Por ahora: idempotencia gana — un plan ya generado no se regenera automáticamente. Para forzar, borrar el JSON de R2.
- ¿Múltiples brand_ids con un mismo format_id? Posible futuro: `formats/podcast_X/`, `formats/podcast_Y/` con diferente paleta pero misma lógica narrativa. No abordado aquí.
- ¿Plantilla de prompt con placeholders? E.g. `{{guest_name}}`, `{{episode_topic}}` rellenados antes de mandar al LLM. Por ahora hardcodeado en el prompt; el LLM infiere del audio. Si la calidad baja, agregar `prompt_vars` a `Project` y substituir antes del call.

## 13. Plan de implementación (alto nivel — el plan detallado lo crea writing-plans)

1. Schema: añadir `format_id` a `Project`, `metadata` a `MaterialSpec`, `narrative_plan` a `StorageKey`.
2. Módulo `pipeline/formats.py` + `load_format()` + tests.
3. Carpeta `formats/podcast_hablando_con_profes/` con los 3 archivos.
4. `pipeline/phases/phase2_narrative.py` con `run_phase_2()` y `register()`.
5. Refactor `validator._validate_phase_2` con whitelist por formato + 3 checks nuevos + tests.
6. `scripts/run_phase2.py` (CLI).
7. Smoke test: `python scripts/run_phase2.py --project-id cudris-20260526` y revisión manual del JSON.
8. Actualizar `aidlc-state.md` con Unit 3 completada + métricas reales del Cudris.

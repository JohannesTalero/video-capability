# Phase 3 Manifest Schema

Output autoritativo de Phase 3 (Unit 4), consumido por Phase 4 (Unit 5 — Composición + Branding).

**R2 key:** `projects/<project_id>/phase3/materials_manifest.json`

## Estructura

```json
[
  {
    "material_id": "<block_id>_m<NN>_<8hex>",
    "block_id": "<block_id>",
    "original_spec": {
      "tipo": "lower_third | pull_quote | chapter_marker | animacion_texto | ecuacion_latex | diagrama",
      "contenido": "<string>",
      "timestamp_relativo": 0,
      "metadata": { }
    },
    "refined_spec": { },
    "decision": "keep | modify | drop",
    "position": "bottom-left | top-left | bottom-right | top-right | center | { x_pct, y_pct } | null",
    "reframe": null,
    "reasoning": "<string en español>",
    "render_status": "ok | fallback | dropped",
    "r2_key": "projects/<id>/phase3/materials/<material_id>.webm | null",
    "render_seconds": 0.0
  }
]
```

## Semántica

| Campo | Descripción |
|---|---|
| `material_id` | Identidad estable. Cambia si cambia `original_spec` (tipo/contenido/metadata/timestamp_relativo). |
| `block_id` | ID del bloque narrativo (Phase 2). |
| `original_spec` | MaterialSpec tal como salió de Phase 2. |
| `refined_spec` | MaterialSpec ajustado por Phase 3a (LLM-vision). Igual a `original_spec` si `decision="keep"`. `null` si `decision="drop"`. |
| `decision` | `"keep"` → spec sin cambios. `"modify"` → Phase 3a refinó tipo/contenido/metadata. `"drop"` → no se renderiza. |
| `position` | Esquina del overlay. Para `chapter_marker` y `diagrama` puede ser `"center"`. Si custom: `{x_pct, y_pct}` en fracción del frame 1920×1080 (esquina superior-izquierda del overlay). |
| `reframe` | Instrucción opcional para Phase 4: cómo recortar/zoom/replace el video subyacente en el rango `[t_start_relative, t_end_relative]`. |
| `reasoning` | Justificación humana-readable de la decisión (≤2 oraciones). Para auditoría. |
| `render_status` | `"ok"` (render normal), `"fallback"` (cayó a text card), `"dropped"` (no se renderizó). |
| `r2_key` | Path en R2 al .webm. `null` si `dropped`. |
| `render_seconds` | Tiempo del worker en segundos. `0.0` si `dropped`. |

## Reframe params por type

| type | params | Phase 4 ffmpeg filter |
|---|---|---|
| `crop` | `{x_pct, y_pct, w_pct, h_pct}` | `crop=iw*W:ih*H:iw*X:ih*Y` |
| `zoom` | `{scale, center_x_pct, center_y_pct}` | ramp 0.3s in + hold + ramp 0.3s out, via zoompan |
| `replace_with_material` | `{}` | source video oculto entre `t_start_relative` y `t_end_relative`; solo se muestra el `.webm` del material full-frame |

## Cómo lo consume Phase 4 (Unit 5)

1. **Descargar** el manifest desde `projects/<id>/phase3/materials_manifest.json`.
2. **Filtrar** entries con `render_status != "dropped"`.
3. Por cada entry, **descargar** el `.webm` desde `r2_key` a working dir local.
4. **Build ffmpeg complex filter graph:**
   - Para cada material, calcular `[start_sec, end_sec]` desde `refined_spec.timestamp_relativo` y duration por tipo (lookup table).
   - Si tiene `reframe`: aplicar al video base durante `[t_start_relative, t_end_relative]`.
   - Overlay del `.webm` sobre el video resultado en `position` y `[start_sec, end_sec]`.
5. **Encode** final como mp4 H.264 + AAC.

## Idempotency garantizada

Cuando Unit 5 procesa el manifest, puede asumir:
- `material_id` es estable: si Phase 3 corrió 2 veces con mismo plan de entrada, el manifest es idéntico.
- `r2_key` apunta a un .webm que NO va a cambiar bajo el mismo `material_id` (se sobrescribe solo si el material_id cambia, lo cual implica spec change).
- Unit 5 puede cachear su propio output indexado por hash del manifest.

## Compatibilidad versional

- v1 (Unit 4 release): este schema.
- Cambios futuros se marcarán con `manifest_schema_version` field en el JSON top-level (no presente en v1 — su ausencia indica v1).

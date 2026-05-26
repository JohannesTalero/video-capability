# Business Rules — Unit 1: Core Pipeline
# PhyMaC Video Auto-Edit Pipeline

---

## BR-01: Generación del project_id

- El `project_id` se genera como slug del título + fecha: `slugify(title) + "-" + YYYYMMDD`
- Ejemplo: título `"Ondas Electromagnéticas Ep12"` → `"ondas-electromagneticas-ep12-20260521"`
- Si ya existe ese slug en storage → agregar sufijo numérico: `-2`, `-3`, etc.
- El `project_id` es inmutable una vez creado.

---

## BR-02: Fases permitidas

- El pipeline tiene exactamente 6 fases, numeradas 1–6.
- Las fases se ejecutan **en orden estricto**: no se puede ejecutar la Fase N sin que la Fase N-1 esté en estado `COMPLETED`.
- Excepción: `start_from_phase` permite reanudar desde cualquier fase, pero solo si las fases anteriores están en `COMPLETED`.
- Si se intenta ejecutar una fase fuera de orden → `InvalidPhaseOrderError`.

---

## BR-03: Sistema de reintentos

- Cada fase tiene un contador de intentos (`attempt`), que comienza en 1.
- Si la validación de la fase falla → `attempt += 1` y re-ejecutar la fase.
- **Máximo 3 intentos** (attempt 1, 2, 3).
- Si los 3 intentos fallan → el proyecto pasa a `PAUSED` y se notifica al usuario.
- En estado `PAUSED`, el usuario puede:
  - `resume` — vuelve a intentar la misma fase (reset de attempt a 1)
  - `skip_validation` — marca la fase como `COMPLETED` sin validación (override manual)
  - `abort` — marca el proyecto como `FAILED`

---

## BR-04: Checkpoints

- El checkpoint se guarda **solo cuando la fase pasa la validación** (no antes).
- El checkpoint incluye: `PhaseState` completo con outputs, `ValidationResult`, timestamp.
- El checkpoint se guarda en storage antes de avanzar a la siguiente fase.
- Si el proceso muere entre fases (crash, timeout) → al reiniciar, el sistema lee el último checkpoint y continúa desde la fase pendiente.
- Los checkpoints son **append-only** en el sentido de que nunca se borra el checkpoint de una fase completada.

---

## BR-05: Outputs de cada fase

- Cada fase produce exactamente un set de outputs definidos (ver `StorageKey`).
- Los outputs de la fase N son **inputs requeridos** de la fase N+1.
- Si un output de una fase anterior no existe en storage → `MissingPhaseOutputError`.
- Los outputs intermedios se preservan indefinidamente (hasta que el usuario elimine el proyecto).

---

## BR-06: Reglas del StorageAdapter

- **Todos** los accesos a storage pasan por `StorageAdapter`. Ningún componente accede directamente al SDK de R2/S3.
- `upload()` es idempotente: subir el mismo key dos veces sobrescribe silenciosamente.
- `download()` descarga a un directorio temporal local (`/tmp/phymac/{project_id}/`).
- El directorio temporal se limpia al finalizar cada fase (no acumular archivos grandes entre fases).
- Si el proveedor cambia (R2 → S3 o viceversa) → solo cambia `StorageAdapter`, nada más.

---

## BR-07: Validación — reglas generales

- La validación se ejecuta **siempre** después de cada fase. No es opcional.
- Un `ValidationResult` con `passed=False` siempre tiene al menos un item en `critical_failures`.
- Un `ValidationResult` con `passed=True` puede tener `warnings` (no bloquea).
- El score `0.0–1.0` es informativo: `score < 0.6` siempre implica `passed=False`. `score >= 0.8` es "buena calidad". Entre 0.6 y 0.8 puede pasar con warnings.
- Los warnings se almacenan en el checkpoint y se muestran al usuario en el resumen final.

---

## BR-08: Notificación al usuario en PAUSED

Cuando el proyecto entra en `PAUSED`, el sistema debe generar un mensaje de notificación que incluya:
1. Fase que falló y número de intento
2. Lista de `critical_failures` de la validación
3. `recommendation` del `ValidationResult`
4. Instrucción exacta para reanudar:
   ```
   Para reanudar: python scripts/resume_pipeline.py --project-id {project_id} --from-phase {phase}
   ```
5. Instrucción para override manual si el usuario confía en el output:
   ```
   Para continuar sin validación: python scripts/resume_pipeline.py --project-id {project_id} --from-phase {phase} --skip-validation
   ```

---

## BR-09: project_id en paths locales temporales

- Todos los archivos temporales van a `/tmp/phymac/{project_id}/phase{N}/`
- Al completar una fase → borrar `/tmp/phymac/{project_id}/phase{N}/` (excepto si el siguiente paso los necesita inmediatamente)
- El directorio `/tmp/phymac/` puede acumular proyectos — limpieza manual o TTL de 24h.

---

## BR-10: Concurrencia

- **Un solo proyecto corre a la vez** en el MVP. No hay ejecución paralela de proyectos distintos.
- Dentro de un proyecto, solo la Fase 3 (MaterialGenerator) usa paralelismo interno (Modal.map()).
- El `PipelineOrchestrator` es single-threaded en el MVP.

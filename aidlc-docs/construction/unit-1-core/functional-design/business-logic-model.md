# Business Logic Model — Unit 1: Core Pipeline
# PhyMaC Video Auto-Edit Pipeline

---

## PipelineOrchestrator — Máquina de Estados

```
Estado inicial del proyecto:
  Project.status = CREATED
  phases = {1: PENDING, 2: PENDING, 3: PENDING, 4: PENDING, 5: PENDING, 6: PENDING}

run(project_id, start_from_phase=1):
  1. Cargar ProjectState desde storage (checkpoint)
  2. Validar que las fases anteriores a start_from_phase estén COMPLETED
  3. Para cada fase N desde start_from_phase hasta 6:
     a. Marcar Project.status = RUNNING, phase[N].status = RUNNING, attempt = 1
     b. Guardar estado parcial
     c. Ejecutar fase N → output
     d. Ejecutar ValidationAgent.validate(N, output)
     e. Si PASS:
        - Marcar phase[N].status = COMPLETED, guardar checkpoint
        - Continuar con fase N+1
     f. Si FAIL y attempt < 3:
        - attempt += 1, re-ejecutar desde paso (c)
     g. Si FAIL y attempt == 3:
        - Marcar phase[N].status = FAILED, Project.status = PAUSED
        - Guardar checkpoint (con el estado de falla)
        - Notificar al usuario
        - STOP (el usuario decide cómo continuar)
  4. Al completar fase 6: Project.status = COMPLETED
```

---

## StorageAdapter — Algoritmo de Upload/Download

```
upload(local_path, remote_key):
  1. Verificar que local_path existe y no está vacío (> 0 bytes)
  2. Calcular MD5 del archivo local
  3. Subir al proveedor (R2 o S3) con put_object()
  4. Verificar que el objeto existe en el proveedor con head_object()
  5. Si la verificación falla → raise UploadVerificationError
  6. Retornar remote_key

download(remote_key, local_path):
  1. Crear el directorio de local_path si no existe
  2. Verificar que remote_key existe (exists())
  3. Si no existe → raise StorageKeyNotFoundError
  4. Descargar con get_object() → escribir a local_path
  5. Verificar que local_path tiene > 0 bytes
  6. Retornar local_path

get_presigned_url(remote_key, expires_in=3600):
  1. Verificar que remote_key existe
  2. Generar URL presigned con el proveedor
  3. Retornar URL (string)
```

---

## ValidationAgent — Algoritmo de Validación

```
validate(phase, output, context):
  1. Seleccionar el validador correcto según phase (1-6)
  2. Ejecutar todos los checks del validador → list[CheckResult]
  3. Separar checks en: passed_checks, failed_checks
  4. critical_failures = [c.message for c in failed_checks if c es crítico]
  5. warnings = [c.message for c in failed_checks if c es warning]
  6. score = len(passed_checks) / len(all_checks)
  7. passed = (len(critical_failures) == 0) AND (score >= 0.6)
  8. recommendation = generar_recomendacion(critical_failures)
  9. Retornar ValidationResult

generar_recomendacion(critical_failures):
  - Si vacío → "Output looks good."
  - Si contiene "transcription coverage" → "Try re-transcribing with temperature=0.2"
  - Si contiene "alpha channel" → "Check the material renderer logs for errors"
  - Si contiene "audio clipping" → "Reduce input gain before audio processing"
  - Default → "Review the phase logs and retry. If persists, use --skip-validation."
```

---

## Checkpoint Save/Load

```
save_checkpoint(project_id, phase_state, project):
  1. Cargar ProjectState actual desde storage (o crear uno nuevo si no existe)
  2. Actualizar project_state.phases[phase_num] = phase_state
  3. Actualizar project_state.project = project (status, current_phase, updated_at)
  4. Serializar ProjectState a JSON
  5. StorageAdapter.upload(json_bytes, StorageKey.project_state(project_id))

load_checkpoint(project_id) -> ProjectState:
  1. key = StorageKey.project_state(project_id)
  2. Si NOT exists(key) → raise ProjectNotFoundError
  3. Descargar JSON desde storage
  4. Deserializar a ProjectState
  5. Retornar ProjectState
```

---

## Project ID Generation

```
generate_project_id(title, created_at) -> str:
  1. slug = slugify(title)          # "Ondas EM Ep12" → "ondas-em-ep12"
  2. date_str = created_at.strftime("%Y%m%d")
  3. base_id = f"{slug}-{date_str}"
  4. Si NOT storage.exists(StorageKey.project_state(base_id)):
       return base_id
  5. Para n en range(2, 100):
       candidate = f"{base_id}-{n}"
       Si NOT storage.exists(StorageKey.project_state(candidate)):
           return candidate
  6. raise ProjectIDCollisionError  # raro pero manejado
```

---

## Flujo de inicialización de un proyecto nuevo

```
create_project(title, video_local_path, brand_id="phymac") -> ProjectState:
  1. project_id = generate_project_id(title, now())
  2. video_key = StorageKey.original_video(project_id, basename(video_local_path))
  3. StorageAdapter.upload(video_local_path, video_key)
  4. project = Project(
       project_id=project_id, title=title, brand_id=brand_id,
       video_original_key=video_key, created_at=now(), updated_at=now(),
       current_phase=0, status=ProjectStatus.CREATED
     )
  5. phases = {n: PhaseState(n, PENDING, 0, None, None, {}, None, None) for n in range(1,7)}
  6. state = ProjectState(project, phases)
  7. save_checkpoint(project_id, phases[1], project)  # guarda estado inicial
  8. return state
```

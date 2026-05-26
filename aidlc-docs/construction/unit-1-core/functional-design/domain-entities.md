# Domain Entities — Unit 1: Core Pipeline
# PhyMaC Video Auto-Edit Pipeline

---

## Project (raíz del dominio)

```python
@dataclass
class Project:
    project_id: str          # slug generado: "titulo-del-video-20260521"
    title: str               # ingresado por el usuario
    brand_id: str            # default: "phymac"
    video_original_key: str  # key en storage del video crudo
    created_at: datetime
    updated_at: datetime
    current_phase: int       # 0=creado, 1-6=en fase, 7=completo
    status: ProjectStatus    # CREATED | RUNNING | PAUSED | COMPLETED | FAILED
```

---

## ProjectStatus (enum)

```python
class ProjectStatus(str, Enum):
    CREATED   = "created"    # proyecto creado, ninguna fase ejecutada
    RUNNING   = "running"    # una fase se está ejecutando ahora
    PAUSED    = "paused"     # falló tras 3 reintentos, espera usuario
    COMPLETED = "completed"  # todas las fases completadas
    FAILED    = "failed"     # el usuario abortó
```

---

## PhaseState (estado de una fase individual)

```python
@dataclass
class PhaseState:
    phase_num: int
    status: PhaseStatus      # PENDING | RUNNING | COMPLETED | FAILED
    attempt: int             # 1, 2 o 3
    started_at: datetime | None
    completed_at: datetime | None
    outputs: dict[str, str]  # {"transcription_key": "projects/x/phase1/transcript.json"}
    validation: ValidationResult | None
    error_message: str | None
```

```python
class PhaseStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
```

---

## ProjectState (checkpoint completo)

```python
@dataclass
class ProjectState:
    project: Project
    phases: dict[int, PhaseState]   # {1: PhaseState, 2: PhaseState, ...}
    
    def last_completed_phase(self) -> int:
        completed = [n for n, p in self.phases.items() if p.status == PhaseStatus.COMPLETED]
        return max(completed) if completed else 0
    
    def next_pending_phase(self) -> int | None:
        pending = [n for n, p in self.phases.items() if p.status == PhaseStatus.PENDING]
        return min(pending) if pending else None
    
    def get_output(self, phase_num: int, key: str) -> str | None:
        phase = self.phases.get(phase_num)
        return phase.outputs.get(key) if phase else None
```

**Persistencia**: `projects/{project_id}/state.json` en storage. Serialización/deserialización con `dataclasses_json` o JSON manual.

---

## ValidationResult

```python
@dataclass
class ValidationResult:
    passed: bool
    phase: int
    score: float                    # 0.0 → 1.0
    checks: list[CheckResult]
    critical_failures: list[str]    # bloquean el pipeline
    warnings: list[str]             # se reportan pero no bloquean
    recommendation: str             # qué hacer si falló

@dataclass
class CheckResult:
    name: str
    passed: bool
    value: Any          # el valor medido
    threshold: Any      # el criterio de pass
    message: str
```

---

## StorageKey (convención de paths en R2/S3)

```python
class StorageKey:
    """Convención centralizada para paths en storage. Sin hardcoding disperso."""
    
    @staticmethod
    def project_state(project_id: str) -> str:
        return f"projects/{project_id}/state.json"
    
    @staticmethod
    def original_video(project_id: str, filename: str) -> str:
        return f"projects/{project_id}/input/{filename}"
    
    @staticmethod
    def extracted_audio(project_id: str) -> str:
        return f"projects/{project_id}/phase1/audio.wav"
    
    @staticmethod
    def transcription(project_id: str) -> str:
        return f"projects/{project_id}/phase1/transcription.json"
    
    @staticmethod
    def narrative_plan(project_id: str) -> str:
        return f"projects/{project_id}/phase2/plan.json"
    
    @staticmethod
    def material_asset(project_id: str, block_id: str, item_idx: int) -> str:
        return f"projects/{project_id}/phase3/materials/{block_id}_{item_idx}.mp4"
    
    @staticmethod
    def composed_video(project_id: str) -> str:
        return f"projects/{project_id}/phase4/composed.mp4"
    
    @staticmethod
    def audio_processed_video(project_id: str) -> str:
        return f"projects/{project_id}/phase5/audio_processed.mp4"
    
    @staticmethod
    def final_video(project_id: str) -> str:
        return f"projects/{project_id}/phase6/final.mp4"
    
    @staticmethod
    def brand_config(brand_id: str) -> str:
        return f"brands/{brand_id}/config.json"
    
    @staticmethod
    def brand_asset(brand_id: str, asset_name: str) -> str:
        return f"brands/{brand_id}/{asset_name}"
```

---

## TranscriptionResult

```python
@dataclass
class TranscriptionSegment:
    id: int
    start: float        # segundos
    end: float          # segundos
    text: str
    confidence: float   # 0.0 → 1.0 (de Whisper)

@dataclass
class TranscriptionResult:
    project_id: str
    segments: list[TranscriptionSegment]
    full_text: str
    duration_seconds: float
    language: str
    model: str          # "large-v3"
    storage_key: str    # donde está guardado el JSON
```

---

## NarrativePlan

```python
@dataclass
class MaterialSpec:
    tipo: str           # "ecuacion_latex" | "diagrama" | "animacion_texto"
    contenido: str      # LaTeX string o descripción en texto
    timestamp_relativo: int  # segundos dentro del bloque donde aparece

@dataclass
class Block:
    id: str             # "bloque_1", "bloque_2", ...
    name: str           # "Introducción al concepto"
    segments: list[int] # IDs de TranscriptionSegment
    estimated_duration: str   # "00:02:15"
    support_material: list[MaterialSpec]
    transition_next: str      # "cortinilla_concepto" | "fade" | "corte_directo"

@dataclass
class NarrativePlan:
    project_id: str
    blocks: list[Block]
    storage_key: str
```

---

## MaterialAsset

```python
@dataclass
class MaterialAsset:
    block_id: str
    item_index: int
    spec: MaterialSpec
    storage_key: str
    duration_seconds: float
    has_alpha: bool      # siempre True en el pipeline
    width: int
    height: int
```

---

## BrandConfig

```python
@dataclass
class BrandColors:
    primary: str    # hex "#1A1A2E"
    secondary: str
    accent: str
    text: str

@dataclass
class BrandFonts:
    heading: str    # "Space Grotesk"
    body: str

@dataclass
class BrandAssets:
    logo: str               # storage key
    intro: str              # storage key al MP4
    outro: str              # storage key al MP4
    lower_third: str        # storage key al SVG template
    cortinillas: dict[str, str]  # {"concepto": key, "datos": key, ...}

@dataclass
class BrandConfig:
    brand_id: str
    display_name: str
    colors: BrandColors
    fonts: BrandFonts
    assets: BrandAssets
```

---

## RenderConfig / RenderResult

```python
@dataclass
class RenderConfig:
    resolution: str = "1920x1080"
    fps: int = 30
    video_codec: str = "libx264"
    crf: int = 18
    preset: str = "slow"
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"

@dataclass
class RenderResult:
    project_id: str
    storage_key: str
    download_url: str
    file_size_mb: float
    duration_seconds: float
    render_time_seconds: float
```

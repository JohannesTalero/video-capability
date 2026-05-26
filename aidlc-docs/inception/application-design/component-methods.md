# Component Methods
# PhyMaC Video Auto-Edit Pipeline

*Nota: Las firmas de métodos son de alto nivel. La lógica de negocio detallada se define en Functional Design (Construction Phase).*

---

## VideoIngestor

```python
def ingest(video_path: str, project_id: str) -> TranscriptionResult:
    """Extrae audio del video y transcribe con Whisper large-v3."""

def extract_audio(video_path: str) -> str:
    """Extrae el track de audio del video. Retorna path al archivo de audio."""

def transcribe(audio_path: str, language: str = "es") -> TranscriptionResult:
    """Llama a Whisper large-v3. Retorna segmentos con timestamps."""
```

**Tipos**:
```python
@dataclass
class TranscriptionResult:
    project_id: str
    segments: list[Segment]       # [{id, start, end, text}]
    full_text: str
    duration_seconds: float
    storage_path: str             # path en R2/S3
```

---

## NarrativePlanner

```python
def generate_plan(transcription: ApprovedTranscription) -> NarrativePlan:
    """Llama a Claude API con el prompt de planificación narrativa."""

def build_prompt(transcription: ApprovedTranscription) -> str:
    """Construye el prompt estructurado para Claude."""

def parse_response(raw_response: str) -> NarrativePlan:
    """Parsea el JSON de respuesta de Claude y valida su estructura."""
```

**Tipos**:
```python
@dataclass
class NarrativePlan:
    project_id: str
    blocks: list[Block]

@dataclass
class Block:
    id: str
    name: str
    segments: list[int]           # IDs de segmentos de transcripción
    estimated_duration: str       # "00:02:15"
    support_material: list[MaterialSpec]
    transition_next: str          # "cortinilla_concepto" | "fade" | "corte"

@dataclass
class MaterialSpec:
    tipo: str                     # "ecuacion_latex" | "diagrama" | "animacion_texto"
    contenido: str                # LaTeX string o descripción
    timestamp_relativo: int       # segundos dentro del bloque
```

---

## MaterialGenerator

```python
def generate_all(plan: ApprovedNarrativePlan) -> list[MaterialAsset]:
    """Dispatcher: lanza todos los workers en paralelo con Modal.map()."""

def generate_for_block(block: Block) -> list[MaterialAsset]:
    """Worker individual: genera todos los materiales de un bloque."""
```

**Sub-renderers**:
```python
def render_latex(spec: MaterialSpec) -> MaterialAsset:
    """MathJax → Puppeteer → PNG → MP4 con canal alpha."""

def render_diagram(spec: MaterialSpec) -> MaterialAsset:
    """Matplotlib → SVG → MP4 con canal alpha."""

def render_animation(spec: MaterialSpec) -> MaterialAsset:
    """Remotion (React) → MP4 con canal alpha."""
```

**Tipos**:
```python
@dataclass
class MaterialAsset:
    block_id: str
    spec: MaterialSpec
    storage_path: str             # path al MP4 con alpha en R2/S3
    duration_seconds: float
    has_alpha: bool               # siempre True
```

---

## BrandManager

```python
def load(brand_id: str) -> BrandConfig:
    """Carga la config JSON de la marca desde storage."""

def get_asset_path(brand_id: str, asset_type: str) -> str:
    """Retorna el path en storage del asset solicitado."""

def list_brands() -> list[str]:
    """Lista los brand_ids disponibles."""

def validate_brand_assets(brand_id: str) -> BrandValidationReport:
    """Verifica que todos los assets requeridos existan en storage."""
```

**Tipos**:
```python
@dataclass
class BrandConfig:
    brand_id: str
    colors: dict[str, str]        # {"primary": "#HEX", "secondary": "#HEX", ...}
    fonts: dict[str, str]         # {"heading": "font-name", "body": "font-name"}
    assets: dict[str, str]        # {"logo": "path", "intro": "path", "outro": "path", ...}
    lower_third_template: str     # path al SVG template
```

---

## VideoComposer

```python
def compose(
    video_path: str,
    plan: ApprovedNarrativePlan,
    materials: list[MaterialAsset],
    brand: BrandConfig
) -> str:
    """Orquesta la composición completa. Retorna path al video compuesto."""

def apply_cuts(video_path: str, segments: list[Segment]) -> str:
    """FFmpeg: aplica cortes al video crudo según los segmentos aprobados."""

def overlay_materials(video_path: str, materials: list[MaterialAsset], plan: ApprovedNarrativePlan) -> str:
    """FFmpeg: inserta cada material de apoyo en su timestamp correcto."""

def insert_transitions(video_path: str, plan: ApprovedNarrativePlan, brand: BrandConfig) -> str:
    """FFmpeg: inserta cortinillas entre bloques."""

def apply_branding(video_path: str, brand: BrandConfig) -> str:
    """FFmpeg: agrega intro, outro, logo, lower thirds."""
```

---

## AudioProcessor

```python
def process(video_path: str, music_path: str | None = None) -> str:
    """Pipeline completo de audio. Retorna video con audio procesado."""

def clean_noise(video_path: str) -> str:
    """DeepFilter: elimina ruido de fondo del audio."""

def normalize_volume(video_path: str, target_lufs: float = -14.0) -> str:
    """FFmpeg loudnorm: normaliza el volumen a target LUFS."""

def mix_audio(voice_path: str, music_path: str, voice_ratio: float = 0.85) -> str:
    """FFmpeg: mezcla voz + música con ducking automático."""
```

---

## VideoRenderer

```python
def render(video_path: str, config: RenderConfig) -> RenderResult:
    """FFmpeg: render final en la calidad y formato especificados."""

def upload_final(local_path: str, project_id: str) -> str:
    """Sube el video final a R2/S3. Retorna URL de descarga."""
```

**Tipos**:
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
    storage_path: str
    download_url: str
    file_size_mb: float
    duration_seconds: float
    render_time_seconds: float
```

---

## PipelineOrchestrator

```python
def run(project_id: str, start_from_phase: int = 1) -> None:
    """Ejecuta el pipeline desde la fase indicada. Guarda checkpoint al completar cada fase."""

def save_checkpoint(project_id: str, phase: int, output: dict) -> None:
    """Persiste el estado de la fase completada en storage."""

def load_checkpoint(project_id: str) -> ProjectState:
    """Recupera el último estado guardado del proyecto."""

def get_status(project_id: str) -> ProjectState:
    """Retorna el estado actual del proyecto."""

def retry_phase(project_id: str, phase: int, max_retries: int = 3) -> bool:
    """Reintenta una fase que falló. Retorna True si tuvo éxito."""
```

---

## StorageAdapter

```python
def upload(local_path: str, remote_key: str) -> str:
    """Sube archivo a R2/S3. Retorna URL pública o presigned."""

def download(remote_key: str, local_path: str) -> None:
    """Descarga archivo de R2/S3 a path local."""

def get_url(remote_key: str, expires_in: int = 3600) -> str:
    """Genera URL presigned con expiración."""

def exists(remote_key: str) -> bool:
    """Verifica si el key existe en storage."""

def delete(remote_key: str) -> None:
    """Elimina un archivo del storage."""

def list_prefix(prefix: str) -> list[str]:
    """Lista todos los keys bajo un prefix dado."""
```

---

## ProjectAPI (REST Endpoints)

```python
POST   /projects                          → ProjectState
GET    /projects/{project_id}             → ProjectState
POST   /projects/{project_id}/phase/{n}/approve  → ProjectState
GET    /projects/{project_id}/transcription      → TranscriptionResult
PUT    /projects/{project_id}/transcription      → ApprovedTranscription
GET    /projects/{project_id}/plan               → NarrativePlan
PUT    /projects/{project_id}/plan               → ApprovedNarrativePlan
GET    /projects/{project_id}/download           → DownloadInfo
DELETE /projects/{project_id}                    → void
```

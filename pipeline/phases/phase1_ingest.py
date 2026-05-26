"""
Phase 1 — Video Ingestion & Transcription

Responsibilities:
- Download the original video from storage to a Modal GPU worker
- Extract audio with FFmpeg
- Transcribe with Whisper large-v3
- Save TranscriptionResult JSON to storage
- Register as the Phase 1 runner with PipelineOrchestrator

Modal worker: GPU (any available), timeout 20 min
Local run: uses Whisper on CPU (slow, for testing without Modal)
"""
from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path

import modal

from pipeline.config import (
    WHISPER_MODEL,
    WHISPER_LANGUAGE,
    get_project_tmp_dir,
)
from pipeline.models import (
    ProjectState,
    StorageKey,
    TranscriptionResult,
    TranscriptionSegment,
)
from pipeline.storage import StorageAdapter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Modal App & Image
# ---------------------------------------------------------------------------

app = modal.App("phymac-pipeline")

# GPU image: CUDA + ffmpeg + whisper
whisper_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        "openai-whisper",
        "torch",
        "numpy",
        "boto3",
    )
)


# ---------------------------------------------------------------------------
# Modal GPU function — Whisper transcription
# ---------------------------------------------------------------------------

@app.function(
    image=whisper_image,
    gpu="any",
    timeout=1200,  # 20 minutes
    retries=0,     # Orchestrator handles retries
)
def transcribe_on_modal(
    audio_key: str,
    storage_config: dict,
    model_name: str = "large-v3",
    language: str = "es",
) -> dict:
    """
    Run Whisper transcription on a Modal GPU worker.

    Downloads the audio from R2/S3 INSIDE the worker to avoid Modal's
    RPC argument size limits (long videos produce >16 MB audio bytes).

    Args:
        audio_key: storage key (e.g. "projects/{id}/phase1/audio.wav")
        storage_config: dict with keys "provider", "bucket" and the
                        provider-specific credentials
                        (r2: account_id, access_key_id, secret_key /
                         s3: access_key_id, secret_access_key, region)
        model_name: Whisper model id
        language: ISO-639-1 code, e.g. "es"
    """
    import tempfile
    from pathlib import Path
    import boto3
    from botocore.client import Config
    import whisper

    # Build storage client inside the Modal worker
    provider = storage_config["provider"]
    bucket = storage_config["bucket"]
    if provider == "r2":
        client = boto3.client(
            "s3",
            endpoint_url=storage_config["endpoint_url"],
            aws_access_key_id=storage_config["access_key_id"],
            aws_secret_access_key=storage_config["secret_key"],
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
    elif provider == "s3":
        client = boto3.client(
            "s3",
            aws_access_key_id=storage_config["access_key_id"],
            aws_secret_access_key=storage_config["secret_access_key"],
            region_name=storage_config.get("region", "us-east-1"),
        )
    else:
        raise ValueError(f"Unknown storage provider: {provider}")

    # Download audio inside the worker
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        audio_path = tmp.name
    print(f"[Modal] Downloading audio from {provider}://{bucket}/{audio_key}")
    client.download_file(bucket, audio_key, audio_path)
    audio_size_mb = Path(audio_path).stat().st_size / (1024 * 1024)
    print(f"[Modal] Audio downloaded: {audio_size_mb:.1f} MB")

    print(f"[Modal] Loading Whisper model: {model_name}")
    model = whisper.load_model(model_name)

    print(f"[Modal] Transcribing...")
    result = model.transcribe(
        audio_path,
        language=language,
        word_timestamps=False,
        verbose=False,
    )

    segments = []
    for i, seg in enumerate(result["segments"]):
        segments.append({
            "id": i,
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text"].strip(),
            # Whisper doesn't always return per-segment confidence
            # Use avg_logprob as a proxy: convert from log space
            "confidence": min(1.0, max(0.0, (seg.get("avg_logprob", -0.5) + 1.0))),
        })

    return {
        "segments": segments,
        "full_text": result["text"].strip(),
        "language": result.get("language", language),
        "model": model_name,
    }


# ---------------------------------------------------------------------------
# Phase 1 Runner — called by PipelineOrchestrator
# ---------------------------------------------------------------------------

def run_phase_1(state: ProjectState) -> dict:
    """
    Phase 1 runner. Registered with PipelineOrchestrator.

    Idempotent: each step is skipped if its artifact already exists, so a
    retry after a Whisper failure does not re-download the 1+ GB video or
    re-extract audio. To force a full re-run, delete the transcription
    JSON from storage before retrying.

    Steps:
    1. Short-circuit: if transcription JSON already in storage, reuse it
    2. Download original video (skip if already local)
    3. Extract audio with FFmpeg (skip if already extracted)
    4. Get video duration
    5. Upload audio to storage (skip if already uploaded)
    6. Transcribe with Whisper (Modal GPU or local CPU fallback)
    7. Save TranscriptionResult to storage
    """
    project_id = state.project.project_id
    storage = StorageAdapter()
    tmp_dir = get_project_tmp_dir(project_id, phase=1)

    audio_key = StorageKey.extracted_audio(project_id)
    transcription_key = StorageKey.transcription(project_id)

    # Step 1: If transcription already exists, return its metadata (idempotent retry)
    if storage.exists(transcription_key):
        logger.info(f"[Phase 1] Transcription already in storage: {transcription_key} — reusing")
        transcription = TranscriptionResult.from_json(storage.download_json(transcription_key))
        return {
            "transcription_key": transcription_key,
            "audio_key": audio_key,
            "transcription": transcription,
            "segment_count": len(transcription.segments),
            "duration_seconds": transcription.duration_seconds,
            "language": transcription.language,
        }

    # Step 2: Download original video (skip if already local)
    video_key = state.project.video_original_key
    video_local = tmp_dir / Path(video_key).name
    if video_local.exists() and video_local.stat().st_size > 0:
        logger.info(f"[Phase 1] Video already local: {video_local} ({video_local.stat().st_size / 1024:.0f} KB)")
    else:
        logger.info(f"[Phase 1] Downloading video: {video_key}")
        storage.download(video_key, video_local)

    # Step 3: Extract audio with FFmpeg (skip if already extracted)
    audio_local = tmp_dir / "audio.wav"
    if audio_local.exists() and audio_local.stat().st_size > 0:
        logger.info(f"[Phase 1] Audio already extracted: {audio_local}")
    else:
        logger.info(f"[Phase 1] Extracting audio → {audio_local}")
        _extract_audio(video_local, audio_local)

    # Step 4: Get video duration
    duration = _get_duration(video_local)
    logger.info(f"[Phase 1] Video duration: {duration:.1f}s ({duration/60:.1f} min)")

    # Step 5: Upload extracted audio to storage (skip if already uploaded).
    # Modal worker will download it from storage (avoids RPC size limits).
    if storage.exists(audio_key):
        logger.info(f"[Phase 1] Audio already in storage: {audio_key}")
    else:
        logger.info(f"[Phase 1] Uploading audio → {audio_key}")
        storage.upload(audio_local, audio_key)

    # Step 6: Transcribe (Modal worker downloads audio_key, or local fallback uses audio_local)
    logger.info(f"[Phase 1] Starting Whisper transcription (model={WHISPER_MODEL})")
    whisper_result = _transcribe(audio_local, audio_key)

    # Build TranscriptionResult
    segments = [
        TranscriptionSegment(
            id=s["id"],
            start=s["start"],
            end=s["end"],
            text=s["text"],
            confidence=s.get("confidence", 1.0),
        )
        for s in whisper_result["segments"]
    ]

    transcription = TranscriptionResult(
        project_id=project_id,
        segments=segments,
        full_text=whisper_result["full_text"],
        duration_seconds=duration,
        language=whisper_result.get("language", WHISPER_LANGUAGE),
        model=whisper_result.get("model", WHISPER_MODEL),
        storage_key=transcription_key,
    )

    # Step 7: Save transcription JSON to storage
    logger.info(f"[Phase 1] Saving transcription → {transcription_key}")
    storage.upload_json(transcription.to_json(), transcription_key)

    logger.info(
        f"[Phase 1] Done. {len(segments)} segments, "
        f"{len(transcription.full_text)} chars, "
        f"language={transcription.language}"
    )

    _cleanup(tmp_dir)

    return {
        "transcription_key": transcription_key,
        "audio_key": audio_key,
        "transcription": transcription,  # passed to ValidationAgent
        "segment_count": len(segments),
        "duration_seconds": duration,
        "language": transcription.language,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_audio(video_path: Path, audio_path: Path) -> None:
    """Use FFmpeg to extract mono WAV audio at 16kHz (Whisper optimal)."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",                      # no video
        "-acodec", "pcm_s16le",     # WAV PCM 16-bit
        "-ar", "16000",             # 16kHz sample rate
        "-ac", "1",                 # mono
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg audio extraction failed:\n{result.stderr}")
    if not audio_path.exists() or audio_path.stat().st_size == 0:
        raise RuntimeError("FFmpeg produced an empty audio file.")


def _get_duration(video_path: Path) -> float:
    """Use ffprobe to get video duration in seconds."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            str(video_path),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe duration check failed: {result.stderr}")
    data = json.loads(result.stdout)
    return float(data.get("format", {}).get("duration", 0))


def _transcribe(audio_local_path: Path, audio_key: str) -> dict:
    """
    Transcribe audio using Whisper.

    Strategy:
    - If MODAL_TOKEN_ID env var is set → run on Modal GPU (cloud, fast).
      The Modal worker downloads the audio from storage via `audio_key`
      to avoid Modal's RPC argument size limits (long videos produce
      audio > 16 MB).
    - Otherwise → run locally with Whisper CPU (slow, for dev/testing).
      Uses the local file at `audio_local_path` directly.
    """
    import os

    use_modal = bool(os.environ.get("MODAL_TOKEN_ID"))

    if use_modal:
        logger.info(f"[Phase 1] Running Whisper on Modal GPU (audio_key={audio_key})...")
        storage_config = _build_storage_config_for_modal()
        with app.run():
            return transcribe_on_modal.remote(
                audio_key=audio_key,
                storage_config=storage_config,
                model_name=WHISPER_MODEL,
                language=WHISPER_LANGUAGE,
            )
    else:
        logger.info("[Phase 1] Running Whisper locally (CPU mode — slow for long videos)...")
        return _transcribe_local(audio_local_path)


def _build_storage_config_for_modal() -> dict:
    """Snapshot of local storage env vars to pass to the Modal worker.
    Modal worker uses this to reconstruct a boto3 client and download audio."""
    from pipeline.config import (
        STORAGE_PROVIDER,
        R2_ACCESS_KEY_ID, R2_SECRET_KEY, R2_ENDPOINT_URL, R2_BUCKET_NAME,
        AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, S3_BUCKET_NAME,
    )
    if STORAGE_PROVIDER == "r2":
        return {
            "provider": "r2",
            "endpoint_url": R2_ENDPOINT_URL,
            "access_key_id": R2_ACCESS_KEY_ID,
            "secret_key": R2_SECRET_KEY,
            "bucket": R2_BUCKET_NAME,
        }
    elif STORAGE_PROVIDER == "s3":
        return {
            "provider": "s3",
            "access_key_id": AWS_ACCESS_KEY_ID,
            "secret_access_key": AWS_SECRET_ACCESS_KEY,
            "region": AWS_REGION,
            "bucket": S3_BUCKET_NAME,
        }
    else:
        raise ValueError(f"Unknown STORAGE_PROVIDER: {STORAGE_PROVIDER}")


def _transcribe_local(audio_path: Path) -> dict:
    """Run Whisper locally (CPU). Used when Modal is not configured."""
    import whisper

    logger.warning(
        "Running Whisper on CPU. For videos > 10 min, this will be slow. "
        "Set MODAL_TOKEN_ID to use GPU on Modal."
    )
    model = whisper.load_model(WHISPER_MODEL)
    result = model.transcribe(
        str(audio_path),
        language=WHISPER_LANGUAGE,
        word_timestamps=False,
        verbose=True,
    )
    segments = []
    for i, seg in enumerate(result["segments"]):
        segments.append({
            "id": i,
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text"].strip(),
            "confidence": min(1.0, max(0.0, (seg.get("avg_logprob", -0.5) + 1.0))),
        })
    return {
        "segments": segments,
        "full_text": result["text"].strip(),
        "language": result.get("language", WHISPER_LANGUAGE),
        "model": WHISPER_MODEL,
    }


def _cleanup(tmp_dir: Path) -> None:
    """Remove large temp files after upload to save local disk space."""
    for f in tmp_dir.glob("*.wav"):
        try:
            f.unlink()
            logger.debug(f"Cleaned up: {f}")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Self-registration with orchestrator (lazy import pattern)
# ---------------------------------------------------------------------------

def register(orchestrator) -> None:
    """
    Register Phase 1 runner with the orchestrator.
    Call this before running the pipeline:

        from pipeline.phases.phase1_ingest import register
        register(orchestrator)
    """
    orchestrator.register_phase(1, run_phase_1)
    logger.info("Phase 1 (Ingestion & Transcription) registered.")

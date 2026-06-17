"""
Configuration and environment variables for PhyMaC Pipeline.
All config is loaded here — never import os.environ directly elsewhere.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

STORAGE_PROVIDER = os.environ.get("STORAGE_PROVIDER", "r2")  # "r2" | "s3"

# Cloudflare R2
R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_KEY = os.environ.get("R2_SECRET_KEY", "")
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "phymac-pipeline")
R2_ENDPOINT_URL = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

# AWS S3 (fallback)
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME", "phymac-pipeline")

# ---------------------------------------------------------------------------
# AI APIs
# ---------------------------------------------------------------------------

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")

# ---------------------------------------------------------------------------
# Whisper
# ---------------------------------------------------------------------------

WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "large-v3")
WHISPER_LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "es")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cuda")  # "cuda" | "cpu"

# ---------------------------------------------------------------------------
# LLM (OpenRouter)
# ---------------------------------------------------------------------------
# All LLM calls go through OpenRouter (https://openrouter.ai), accessed via
# the OpenAI Python SDK with a custom base_url. One API key, many providers.

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# Models per use case — overridable via env. Defaults are the production-grade
# Claude Sonnet 4.6 (strong, balanced). Override per-use-case via env if needed
# (e.g. a cheaper validator). Free models (openai/gpt-oss-120b:free) remain
# available by setting the env var during low-cost testing.
LLM_MODEL_PLANNER = os.environ.get("LLM_MODEL_PLANNER", "anthropic/claude-sonnet-4-6")
LLM_MODEL_VALIDATOR = os.environ.get("LLM_MODEL_VALIDATOR", "anthropic/claude-sonnet-4-6")
LLM_MODEL_VISION = os.environ.get("LLM_MODEL_VISION", "anthropic/claude-sonnet-4-6")
LLM_MODEL_VISION_PLANNER = os.getenv(
    "LLM_MODEL_VISION_PLANNER",
    "anthropic/claude-sonnet-4-6",
)

# Optional metadata for OpenRouter analytics dashboard
OPENROUTER_APP_NAME = os.environ.get("OPENROUTER_APP_NAME", "phymac-pipeline")
OPENROUTER_SITE_URL = os.environ.get("OPENROUTER_SITE_URL", "")

# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

MAX_PHASE_RETRIES = int(os.environ.get("MAX_PHASE_RETRIES", "5"))
DEFAULT_BRAND_ID = os.environ.get("DEFAULT_BRAND_ID", "phymac")
DEFAULT_FORMAT_ID = os.environ.get("DEFAULT_FORMAT_ID", "podcast_hablando_con_profes")

# Validation score threshold (below this = failed)
VALIDATION_PASS_SCORE = float(os.environ.get("VALIDATION_PASS_SCORE", "0.6"))

# ---------------------------------------------------------------------------
# Local temp directory
# ---------------------------------------------------------------------------

TMP_DIR = Path(os.environ.get("PHYMAC_TMP_DIR", "/tmp/phymac"))


def get_project_tmp_dir(project_id: str, phase: int) -> Path:
    d = TMP_DIR / project_id / f"phase{phase}"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Render defaults
# ---------------------------------------------------------------------------

RENDER_RESOLUTION = "1920x1080"
RENDER_FPS = 30
RENDER_VIDEO_CODEC = "libx264"
RENDER_CRF = 18
RENDER_PRESET = "slow"
RENDER_AUDIO_CODEC = "aac"
RENDER_AUDIO_BITRATE = "192k"

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def require_env(key: str) -> str:
    """Raise immediately if a required env var is missing."""
    value = os.environ.get(key, "")
    if not value:
        raise OSError(
            f"Required environment variable '{key}' is not set. "
            f"Add it to your .env file or export it before running."
        )
    return value

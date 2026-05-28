"""Modal app for Phase 3 rendering."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import modal

HF_PROJECT_LOCAL = Path(__file__).parent / "renderers" / "hf-project"

hf_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install(
        "ffmpeg",
        "chromium",
        "fonts-liberation",
        "libcairo2",
        "libpango-1.0-0",
        "libpangocairo-1.0-0",
        "curl",
        "ca-certificates",
    )
    .run_commands(
        "curl -fsSL https://deb.nodesource.com/setup_22.x | bash -",
        "apt-get install -y nodejs",
    )
    .pip_install("boto3>=1.34.0", "python-dotenv>=1.0.0")
    .add_local_dir(
        local_path=str(HF_PROJECT_LOCAL),
        remote_path="/app/hf-project",
        copy=True,
    )
    .run_commands(
        "cd /app/hf-project && npm install --omit=dev --no-audit --no-fund",
    )
    .add_local_python_source("pipeline")
)

app = modal.App("phymac-phase3-render")


@app.function(
    image=hf_image,
    secrets=[
        modal.Secret.from_name("phymac-r2-creds"),
    ],
    timeout=600,
    cpu=2.0,
    memory=4096,
    retries=modal.Retries(max_retries=1, backoff_coefficient=2.0),
)
def render_material(payload: dict[str, Any]) -> dict[str, Any]:
    """Modal entry point: renders one material end-to-end."""
    from pipeline.modal_render import render_one

    return render_one(
        payload,
        hf_project_dir=Path("/app/hf-project"),
        tmp_dir=Path("/tmp/phymac-phase3"),
    )

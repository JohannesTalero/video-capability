"""Worker-side render logic. Runs inside Modal function (or locally for tests)."""

from __future__ import annotations

import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Any

from pipeline.models import PlannedMaterial
from pipeline.phase3_r2 import upload_webm
from pipeline.renderers.brand_css import render_brand_css
from pipeline.renderers.dispatch import DispatchError, build_render_input
from pipeline.renderers.output_validator import (
    OutputValidationError,
    validate_webm,
)

logger = logging.getLogger(__name__)

DURATION_BY_TIPO: dict[str, float] = {
    "lower_third": 6.0,
    "pull_quote": 6.6,
    "chapter_marker": 4.2,
    "animacion_texto": 2.2,
    "ecuacion_latex": 5.0,
    "diagrama": 6.0,
    "transcript_fix": 0.0,
}


def write_brand_assets(hf_project_dir: Path, brand: dict[str, Any]) -> None:
    """Write brand.css inside the HF project. brand-assets symlink optional."""
    (hf_project_dir / "brand.css").write_text(render_brand_css(brand), encoding="utf-8")


def _invoke_hf_render(
    hf_project_dir: Path,
    composition_path: str,
    variables: dict[str, Any],
    mov_out: Path,
) -> None:
    cmd = [
        "npx",
        "hyperframes",
        "render",
        str(hf_project_dir),
        "--composition",
        composition_path,
        "--output",
        str(mov_out),
        "--format",
        "mov",
        "--fps",
        "30",
        "--variables",
        json.dumps(variables, ensure_ascii=False),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not mov_out.exists() or mov_out.stat().st_size < 1024:
        raise RuntimeError(
            f"hyperframes render failed: rc={result.returncode}, "
            f"stderr={result.stderr.strip()[-300:]}"
        )


def _transcode_to_webm(mov_in: Path, webm_out: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(mov_in),
        "-c:v",
        "libvpx-vp9",
        "-pix_fmt",
        "yuva420p",
        "-auto-alt-ref",
        "0",
        "-b:v",
        "0",
        "-crf",
        "22",
        "-row-mt",
        "1",
        "-an",
        str(webm_out),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not webm_out.exists() or webm_out.stat().st_size < 1024:
        raise RuntimeError(
            f"ffmpeg transcode failed: rc={result.returncode}, "
            f"stderr={result.stderr.strip()[-300:]}"
        )


def _render_text_card_fallback(
    hf_project_dir: Path,
    planned: PlannedMaterial,
    mov_out: Path,
) -> None:
    spec = planned.spec_refined or planned.original_spec
    variables = {
        "text": spec.contenido,
        "position": planned.position if isinstance(planned.position, str) else "center",
    }
    _invoke_hf_render(
        hf_project_dir,
        "compositions/text_card_fallback.html",
        variables,
        mov_out,
    )


def render_one(
    payload: dict[str, Any],
    hf_project_dir: Path,
    tmp_dir: Path,
) -> dict[str, Any]:
    """Process one PlannedMaterial. Returns ManifestEntry-shaped dict."""
    planned = PlannedMaterial.from_dict(payload["planned"])
    project_id = payload["project_id"]
    material_id = payload["material_id"]
    brand = payload["brand"]
    tmp_dir.mkdir(parents=True, exist_ok=True)
    base_entry: dict[str, Any] = {
        "material_id": material_id,
        "block_id": planned.block_id,
        "original_spec": planned.original_spec.to_dict(),
        "refined_spec": planned.spec_refined.to_dict() if planned.spec_refined else None,
        "decision": planned.decision,
        "position": planned.position,
        "reframe": planned.reframe,
        "reasoning": planned.reasoning,
    }

    if planned.decision == "drop":
        return {
            **base_entry,
            "render_status": "dropped",
            "r2_key": None,
            "render_seconds": 0.0,
        }

    # Setup
    write_brand_assets(hf_project_dir, brand)
    mov_out = tmp_dir / f"{material_id}.mov"
    webm_out = tmp_dir / f"{material_id}.webm"
    spec = planned.spec_refined or planned.original_spec
    expected_duration = DURATION_BY_TIPO.get(spec.tipo, 5.0)
    t0 = time.time()
    status = "ok"
    error: str | None = None
    try:
        composition, variables = build_render_input(planned)
        _invoke_hf_render(hf_project_dir, composition, variables, mov_out)
        _transcode_to_webm(mov_out, webm_out)
        validate_webm(webm_out, expected_duration=expected_duration)
    except (RuntimeError, OutputValidationError, DispatchError) as e:
        logger.warning("render failed for %s: %s. Falling back to text card.", material_id, e)
        error = f"{type(e).__name__}: {e}"
        try:
            if mov_out.exists():
                mov_out.unlink()
            if webm_out.exists():
                webm_out.unlink()
            _render_text_card_fallback(hf_project_dir, planned, mov_out)
            _transcode_to_webm(mov_out, webm_out)
            validate_webm(webm_out, expected_duration=5.0)
            status = "fallback"
        except (RuntimeError, OutputValidationError) as fe:
            elapsed = time.time() - t0
            return {
                **base_entry,
                "render_status": "fallback",
                "r2_key": None,
                "render_seconds": round(elapsed, 2),
                "error": f"both render + fallback failed: original={error}; fallback={fe}",
            }

    r2_key = upload_webm(project_id, material_id, webm_out)
    elapsed = time.time() - t0
    # Cleanup local
    for p in (mov_out, webm_out):
        if p.exists():
            p.unlink()
    return {
        **base_entry,
        "render_status": status,
        "r2_key": r2_key,
        "render_seconds": round(elapsed, 2),
        "error": error,
    }

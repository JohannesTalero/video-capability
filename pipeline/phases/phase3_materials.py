"""Phase 3 orchestrator: visual planning + render + manifest."""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

from pipeline.formats import load_format
from pipeline.modal_app import app as modal_app
from pipeline.modal_app import render_material
from pipeline.models import NarrativePlan, PlannedMaterial, ProjectState, StorageKey
from pipeline.phase3_helpers import flatten_plan_to_materials
from pipeline.phase3_r2 import (
    download_video_to_local,
    head_object_exists,
    load_manifest,
    load_visual_plan,
    material_webm_key,
    upload_frame,
    upload_manifest,
    upload_visual_plan,
)
from pipeline.renderers.dispatch import load_diagram_registry
from pipeline.storage import StorageAdapter
from pipeline.validator import validate_phase3
from pipeline.vision.frame_extractor import extract_frames
from pipeline.vision.visual_planner import plan_material_visual

logger = logging.getLogger(__name__)


def _visual_plan_to_dict(planned: PlannedMaterial) -> dict[str, Any]:
    return planned.to_dict()


def _visual_plan_from_dict(d: dict[str, Any]) -> PlannedMaterial:
    return PlannedMaterial.from_dict(d)


def _ensure_video_local(project_id: str, tmp_dir: Path) -> Path:
    target = tmp_dir / "video.mp4"
    if not target.exists():
        download_video_to_local(project_id, target)
    return target


def _phase3a_for_material(
    project_id: str,
    material_id: str,
    block_id: str,
    spec: Any,
    video_local: Path,
    transcript_window: str,
    block_name: str,
    brand: dict[str, Any],
    visual_specs_summary: dict[str, Any],
    template_registry: list[dict[str, Any]],
    tmp_dir: Path,
) -> PlannedMaterial:
    t = float(spec.timestamp_relativo)
    timestamps = [max(0.0, t - 1.0), t, t + 1.0]
    frames_dir = tmp_dir / "frames"
    frames = extract_frames(video_local, timestamps, frames_dir, prefix=material_id)
    # Upload frames to R2 (audit + cache)
    for i, fp in enumerate(frames):
        suffix = ["tm1", "t0", "tp1"][i]
        upload_frame(project_id, material_id, suffix, fp)
    planned = plan_material_visual(
        material_id=material_id,
        block_id=block_id,
        original_spec=spec,
        frames_paths=frames,
        phase2_context={
            "block_id": block_id,
            "block_name": block_name,
            "material_spec": spec.to_dict(),
            "transcript_window": transcript_window,
        },
        brand=brand,
        visual_specs_summary=visual_specs_summary,
        diagram_template_registry=template_registry if spec.tipo == "diagrama" else [],
    )
    return planned


def run_phase3(
    plan: NarrativePlan,
    brand: dict[str, Any],
    visual_specs_summary: dict[str, Any],
) -> dict[str, Any]:
    """Run Phase 3 end-to-end for a project. Returns {"manifest": [...]}."""
    project_id = plan.project_id
    existing_manifest = load_manifest(project_id) or []
    existing_planned = load_visual_plan(project_id) or []
    materials = flatten_plan_to_materials(plan)

    # Defensive: Phase 2 may omit chapter_number; inject 1-indexed by appearance order.
    chapter_counter = 0
    for _, _, spec in materials:
        if spec.tipo == "chapter_marker":
            chapter_counter += 1
            if "chapter_number" not in spec.metadata:
                spec.metadata = {**spec.metadata, "chapter_number": chapter_counter}

    # template_registry does not depend on format — caller resolves format externally
    template_registry = load_diagram_registry().get("templates", [])

    with tempfile.TemporaryDirectory(prefix="phase3-") as td:
        tmp_dir = Path(td)
        video_local = _ensure_video_local(project_id, tmp_dir)

        # ---- Phase 3a: visual planning (sequential; LLM-vision per material) ----
        planned_by_id: dict[str, PlannedMaterial] = {}
        existing_planned_by_id = {p["material_id"]: p for p in existing_planned}
        for mid, block_id, spec in materials:
            cached = existing_planned_by_id.get(mid)
            if cached is not None:
                planned_by_id[mid] = _visual_plan_from_dict(cached)
                continue
            block = next(b for b in plan.blocks if b.id == block_id)
            transcript_window = ""  # populated from transcription if available
            planned_by_id[mid] = _phase3a_for_material(
                project_id=project_id,
                material_id=mid,
                block_id=block_id,
                spec=spec,
                video_local=video_local,
                transcript_window=transcript_window,
                block_name=block.name,
                brand=brand,
                visual_specs_summary=visual_specs_summary,
                template_registry=template_registry,
                tmp_dir=tmp_dir,
            )
        upload_visual_plan(
            project_id,
            [_visual_plan_to_dict(p) for p in planned_by_id.values()],
        )

        # ---- Phase 3b: render via Modal.map() ----
        existing_by_id = {e["material_id"]: e for e in existing_manifest}
        to_render: list[dict[str, Any]] = []
        cached_entries: list[dict[str, Any]] = []
        for mid, _, _ in materials:
            planned = planned_by_id[mid]
            cached = existing_by_id.get(mid)
            if (
                cached is not None
                and cached.get("render_status") == "ok"
                and cached.get("r2_key")
                and head_object_exists(material_webm_key(project_id, mid))
            ):
                cached_entries.append(cached)
                continue
            to_render.append(
                {
                    "planned": planned.to_dict(),
                    "project_id": project_id,
                    "material_id": mid,
                    "brand": brand,
                }
            )

        new_entries: list[dict[str, Any]] = []
        if to_render:
            with modal_app.run():
                new_entries = list(render_material.map(to_render))

        # ---- Phase 3c: merge + upload manifest ----
        manifest = cached_entries + new_entries
        # preserve order of materials
        order = {mid: i for i, (mid, _, _) in enumerate(materials)}
        manifest.sort(key=lambda e: order.get(e["material_id"], 1_000_000))
        upload_manifest(project_id, manifest)

    return {"manifest": manifest}


# ---------------------------------------------------------------------------
# Visual specs summary (hard-coded for Phase 3; sourced from format in future)
# ---------------------------------------------------------------------------

_VISUAL_SPECS_SUMMARY: dict[str, Any] = {
    "lower_third": {
        "description": "Franja semitransparente en la parte inferior con nombre y cargo del speaker.",
        "default_position": "bottom-left",
        "duration_seconds": 6.0,
    },
    "pull_quote": {
        "description": "Frase destacada del speaker, centrada sobre fondo con overlay de marca.",
        "default_position": "center",
        "duration_seconds": 6.6,
    },
    "chapter_marker": {
        "description": "Título de capítulo en pantalla completa, transición breve al inicio del bloque.",
        "default_position": "center",
        "duration_seconds": 4.2,
    },
    "animacion_texto": {
        "description": "Texto animado de una a tres palabras clave, entrada de izquierda.",
        "default_position": "top-right",
        "duration_seconds": 2.2,
    },
    "ecuacion_latex": {
        "description": "Ecuación matemática renderizada con KaTeX sobre fondo claro.",
        "default_position": "center",
        "duration_seconds": 5.0,
    },
    "diagrama": {
        "description": "Diagrama visual (barras, ciclo o esquema libre) generado desde datos estructurados.",
        "default_position": "center",
        "duration_seconds": 6.0,
    },
}


# ---------------------------------------------------------------------------
# Orchestrator-compatible runner
# ---------------------------------------------------------------------------


def run_phase_3(state: ProjectState) -> dict:
    """
    Phase 3 runner. Registered with PipelineOrchestrator.

    Loads the Phase 2 plan and brand pack from storage, then delegates to
    run_phase3() for visual planning + render + manifest assembly. The
    resulting manifest is validated with validate_phase3() before returning.

    Returns:
        dict with scalar keys consumed by the orchestrator:
          - manifest_count       (int)
          - manifest_storage_key (str)
    """
    project_id = state.project.project_id
    storage = StorageAdapter()

    # 1. Load Phase 2 plan.
    plan_key = StorageKey.narrative_plan(project_id)
    logger.info(f"[Phase 3] Loading narrative plan: {plan_key}")
    plan = NarrativePlan.from_json(storage.download_json(plan_key))

    # 2. Load brand pack.
    # TODO: resolve brand_id from format.json once that field is added.
    brand_id = state.project.brand_id
    brand_key = f"brands/{brand_id}/brand.json"
    logger.info(f"[Phase 3] Loading brand pack: {brand_key}")
    brand: dict[str, Any] = json.loads(storage.download_json(brand_key))

    # 3. Load format config for whitelist validation.
    format_id = state.project.format_id
    logger.info(f"[Phase 3] Loading format config: {format_id}")
    fmt = load_format(format_id)

    # 4. Run Phase 3 (visual planning → render → manifest).
    logger.info(f"[Phase 3] Starting pipeline for project {project_id}...")
    result = run_phase3(plan, brand, _VISUAL_SPECS_SUMMARY)
    manifest: list[dict] = result["manifest"]

    # 5. Validate manifest.
    logger.info(f"[Phase 3] Validating manifest ({len(manifest)} entries)...")
    validation = validate_phase3(manifest, whitelist=list(fmt.materials_whitelist))
    if validation.critical_failures:
        raise ValueError(
            f"Phase 3 manifest failed validation — {len(validation.critical_failures)} "
            f"critical failure(s): {'; '.join(validation.critical_failures[:3])}"
        )

    manifest_key = StorageKey.materials_manifest(project_id)
    logger.info(f"[Phase 3] Complete: {len(manifest)} materials, manifest at {manifest_key}")

    return {
        "manifest_count": len(manifest),
        "manifest_storage_key": manifest_key,
    }


# ---------------------------------------------------------------------------
# Orchestrator registration
# ---------------------------------------------------------------------------


def register(orchestrator) -> None:
    """Register the Phase 3 runner with the orchestrator."""
    orchestrator.register_phase(3, run_phase_3)
    logger.info("Phase 3 (Materials) registered.")

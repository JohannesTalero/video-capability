"""Phase 3 orchestrator: visual planning + render + manifest."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from pipeline.modal_app import app as modal_app
from pipeline.modal_app import render_material
from pipeline.models import NarrativePlan, PlannedMaterial
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

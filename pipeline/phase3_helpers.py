"""Phase 3 helpers — material ID computation and plan flattening.

Pure functions; no I/O. Used by phase3_materials orchestrator.
"""

from __future__ import annotations

import hashlib
import json

from pipeline.models import MaterialSpec, NarrativePlan


def compute_material_id(block_id: str, idx_in_block: int, spec: MaterialSpec) -> str:
    """Stable, content-aware ID. Format: <block_id>_m<idx02d>_<8hex>.

    Cache key contract:
    - block_id changes → new ID
    - idx within block changes → new ID
    - any field of spec (tipo, contenido, metadata) changes → new ID via hash
    - metadata key order does NOT affect ID (sort_keys=True)
    """
    payload = json.dumps(
        [spec.tipo, spec.contenido, spec.metadata, spec.timestamp_relativo],
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    content_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]
    return f"{block_id}_m{idx_in_block:02d}_{content_hash}"


def flatten_plan_to_materials(
    plan: NarrativePlan,
) -> list[tuple[str, str, MaterialSpec]]:
    """Flatten plan to [(material_id, block_id, spec), ...] preserving order.

    Indexes within each block start at 0.
    """
    out: list[tuple[str, str, MaterialSpec]] = []
    for block in plan.blocks:
        for idx, spec in enumerate(block.support_material):
            mid = compute_material_id(block.id, idx, spec)
            out.append((mid, block.id, spec))
    return out

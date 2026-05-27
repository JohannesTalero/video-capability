"""R2 helpers for Phase 3 — keys, upload/download, HEAD checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.storage import StorageAdapter

# ---------------------------------------------------------------------------
# Singleton lazy adapter
# ---------------------------------------------------------------------------

_adapter: StorageAdapter | None = None


def _get_adapter() -> StorageAdapter:
    global _adapter
    if _adapter is None:
        _adapter = StorageAdapter()
    return _adapter


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------


def visual_plan_key(project_id: str) -> str:
    return f"projects/{project_id}/phase3/visual_plan.json"


def materials_manifest_key(project_id: str) -> str:
    return f"projects/{project_id}/phase3/materials_manifest.json"


def material_webm_key(project_id: str, material_id: str) -> str:
    return f"projects/{project_id}/phase3/materials/{material_id}.webm"


def frame_key(project_id: str, material_id: str, suffix: str) -> str:
    return f"projects/{project_id}/phase3/frames/{material_id}_{suffix}.png"


def video_raw_key(project_id: str) -> str:
    return f"projects/{project_id}/phase1/video.mp4"


# ---------------------------------------------------------------------------
# HEAD check
# ---------------------------------------------------------------------------


def head_object_exists(key: str) -> bool:
    return _get_adapter().exists(key)


# ---------------------------------------------------------------------------
# Upload helpers
# ---------------------------------------------------------------------------


def upload_manifest(project_id: str, manifest: list[dict[str, Any]]) -> str:
    key = materials_manifest_key(project_id)
    body = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    _get_adapter().upload_bytes(body, key, content_type="application/json")
    return key


def upload_visual_plan(project_id: str, planned: list[dict[str, Any]]) -> str:
    key = visual_plan_key(project_id)
    body = json.dumps(planned, ensure_ascii=False, indent=2).encode("utf-8")
    _get_adapter().upload_bytes(body, key, content_type="application/json")
    return key


def upload_webm(project_id: str, material_id: str, local_path: Path) -> str:
    key = material_webm_key(project_id, material_id)
    _get_adapter().upload(str(local_path), key)
    return key


def upload_frame(project_id: str, material_id: str, suffix: str, local_path: Path) -> str:
    key = frame_key(project_id, material_id, suffix)
    _get_adapter().upload(str(local_path), key)
    return key


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------


def load_manifest(project_id: str) -> list[dict[str, Any]] | None:
    key = materials_manifest_key(project_id)
    if not _get_adapter().exists(key):
        return None
    data = _get_adapter().download_bytes(key)
    return json.loads(data.decode("utf-8"))


def load_visual_plan(project_id: str) -> list[dict[str, Any]] | None:
    key = visual_plan_key(project_id)
    if not _get_adapter().exists(key):
        return None
    data = _get_adapter().download_bytes(key)
    return json.loads(data.decode("utf-8"))


def download_video_to_local(project_id: str, target: Path) -> None:
    key = video_raw_key(project_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    _get_adapter().download(key, target)


def download_to_local(key: str, target: Path) -> None:
    """Download arbitrary R2 key to local path."""
    target.parent.mkdir(parents=True, exist_ok=True)
    _get_adapter().download(key, target)

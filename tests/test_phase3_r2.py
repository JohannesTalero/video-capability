"""Tests for phase3_r2 helpers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from pipeline.phase3_r2 import (
    download_video_to_local,
    head_object_exists,
    materials_manifest_key,
    upload_manifest,
    visual_plan_key,
)


def test_visual_plan_key():
    assert visual_plan_key("p1") == "projects/p1/phase3/visual_plan.json"


def test_materials_manifest_key():
    assert materials_manifest_key("p1") == "projects/p1/phase3/materials_manifest.json"


@patch("pipeline.phase3_r2._get_adapter")
def test_head_object_exists_true(mock_get_adapter):
    mock_adapter = MagicMock()
    mock_adapter.exists.return_value = True
    mock_get_adapter.return_value = mock_adapter
    assert head_object_exists("some/key") is True
    mock_adapter.exists.assert_called_once_with("some/key")


@patch("pipeline.phase3_r2._get_adapter")
def test_head_object_exists_false(mock_get_adapter):
    mock_adapter = MagicMock()
    mock_adapter.exists.return_value = False
    mock_get_adapter.return_value = mock_adapter
    assert head_object_exists("missing/key") is False
    mock_adapter.exists.assert_called_once_with("missing/key")


@patch("pipeline.phase3_r2._get_adapter")
def test_upload_manifest_serializes(mock_get_adapter):
    mock_adapter = MagicMock()
    mock_get_adapter.return_value = mock_adapter
    manifest = [{"material_id": "x", "render_status": "ok"}]
    upload_manifest("p1", manifest)
    mock_adapter.upload_bytes.assert_called_once()
    args, kwargs = mock_adapter.upload_bytes.call_args
    # upload_bytes(body, key, content_type=...)
    body = args[0] if args else kwargs.get("data")
    key = args[1] if len(args) > 1 else kwargs.get("remote_key")
    assert key == "projects/p1/phase3/materials_manifest.json"
    parsed = json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
    assert parsed[0]["material_id"] == "x"


@patch("pipeline.phase3_r2._get_adapter")
def test_download_video_to_local(mock_get_adapter, tmp_path: Path):
    mock_adapter = MagicMock()
    mock_get_adapter.return_value = mock_adapter
    target = tmp_path / "v.mp4"
    download_video_to_local("p1", target)
    mock_adapter.download.assert_called_once_with("projects/p1/phase1/video.mp4", target)

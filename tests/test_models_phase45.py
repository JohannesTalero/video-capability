"""Tests para modelos compartidos de Fases 4-6 (contrato Units 5-8)."""

import json
from pathlib import Path

from pipeline.models import BrandConfig

BRAND_JSON = Path(__file__).parent.parent / "brands" / "phymac" / "brand.json"


def test_brand_config_loads_real_brand_json():
    data = json.loads(BRAND_JSON.read_text(encoding="utf-8"))
    cfg = BrandConfig.from_dict(data)
    assert cfg.id == "phymac"
    assert cfg.name == "PhyMaC"
    assert cfg.colors["primary"] == "#2962FF"
    assert cfg.fonts["display"]["family"] == "Montserrat"
    assert cfg.assets["logo"] == "brand-assets/logo.svg"
    assert cfg.pattern["type"] == "cross-grid"


def test_brand_config_roundtrip():
    data = json.loads(BRAND_JSON.read_text(encoding="utf-8"))
    cfg = BrandConfig.from_dict(data)
    assert cfg.to_dict() == data


def test_phase5_audio_result_roundtrip():
    from pipeline.models import Phase5AudioResult

    r = Phase5AudioResult(
        project_id="p1",
        storage_key="projects/p1/phase5/audio_processed.mp4",
        loudness_in_lufs=-23.5,
        loudness_out_lufs=-14.1,
        true_peak_dbtp=-1.4,
        noise_reduction_applied=True,
        duration_seconds=712.3,
        process_time_seconds=95.0,
    )
    d = r.to_dict()
    assert d["loudness_out_lufs"] == -14.1
    assert Phase5AudioResult.from_dict(d) == r


def test_storage_keys_phase4():
    from pipeline.models import StorageKey

    assert StorageKey.phase4_timeline("p1") == "projects/p1/phase4/timeline.json"
    assert StorageKey.brand_render("p1", "intro") == "projects/p1/phase4/brand/intro.mp4"

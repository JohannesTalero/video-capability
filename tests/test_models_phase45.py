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

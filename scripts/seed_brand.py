#!/usr/bin/env python3
"""
CLI — Seed a brand pack (brand.json + assets) into storage (R2/S3).

Phase 3 loads the brand pack from `brands/<brand_id>/brand.json` in storage and
may reference its assets; this uploads the local `brands/<brand_id>/` tree so
those keys exist. Run once per brand (idempotent — re-uploads overwrite).

Usage:
    uv run python scripts/seed_brand.py                 # seeds "phymac"
    uv run python scripts/seed_brand.py --brand-id phymac
"""

import argparse
import logging
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("phymac.cli.seed_brand")

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.storage import StorageAdapter  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a brand pack into storage")
    parser.add_argument("--brand-id", default="phymac", help="Brand id (default: phymac)")
    args = parser.parse_args()

    brand_dir = REPO_ROOT / "brands" / args.brand_id
    if not (brand_dir / "brand.json").exists():
        logger.error(f"brand.json not found for '{args.brand_id}': {brand_dir / 'brand.json'}")
        sys.exit(1)

    storage = StorageAdapter()
    files = [p for p in brand_dir.rglob("*") if p.is_file()]
    for path in files:
        rel = path.relative_to(brand_dir).as_posix()
        key = f"brands/{args.brand_id}/{rel}"
        storage.upload(str(path), key)
        logger.info(f"uploaded {key} ({'ok' if storage.exists(key) else 'MISSING'})")

    print(f"\n✅ Seeded {len(files)} files for brand '{args.brand_id}'")


if __name__ == "__main__":
    main()

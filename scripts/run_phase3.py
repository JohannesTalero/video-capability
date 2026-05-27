#!/usr/bin/env python3
"""
CLI — Run Phase 3 (Materials: Visual Planning + Render + Manifest) standalone.

Phase 2 (Narrative Plan) must already be COMPLETED for the given project_id.

Usage:
    python scripts/run_phase3.py --project-id cudris-20260526
    python scripts/run_phase3.py --project-id cudris-20260526 --skip-validation

Environment variables required (.env file):
    STORAGE_PROVIDER=r2
    R2_ACCOUNT_ID=...
    R2_ACCESS_KEY_ID=...
    R2_SECRET_KEY=...
    R2_BUCKET_NAME=phymac-pipeline
    OPENROUTER_API_KEY=...
    MODAL_TOKEN_ID=...
    MODAL_TOKEN_SECRET=...
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("phymac.cli.phase3")

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.orchestrator import PipelineOrchestrator
from pipeline.phases.phase3_materials import register as register_phase3
from pipeline.storage import StorageAdapter


def main():
    parser = argparse.ArgumentParser(
        description="PhyMaC Pipeline — Phase 3: Materials (Visual Planning + Render + Manifest)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run Phase 3 on a project that already completed Phase 2:
  python scripts/run_phase3.py --project-id cudris-20260526

  # Skip validation (manual override):
  python scripts/run_phase3.py --project-id cudris-20260526 --skip-validation
        """,
    )
    parser.add_argument(
        "--project-id", type=str, required=True, help="Project ID that has Phase 2 completed"
    )
    parser.add_argument(
        "--skip-validation", action="store_true", help="Skip ValidationAgent checks"
    )
    args = parser.parse_args()

    logger.info("Initializing storage adapter...")
    storage = StorageAdapter()
    orchestrator = PipelineOrchestrator(storage)
    register_phase3(orchestrator)

    project_id = args.project_id
    state = orchestrator.load_checkpoint(project_id)
    print(f"\n▶ Resuming project: {project_id}")
    print(f"   Title:     {state.project.title}")
    print(f"   Brand:     {state.project.brand_id}")
    print(f"   Format:    {state.project.format_id}")

    logger.info("Starting Phase 3: Materials (Visual Planning + Render + Manifest)...")
    state = orchestrator.run(
        project_id=project_id,
        start_from_phase=3,
        end_at_phase=3,
        skip_validation=args.skip_validation,
    )

    phase3 = state.phases.get(3)
    if phase3 and phase3.status.value == "completed":
        validation = phase3.validation
        print("\n" + "═" * 60)
        print("✅ Phase 3 Complete!")
        print("═" * 60)
        print(f"  Manifest key:    {phase3.outputs.get('manifest_storage_key', 'N/A')}")
        print(f"  Materials:       {phase3.outputs.get('manifest_count', 'N/A')}")
        if validation:
            print(f"  Validation score: {validation.score:.2f}")
            if validation.warnings:
                print("\n  ⚠ Warnings:")
                for w in validation.warnings:
                    print(f"    • {w}")
        print("\n  Next step:")
        print(f"  python scripts/run_phase4.py --project-id {project_id}")
    else:
        print("\n❌ Phase 3 FAILED. Check logs above for details.")
        if phase3:
            print(f"  Error: {phase3.error_message}")
            print("\n  To retry:")
            print(f"  python scripts/run_phase3.py --project-id {project_id}")
        sys.exit(1)


if __name__ == "__main__":
    main()

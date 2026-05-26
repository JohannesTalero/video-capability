#!/usr/bin/env python3
"""
CLI — Run Phase 2 (Narrative Plan & Cuts) standalone.

Phase 1 (transcription) must already be COMPLETED for the given project_id.

Usage:
    python scripts/run_phase2.py --project-id cudris-20260526
    python scripts/run_phase2.py --project-id cudris-20260526 --skip-validation

Environment variables required (.env file):
    STORAGE_PROVIDER=r2
    R2_ACCOUNT_ID=...
    R2_ACCESS_KEY_ID=...
    R2_SECRET_KEY=...
    R2_BUCKET_NAME=phymac-pipeline
    OPENROUTER_API_KEY=...
    LLM_MODEL_PLANNER=...      (optional — defaults to free Gemini Flash)
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
logger = logging.getLogger("phymac.cli.phase2")

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.orchestrator import PipelineOrchestrator
from pipeline.storage import StorageAdapter
from pipeline.phases.phase2_narrative import register as register_phase2


def main():
    parser = argparse.ArgumentParser(
        description="PhyMaC Pipeline — Phase 2: Narrative Plan & Cuts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run Phase 2 on a project that already completed Phase 1:
  python scripts/run_phase2.py --project-id cudris-20260526

  # Skip validation (manual override):
  python scripts/run_phase2.py --project-id cudris-20260526 --skip-validation
        """,
    )
    parser.add_argument("--project-id", type=str, required=True,
                        help="Project ID that has Phase 1 completed")
    parser.add_argument("--skip-validation", action="store_true",
                        help="Skip ValidationAgent checks")
    args = parser.parse_args()

    logger.info("Initializing storage adapter...")
    storage = StorageAdapter()
    orchestrator = PipelineOrchestrator(storage)
    register_phase2(orchestrator)

    project_id = args.project_id
    state = orchestrator.load_checkpoint(project_id)
    print(f"\n▶ Resuming project: {project_id}")
    print(f"   Title:     {state.project.title}")
    print(f"   Brand:     {state.project.brand_id}")
    print(f"   Format:    {state.project.format_id}")

    logger.info("Starting Phase 2: Narrative Plan & Cuts...")
    state = orchestrator.run(
        project_id=project_id,
        start_from_phase=2,
        end_at_phase=2,
        skip_validation=args.skip_validation,
    )

    phase2 = state.phases.get(2)
    if phase2 and phase2.status.value == "completed":
        validation = phase2.validation
        print("\n" + "═" * 60)
        print("✅ Phase 2 Complete!")
        print("═" * 60)
        print(f"  Plan key:         {phase2.outputs.get('plan_key', 'N/A')}")
        print(f"  Blocks:           {phase2.outputs.get('block_count', 'N/A')}")
        print(f"  Segments used:    {phase2.outputs.get('total_segments_used', 'N/A')}")
        print(f"  Format:           {phase2.outputs.get('format_id', 'N/A')}")
        if validation:
            print(f"  Validation score: {validation.score:.2f}")
            if validation.warnings:
                print("\n  ⚠ Warnings:")
                for w in validation.warnings:
                    print(f"    • {w}")
        print("\n  Next step:")
        print(f"  python scripts/run_phase3.py --project-id {project_id}")
    else:
        print("\n❌ Phase 2 FAILED. Check logs above for details.")
        if phase2:
            print(f"  Error: {phase2.error_message}")
            print(f"\n  To retry:")
            print(f"  python scripts/run_phase2.py --project-id {project_id}")
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
CLI — Resume a paused pipeline from any phase.

Usage:
    python scripts/resume_pipeline.py --project-id ondas-ep12-20260521
    python scripts/resume_pipeline.py --project-id ondas-ep12-20260521 --from-phase 3
    python scripts/resume_pipeline.py --project-id ondas-ep12-20260521 --skip-validation
    python scripts/resume_pipeline.py --project-id ondas-ep12-20260521 --status
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
logger = logging.getLogger("phymac.cli.resume")

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.orchestrator import PipelineOrchestrator
from pipeline.storage import StorageAdapter
# Import all phase runners so they register themselves
from pipeline.phases.phase1_ingest import register as r1


def register_all_phases(orchestrator):
    r1(orchestrator)
    # Future phases will be imported here as they're built:
    # r2(orchestrator)
    # r3(orchestrator)
    # r4(orchestrator)
    # r5(orchestrator)
    # r6(orchestrator)


def _status_report(state) -> None:
    """Print a formatted status report of the project."""
    from pipeline.models import PhaseStatus
    icons = {
        PhaseStatus.PENDING: "⏳",
        PhaseStatus.RUNNING: "🔄",
        PhaseStatus.COMPLETED: "✅",
        PhaseStatus.FAILED: "❌",
    }
    print("\n" + "═" * 60)
    print(f"  Project: {state.project.title}")
    print(f"  ID:      {state.project.project_id}")
    print(f"  Status:  {state.project.status.value.upper()}")
    print("═" * 60)
    for n in range(1, 7):
        phase = state.phases.get(n)
        if phase:
            icon = icons.get(phase.status, "?")
            score = ""
            if phase.validation:
                score = f" (score={phase.validation.score:.2f})"
            print(f"  Phase {n}: {icon} {phase.status.value}{score}")
            if phase.error_message:
                print(f"           ⚠ {phase.error_message[:80]}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="PhyMaC Pipeline — Resume or inspect a project",
    )
    parser.add_argument("--project-id", required=True, help="Project ID to resume")
    parser.add_argument("--from-phase", type=int, help="Force start from this phase (1-6)")
    parser.add_argument("--skip-validation", action="store_true",
                        help="Skip ValidationAgent (manual override — use carefully)")
    parser.add_argument("--status", action="store_true",
                        help="Show project status without running anything")
    args = parser.parse_args()

    storage = StorageAdapter()
    orchestrator = PipelineOrchestrator(storage)
    register_all_phases(orchestrator)

    state = orchestrator.load_checkpoint(args.project_id)
    _status_report(state)

    if args.status:
        return

    if args.from_phase:
        logger.info(f"Running from Phase {args.from_phase} (forced)...")
        state = orchestrator.run(
            args.project_id,
            start_from_phase=args.from_phase,
            skip_validation=args.skip_validation,
        )
    else:
        logger.info("Resuming from last failed/paused phase...")
        state = orchestrator.resume(
            args.project_id,
            skip_validation=args.skip_validation,
        )

    _status_report(state)

    if state.project.status.value == "completed":
        print("🎉 Pipeline complete! Video is ready.")
        phase6 = state.phases.get(6)
        if phase6:
            print(f"  Download URL: {phase6.outputs.get('download_url', 'N/A')}")
    elif state.project.status.value == "paused":
        print("⛔ Pipeline still paused. Review errors above and retry.")
        sys.exit(1)


if __name__ == "__main__":
    main()

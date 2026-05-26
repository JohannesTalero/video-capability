#!/usr/bin/env python3
"""
CLI — Run Phase 1 (Ingestion & Transcription) standalone.

Usage:
    python scripts/run_phase1.py --video /path/to/video.mp4 --title "Mi Episodio"
    python scripts/run_phase1.py --project-id ondas-ep12-20260521   # resume existing project
    python scripts/run_phase1.py --video /path/to/video.mp4 --title "Test" --dry-run

Environment variables required (.env file):
    STORAGE_PROVIDER=r2
    R2_ACCOUNT_ID=...
    R2_ACCESS_KEY_ID=...
    R2_SECRET_KEY=...
    R2_BUCKET_NAME=phymac-pipeline
    MODAL_TOKEN_ID=...    (optional — uses CPU if not set)
    MODAL_TOKEN_SECRET=...
"""

import argparse
import logging
import sys
from pathlib import Path

# Load .env if present
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # python-dotenv optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("phymac.cli.phase1")

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.orchestrator import PipelineOrchestrator
from pipeline.phases.phase1_ingest import register as register_phase1
from pipeline.storage import StorageAdapter


def main():
    parser = argparse.ArgumentParser(
        description="PhyMaC Pipeline — Phase 1: Ingest & Transcribe",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # New project:
  python scripts/run_phase1.py --video ~/Videos/episodio12.mp4 --title "Ondas EM Episodio 12"

  # Retry Phase 1 for existing project:
  python scripts/run_phase1.py --project-id ondas-em-episodio-12-20260521

  # Skip validation (manual override):
  python scripts/run_phase1.py --project-id ondas-em-episodio-12-20260521 --skip-validation
        """,
    )
    parser.add_argument("--video", type=str, help="Path to the source video file (MP4 or MOV)")
    parser.add_argument("--title", type=str, help="Project title (used to generate project ID)")
    parser.add_argument("--project-id", type=str, help="Existing project ID to resume/retry")
    parser.add_argument("--brand-id", type=str, default="phymac", help="Brand ID (default: phymac)")
    parser.add_argument(
        "--skip-validation", action="store_true", help="Skip ValidationAgent checks"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Check config and storage connection only"
    )
    args = parser.parse_args()

    if not args.video and not args.project_id:
        parser.error("Provide either --video (new project) or --project-id (resume)")

    if args.video and not args.title:
        parser.error("--title is required when creating a new project with --video")

    # Init storage and orchestrator
    logger.info("Initializing storage adapter...")
    storage = StorageAdapter()
    orchestrator = PipelineOrchestrator(storage)
    register_phase1(orchestrator)

    if args.dry_run:
        logger.info("✅ Dry run: storage connected, Phase 1 registered. Ready to run.")
        print("\nDry run complete. Configuration looks good.")
        print(f"  Storage provider: {storage._provider}")
        print(f"  Bucket: {storage._bucket}")
        return

    # Create or load project
    if args.video:
        video_path = Path(args.video)
        if not video_path.exists():
            logger.error(f"Video file not found: {video_path}")
            sys.exit(1)

        logger.info(f"Creating new project: '{args.title}'")
        state = orchestrator.create_project(
            title=args.title,
            video_local_path=str(video_path),
            brand_id=args.brand_id,
        )
        project_id = state.project.project_id
        print(f"\n✅ Project created: {project_id}")
    else:
        project_id = args.project_id
        state = orchestrator.load_checkpoint(project_id)
        print(f"\n▶ Resuming project: {project_id}")

    print(f"   Title: {state.project.title}")
    print(f"   Brand: {state.project.brand_id}")
    print(f"   Video: {state.project.video_original_key}")
    print()

    # Run Phase 1 only
    logger.info("Starting Phase 1: Ingestion & Transcription...")
    state = orchestrator.run(
        project_id=project_id,
        start_from_phase=1,
        end_at_phase=1,
        skip_validation=args.skip_validation,
    )

    # Report result
    phase1 = state.phases.get(1)
    if phase1 and phase1.status.value == "completed":
        validation = phase1.validation
        print("\n" + "═" * 60)
        print("✅ Phase 1 Complete!")
        print("═" * 60)
        print(f"  Transcription key: {phase1.outputs.get('transcription_key', 'N/A')}")
        print(f"  Segments:          {phase1.outputs.get('segment_count', 'N/A')}")
        print(
            f"  Duration:          {float(phase1.outputs.get('duration_seconds', 0)) / 60:.1f} min"
        )
        print(f"  Language:          {phase1.outputs.get('language', 'N/A')}")
        if validation:
            print(f"  Validation score:  {validation.score:.2f}")
            if validation.warnings:
                print("\n  ⚠ Warnings:")
                for w in validation.warnings:
                    print(f"    • {w}")
        print("\n  Next step:")
        print(f"  python scripts/run_phase2.py --project-id {project_id}")
    else:
        print("\n❌ Phase 1 FAILED. Check logs above for details.")
        if phase1:
            print(f"  Error: {phase1.error_message}")
            print("\n  To retry:")
            print(f"  python scripts/run_phase1.py --project-id {project_id}")
        sys.exit(1)


if __name__ == "__main__":
    main()

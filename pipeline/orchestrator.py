"""
PipelineOrchestrator — state machine coordinating all 6 pipeline phases.

Responsibilities:
- Create and manage projects
- Execute phases in sequence with checkpoint persistence
- Retry failed phases (max 3 attempts)
- Pause and notify user on persistent failures
- Load checkpoints to resume interrupted runs
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pipeline.config import DEFAULT_BRAND_ID, DEFAULT_FORMAT_ID, MAX_PHASE_RETRIES
from pipeline.models import (
    PhaseState,
    PhaseStatus,
    Project,
    ProjectState,
    ProjectStatus,
    StorageKey,
    ValidationResult,
)
from pipeline.storage import StorageAdapter, StorageKeyNotFoundError
from pipeline.validator import ValidationAgent

logger = logging.getLogger(__name__)


class InvalidPhaseOrderError(Exception):
    pass


class ProjectNotFoundError(Exception):
    pass


class ProjectIDCollisionError(Exception):
    pass


class MissingPhaseOutputError(Exception):
    pass


class PipelineOrchestrator:
    """
    Main coordinator for the PhyMaC video pipeline.

    Usage:
        storage = StorageAdapter()
        orchestrator = PipelineOrchestrator(storage)

        # Create a new project
        state = orchestrator.create_project("Mi Video", "/path/to/video.mp4")

        # Run from phase 1
        orchestrator.run(state.project.project_id)

        # Resume from phase 3 after a failure
        orchestrator.run("mi-video-20260521", start_from_phase=3)
    """

    TOTAL_PHASES = 6

    def __init__(self, storage: StorageAdapter, validator: ValidationAgent | None = None):
        self.storage = storage
        self.validator = validator or ValidationAgent()
        self._phase_runners: dict[int, Callable[[ProjectState], dict]] = {}

    def register_phase(self, phase_num: int, runner: Callable[[ProjectState], dict]) -> None:
        """
        Register a phase runner function.
        Called by each phase module (phase1_ingest.py, etc.) at import time.

        The runner signature: runner(project_state: ProjectState) -> dict
        The dict is the phase output passed to ValidationAgent.
        """
        self._phase_runners[phase_num] = runner
        logger.debug(f"Registered runner for Phase {phase_num}: {runner.__name__}")

    # ------------------------------------------------------------------
    # Project lifecycle
    # ------------------------------------------------------------------

    def create_project(
        self,
        title: str,
        video_local_path: str,
        brand_id: str = DEFAULT_BRAND_ID,
        format_id: str = DEFAULT_FORMAT_ID,
    ) -> ProjectState:
        """
        Create a new project: upload video, generate ID, save initial checkpoint.
        Returns the initial ProjectState.
        """
        now = self._now()
        project_id = self._generate_project_id(title, now)
        filename = Path(video_local_path).name
        video_key = StorageKey.original_video(project_id, filename)

        logger.info(f"Creating project '{title}' ({project_id}, format={format_id})")
        logger.info(f"Uploading video: {video_local_path} → {video_key}")
        self.storage.upload(video_local_path, video_key)

        project = Project(
            project_id=project_id,
            title=title,
            brand_id=brand_id,
            format_id=format_id,
            video_original_key=video_key,
            created_at=now,
            updated_at=now,
            current_phase=0,
            status=ProjectStatus.CREATED,
        )
        phases = {
            n: PhaseState(phase_num=n, status=PhaseStatus.PENDING)
            for n in range(1, self.TOTAL_PHASES + 1)
        }
        state = ProjectState(project=project, phases=phases)
        self._save_checkpoint(state)

        logger.info(f"Project created: {project_id}")
        return state

    def run(
        self,
        project_id: str,
        start_from_phase: int = 1,
        end_at_phase: int | None = None,
        skip_validation: bool = False,
    ) -> ProjectState:
        """
        Execute pipeline phases sequentially from start_from_phase.

        Args:
            project_id: The project to run.
            start_from_phase: Phase to start from (1–6). Use > 1 to resume.
            end_at_phase: Last phase to execute (inclusive). Defaults to TOTAL_PHASES.
                          Use this to run a single phase, e.g. end_at_phase=1.
            skip_validation: If True, skip ValidationAgent and mark phases as passed.
                             Use only as manual override after inspecting output.
        """
        state = self.load_checkpoint(project_id)
        self._validate_start_phase(state, start_from_phase)

        last_phase = end_at_phase if end_at_phase is not None else self.TOTAL_PHASES
        if last_phase < start_from_phase or last_phase > self.TOTAL_PHASES:
            raise ValueError(
                f"Invalid end_at_phase={last_phase}; must be in "
                f"[{start_from_phase}, {self.TOTAL_PHASES}]"
            )

        logger.info(
            f"▶ Running pipeline for '{state.project.title}' "
            f"from Phase {start_from_phase} to Phase {last_phase}"
        )

        for phase_num in range(start_from_phase, last_phase + 1):
            success = self._run_phase_with_retry(state, phase_num, skip_validation)
            if not success:
                # Project is now PAUSED — stop here
                return self.load_checkpoint(project_id)
            # Reload state to get fresh outputs from checkpoint
            state = self.load_checkpoint(project_id)

        # Mark COMPLETED only if we ran through the final phase; otherwise
        # this was a partial run (e.g. end_at_phase=1) and the project is
        # paused mid-pipeline waiting for the next stage.
        if last_phase == self.TOTAL_PHASES:
            state.project.status = ProjectStatus.COMPLETED
            state.project.updated_at = self._now()
            self._save_checkpoint(state)
            logger.info(f"✅ Pipeline complete for project: {project_id}")
        else:
            logger.info(
                f"✓ Partial run complete for project {project_id} "
                f"(Phases {start_from_phase}–{last_phase})"
            )
        return state

    def get_status(self, project_id: str) -> ProjectState:
        """Return current project state from checkpoint."""
        return self.load_checkpoint(project_id)

    def resume(
        self,
        project_id: str,
        skip_validation: bool = False,
    ) -> ProjectState:
        """
        Resume a PAUSED project from the last failed phase.
        Resets the failed phase's attempt counter.
        """
        state = self.load_checkpoint(project_id)
        if state.project.status not in (ProjectStatus.PAUSED, ProjectStatus.RUNNING):
            logger.warning(
                f"Project {project_id} is not paused (status={state.project.status}). Nothing to resume."
            )
            return state

        # Find the failed phase
        failed_phases = [n for n, p in state.phases.items() if p.status == PhaseStatus.FAILED]
        if not failed_phases:
            logger.warning("No failed phases found. Running from next pending phase.")
        start_phase = min(failed_phases) if failed_phases else state.last_completed_phase() + 1

        # Reset attempt counter for the failed phase
        if start_phase in state.phases:
            state.phases[start_phase].attempt = 0
            state.phases[start_phase].status = PhaseStatus.PENDING

        state.project.status = ProjectStatus.RUNNING
        self._save_checkpoint(state)

        return self.run(project_id, start_from_phase=start_phase, skip_validation=skip_validation)

    # ------------------------------------------------------------------
    # Internal phase execution
    # ------------------------------------------------------------------

    def _run_phase_with_retry(
        self,
        state: ProjectState,
        phase_num: int,
        skip_validation: bool,
    ) -> bool:
        """
        Execute a phase with up to MAX_PHASE_RETRIES attempts.
        Returns True if phase completed successfully, False if it exhausted retries.
        """
        phase_state = state.phases[phase_num]
        max_attempts = MAX_PHASE_RETRIES

        for attempt in range(1, max_attempts + 1):
            logger.info(f"  Phase {phase_num} — attempt {attempt}/{max_attempts}")
            phase_state.attempt = attempt
            phase_state.status = PhaseStatus.RUNNING
            phase_state.started_at = self._now()
            phase_state.error_message = None
            state.project.current_phase = phase_num
            state.project.status = ProjectStatus.RUNNING
            self._save_checkpoint(state)

            try:
                output = self._execute_phase(phase_num, state)
            except Exception as e:
                logger.error(f"  Phase {phase_num} execution error: {e}")
                phase_state.error_message = str(e)
                if attempt < max_attempts:
                    logger.info(f"  Retrying Phase {phase_num}...")
                    continue
                else:
                    self._pause_project(state, phase_num, phase_state, str(e))
                    return False

            # Validation
            if skip_validation:
                validation = ValidationResult(
                    passed=True,
                    phase=phase_num,
                    score=1.0,
                    recommendation="Validation skipped by user (--skip-validation)",
                )
            else:
                validation = self.validator.validate(phase_num, output, self._build_context(state))

            phase_state.validation = validation

            if validation.passed:
                phase_state.status = PhaseStatus.COMPLETED
                phase_state.completed_at = self._now()
                phase_state.outputs = {
                    k: v
                    for k, v in output.items()
                    if isinstance(v, (str, int, float, bool)) or v is None
                }
                self._save_checkpoint(state)
                logger.info(f"  ✓ Phase {phase_num} complete (score={validation.score:.2f})")
                if validation.warnings:
                    for w in validation.warnings:
                        logger.warning(f"    ⚠ {w}")
                return True
            else:
                logger.warning(
                    f"  Phase {phase_num} validation failed: {validation.critical_failures}"
                )
                if attempt < max_attempts:
                    logger.info(f"  Retrying Phase {phase_num}...")
                    continue
                else:
                    self._pause_project(
                        state,
                        phase_num,
                        phase_state,
                        str(validation.critical_failures),
                        validation=validation,
                    )
                    return False

        return False  # should not reach here

    def _execute_phase(self, phase_num: int, state: ProjectState) -> dict:
        """Dispatch to the registered phase runner."""
        runner = self._phase_runners.get(phase_num)
        if not runner:
            raise NotImplementedError(
                f"No runner registered for Phase {phase_num}. "
                f"Import the phase module before running the orchestrator."
            )
        return runner(state)

    def _build_context(self, state: ProjectState) -> dict:
        """Build context dict passed to ValidationAgent."""
        return {
            "project_id": state.project.project_id,
            "brand_id": state.project.brand_id,
            "state": state,
        }

    def _pause_project(
        self,
        state: ProjectState,
        phase_num: int,
        phase_state: PhaseState,
        error: str,
        validation: ValidationResult | None = None,
    ) -> None:
        """Mark project as PAUSED and log notification."""
        phase_state.status = PhaseStatus.FAILED
        phase_state.error_message = error
        state.project.status = ProjectStatus.PAUSED
        state.project.updated_at = self._now()
        self._save_checkpoint(state)

        pid = state.project.project_id
        failures = validation.critical_failures if validation else [error]
        recommendation = validation.recommendation if validation else "Check logs and retry."

        notification = f"""
╔══════════════════════════════════════════════════════════╗
║  ⛔ PIPELINE PAUSED — Phase {phase_num} failed after {MAX_PHASE_RETRIES} attempts  ║
╠══════════════════════════════════════════════════════════╣
║  Project: {pid}
║  Critical failures:
"""
        for f in failures:
            notification += f"║    • {f}\n"
        notification += f"""║
║  Recommendation: {recommendation}
║
║  To resume:
║    python scripts/resume_pipeline.py --project-id {pid}
║
║  To resume without validation (manual override):
║    python scripts/resume_pipeline.py --project-id {pid} --skip-validation
╚══════════════════════════════════════════════════════════╝"""

        logger.error(notification)
        # Also print to stdout so it's visible in CLI
        print(notification)

    # ------------------------------------------------------------------
    # Checkpoint persistence
    # ------------------------------------------------------------------

    def _save_checkpoint(self, state: ProjectState) -> None:
        """Serialize and save ProjectState to storage."""
        key = StorageKey.project_state(state.project.project_id)
        self.storage.upload_json(state.to_json(), key)
        logger.debug(f"Checkpoint saved: {key}")

    def load_checkpoint(self, project_id: str) -> ProjectState:
        """Load ProjectState from storage."""
        key = StorageKey.project_state(project_id)
        try:
            json_str = self.storage.download_json(key)
            return ProjectState.from_json(json_str)
        except StorageKeyNotFoundError as e:
            raise ProjectNotFoundError(
                f"Project '{project_id}' not found in storage. "
                f"Create it first with orchestrator.create_project()."
            ) from e

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _validate_start_phase(self, state: ProjectState, start_from: int) -> None:
        """Ensure all phases before start_from are COMPLETED."""
        if start_from == 1:
            return
        for n in range(1, start_from):
            phase = state.phases.get(n)
            if not phase or phase.status != PhaseStatus.COMPLETED:
                raise InvalidPhaseOrderError(
                    f"Cannot start from Phase {start_from}: Phase {n} is not COMPLETED "
                    f"(status={phase.status.value if phase else 'missing'}). "
                    f"Run phases in order or use resume()."
                )

    def _generate_project_id(self, title: str, timestamp: str) -> str:
        """Generate a unique project_id from title + date."""
        date_str = timestamp[:10].replace("-", "")
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower().strip()).strip("-")
        slug = slug[:50]  # max 50 chars
        base_id = f"{slug}-{date_str}"

        if not self.storage.exists(StorageKey.project_state(base_id)):
            return base_id

        for n in range(2, 100):
            candidate = f"{base_id}-{n}"
            if not self.storage.exists(StorageKey.project_state(candidate)):
                return candidate

        raise ProjectIDCollisionError(f"Could not generate unique ID for title: {title}")

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

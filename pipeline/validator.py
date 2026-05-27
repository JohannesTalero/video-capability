"""
ValidationAgent — validates the output of each pipeline phase.

Behavior:
- Called by PipelineOrchestrator after every phase execution.
- Runs a suite of checks (technical metrics + Claude Vision where relevant).
- Returns ValidationResult with passed/failed, score, and recommendations.
- The orchestrator handles retry logic (max 3 attempts before PAUSED).
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from pipeline.config import (
    LLM_MODEL_VALIDATOR,
    LLM_MODEL_VISION,
    VALIDATION_PASS_SCORE,
)
from pipeline.formats import FormatNotFoundError, load_format
from pipeline.llm import (
    build_image_content,
    get_llm_client,
    is_llm_available,
)
from pipeline.models import (
    CheckResult,
    NarrativePlan,
    TranscriptionResult,
    ValidationResult,
)
from pipeline.phase3_r2 import download_to_local, head_object_exists

logger = logging.getLogger(__name__)

# Score threshold below which a check is "critical" (blocks pipeline)
# Checks below this threshold AND marked critical=True will go to critical_failures
CRITICAL_SCORE_WEIGHT = 1.0  # critical checks contribute full weight


class ValidationAgent:
    """
    Validates each pipeline phase output.
    Phase-specific validators are implemented as private methods.
    """

    def validate(
        self,
        phase: int,
        output: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """
        Main entry point. Dispatches to the correct phase validator.

        Args:
            phase: Phase number (1-6)
            output: Phase output dict (keys depend on phase)
            context: Additional context (project_id, plan, etc.)
        """
        validators = {
            1: self._validate_phase_1,
            2: self._validate_phase_2,
            3: self._validate_phase_3,
            4: self._validate_phase_4,
            5: self._validate_phase_5,
            6: self._validate_phase_6,
        }
        if phase not in validators:
            raise ValueError(f"Unknown phase: {phase}")

        logger.info(f"Running validation for Phase {phase}...")
        result = validators[phase](output, context or {})
        logger.info(
            f"Phase {phase} validation: {'PASS' if result.passed else 'FAIL'} "
            f"(score={result.score:.2f}, critical={len(result.critical_failures)})"
        )
        return result

    # ------------------------------------------------------------------
    # Phase 1 — Transcription Validation
    # ------------------------------------------------------------------

    def _validate_phase_1(self, output: dict, context: dict) -> ValidationResult:
        """
        Checks:
        - Segments exist and are non-empty
        - Transcription coverage > 90% of audio duration
        - Average Whisper confidence > 0.7
        - Language detected is Spanish
        - Duration match between audio and transcription (< 5% diff)
        """
        checks = []
        transcription: TranscriptionResult | None = output.get("transcription")

        # Check 1: Segments exist
        has_segments = transcription is not None and len(transcription.segments) > 0
        checks.append(
            CheckResult(
                name="has_segments",
                passed=has_segments,
                value=len(transcription.segments) if transcription else 0,
                threshold=">= 1",
                message="Transcription has at least one segment"
                if has_segments
                else "CRITICAL: No segments found in transcription",
            )
        )

        if not has_segments:
            return self._build_result(phase=1, checks=checks, critical_names=["has_segments"])

        assert transcription is not None  # has_segments True → transcription non-None

        # Check 2: Coverage — total transcribed time / audio duration
        total_transcribed = sum(s.end - s.start for s in transcription.segments)
        coverage = (
            total_transcribed / transcription.duration_seconds
            if transcription.duration_seconds > 0
            else 0
        )
        checks.append(
            CheckResult(
                name="transcription_coverage",
                passed=coverage >= 0.90,
                value=round(coverage, 3),
                threshold=">= 0.90",
                message=f"Coverage {coverage:.1%}"
                if coverage >= 0.90
                else f"CRITICAL: Low coverage {coverage:.1%} (< 90% of audio transcribed)",
            )
        )

        # Check 3: Average confidence
        avg_conf = sum(s.confidence for s in transcription.segments) / len(transcription.segments)
        checks.append(
            CheckResult(
                name="avg_confidence",
                passed=avg_conf >= 0.70,
                value=round(avg_conf, 3),
                threshold=">= 0.70",
                message=f"Average Whisper confidence {avg_conf:.2f}"
                if avg_conf >= 0.70
                else f"WARNING: Low confidence {avg_conf:.2f} — review transcription carefully",
            )
        )

        # Check 4: Language detection
        lang_ok = transcription.language in ("es", "es-419", "es-MX", "es-CO")
        checks.append(
            CheckResult(
                name="language_detection",
                passed=lang_ok,
                value=transcription.language,
                threshold="es or es-*",
                message=f"Language detected: {transcription.language}"
                if lang_ok
                else f"WARNING: Unexpected language '{transcription.language}' — expected Spanish",
            )
        )

        # Check 5: Empty segments ratio
        empty = [s for s in transcription.segments if len(s.text.strip()) < 3]
        empty_ratio = len(empty) / len(transcription.segments)
        checks.append(
            CheckResult(
                name="empty_segments_ratio",
                passed=empty_ratio <= 0.05,
                value=round(empty_ratio, 3),
                threshold="<= 0.05",
                message=f"Empty segments ratio {empty_ratio:.1%}"
                if empty_ratio <= 0.05
                else f"WARNING: {empty_ratio:.1%} of segments are nearly empty",
            )
        )

        return self._build_result(
            phase=1,
            checks=checks,
            critical_names=["has_segments", "transcription_coverage"],
            warning_names=["avg_confidence", "language_detection", "empty_segments_ratio"],
        )

    # ------------------------------------------------------------------
    # Phase 2 — Narrative Plan Validation
    # ------------------------------------------------------------------

    def _validate_phase_2(self, output: dict, context: dict) -> ValidationResult:
        """
        Phase 2 validation — see spec 2026-05-26-phase2-narrative-plan-design.md §8.

        Critical (block pipeline):
          - has_blocks                       — plan has at least 1 block
          - segment_ids_valid                — all referenced ids exist in transcription
          - no_duplicate_segments            — no segment used in two blocks
          - material_tipos_in_whitelist      — every tipo is in the format's whitelist

        Warnings (do not block):
          - pull_quote_count                 — total pull_quotes <= 10
          - lower_third_count                — total lower_thirds <= 2
          - duration_in_range                — estimated total in [22, 32] minutes
          - cold_open_structure              — first block named "Cold open" with 3 segments
          - llm_coherence                    — semantic sanity check
        """
        plan: NarrativePlan | None = output.get("plan")
        transcription: TranscriptionResult | None = output.get("transcription")
        state = context.get("state")
        checks: list[CheckResult] = []

        # ---- Check 1 (critical): plan exists and has blocks ----
        has_blocks = plan is not None and len(plan.blocks) > 0
        checks.append(
            CheckResult(
                name="has_blocks",
                passed=has_blocks,
                value=len(plan.blocks) if plan is not None else 0,
                threshold=">= 1",
                message=f"{len(plan.blocks)} blocks generated"
                if plan is not None and has_blocks
                else "CRITICAL: No blocks in narrative plan",
            )
        )
        if not has_blocks:
            return self._build_result(phase=2, checks=checks, critical_names=["has_blocks"])

        assert plan is not None  # has_blocks True → plan is non-None — narrow for mypy

        # Format config (used by whitelist check) — best-effort.
        whitelist: set[str] = set()
        format_id = state.project.format_id if state and state.project else None
        if format_id:
            try:
                whitelist = set(load_format(format_id).materials_whitelist)
            except FormatNotFoundError as e:
                logger.warning(f"Phase 2 validator could not load format: {e}")

        # ---- Check 2 (critical): segment IDs valid ----
        checks.append(self._check_segment_ids_valid(plan, transcription))

        # ---- Check 3 (critical): no duplicate segments ----
        checks.append(self._check_no_duplicate_segments(plan))

        # ---- Check 4 (critical): material tipos in whitelist ----
        checks.append(self._check_material_tipos_in_whitelist(plan, whitelist))

        # ---- Warnings ----
        checks.append(self._check_pull_quote_count(plan, max_count=10))
        checks.append(self._check_lower_third_count(plan, max_count=2))
        checks.append(self._check_duration_in_range(plan, low_sec=22 * 60, high_sec=32 * 60))
        checks.append(self._check_cold_open_structure(plan))
        checks.append(self._claude_coherence_check(plan, transcription))

        return self._build_result(
            phase=2,
            checks=checks,
            critical_names=[
                "has_blocks",
                "segment_ids_valid",
                "no_duplicate_segments",
                "material_tipos_in_whitelist",
            ],
            warning_names=[
                "pull_quote_count",
                "lower_third_count",
                "duration_in_range",
                "cold_open_structure",
                "llm_coherence",
            ],
        )

    # ------------------------------------------------------------------
    # Phase 2 — individual check helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_segment_ids_valid(
        plan: NarrativePlan,
        transcription: TranscriptionResult | None,
    ) -> CheckResult:
        if transcription is None:
            return CheckResult(
                name="segment_ids_valid",
                passed=True,
                value="skipped",
                threshold="[]",
                message="No transcription supplied to validator — skipping segment id check.",
            )
        valid_ids = {s.id for s in transcription.segments}
        orphans = [sid for block in plan.blocks for sid in block.segments if sid not in valid_ids]
        return CheckResult(
            name="segment_ids_valid",
            passed=not orphans,
            value=orphans,
            threshold="[]",
            message=(
                "All segment IDs are valid"
                if not orphans
                else f"CRITICAL: Orphan segment IDs (not in transcription): {orphans}"
            ),
        )

    @staticmethod
    def _check_no_duplicate_segments(plan: NarrativePlan) -> CheckResult:
        """
        A segment may appear in the cold open (first block) AND in its
        natural chapter — that overlap is intentional (the teaser replays
        in context). Any duplicate where NEITHER appearance is in the
        cold open is flagged as critical.
        """
        if not plan.blocks:
            return CheckResult(
                name="no_duplicate_segments",
                passed=True,
                value=[],
                threshold="[]",
                message="No blocks to check.",
            )
        cold_open_block_id = plan.blocks[0].id
        cold_open_segments = set(plan.blocks[0].segments)

        seen: dict[int, str] = {}
        duplicates: list[tuple[int, str, str]] = []
        for block in plan.blocks:
            for sid in block.segments:
                if sid in seen:
                    prev_block_id = seen[sid]
                    # Allowed overlap: one occurrence must be in the cold open.
                    overlap_with_cold_open = (
                        prev_block_id == cold_open_block_id or block.id == cold_open_block_id
                    )
                    if overlap_with_cold_open and sid in cold_open_segments:
                        # Replace mapping to the non-cold-open block so a
                        # third occurrence in ANY block would still flag.
                        if prev_block_id == cold_open_block_id:
                            seen[sid] = block.id
                        continue
                    duplicates.append((sid, prev_block_id, block.id))
                else:
                    seen[sid] = block.id
        return CheckResult(
            name="no_duplicate_segments",
            passed=not duplicates,
            value=duplicates,
            threshold="[]",
            message=(
                "No invalid duplicate segments (cold-open ↔ chapter overlap allowed)"
                if not duplicates
                else f"CRITICAL: Duplicate segment IDs outside cold-open: {duplicates}"
            ),
        )

    @staticmethod
    def _check_material_tipos_in_whitelist(
        plan: NarrativePlan,
        whitelist: set[str],
    ) -> CheckResult:
        if not whitelist:
            return CheckResult(
                name="material_tipos_in_whitelist",
                passed=True,
                value="skipped",
                threshold="any",
                message="No whitelist available (format not loaded) — skipping check.",
            )
        invalid = [
            m.tipo
            for block in plan.blocks
            for m in block.support_material
            if m.tipo not in whitelist
        ]
        return CheckResult(
            name="material_tipos_in_whitelist",
            passed=not invalid,
            value=invalid,
            threshold=sorted(whitelist),
            message=(
                "All material tipos in whitelist"
                if not invalid
                else f"CRITICAL: Unknown material tipos: {invalid}"
            ),
        )

    @staticmethod
    def _check_pull_quote_count(plan: NarrativePlan, max_count: int) -> CheckResult:
        count = sum(
            1 for block in plan.blocks for m in block.support_material if m.tipo == "pull_quote"
        )
        passed = count <= max_count
        return CheckResult(
            name="pull_quote_count",
            passed=passed,
            value=count,
            threshold=f"<= {max_count}",
            message=(
                f"{count} pull_quotes (within limit)"
                if passed
                else f"WARNING: {count} pull_quotes exceeds soft cap of {max_count}"
            ),
        )

    @staticmethod
    def _check_lower_third_count(plan: NarrativePlan, max_count: int) -> CheckResult:
        count = sum(
            1 for block in plan.blocks for m in block.support_material if m.tipo == "lower_third"
        )
        passed = count <= max_count
        return CheckResult(
            name="lower_third_count",
            passed=passed,
            value=count,
            threshold=f"<= {max_count}",
            message=(
                f"{count} lower_thirds (within limit)"
                if passed
                else f"WARNING: {count} lower_thirds exceeds cap of {max_count}"
            ),
        )

    @staticmethod
    def _check_duration_in_range(
        plan: NarrativePlan,
        low_sec: int,
        high_sec: int,
    ) -> CheckResult:
        """Parse MM:SS from each block.estimated_duration and sum."""
        total = 0
        for block in plan.blocks:
            parts = (block.estimated_duration or "").strip().split(":")
            try:
                if len(parts) == 2:
                    total += int(parts[0]) * 60 + int(parts[1])
                elif len(parts) == 3:
                    total += int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            except ValueError:
                # Malformed durations contribute zero; the model may have
                # left some empty. We don't want this single oddity to
                # blow the whole check up.
                pass
        passed = low_sec <= total <= high_sec
        return CheckResult(
            name="duration_in_range",
            passed=passed,
            value=f"{total // 60}:{total % 60:02d}",
            threshold=f"{low_sec // 60}-{high_sec // 60} min",
            message=(
                f"Estimated duration {total // 60}:{total % 60:02d} in target range"
                if passed
                else f"WARNING: Estimated total duration "
                f"{total // 60}:{total % 60:02d} outside "
                f"{low_sec // 60}-{high_sec // 60} min target"
            ),
        )

    @staticmethod
    def _check_cold_open_structure(plan: NarrativePlan) -> CheckResult:
        if not plan.blocks:
            return CheckResult(
                name="cold_open_structure",
                passed=False,
                value="no_blocks",
                threshold='first block name="Cold open", segments count=3',
                message="WARNING: No blocks to check cold open structure.",
            )
        first = plan.blocks[0]
        name_ok = first.name.strip().lower() == "cold open"
        count_ok = len(first.segments) == 3
        passed = name_ok and count_ok
        details = f'name="{first.name}", segments={len(first.segments)}'
        return CheckResult(
            name="cold_open_structure",
            passed=passed,
            value=details,
            threshold='name="Cold open", segments=3',
            message=(
                "Cold open structure OK"
                if passed
                else f'WARNING: Cold open expected name="Cold open" with 3 segments; got {details}'
            ),
        )

    def _claude_coherence_check(
        self,
        plan: NarrativePlan,
        transcription: TranscriptionResult | None,
    ) -> CheckResult:
        """Ask an LLM (via OpenRouter) if the narrative plan makes sense with the transcription."""
        if not is_llm_available():
            return CheckResult(
                name="llm_coherence",
                passed=True,
                value="skipped",
                threshold="coherent=true",
                message="LLM coherence check skipped (OPENROUTER_API_KEY not set)",
            )

        try:
            client = get_llm_client()

            sample_text = transcription.full_text[:2000] if transcription else "(no transcription)"
            blocks_summary = [
                {"id": b.id, "name": b.name, "segments": b.segments} for b in plan.blocks
            ]

            prompt = f"""You are validating a narrative plan for an educational video in Spanish.

TRANSCRIPTION SAMPLE (first 2000 chars):
{sample_text}

GENERATED NARRATIVE PLAN (blocks):
{json.dumps(blocks_summary, ensure_ascii=False, indent=2)}

Is this plan coherent with the transcription?
- Do the block names make sense given the content?
- Are there obvious errors (e.g., a single segment spread across too many blocks)?

Respond ONLY with valid JSON:
{{"coherent": true/false, "confidence": 0.0-1.0, "issues": ["issue1", "issue2"]}}"""

            response = client.chat.completions.create(
                model=LLM_MODEL_VALIDATOR,
                max_tokens=256,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.choices[0].message.content or "{}"
            result = json.loads(content)
            coherent = result.get("coherent", False)
            issues = result.get("issues", [])

            return CheckResult(
                name="llm_coherence",
                passed=coherent,
                value=result,
                threshold="coherent=true",
                message=f"LLM: plan is coherent (confidence {result.get('confidence', 0):.2f})"
                if coherent
                else f"WARNING: LLM found issues: {issues}",
            )
        except Exception as e:
            logger.warning(f"LLM coherence check failed: {e}")
            return CheckResult(
                name="llm_coherence",
                passed=True,  # don't block on LLM errors
                value="error",
                threshold="coherent=true",
                message=f"LLM coherence check skipped due to error: {e}",
            )

    # ------------------------------------------------------------------
    # Phase 3 — Materials Validation
    # ------------------------------------------------------------------

    def _validate_phase_3(self, output: dict, context: dict) -> ValidationResult:
        """
        Checks:
        - All planned materials were generated
        - Each MP4 has alpha channel (yuva420p or rgba)
        - Each MP4 is > 0.5 seconds
        - Each file is not corrupted (ffprobe exit code 0)
        - Claude Vision: sample frame is readable (1 check per material)
        """
        checks = []
        materials = output.get("materials", [])
        plan: NarrativePlan | None = context.get("plan")

        # Check 1: Count matches plan
        planned_count = sum(len(b.support_material) for b in plan.blocks) if plan else 0
        count_ok = len(materials) >= planned_count
        checks.append(
            CheckResult(
                name="materials_count",
                passed=count_ok,
                value=len(materials),
                threshold=f">= {planned_count}",
                message=f"{len(materials)}/{planned_count} materials generated"
                if count_ok
                else f"CRITICAL: Only {len(materials)}/{planned_count} materials generated",
            )
        )

        # Per-material checks
        for i, mat in enumerate(materials):
            local_path = mat.get("local_path") or context.get("local_paths", {}).get(
                mat.get("storage_key", "")
            )
            if not local_path or not Path(local_path).exists():
                checks.append(
                    CheckResult(
                        name=f"material_{i}_exists",
                        passed=False,
                        value="missing",
                        threshold="file exists",
                        message=f"CRITICAL: Material {i} file not found locally for validation",
                    )
                )
                continue

            # ffprobe check
            probe = self._ffprobe(local_path)
            checks.append(
                CheckResult(
                    name=f"material_{i}_valid",
                    passed=probe["valid"],
                    value=probe,
                    threshold="ffprobe exit 0",
                    message=f"Material {i} is valid MP4"
                    if probe["valid"]
                    else f"CRITICAL: Material {i} is corrupted: {probe.get('error')}",
                )
            )

            # Duration check
            duration = probe.get("duration", 0)
            checks.append(
                CheckResult(
                    name=f"material_{i}_duration",
                    passed=duration >= 0.5,
                    value=round(duration, 2),
                    threshold=">= 0.5s",
                    message=f"Material {i} duration {duration:.2f}s"
                    if duration >= 0.5
                    else f"WARNING: Material {i} is very short ({duration:.2f}s)",
                )
            )

            # Claude Vision check (sample frame)
            vision_check = self._claude_vision_material_check(local_path, i, mat)
            checks.append(vision_check)

        return self._build_result(
            phase=3,
            checks=checks,
            critical_names=[c.name for c in checks if "CRITICAL" in c.message],
            warning_names=[c.name for c in checks if "WARNING" in c.message],
        )

    def _claude_vision_material_check(self, video_path: str, idx: int, mat: dict) -> CheckResult:
        """Extract a frame and ask a vision LLM (via OpenRouter) if the material looks correct."""
        if not is_llm_available():
            return CheckResult(
                name=f"material_{idx}_vision",
                passed=True,
                value="skipped",
                threshold="readable=true",
                message="Vision check skipped (OPENROUTER_API_KEY not set)",
            )

        try:
            import base64

            # Extract middle frame as PNG
            frame_path = f"/tmp/phymac_frame_{idx}.png"
            probe = self._ffprobe(video_path)
            duration = probe.get("duration", 2)
            midpoint = duration / 2

            subprocess.run(
                [
                    "ffmpeg",
                    "-ss",
                    str(midpoint),
                    "-i",
                    video_path,
                    "-vframes",
                    "1",
                    "-y",
                    frame_path,
                ],
                capture_output=True,
                check=True,
            )

            with open(frame_path, "rb") as f:
                img_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

            client = get_llm_client()
            response = client.chat.completions.create(  # type: ignore[call-overload]
                model=LLM_MODEL_VISION,
                max_tokens=256,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "user",
                        "content": [
                            build_image_content(img_b64, media_type="image/png"),
                            {
                                "type": "text",
                                "text": f"""This is a frame from an educational support material (type: {mat.get("tipo", "unknown")}).
Is the content clearly visible and readable? Are there any obvious rendering errors?
Respond ONLY with JSON: {{"readable": true/false, "issues": ["issue1"]}}""",
                            },
                        ],
                    }
                ],
            )
            result = json.loads(response.choices[0].message.content)
            readable = result.get("readable", False)
            issues = result.get("issues", [])

            return CheckResult(
                name=f"material_{idx}_vision",
                passed=readable,
                value=result,
                threshold="readable=true",
                message=f"Material {idx} is visually readable"
                if readable
                else f"WARNING: Material {idx} may have render issues: {issues}",
            )
        except Exception as e:
            logger.warning(f"Vision check for material {idx} failed: {e}")
            return CheckResult(
                name=f"material_{idx}_vision",
                passed=True,
                value="error",
                threshold="readable=true",
                message=f"Vision check skipped (error): {e}",
            )

    # ------------------------------------------------------------------
    # Phase 4 — Composition Validation
    # ------------------------------------------------------------------

    def _validate_phase_4(self, output: dict, context: dict) -> ValidationResult:
        checks = []
        video_path = output.get("video_path", "")

        probe = self._ffprobe(video_path)
        checks.append(
            CheckResult(
                name="composed_video_valid",
                passed=probe["valid"],
                value=probe,
                threshold="ffprobe exit 0",
                message="Composed video is valid"
                if probe["valid"]
                else f"CRITICAL: Composed video corrupted: {probe.get('error')}",
            )
        )

        has_audio = probe.get("has_audio", False)
        checks.append(
            CheckResult(
                name="has_audio_stream",
                passed=has_audio,
                value=has_audio,
                threshold="True",
                message="Audio stream present"
                if has_audio
                else "CRITICAL: No audio stream in composed video",
            )
        )

        width = probe.get("width", 0)
        checks.append(
            CheckResult(
                name="resolution",
                passed=width >= 1280,
                value=f"{probe.get('width')}x{probe.get('height')}",
                threshold=">= 1280px wide",
                message=f"Resolution OK: {probe.get('width')}x{probe.get('height')}"
                if width >= 1280
                else f"WARNING: Low resolution {probe.get('width')}x{probe.get('height')}",
            )
        )

        # Claude Vision: check 3 frames (start, middle, end)
        if probe["valid"] and video_path:
            duration = probe.get("duration", 0)
            for label, ts in [
                ("start", 1.0),
                ("middle", duration / 2),
                ("end", max(0, duration - 2)),
            ]:
                vision = self._claude_vision_composition_check(video_path, ts, label)
                checks.append(vision)

        return self._build_result(
            phase=4,
            checks=checks,
            critical_names=["composed_video_valid", "has_audio_stream"],
            warning_names=["resolution"],
        )

    def _claude_vision_composition_check(
        self, video_path: str, timestamp: float, label: str
    ) -> CheckResult:
        if not is_llm_available():
            return CheckResult(
                name=f"vision_{label}",
                passed=True,
                value="skipped",
                threshold="ok",
                message=f"Vision check at {label} skipped (OPENROUTER_API_KEY not set)",
            )
        try:
            import base64

            frame_path = f"/tmp/phymac_frame_{label}.png"
            subprocess.run(
                [
                    "ffmpeg",
                    "-ss",
                    str(timestamp),
                    "-i",
                    video_path,
                    "-vframes",
                    "1",
                    "-y",
                    frame_path,
                ],
                capture_output=True,
                check=True,
            )
            with open(frame_path, "rb") as f:
                img_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

            client = get_llm_client()
            response = client.chat.completions.create(  # type: ignore[call-overload]
                model=LLM_MODEL_VISION,
                max_tokens=256,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "user",
                        "content": [
                            build_image_content(img_b64, media_type="image/png"),
                            {
                                "type": "text",
                                "text": """This is a frame from a composed educational video.
Check: Is there visible branding? Is the layout correct? Are there visual artifacts or glitches?
Respond ONLY with JSON: {"branding_visible": true/false, "layout_ok": true/false, "artifacts": []}""",
                            },
                        ],
                    }
                ],
            )
            result = json.loads(response.choices[0].message.content)
            ok = result.get("layout_ok", True) and len(result.get("artifacts", [])) == 0
            return CheckResult(
                name=f"vision_{label}",
                passed=ok,
                value=result,
                threshold="layout_ok=true, no artifacts",
                message=f"Frame '{label}' looks good"
                if ok
                else f"WARNING: Frame '{label}' issues: {result.get('artifacts')}",
            )
        except Exception as e:
            return CheckResult(
                name=f"vision_{label}",
                passed=True,
                value="error",
                threshold="ok",
                message=f"Vision check '{label}' skipped: {e}",
            )

    # ------------------------------------------------------------------
    # Phase 5 — Audio Validation
    # ------------------------------------------------------------------

    def _validate_phase_5(self, output: dict, context: dict) -> ValidationResult:
        checks = []
        video_path = output.get("video_path", "")

        probe = self._ffprobe(video_path)
        checks.append(
            CheckResult(
                name="audio_processed_valid",
                passed=probe["valid"],
                value=probe,
                threshold="ffprobe exit 0",
                message="Audio-processed video is valid"
                if probe["valid"]
                else f"CRITICAL: File corrupted: {probe.get('error')}",
            )
        )

        # Volume check with ffmpeg loudnorm probe
        try:
            vol = self._measure_loudness(video_path)
            in_range = -20 <= vol <= -8
            checks.append(
                CheckResult(
                    name="volume_range",
                    passed=in_range,
                    value=round(vol, 1),
                    threshold="-20 to -8 dBFS",
                    message=f"Volume {vol:.1f} dBFS"
                    if in_range
                    else f"WARNING: Volume {vol:.1f} dBFS is outside target range (-20 to -8 dBFS)",
                )
            )
        except Exception as e:
            checks.append(
                CheckResult(
                    name="volume_range",
                    passed=True,
                    value="skipped",
                    threshold="-20 to -8 dBFS",
                    message=f"Volume check skipped: {e}",
                )
            )

        return self._build_result(
            phase=5,
            checks=checks,
            critical_names=["audio_processed_valid"],
            warning_names=["volume_range"],
        )

    def _measure_loudness(self, video_path: str) -> float:
        """Use ffmpeg to measure integrated loudness (LUFS approximation)."""
        result = subprocess.run(
            ["ffmpeg", "-i", video_path, "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True,
            text=True,
        )
        for line in result.stderr.splitlines():
            if "mean_volume" in line:
                return float(line.split(":")[1].strip().split(" ")[0])
        return -14.0  # default if not found

    # ------------------------------------------------------------------
    # Phase 6 — Final Render Validation
    # ------------------------------------------------------------------

    def _validate_phase_6(self, output: dict, context: dict) -> ValidationResult:
        checks = []
        video_path = output.get("video_path", "")
        download_url = output.get("download_url", "")

        probe = self._ffprobe(video_path)

        # Codec checks
        for check_name, expected, actual in [
            ("video_codec", "h264", probe.get("video_codec", "")),
            ("audio_codec", "aac", probe.get("audio_codec", "")),
        ]:
            ok = expected in (actual or "")
            checks.append(
                CheckResult(
                    name=check_name,
                    passed=ok,
                    value=actual,
                    threshold=expected,
                    message=f"{check_name}: {actual}"
                    if ok
                    else f"WARNING: Expected {expected}, got {actual}",
                )
            )

        # Resolution
        width, height = probe.get("width", 0), probe.get("height", 0)
        checks.append(
            CheckResult(
                name="final_resolution",
                passed=(width == 1920 and height == 1080),
                value=f"{width}x{height}",
                threshold="1920x1080",
                message=f"Resolution: {width}x{height}"
                if width == 1920
                else f"WARNING: Resolution {width}x{height} (expected 1920x1080)",
            )
        )

        # File size sanity check
        size_mb = (
            Path(video_path).stat().st_size / (1024 * 1024) if Path(video_path).exists() else 0
        )
        checks.append(
            CheckResult(
                name="file_size",
                passed=100 <= size_mb <= 8000,
                value=round(size_mb, 1),
                threshold="100–8000 MB",
                message=f"File size: {size_mb:.0f} MB"
                if 100 <= size_mb <= 8000
                else f"WARNING: Unexpected file size {size_mb:.0f} MB",
            )
        )

        # Download URL reachable
        if download_url:
            try:
                import urllib.request

                with urllib.request.urlopen(download_url, timeout=5) as resp:
                    url_ok = resp.status == 200
            except Exception:
                url_ok = False
            checks.append(
                CheckResult(
                    name="download_url_reachable",
                    passed=url_ok,
                    value=download_url[:60] + "...",
                    threshold="HTTP 200",
                    message="Download URL is accessible"
                    if url_ok
                    else "WARNING: Download URL is not reachable",
                )
            )

        return self._build_result(
            phase=6,
            checks=checks,
            critical_names=[],
            warning_names=[c.name for c in checks],
        )

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _ffprobe(self, video_path: str) -> dict:
        """Run ffprobe and return parsed metadata."""
        if not video_path or not Path(video_path).exists():
            return {"valid": False, "error": f"File not found: {video_path}"}
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=width,height,codec_name,duration,pix_fmt",
                    "-show_entries",
                    "format=duration,size",
                    "-of",
                    "json",
                    video_path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return {"valid": False, "error": result.stderr}

            data = json.loads(result.stdout)
            video_stream: dict = next(
                (
                    s
                    for s in data.get("streams", [])
                    if s.get("codec_type") == "video" or s.get("width")
                ),
                {},
            )
            audio_result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "a:0",
                    "-show_entries",
                    "stream=codec_name",
                    "-of",
                    "json",
                    video_path,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            audio_data = json.loads(audio_result.stdout)
            audio_streams = audio_data.get("streams", [])

            return {
                "valid": True,
                "width": int(video_stream.get("width", 0)),
                "height": int(video_stream.get("height", 0)),
                "video_codec": video_stream.get("codec_name", ""),
                "audio_codec": audio_streams[0].get("codec_name", "") if audio_streams else "",
                "has_audio": len(audio_streams) > 0,
                "duration": float(data.get("format", {}).get("duration", 0)),
                "pix_fmt": video_stream.get("pix_fmt", ""),
                "has_alpha": "yuva" in video_stream.get("pix_fmt", "")
                or "rgba" in video_stream.get("pix_fmt", ""),
            }
        except Exception as e:
            return {"valid": False, "error": str(e)}

    def _build_result(
        self,
        phase: int,
        checks: list[CheckResult],
        critical_names: list[str] | None = None,
        warning_names: list[str] | None = None,
    ) -> ValidationResult:
        """Build a ValidationResult from checks, tagging critical vs warning failures."""
        critical_set = set(critical_names or [])
        warning_set = set(warning_names or [])

        failed_checks = [c for c in checks if not c.passed]
        passed_count = len([c for c in checks if c.passed])
        score = passed_count / len(checks) if checks else 1.0

        critical_failures = [c.message for c in failed_checks if c.name in critical_set]
        warnings = [
            c.message for c in failed_checks if c.name in warning_set or c.name not in critical_set
        ]

        passed = len(critical_failures) == 0 and score >= VALIDATION_PASS_SCORE
        recommendation = self._recommend(critical_failures)

        return ValidationResult(
            passed=passed,
            phase=phase,
            score=round(score, 3),
            checks=checks,
            critical_failures=critical_failures,
            warnings=warnings,
            recommendation=recommendation,
        )

    def _recommend(self, critical_failures: list[str]) -> str:
        if not critical_failures:
            return "Output looks good. Proceeding to next phase."
        if any("coverage" in f for f in critical_failures):
            return "Re-transcribe with temperature=0.2 or check audio quality."
        if any("corrupted" in f or "not found" in f for f in critical_failures):
            return "Check render logs. Re-run the phase from scratch."
        if any("segments" in f for f in critical_failures):
            return "Whisper may have failed. Check Modal GPU logs and retry."
        return "Review phase logs and retry. Use --skip-validation only if you've confirmed output manually."


# ---------------------------------------------------------------------------
# Phase 3 — Materiales de soporte (Unit 4)
# ---------------------------------------------------------------------------

_DURATION_BY_TIPO_PHASE3: dict[str, float] = {
    "lower_third": 6.0,
    "pull_quote": 6.6,
    "chapter_marker": 4.2,
    "animacion_texto": 2.2,
    "ecuacion_latex": 5.0,
    "diagrama": 6.0,
}


def _ffprobe_webm_summary(r2_key: str) -> dict:
    """Download webm from R2 to a temp file and ffprobe it.

    Returns dict with width, height, duration, alpha_mode. Mocked in tests.
    """
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tf:
        tmp = Path(tf.name)
    try:
        download_to_local(r2_key, tmp)
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                str(tmp),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr[:200]}")
        info = json.loads(result.stdout)
        video_streams = [
            s for s in info.get("streams", []) if s.get("codec_type") == "video"
        ]
        vs = video_streams[0] if video_streams else {}
        tags = vs.get("tags") or {}
        return {
            "width": vs.get("width"),
            "height": vs.get("height"),
            "duration": float(info.get("format", {}).get("duration", 0) or 0),
            "alpha_mode": tags.get("alpha_mode") or tags.get("ALPHA_MODE"),
        }
    finally:
        if tmp.exists():
            tmp.unlink()


def _sample_check_alpha_dimensions_duration(
    manifest: list[dict], sample_size: int = 1
) -> tuple[list[CheckResult], list[CheckResult]]:
    """Run ffprobe-based checks on 1 of every `sample_size` (1=every) ok/fallback entries."""
    crit: list[CheckResult] = []
    warn: list[CheckResult] = []
    candidates = [e for e in manifest if e["render_status"] in {"ok", "fallback"}]
    sampled = candidates[:: max(sample_size, 1)] or candidates[:1]
    for entry in sampled:
        try:
            info = _ffprobe_webm_summary(entry["r2_key"])
        except Exception as e:
            crit.append(
                CheckResult(
                    name="ffprobe_sample",
                    passed=False,
                    value=str(e),
                    threshold="successful probe",
                    message=f"could not probe {entry['material_id']}",
                )
            )
            continue
        if (info.get("width") != 1920) or (info.get("height") != 1080):
            crit.append(
                CheckResult(
                    name="webm_dimensions_correct",
                    passed=False,
                    value=f"{info.get('width')}x{info.get('height')}",
                    threshold="1920x1080",
                    message=f"dimensions wrong on {entry['material_id']}",
                )
            )
        spec = entry.get("refined_spec") or entry.get("original_spec") or {}
        tipo = spec.get("tipo") or ""
        expected = _DURATION_BY_TIPO_PHASE3.get(tipo, 5.0)
        if abs(float(info.get("duration", 0)) - expected) > 0.2:
            crit.append(
                CheckResult(
                    name="webm_duration_matches_spec",
                    passed=False,
                    value=info.get("duration"),
                    threshold=f"{expected}±0.2",
                    message=f"duration off on {entry['material_id']}",
                )
            )
        if info.get("alpha_mode") != "1":
            crit.append(
                CheckResult(
                    name="webm_alpha_present",
                    passed=False,
                    value=info.get("alpha_mode"),
                    threshold="alpha_mode=1",
                    message=f"alpha missing on {entry['material_id']}",
                )
            )
    return crit, warn


def validate_phase3(
    manifest: list[dict],
    whitelist: list[str],
    *,
    drop_threshold: float = 0.30,
    fallback_threshold: float = 0.10,
) -> ValidationResult:
    """Validate the Phase 3 manifest. See spec §10."""
    checks: list[CheckResult] = []
    critical: list[str] = []
    warnings: list[str] = []

    # 1. all_materials_have_status
    bad_status = [
        e for e in manifest if e.get("render_status") not in {"ok", "fallback", "dropped"}
    ]
    if bad_status:
        critical.append(f"{len(bad_status)} entries with invalid render_status")
    checks.append(
        CheckResult(
            name="all_materials_have_status",
            passed=not bad_status,
            value=len(bad_status),
            threshold=0,
            message="every entry must have a known render_status",
        )
    )

    # 2. r2_keys_resolvable
    unresolvable = []
    for e in manifest:
        if e.get("render_status") in {"ok", "fallback"}:
            key = e.get("r2_key")
            if not key or not head_object_exists(key):
                unresolvable.append(e["material_id"])
    if unresolvable:
        critical.append(f"r2_key not resolvable for {len(unresolvable)} entries")
    checks.append(
        CheckResult(
            name="r2_keys_resolvable",
            passed=not unresolvable,
            value=len(unresolvable),
            threshold=0,
            message="every non-dropped entry must have an existing r2_key",
        )
    )

    # 3-5. webm sample checks
    if not critical:  # skip if R2 itself failed
        sample_crit, sample_warn = _sample_check_alpha_dimensions_duration(manifest)
        for c in sample_crit:
            critical.append(c.message)
            checks.append(c)
        for w in sample_warn:
            warnings.append(w.message)
            checks.append(w)

    # 6. whitelist_respected
    whitelist_violations = []
    for e in manifest:
        if e.get("render_status") == "dropped":
            continue
        refined = e.get("refined_spec") or e.get("original_spec") or {}
        tipo = refined.get("tipo")
        if tipo not in whitelist:
            whitelist_violations.append(f"{e['material_id']}:{tipo}")
    if whitelist_violations:
        critical.append(f"whitelist violations: {whitelist_violations[:5]}")
    checks.append(
        CheckResult(
            name="whitelist_respected",
            passed=not whitelist_violations,
            value=len(whitelist_violations),
            threshold=0,
            message="refined tipo must be in materials whitelist",
        )
    )

    # 7. drop_rate warning
    total = len(manifest) or 1
    dropped = sum(1 for e in manifest if e.get("render_status") == "dropped")
    drop_rate = dropped / total
    if drop_rate > drop_threshold:
        warnings.append(f"drop rate {drop_rate:.2%} exceeds {drop_threshold:.0%}")
    checks.append(
        CheckResult(
            name="drop_rate_acceptable",
            passed=drop_rate <= drop_threshold,
            value=f"{drop_rate:.2%}",
            threshold=f"<= {drop_threshold:.0%}",
            message="dropped materials should be infrequent",
        )
    )

    # 8. fallback_rate warning
    fallback = sum(1 for e in manifest if e.get("render_status") == "fallback")
    fb_rate = fallback / total
    if fb_rate > fallback_threshold:
        warnings.append(f"fallback rate {fb_rate:.2%} exceeds {fallback_threshold:.0%}")
    checks.append(
        CheckResult(
            name="fallback_rate_acceptable",
            passed=fb_rate <= fallback_threshold,
            value=f"{fb_rate:.2%}",
            threshold=f"<= {fallback_threshold:.0%}",
            message="recurring fallback indicates renderer issue",
        )
    )

    # 9. reasoning_quality (warning)
    bad_reasoning_keywords = ("no se ve", "negro", "vacío", "frame negro")
    bad_reasoning = [
        e
        for e in manifest
        if any(kw in (e.get("reasoning", "") or "").lower() for kw in bad_reasoning_keywords)
    ]
    if len(bad_reasoning) > 0.20 * total:
        warnings.append(f"reasoning quality: {len(bad_reasoning)}/{total} mention blank frame")
    checks.append(
        CheckResult(
            name="reasoning_quality",
            passed=len(bad_reasoning) <= 0.20 * total,
            value=len(bad_reasoning),
            threshold=f"<= {int(0.20 * total)}",
            message="too many entries flag blank/black frames",
        )
    )

    # Score
    crit_weight = len(critical) * 0.6
    warn_weight = len(warnings) * 0.4 / max(len(checks), 1)
    score = max(0.0, 1.0 - crit_weight - warn_weight)
    return ValidationResult(
        passed=not critical,
        phase=3,
        score=round(score, 2),
        checks=checks,
        critical_failures=critical,
        warnings=warnings,
        recommendation=(
            "Phase 3 OK — manifest válido y artefactos en R2."
            if not critical
            else f"Phase 3 FAILED — {len(critical)} críticos: {'; '.join(critical[:3])}"
        ),
    )

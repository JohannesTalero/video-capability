"""
Domain models for PhyMaC Video Auto-Edit Pipeline.
All dataclasses shared across pipeline phases.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ProjectStatus(str, Enum):
    CREATED   = "created"
    RUNNING   = "running"
    PAUSED    = "paused"
    COMPLETED = "completed"
    FAILED    = "failed"


class PhaseStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@dataclass
class CheckResult:
    name: str
    passed: bool
    value: Any
    threshold: Any
    message: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "value": str(self.value),
            "threshold": str(self.threshold),
            "message": self.message,
        }


@dataclass
class ValidationResult:
    passed: bool
    phase: int
    score: float
    checks: list[CheckResult] = field(default_factory=list)
    critical_failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommendation: str = ""

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "phase": self.phase,
            "score": self.score,
            "checks": [c.to_dict() for c in self.checks],
            "critical_failures": self.critical_failures,
            "warnings": self.warnings,
            "recommendation": self.recommendation,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ValidationResult":
        checks = [CheckResult(**c) for c in d.get("checks", [])]
        return cls(
            passed=d["passed"],
            phase=d["phase"],
            score=d["score"],
            checks=checks,
            critical_failures=d.get("critical_failures", []),
            warnings=d.get("warnings", []),
            recommendation=d.get("recommendation", ""),
        )


# ---------------------------------------------------------------------------
# Phase State
# ---------------------------------------------------------------------------

@dataclass
class PhaseState:
    phase_num: int
    status: PhaseStatus
    attempt: int = 0
    started_at: str | None = None       # ISO string
    completed_at: str | None = None     # ISO string
    outputs: dict[str, Any] = field(default_factory=dict)
    validation: ValidationResult | None = None
    error_message: str | None = None

    def to_dict(self) -> dict:
        return {
            "phase_num": self.phase_num,
            "status": self.status.value,
            "attempt": self.attempt,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "outputs": self.outputs,
            "validation": self.validation.to_dict() if self.validation else None,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PhaseState":
        validation = None
        if d.get("validation"):
            validation = ValidationResult.from_dict(d["validation"])
        return cls(
            phase_num=d["phase_num"],
            status=PhaseStatus(d["status"]),
            attempt=d.get("attempt", 0),
            started_at=d.get("started_at"),
            completed_at=d.get("completed_at"),
            outputs=d.get("outputs", {}),
            validation=validation,
            error_message=d.get("error_message"),
        )


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

@dataclass
class Project:
    project_id: str
    title: str
    brand_id: str
    format_id: str          # e.g. "podcast_hablando_con_profes"
    video_original_key: str
    created_at: str     # ISO string
    updated_at: str     # ISO string
    current_phase: int
    status: ProjectStatus

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "title": self.title,
            "brand_id": self.brand_id,
            "format_id": self.format_id,
            "video_original_key": self.video_original_key,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "current_phase": self.current_phase,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        # Backward compat: older state.json files written before Phase 2
        # do not have format_id — fall back to the configured default.
        from pipeline.config import DEFAULT_FORMAT_ID
        return cls(
            project_id=d["project_id"],
            title=d["title"],
            brand_id=d.get("brand_id", "phymac"),
            format_id=d.get("format_id", DEFAULT_FORMAT_ID),
            video_original_key=d["video_original_key"],
            created_at=d["created_at"],
            updated_at=d["updated_at"],
            current_phase=d["current_phase"],
            status=ProjectStatus(d["status"]),
        )


@dataclass
class ProjectState:
    project: Project
    phases: dict[int, PhaseState]

    def last_completed_phase(self) -> int:
        completed = [n for n, p in self.phases.items() if p.status == PhaseStatus.COMPLETED]
        return max(completed) if completed else 0

    def next_pending_phase(self) -> int | None:
        pending = [n for n, p in self.phases.items() if p.status == PhaseStatus.PENDING]
        return min(pending) if pending else None

    def get_output(self, phase_num: int, key: str) -> str | None:
        phase = self.phases.get(phase_num)
        return phase.outputs.get(key) if phase else None

    def to_dict(self) -> dict:
        return {
            "project": self.project.to_dict(),
            "phases": {str(k): v.to_dict() for k, v in self.phases.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ProjectState":
        project = Project.from_dict(d["project"])
        phases = {int(k): PhaseState.from_dict(v) for k, v in d["phases"].items()}
        return cls(project=project, phases=phases)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, s: str) -> "ProjectState":
        return cls.from_dict(json.loads(s))


# ---------------------------------------------------------------------------
# Storage Key Convention
# ---------------------------------------------------------------------------

class StorageKey:
    """Centralized path convention for R2/S3 storage. No hardcoded paths elsewhere."""

    @staticmethod
    def project_state(project_id: str) -> str:
        return f"projects/{project_id}/state.json"

    @staticmethod
    def original_video(project_id: str, filename: str) -> str:
        return f"projects/{project_id}/input/{filename}"

    @staticmethod
    def extracted_audio(project_id: str) -> str:
        return f"projects/{project_id}/phase1/audio.wav"

    @staticmethod
    def transcription(project_id: str) -> str:
        return f"projects/{project_id}/phase1/transcription.json"

    @staticmethod
    def narrative_plan(project_id: str) -> str:
        return f"projects/{project_id}/phase2/plan.json"

    @staticmethod
    def material_asset(project_id: str, block_id: str, item_idx: int) -> str:
        return f"projects/{project_id}/phase3/materials/{block_id}_{item_idx}.mp4"

    @staticmethod
    def composed_video(project_id: str) -> str:
        return f"projects/{project_id}/phase4/composed.mp4"

    @staticmethod
    def audio_processed_video(project_id: str) -> str:
        return f"projects/{project_id}/phase5/audio_processed.mp4"

    @staticmethod
    def final_video(project_id: str) -> str:
        return f"projects/{project_id}/phase6/final.mp4"

    @staticmethod
    def brand_config(brand_id: str) -> str:
        return f"brands/{brand_id}/config.json"

    @staticmethod
    def brand_asset(brand_id: str, asset_name: str) -> str:
        return f"brands/{brand_id}/{asset_name}"


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------

@dataclass
class TranscriptionSegment:
    id: int
    start: float
    end: float
    text: str
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TranscriptionResult:
    project_id: str
    segments: list[TranscriptionSegment]
    full_text: str
    duration_seconds: float
    language: str
    model: str
    storage_key: str

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "segments": [s.to_dict() for s in self.segments],
            "full_text": self.full_text,
            "duration_seconds": self.duration_seconds,
            "language": self.language,
            "model": self.model,
            "storage_key": self.storage_key,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "TranscriptionResult":
        segments = [TranscriptionSegment(**s) for s in d["segments"]]
        return cls(
            project_id=d["project_id"],
            segments=segments,
            full_text=d["full_text"],
            duration_seconds=d["duration_seconds"],
            language=d["language"],
            model=d["model"],
            storage_key=d["storage_key"],
        )

    @classmethod
    def from_json(cls, s: str) -> "TranscriptionResult":
        return cls.from_dict(json.loads(s))


# ---------------------------------------------------------------------------
# Narrative Plan
# ---------------------------------------------------------------------------

@dataclass
class MaterialSpec:
    tipo: str   # validated against the format's materials_whitelist
    contenido: str
    timestamp_relativo: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Block:
    id: str
    name: str
    segments: list[int]
    estimated_duration: str
    support_material: list[MaterialSpec]
    transition_next: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "segments": self.segments,
            "estimated_duration": self.estimated_duration,
            "support_material": [m.to_dict() for m in self.support_material],
            "transition_next": self.transition_next,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Block":
        # Tolerate extra keys (LLM-generated dicts sometimes carry fields
        # we don't model) — keep only what MaterialSpec accepts.
        allowed = {"tipo", "contenido", "timestamp_relativo", "metadata"}
        material = [
            MaterialSpec(**{k: v for k, v in m.items() if k in allowed})
            for m in d.get("support_material", [])
        ]
        return cls(
            id=d["id"],
            name=d["name"],
            segments=d["segments"],
            estimated_duration=d.get("estimated_duration", ""),
            support_material=material,
            transition_next=d.get("transition_next", "corte_directo"),
        )


@dataclass
class NarrativePlan:
    project_id: str
    blocks: list[Block]
    storage_key: str = ""

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "blocks": [b.to_dict() for b in self.blocks],
            "storage_key": self.storage_key,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "NarrativePlan":
        blocks = [Block.from_dict(b) for b in d["blocks"]]
        return cls(
            project_id=d["project_id"],
            blocks=blocks,
            storage_key=d.get("storage_key", ""),
        )

    @classmethod
    def from_json(cls, s: str) -> "NarrativePlan":
        return cls.from_dict(json.loads(s))


# ---------------------------------------------------------------------------
# Material Asset
# ---------------------------------------------------------------------------

@dataclass
class MaterialAsset:
    block_id: str
    item_index: int
    spec: MaterialSpec
    storage_key: str
    duration_seconds: float
    has_alpha: bool
    width: int
    height: int

    def to_dict(self) -> dict:
        return {
            "block_id": self.block_id,
            "item_index": self.item_index,
            "spec": self.spec.to_dict(),
            "storage_key": self.storage_key,
            "duration_seconds": self.duration_seconds,
            "has_alpha": self.has_alpha,
            "width": self.width,
            "height": self.height,
        }


# ---------------------------------------------------------------------------
# Brand Config
# ---------------------------------------------------------------------------

@dataclass
class BrandColors:
    primary: str
    secondary: str
    accent: str
    text: str

@dataclass
class BrandFonts:
    heading: str
    body: str

@dataclass
class BrandAssets:
    logo: str
    intro: str
    outro: str
    lower_third: str
    cortinillas: dict[str, str] = field(default_factory=dict)

@dataclass
class BrandConfig:
    brand_id: str
    display_name: str
    colors: BrandColors
    fonts: BrandFonts
    assets: BrandAssets

    @classmethod
    def from_dict(cls, d: dict) -> "BrandConfig":
        return cls(
            brand_id=d["brand_id"],
            display_name=d["display_name"],
            colors=BrandColors(**d["colors"]),
            fonts=BrandFonts(**d["fonts"]),
            assets=BrandAssets(**d["assets"]),
        )


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

@dataclass
class RenderConfig:
    resolution: str = "1920x1080"
    fps: int = 30
    video_codec: str = "libx264"
    crf: int = 18
    preset: str = "slow"
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"


@dataclass
class RenderResult:
    project_id: str
    storage_key: str
    download_url: str
    file_size_mb: float
    duration_seconds: float
    render_time_seconds: float

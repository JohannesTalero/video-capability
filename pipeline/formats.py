"""
Format registry — single source of truth for per-format LLM prompts and
material whitelists used across the pipeline (Phase 2 narrative planner,
Phase 4 branding, Phase 5 audio — anywhere format-specific behavior lives).

A "format" is a content shape (podcast interview, expository class, tutorial,
ad spot) that determines the editorial logic of the narrative plan and the
catalog of support materials allowed.

Each format lives in `formats/<format_id>/` at the repo root and contains:
  - format.json              metadata (id, name, version, description)
  - narrative_prompt.md      system prompt for the Phase 2 LLM call
  - materials_whitelist.json {"allowed": ["lower_third", ...]}

Loaders are memoized so repeated load_format() calls are cheap.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

FORMATS_ROOT = Path(__file__).parent.parent / "formats"


class FormatNotFoundError(Exception):
    """Raised when a format_id does not have a corresponding folder."""


class FormatConfigError(Exception):
    """Raised when a format folder is malformed (missing files, bad JSON)."""


@dataclass(frozen=True)
class FormatConfig:
    format_id: str
    name: str
    version: str
    description: str
    narrative_prompt: str
    materials_whitelist: tuple[str, ...]  # frozen for hashability


@lru_cache(maxsize=16)
def load_format(format_id: str) -> FormatConfig:
    """
    Load `formats/<format_id>/` from disk and return a FormatConfig.
    Cached — repeated calls return the same instance.

    Raises:
        FormatNotFoundError: if the folder does not exist.
        FormatConfigError:   if any required file is missing or malformed.
    """
    base = FORMATS_ROOT / format_id
    if not base.is_dir():
        raise FormatNotFoundError(f"Unknown format_id '{format_id}'. Expected folder: {base}")

    meta_path = base / "format.json"
    prompt_path = base / "narrative_prompt.md"
    whitelist_path = base / "materials_whitelist.json"

    for p in (meta_path, prompt_path, whitelist_path):
        if not p.is_file():
            raise FormatConfigError(f"Format '{format_id}' is missing required file: {p.name}")

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        whitelist_data = json.loads(whitelist_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise FormatConfigError(f"Format '{format_id}' has invalid JSON: {e}") from e

    prompt = prompt_path.read_text(encoding="utf-8")

    allowed = whitelist_data.get("allowed")
    if not isinstance(allowed, list) or not all(isinstance(x, str) for x in allowed):
        raise FormatConfigError(
            f"Format '{format_id}' materials_whitelist.json must have "
            "'allowed' as a list of strings."
        )

    for required in ("format_id", "name", "version", "description"):
        if required not in meta:
            raise FormatConfigError(f"Format '{format_id}' format.json missing field: {required}")

    if meta["format_id"] != format_id:
        raise FormatConfigError(
            f"Format folder '{format_id}' has mismatched format_id in "
            f"format.json: {meta['format_id']!r}"
        )

    logger.debug(f"Loaded format: {format_id} v{meta['version']}")

    return FormatConfig(
        format_id=meta["format_id"],
        name=meta["name"],
        version=meta["version"],
        description=meta["description"],
        narrative_prompt=prompt,
        materials_whitelist=tuple(allowed),
    )

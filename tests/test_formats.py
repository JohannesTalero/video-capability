"""Unit tests for pipeline.formats.load_format()."""
from __future__ import annotations

import pytest

from pipeline.formats import (
    FormatConfig,
    FormatNotFoundError,
    load_format,
)


def test_load_podcast_format_returns_config():
    """The shipped podcast format loads and exposes its prompt + whitelist."""
    fmt = load_format("podcast_hablando_con_profes")
    assert isinstance(fmt, FormatConfig)
    assert fmt.format_id == "podcast_hablando_con_profes"
    assert fmt.name and len(fmt.name) > 5
    assert fmt.version
    assert fmt.description
    # Prompt should be substantial — covers cold open rules, materials, etc.
    assert len(fmt.narrative_prompt) > 1000
    assert "Cold open" in fmt.narrative_prompt
    assert "transcript_fix" in fmt.narrative_prompt


def test_podcast_whitelist_contains_expected_tipos():
    fmt = load_format("podcast_hablando_con_profes")
    whitelist = set(fmt.materials_whitelist)
    expected = {
        "lower_third", "pull_quote", "chapter_marker",
        "animacion_texto", "transcript_fix",
    }
    assert whitelist == expected


def test_load_unknown_format_raises():
    with pytest.raises(FormatNotFoundError):
        load_format("does-not-exist-format-id")


def test_load_format_is_cached():
    """lru_cache should return the same instance for repeated calls."""
    a = load_format("podcast_hablando_con_profes")
    b = load_format("podcast_hablando_con_profes")
    assert a is b

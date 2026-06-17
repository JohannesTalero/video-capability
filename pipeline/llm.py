"""
LLM client helper — single source of truth for LLM calls in the pipeline.

All LLM traffic in the project goes through OpenRouter (https://openrouter.ai)
accessed via the OpenAI Python SDK with a custom base_url. One API key, many
providers (Anthropic, OpenAI, Google, Meta, etc.). Switching models is an
env-var change, not a code change.

Models per use case are read from pipeline.config:
  - LLM_MODEL_PLANNER   → NarrativePlanner (Phase 2)
  - LLM_MODEL_VALIDATOR → ValidationAgent text checks
  - LLM_MODEL_VISION    → ValidationAgent vision checks on rendered frames

Defaults are FREE models suitable for the early testing phase. Set the env
vars to paid model IDs (e.g. "anthropic/claude-sonnet-4.5") for production.
"""

from __future__ import annotations

from typing import Any

from openai import OpenAI

from pipeline.config import (
    OPENROUTER_API_KEY,
    OPENROUTER_APP_NAME,
    OPENROUTER_BASE_URL,
    OPENROUTER_SITE_URL,
)


class LLMNotConfiguredError(Exception):
    """Raised when OPENROUTER_API_KEY is missing and an LLM call is attempted."""


def get_llm_client() -> OpenAI:
    """
    Return an OpenAI SDK client configured for OpenRouter.

    Headers HTTP-Referer and X-Title are optional; OpenRouter uses them to
    attribute traffic in the dashboard. Empty values are accepted.
    """
    if not OPENROUTER_API_KEY:
        raise LLMNotConfiguredError(
            "OPENROUTER_API_KEY is not set. Add it to .env or export it.\n"
            "Get a key at: https://openrouter.ai/settings/keys"
        )

    default_headers: dict[str, str] = {}
    if OPENROUTER_SITE_URL:
        default_headers["HTTP-Referer"] = OPENROUTER_SITE_URL
    if OPENROUTER_APP_NAME:
        default_headers["X-Title"] = OPENROUTER_APP_NAME

    return OpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        default_headers=default_headers or None,
    )


def is_llm_available() -> bool:
    """Cheap check: does the env have an API key? Doesn't make any network call."""
    return bool(OPENROUTER_API_KEY)


def strip_code_fence(text: str) -> str:
    """Strip a leading/trailing markdown code fence from an LLM response.

    Some models (e.g. Claude via OpenRouter) wrap JSON in ```json ... ``` even
    when response_format=json_object is requested. Returns the inner content;
    if no fence is present, returns the text unchanged. Single source of truth
    for the whole pipeline (Phase 2 plan, validator LLM checks, vision planner).
    """
    s = text.strip()
    if not s.startswith("```"):
        return text
    s = s[3:]  # drop opening ```
    newline = s.find("\n")
    if newline != -1:
        s = s[newline + 1 :]  # drop the optional language tag line (e.g. "json")
    s = s.rstrip()
    if s.endswith("```"):
        s = s[:-3]
    return s.strip()


def build_image_content(img_b64: str, media_type: str = "image/png") -> dict[str, Any]:
    """
    Build an OpenAI-compatible image content block from base64 data.
    Use as: messages=[{"role":"user", "content":[build_image_content(b64), {"type":"text", "text": "..."}]}]
    """
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{media_type};base64,{img_b64}"},
    }

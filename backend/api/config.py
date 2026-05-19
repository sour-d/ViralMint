# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""REST /api/config — serve app config defaults to frontend."""
from fastapi import APIRouter, HTTPException

router = APIRouter()

_DEFAULTS = {
    "model_registry": {
        # Models verified May 2026. Anthropic / OpenAI defaults pick the
        # best price/perf tier; OpenRouter defaults to a premium model
        # because BYOK users routing through OpenRouter typically want
        # access to the top tier without juggling multiple provider keys.
        "anthropic": {
            "default_model": "claude-sonnet-4-6",
            "models": [
                "claude-haiku-4-5",
                "claude-sonnet-4-6",
                "claude-opus-4-6",
                "claude-opus-4-7",
            ],
        },
        "openai": {
            "default_model": "gpt-5.4-mini",
            "models": [
                "gpt-5.4-nano",
                "gpt-5.4-mini",
                "gpt-5.4",
                "gpt-5.5",
            ],
        },
        # OpenRouter slugs use the vendor/model format. Verified live
        # against https://openrouter.ai/api/v1/models on 2026-05-07. If
        # you want a model that isn't here, OpenRouter accepts any of its
        # published slugs — but the dropdown only exposes this curated
        # set so users don't have to guess.
        "openrouter": {
            "default_model": "anthropic/claude-opus-4.7",
            "models": [
                "anthropic/claude-opus-4.7",
                "anthropic/claude-opus-4.6-fast",
                "anthropic/claude-sonnet-4.6",
                "openai/gpt-5.5",
                "openai/gpt-5.4",
                "openai/gpt-5.4-mini",
                "google/gemini-3.1-pro-preview",
                "google/gemini-3.1-flash-lite",
                "openrouter/free",
                "nvidia/nemotron-3-super-120b-a12b:free",
                "openrouter/owl-alpha",
                "openai/gpt-oss-120b:free",
                "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
                "google/gemma-4-31b-it:free",
                ""
            ],
        },
    },
    "tts_providers": {
        "edge_tts":   {"label": "Edge TTS — Free",          "cost_1k": 0.0,   "requires_key": False},
        "openai_tts": {"label": "OpenAI TTS — Standard",    "cost_1k": 0.015, "requires_key": True},
    },
    "caption_styles": {
        "viral":   {"label": "Viral — word-by-word highlight", "words_per_group": 3},
        "classic": {"label": "Classic — full sentence",        "words_per_group": 8},
        "bold":    {"label": "Bold — 2-word highlight",        "words_per_group": 2},
        "none":    {"label": "No captions"},
    },
}


@router.get("/config/{key}")
async def get_config(key: str):
    """Return config for a given key."""
    value = _DEFAULTS.get(key)
    if value is None:
        raise HTTPException(status_code=404, detail=f"Unknown config key: {key}")
    return {"key": key, "value": value}

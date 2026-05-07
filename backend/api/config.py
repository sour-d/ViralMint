# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""REST /api/config — serve app config defaults to frontend."""
from fastapi import APIRouter, HTTPException

router = APIRouter()

_DEFAULTS = {
    "model_registry": {
        # Models verified May 2026. Defaults pick the best price/perf tier:
        # Sonnet for Anthropic, GPT-5.4 mini for OpenAI.
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

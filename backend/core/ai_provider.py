# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""
AI client factory — BYOK (Bring Your Own Key).

Supports Anthropic and OpenAI. Keys come from `.env` (system-wide default)
or per-user `UserSettings` (overrides env). No cloud-managed keys.
"""
from enum import Enum
from typing import AsyncIterator, Optional
import logging

from backend.config import settings
from backend.core.crypto import decrypt_safe
from backend.core.exceptions import AIKeyMissingError

logger = logging.getLogger(__name__)


class AIProvider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


PROVIDER_DEFAULTS = {
    AIProvider.ANTHROPIC: "claude-sonnet-4-6",
    AIProvider.OPENAI:    "gpt-5.4-mini",
}


class AIClient:
    """Universal AI client — same interface regardless of underlying provider."""

    def __init__(self, provider: AIProvider, api_key: str, model: Optional[str] = None):
        self.provider = provider
        self.api_key = api_key
        self.model = model or PROVIDER_DEFAULTS[provider]

    async def chat_stream(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> AsyncIterator[str]:
        """Yield text chunks as they stream in."""
        if self.provider == AIProvider.ANTHROPIC:
            async for chunk in self._anthropic_stream(messages, system, max_tokens):
                yield chunk
        elif self.provider == AIProvider.OPENAI:
            async for chunk in self._openai_stream(messages, system, max_tokens):
                yield chunk

    async def chat(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> str:
        """Non-streaming — returns full response string."""
        chunks = []
        async for chunk in self.chat_stream(messages, system, max_tokens):
            chunks.append(chunk)
        return "".join(chunks)

    # ── Provider implementations ──────────────────────────────────────────────

    async def _anthropic_stream(self, messages, system, max_tokens):
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=self.api_key)
        async with client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=system or "",
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def _openai_stream(self, messages, system, max_tokens):
        import openai
        client = openai.AsyncOpenAI(api_key=self.api_key, timeout=55.0)
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        # GPT-5+ and o-series reasoning models reject `max_tokens` and require
        # `max_completion_tokens` (OpenAI API change, late 2024). Older models
        # accept either, but we only ship gpt-5.x in the registry, so this
        # branch is the common path.
        m = self.model.lower()
        uses_completion_tokens = (
            m.startswith(("gpt-5", "o1", "o3", "o4"))
        )
        token_kwargs = (
            {"max_completion_tokens": max_tokens}
            if uses_completion_tokens
            else {"max_tokens": max_tokens}
        )

        stream = await client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            stream=True,
            **token_kwargs,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


# ── Factory ───────────────────────────────────────────────────────────────────

def _resolve_user_provider_and_key(user_settings) -> tuple[Optional[AIProvider], Optional[str]]:
    """Read provider preference and decrypted API key from UserSettings, if set."""
    if not user_settings:
        return None, None

    provider_str = (getattr(user_settings, "ai_provider", None) or "").lower().strip()
    encrypted_key = getattr(user_settings, "ai_api_key_encrypted", None)
    if not provider_str or not encrypted_key:
        return None, None

    try:
        provider = AIProvider(provider_str)
    except ValueError:
        return None, None

    api_key = decrypt_safe(encrypted_key) or ""
    return provider, api_key or None


def get_ai_client(user_settings=None, **_kwargs) -> AIClient:
    """
    Return a configured AI client.

    Resolution order:
      1. UserSettings.ai_provider + UserSettings.ai_api_key_encrypted (BYOK from UI)
      2. .env keys (ANTHROPIC_API_KEY then OPENAI_API_KEY)
      3. Raise AIKeyMissingError with setup instructions.
    """
    user_model = getattr(user_settings, "ai_model", None) if user_settings else None

    # 1. User-configured BYOK
    user_provider, user_key = _resolve_user_provider_and_key(user_settings)
    if user_provider and user_key:
        return AIClient(provider=user_provider, api_key=user_key, model=user_model)

    # 2. .env fallback
    if settings.ANTHROPIC_API_KEY:
        return AIClient(
            provider=AIProvider.ANTHROPIC,
            api_key=settings.ANTHROPIC_API_KEY,
            model=user_model,
        )
    if settings.OPENAI_API_KEY:
        return AIClient(
            provider=AIProvider.OPENAI,
            api_key=settings.OPENAI_API_KEY,
            model=user_model,
        )

    raise AIKeyMissingError(
        "No AI provider configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY in your .env, "
        "or configure your provider and key in Settings."
    )

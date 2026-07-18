# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""
AI client factory — BYOK (Bring Your Own Key).

Supports Anthropic, OpenAI, and OpenRouter. Keys come from `.env`
(system-wide default) or per-user `UserSettings` (overrides env). No
cloud-managed keys.

OpenRouter is a unified gateway that resells access to Claude / GPT /
Gemini / Llama / Mistral / etc. behind a single key. We talk to it via
the OpenAI-compatible chat-completions endpoint at
`https://openrouter.ai/api/v1`, with `model` set to a vendor-prefixed
slug like `anthropic/claude-opus-4.7`.
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
    OPENROUTER = "openrouter"


PROVIDER_DEFAULTS = {
    AIProvider.ANTHROPIC:  "claude-sonnet-4-6",
    AIProvider.OPENAI:     "gpt-5.4-mini",
    # OpenRouter BYOK users pay their own bill — default to a premium
    # model so the experience matches the gateway's value prop. Users
    # can pick a cheaper model in Settings → Model dropdown.
    AIProvider.OPENROUTER: "anthropic/claude-opus-4.7",
}

# OpenRouter's optional analytics headers — show up on the public model
# leaderboard at openrouter.ai/rankings. Harmless to send; helps us
# track how much OSS-variant traffic flows through the gateway.
_OPENROUTER_HEADERS = {
    "HTTP-Referer": "https://github.com/openclaw-easy/ViralMint",
    "X-Title": "ViralMint (OSS)",
}


def _to_anthropic_messages(messages: list[dict]) -> list[dict]:
    """
    Convert OpenAI-style chat messages to Anthropic format.

    Plain `content: str` passes through. OpenAI multimodal content arrays
    (`[{type:"text",text:...}, {type:"image_url", image_url:{url:"data:..."}}]`)
    get rewritten into Anthropic's `{type:"image", source:{type:"base64",
    media_type, data}}` blocks. URLs that aren't data URIs are sent through
    as Anthropic `{type:"image", source:{type:"url", url}}` (supported in
    recent SDK versions).
    """
    out: list[dict] = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str) or content is None:
            out.append(msg)
            continue
        if not isinstance(content, list):
            out.append(msg)
            continue
        new_blocks: list[dict] = []
        for block in content:
            btype = block.get("type")
            if btype == "text":
                new_blocks.append({"type": "text", "text": block.get("text", "")})
            elif btype == "image_url":
                url = (block.get("image_url") or {}).get("url", "")
                if url.startswith("data:") and ";base64," in url:
                    header, b64 = url.split(",", 1)
                    media_type = header.split(":", 1)[1].split(";", 1)[0]
                    new_blocks.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64},
                    })
                elif url:
                    new_blocks.append({
                        "type": "image",
                        "source": {"type": "url", "url": url},
                    })
            else:
                # Unknown block type — drop instead of breaking the API call.
                logger.debug("DEBUG:: dropping unknown content block type %r for Anthropic", btype)
        out.append({"role": msg.get("role", "user"), "content": new_blocks})
    return out


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
        elif self.provider == AIProvider.OPENROUTER:
            async for chunk in self._openrouter_stream(messages, system, max_tokens):
                yield chunk

    async def chat(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> str:
        """Non-streaming — returns full response string.

        Some OpenRouter free models don't stream reliably. If streaming
        returns empty, fall back to a non-streaming call.
        """
        chunks = []
        async for chunk in self.chat_stream(messages, system, max_tokens):
            chunks.append(chunk)
        result = "".join(chunks)
        if not result and self.provider == AIProvider.OPENROUTER:
            logger.info("Stream returned empty for %s — retrying non-streaming", self.model)
            result = await self._openrouter_chat(messages, system, max_tokens)
        return result

    # ── Provider implementations ──────────────────────────────────────────────

    async def _anthropic_stream(self, messages, system, max_tokens):
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=self.api_key)
        async with client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=system or "",
            messages=_to_anthropic_messages(messages),
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

    async def _openrouter_stream(self, messages, system, max_tokens):
        """OpenRouter is OpenAI-compatible — same client, different base URL."""
        import openai
        client = openai.AsyncOpenAI(
            api_key=self.api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers=_OPENROUTER_HEADERS,
            timeout=55.0,
        )
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        # OpenRouter normalises max_tokens vs max_completion_tokens internally
        # for downstream models, so we always send max_tokens here regardless
        # of which underlying provider is being routed to.
        stream = await client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            stream=True,
            max_tokens=max_tokens,
        )
        async for chunk in stream:
            # Defensive: OpenRouter sometimes emits keepalive chunks with
            # an empty `choices` array before real tokens start flowing.
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    async def _openrouter_chat(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> str:
        """Non-streaming OpenRouter call — fallback for free models."""
        import openai
        client = openai.AsyncOpenAI(
            api_key=self.api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers=_OPENROUTER_HEADERS,
            timeout=55.0,
        )
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        response = await client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            stream=False,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""


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
      2. .env keys (ANTHROPIC_API_KEY → OPENAI_API_KEY → OPENROUTER_API_KEY)
      3. Raise AIKeyMissingError with setup instructions.
    """
    user_model = getattr(user_settings, "ai_model", None) if user_settings else None

    # 1. User-configured BYOK
    user_provider, user_key = _resolve_user_provider_and_key(user_settings)
    if user_provider and user_key:
        return AIClient(provider=user_provider, api_key=user_key, model=user_model)

    # 2. .env fallback. Order is by historical precedence, not preference —
    # whichever key is set in the env wins. Users who want a different
    # default should configure it in Settings.
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
    if settings.OPENROUTER_API_KEY:
        return AIClient(
            provider=AIProvider.OPENROUTER,
            api_key=settings.OPENROUTER_API_KEY,
            model=user_model,
        )

    raise AIKeyMissingError(
        "No AI provider configured. Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or "
        "OPENROUTER_API_KEY in your .env, or configure your provider and key in Settings."
    )

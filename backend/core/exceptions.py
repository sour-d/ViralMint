# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Custom exception hierarchy for ViralMint."""
import json
import logging as _logging


def safe_json_loads(raw, default=None, logger=None):
    """Parse JSON safely. Returns *default* on failure instead of raising."""
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        if logger:
            logger.warning("safe_json_loads failed: %s", exc)
        return default


class ViralMintError(Exception):
    """Base exception."""
    pass


# ── Scout errors ──────────────────────────────────────────────────────────────
class ScoutError(ViralMintError):
    pass

class PlatformUnavailableError(ScoutError):
    """Scout platform (TikTok, Douyin) is temporarily unavailable."""
    pass

class CookieExpiredError(ScoutError):
    """Session cookie is expired or invalid."""
    pass

class QuotaExceededError(ScoutError):
    """API quota (YouTube) exceeded."""
    pass


# ── Download errors ───────────────────────────────────────────────────────────
class DownloadError(ViralMintError):
    pass

class RateLimitError(DownloadError):
    """HTTP 429 — platform rate limiting."""
    pass

class VideoUnavailableError(DownloadError):
    """Video is private, deleted, or region-blocked."""
    pass


# ── Generation errors ─────────────────────────────────────────────────────────
class GenerationError(ViralMintError):
    pass

class VoiceGenerationError(GenerationError):
    pass

class VideoGenerationError(GenerationError):
    pass


# ── Upload errors ─────────────────────────────────────────────────────────────
class UploadError(ViralMintError):
    pass

class UploadAuthError(UploadError):
    """OAuth token missing or expired."""
    pass


# ── AI errors ─────────────────────────────────────────────────────────────────
class AIProviderError(ViralMintError):
    pass

class AIKeyMissingError(AIProviderError):
    pass

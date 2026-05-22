# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
import secrets
import logging
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ───────────────────────────────────────────
    APP_NAME: str = "ViralMint"
    DEBUG: bool = True
    # Loopback by default. The README markets ViralMint as "100% local —
    # your scripts, transcripts, downloads, and generated videos never
    # leave your machine," and binding to 0.0.0.0 silently breaks that
    # promise: anyone on the same WiFi can reach your library, chat
    # sessions and (encrypted) credential store. Users who genuinely
    # want LAN access (e.g. driving the planner from a phone) can set
    # HOST=0.0.0.0 in their .env explicitly.
    HOST: str = "127.0.0.1"
    PORT: int = 16888
    SECRET_KEY: str = Field(default="")
    ENCRYPTION_KEY: str = Field(default="")  # Fernet key — auto-generated on first run if empty

    # ── Database ──────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./viralmint.db"

    # ── AI Providers (BYOK) ───────────────────────────
    # Set at least one. OpenRouter unlocks Claude / GPT / Gemini / Llama
    # / Mistral through a single key — handy if you want to mix premium
    # models without managing multiple provider accounts.
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""

    # ── Service keys (BYOK) ───────────────────────────
    # All optional — features gracefully degrade when keys are missing.
    YOUTUBE_API_KEY: str = ""           # YouTube scout, channel reader, comments
    TIKHUB_API_KEY: str = ""            # TikTok / Douyin scout (alternative: cookies in Settings)
    PEXELS_API_KEY: str = ""            # Stock video footage
    RUNPOD_API_KEY: str = ""            # RunPod GPU Pod + ComfyUI (AI Video)
    RUNPOD_NETWORK_VOLUME_ID: str = ""  # Optional: persist models across pods (paid volume)
    RUNPOD_HF_TOKEN: str = ""           # Optional: gated HuggingFace downloads on the pod

    # ── Upload OAuth ──────────────────────────────────
    YOUTUBE_CLIENT_ID: str = ""
    YOUTUBE_CLIENT_SECRET: str = ""
    YOUTUBE_REDIRECT_URI: str = "http://localhost:16888/api/settings/youtube-callback"

    TIKTOK_CLIENT_KEY: str = ""
    TIKTOK_CLIENT_SECRET: str = ""
    TIKTOK_REDIRECT_URI: str = "http://localhost:16888/api/settings/tiktok-upload-callback"

    # ── Frontend ──────────────────────────────────────
    FRONTEND_URL: str = "http://localhost:5173"

    # ── Storage paths ─────────────────────────────────
    @property
    def STORAGE_ROOT(self) -> Path:
        return Path("storage")

    @property
    def VIDEOS_DIR(self) -> Path:
        return self.STORAGE_ROOT / "videos"

    @property
    def AUDIO_DIR(self) -> Path:
        return self.STORAGE_ROOT / "audio"

    @property
    def GENERATED_DIR(self) -> Path:
        return self.STORAGE_ROOT / "generated"

    @property
    def THUMBNAILS_DIR(self) -> Path:
        return self.STORAGE_ROOT / "thumbnails"

    @property
    def TMP_DIR(self) -> Path:
        return self.STORAGE_ROOT / "tmp"


def _ensure_secrets(s: Settings) -> Settings:
    """Auto-generate SECRET_KEY and ENCRYPTION_KEY if missing, persist to .env."""
    env_path = Path(".env")
    lines_to_append = []

    if not s.SECRET_KEY or s.SECRET_KEY == "change-me-in-production-use-secrets-token-hex-32":
        key = secrets.token_hex(32)
        s.__dict__["SECRET_KEY"] = key
        lines_to_append.append(f"SECRET_KEY={key}")
        logger.warning("SECRET_KEY was not set — generated and saved to .env")

    if not s.ENCRYPTION_KEY:
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        s.__dict__["ENCRYPTION_KEY"] = key
        lines_to_append.append(f"ENCRYPTION_KEY={key}")
        logger.warning("ENCRYPTION_KEY was not set — generated and saved to .env")

    if lines_to_append:
        existing = env_path.read_text() if env_path.exists() else ""
        with open(env_path, "a") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            for line in lines_to_append:
                key_name = line.split("=", 1)[0]
                if key_name + "=" not in existing:
                    f.write(line + "\n")

    return s


# Singleton — import this everywhere
settings = _ensure_secrets(Settings())

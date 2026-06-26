# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Vision LLM cataloging of uploaded long-form assets."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from backend.core.ai_provider import AIClient, get_ai_client
from backend.services.prompt_synth_service import _encode_image_data_url, _safe_json_load
from backend.services.video_utils import probe_duration

logger = logging.getLogger(__name__)

CATALOG_SYSTEM = """You analyze media assets for a documentary-style video editor.
Return JSON only:
{
  "description": "one sentence",
  "tags": ["tag1", "tag2"],
  "detected_type": "portrait|screenshot|broll|document|other",
  "suggested_use": "intro|evidence|reaction|transition|broll"
}"""


async def catalog_image(path: Path, caption: str = "", topic: str = "", ai_client: Optional[AIClient] = None) -> dict:
    """Describe an uploaded image via vision LLM (fallback to heuristic)."""
    base = {
        "description": caption or path.stem.replace("_", " "),
        "tags": [],
        "detected_type": "other",
        "suggested_use": "broll",
        "duration_s": None,
    }
    if not ai_client:
        return _heuristic_image_catalog(path, caption, base)

    try:
        user_text = f"Topic: {topic or 'general'}\nCaption: {caption or 'none'}\nDescribe this asset."
        messages = [
            {"role": "system", "content": CATALOG_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": _encode_image_data_url(path)}},
                ],
            },
        ]
        resp = await ai_client.chat(messages, max_tokens=400)
        data = _safe_json_load(resp)
        base.update({k: data.get(k, base[k]) for k in base if k in data or k in data})
        for k in ("description", "tags", "detected_type", "suggested_use"):
            if k in data:
                base[k] = data[k]
        return base
    except Exception as e:
        logger.warning("DEBUG:: asset catalog vision failed: %s", e)
        return _heuristic_image_catalog(path, caption, base)


async def catalog_video(path: Path, caption: str = "", topic: str = "", ai_client: Optional[AIClient] = None) -> dict:
    """Catalog a video asset — duration + optional thumbnail vision pass."""
    duration = probe_duration(path, default=0.0)
    base = {
        "description": caption or f"Video clip ({duration:.0f}s)",
        "tags": ["video"],
        "detected_type": "broll",
        "suggested_use": "broll",
        "duration_s": duration,
    }
    if ai_client:
        try:
            from backend.services.ffmpeg_service import extract_thumbnail
            thumb = await extract_thumbnail(path, timestamp=min(1.0, duration * 0.1))
            img_cat = await catalog_image(thumb, caption, topic, ai_client)
            base.update({k: img_cat.get(k, base.get(k)) for k in ("description", "tags", "detected_type", "suggested_use")})
            base["duration_s"] = duration
            return base
        except Exception as e:
            logger.warning("DEBUG:: video catalog failed: %s", e)
    return base


def _heuristic_image_catalog(path: Path, caption: str, base: dict) -> dict:
    name = path.stem.lower()
    if any(x in name for x in ("ss", "screenshot", "post", "instagram", "tweet")):
        base["detected_type"] = "screenshot"
        base["suggested_use"] = "evidence"
    elif any(x in name for x in ("portrait", "photo", "face", "boy", "girl")):
        base["detected_type"] = "portrait"
        base["suggested_use"] = "intro"
    if caption:
        base["description"] = caption
    return base


async def catalog_assets(assets: list[dict], topic: str = "", user_id: str = "local") -> list[dict]:
    """Catalog a list of {id, kind, path, caption} assets."""
    ai_client = None
    try:
        from sqlalchemy import select
        from backend.database import AsyncSessionLocal
        from backend.models.user_settings import UserSettings
        async with AsyncSessionLocal() as db:
            r = await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
            user_settings = r.scalar_one_or_none()
        ai_client = get_ai_client(user_settings)
    except Exception:
        pass

    out = []
    for a in assets:
        path = Path(a["path"])
        kind = a.get("kind", "image")
        caption = a.get("caption") or ""
        if kind == "video":
            cat = await catalog_video(path, caption, topic, ai_client)
        else:
            cat = await catalog_image(path, caption, topic, ai_client)
        out.append({**a, "catalog": cat})
    return out

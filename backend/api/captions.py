# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""REST API for custom caption styles — CRUD + AI generation."""
import json
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from backend.database import AsyncSessionLocal
from backend.models.caption_style import CaptionStyle
from backend.models.user_settings import UserSettings
from backend.core.ai_provider import get_ai_client

logger = logging.getLogger(__name__)
router = APIRouter()


class CaptionStyleCreate(BaseModel):
    name: str
    font: str = "Arial Bold"
    font_size_portrait: int = 56
    font_size_landscape: int = 42
    primary_color: str = "&H00FFFFFF"
    highlight_color: str = "&H0000FFFF"
    outline_color: str = "&H00000000"
    outline_width: int = 3
    shadow_depth: int = 1
    alignment: int = 5
    margin_v: int = 80
    words_per_group: int = 3
    description: Optional[str] = None


class CaptionStyleUpdate(BaseModel):
    name: Optional[str] = None
    font: Optional[str] = None
    font_size_portrait: Optional[int] = None
    font_size_landscape: Optional[int] = None
    primary_color: Optional[str] = None
    highlight_color: Optional[str] = None
    outline_color: Optional[str] = None
    outline_width: Optional[int] = None
    shadow_depth: Optional[int] = None
    alignment: Optional[int] = None
    margin_v: Optional[int] = None
    words_per_group: Optional[int] = None
    description: Optional[str] = None


class AIGenerateRequest(BaseModel):
    description: str  # e.g. "TikTok dance style with bright neon colors"


# ── Built-in styles (returned alongside custom ones) ─────────────────────────

BUILTIN_STYLES = [
    {"id": "viral", "name": "Viral", "builtin": True, "font": "Arial Bold", "font_size_portrait": 56, "font_size_landscape": 42, "primary_color": "&H00FFFFFF", "highlight_color": "&H0000FFFF", "outline_color": "&H00000000", "outline_width": 3, "shadow_depth": 1, "alignment": 5, "margin_v": 80, "words_per_group": 3, "description": "Word-by-word yellow highlight, centered"},
    {"id": "classic", "name": "Classic", "builtin": True, "font": "Arial", "font_size_portrait": 42, "font_size_landscape": 32, "primary_color": "&H00FFFFFF", "highlight_color": "&H00FFFFFF", "outline_color": "&H00000000", "outline_width": 2, "shadow_depth": 0, "alignment": 2, "margin_v": 40, "words_per_group": 8, "description": "Full sentence at bottom, no highlight"},
    {"id": "bold", "name": "Bold", "builtin": True, "font": "Impact", "font_size_portrait": 64, "font_size_landscape": 48, "primary_color": "&H00FFFFFF", "highlight_color": "&H0000FF00", "outline_color": "&H00000000", "outline_width": 4, "shadow_depth": 2, "alignment": 5, "margin_v": 60, "words_per_group": 2, "description": "Impact font, green highlight, 2 words"},
    {"id": "neon", "name": "Neon", "builtin": True, "font": "Arial Bold", "font_size_portrait": 58, "font_size_landscape": 44, "primary_color": "&H00FFAAFF", "highlight_color": "&H0000FFFF", "outline_color": "&H00330033", "outline_width": 3, "shadow_depth": 2, "alignment": 5, "margin_v": 70, "words_per_group": 3, "description": "Pink/cyan neon glow"},
    {"id": "minimal", "name": "Minimal", "builtin": True, "font": "Arial", "font_size_portrait": 40, "font_size_landscape": 30, "primary_color": "&H00FFFFFF", "highlight_color": "&H00FFFFFF", "outline_color": "&H00333333", "outline_width": 1, "shadow_depth": 0, "alignment": 2, "margin_v": 30, "words_per_group": 10, "description": "Subtle, long phrases"},
    {"id": "karaoke", "name": "Karaoke", "builtin": True, "font": "Arial Bold", "font_size_portrait": 52, "font_size_landscape": 40, "primary_color": "&H00AAAAAA", "highlight_color": "&H0000FFFF", "outline_color": "&H00000000", "outline_width": 3, "shadow_depth": 1, "alignment": 2, "margin_v": 50, "words_per_group": 5, "description": "Gray-to-yellow karaoke sweep"},
    {"id": "glow", "name": "Glow", "builtin": True, "font": "Arial Bold", "font_size_portrait": 60, "font_size_landscape": 46, "primary_color": "&H00FFFFFF", "highlight_color": "&H0066CCFF", "outline_color": "&H000066CC", "outline_width": 4, "shadow_depth": 3, "alignment": 5, "margin_v": 75, "words_per_group": 3, "description": "Orange-gold glow effect"},
]


def _style_to_dict(s: CaptionStyle) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "builtin": False,
        "font": s.font,
        "font_size_portrait": s.font_size_portrait,
        "font_size_landscape": s.font_size_landscape,
        "primary_color": s.primary_color,
        "highlight_color": s.highlight_color,
        "outline_color": s.outline_color,
        "outline_width": s.outline_width,
        "shadow_depth": s.shadow_depth,
        "alignment": s.alignment,
        "margin_v": s.margin_v,
        "words_per_group": s.words_per_group,
        "is_ai_generated": s.is_ai_generated,
        "description": s.description,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


@router.get("/captions/styles")
async def list_caption_styles():
    """Return all built-in + custom caption styles."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CaptionStyle)
            .where(CaptionStyle.user_id == "local")
            .order_by(CaptionStyle.created_at.desc())
        )
        custom = result.scalars().all()
    return {
        "builtin": BUILTIN_STYLES,
        "custom": [_style_to_dict(s) for s in custom],
    }


@router.post("/captions/styles", status_code=201)
async def create_caption_style(body: CaptionStyleCreate):
    """Create a custom caption style."""
    if not body.name or not body.name.strip():
        raise HTTPException(422, "Style name cannot be empty")
    async with AsyncSessionLocal() as db:
        style = CaptionStyle(
            user_id="local",
            name=body.name.strip(),
            font=body.font,
            font_size_portrait=body.font_size_portrait,
            font_size_landscape=body.font_size_landscape,
            primary_color=body.primary_color,
            highlight_color=body.highlight_color,
            outline_color=body.outline_color,
            outline_width=body.outline_width,
            shadow_depth=body.shadow_depth,
            alignment=body.alignment,
            margin_v=body.margin_v,
            words_per_group=body.words_per_group,
            description=body.description,
        )
        db.add(style)
        await db.commit()
        await db.refresh(style)
    return _style_to_dict(style)


@router.put("/captions/styles/{style_id}")
async def update_caption_style(style_id: str, body: CaptionStyleUpdate):
    """Update a custom caption style."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(CaptionStyle).where(CaptionStyle.id == style_id))
        style = result.scalar_one_or_none()
        if not style:
            raise HTTPException(404, "Caption style not found")
        for field, value in body.model_dump(exclude_none=True).items():
            setattr(style, field, value)
        await db.commit()
        await db.refresh(style)
    return _style_to_dict(style)


@router.delete("/captions/styles/{style_id}")
async def delete_caption_style(style_id: str):
    """Delete a custom caption style."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(CaptionStyle).where(CaptionStyle.id == style_id))
        style = result.scalar_one_or_none()
        if not style:
            raise HTTPException(404, "Caption style not found")
        await db.delete(style)
        await db.commit()
    return {"ok": True}


AI_CAPTION_PROMPT = """You are a video caption style designer. Generate a caption style configuration for video subtitles based on the user's description.

Return ONLY a JSON object with these fields (no other text):
{
  "name": "short descriptive name (max 30 chars)",
  "font": "font family (use common fonts: Arial, Arial Bold, Impact, Georgia, Courier New, Verdana, Trebuchet MS, Comic Sans MS)",
  "font_size_portrait": number (40-72, for 9:16 vertical video),
  "font_size_landscape": number (30-54, for 16:9 horizontal video),
  "primary_color": "ASS color in &HBBGGRR format (e.g. &H00FFFFFF for white)",
  "highlight_color": "ASS color for the active/spoken word",
  "outline_color": "ASS color for text outline",
  "outline_width": number (0-6),
  "shadow_depth": number (0-4),
  "alignment": number (ASS numpad: 2=bottom-center, 5=center, 8=top-center),
  "margin_v": number (20-120, vertical margin in pixels),
  "words_per_group": number (1-12, how many words shown at once),
  "description": "one-line description of the style"
}

IMPORTANT: ASS uses BGR color format, NOT RGB. &H00FFFFFF = white, &H000000FF = red, &H00FF0000 = blue, &H0000FF00 = green, &H0000FFFF = yellow."""


@router.post("/captions/styles/generate")
async def generate_caption_style(body: AIGenerateRequest):
    """Use AI to generate a caption style from a description."""
    if not body.description or not body.description.strip():
        raise HTTPException(422, "Description cannot be empty")

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(UserSettings).where(UserSettings.user_id == "local")
        )
        user_settings = result.scalar_one_or_none()

    try:
        ai = get_ai_client(user_settings)
    except Exception:
        raise HTTPException(400, "AI provider not configured. Add an API key in Settings.")

    response = await ai.chat(
        messages=[{"role": "user", "content": f"Create a caption style: {body.description.strip()}"}],
        system=AI_CAPTION_PROMPT,
        max_tokens=512,
    )

    # Parse AI response
    try:
        # Extract JSON from response (AI might wrap it in markdown)
        text = response.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        config = json.loads(text.strip())
    except (json.JSONDecodeError, IndexError):
        raise HTTPException(500, "AI generated invalid caption style. Try again with a different description.")

    # Validate and clamp values
    config["font_size_portrait"] = max(40, min(72, config.get("font_size_portrait", 56)))
    config["font_size_landscape"] = max(30, min(54, config.get("font_size_landscape", 42)))
    config["outline_width"] = max(0, min(6, config.get("outline_width", 3)))
    config["shadow_depth"] = max(0, min(4, config.get("shadow_depth", 1)))
    config["alignment"] = config.get("alignment", 5) if config.get("alignment") in (1,2,3,4,5,6,7,8,9) else 5
    config["margin_v"] = max(20, min(120, config.get("margin_v", 80)))
    config["words_per_group"] = max(1, min(12, config.get("words_per_group", 3)))

    # Save to DB
    async with AsyncSessionLocal() as db:
        style = CaptionStyle(
            user_id="local",
            name=config.get("name", "AI Style")[:100],
            font=config.get("font", "Arial Bold"),
            font_size_portrait=config["font_size_portrait"],
            font_size_landscape=config["font_size_landscape"],
            primary_color=config.get("primary_color", "&H00FFFFFF"),
            highlight_color=config.get("highlight_color", "&H0000FFFF"),
            outline_color=config.get("outline_color", "&H00000000"),
            outline_width=config["outline_width"],
            shadow_depth=config["shadow_depth"],
            alignment=config["alignment"],
            margin_v=config["margin_v"],
            words_per_group=config["words_per_group"],
            description=config.get("description", body.description),
            is_ai_generated=True,
        )
        db.add(style)
        await db.commit()
        await db.refresh(style)

    return _style_to_dict(style)

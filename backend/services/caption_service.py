# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""
Word-by-word animated caption renderer.
Generates ASS (Advanced SubStation Alpha) subtitle files with per-word highlighting.
This is THE key visual feature for viral short-form content.
"""
import logging
import re
import subprocess
import asyncio
from pathlib import Path

from backend.config import settings
from backend.core.exceptions import VideoGenerationError

logger = logging.getLogger(__name__)

# ── Auto Emoji Mapping ───────────────────────────────────────────────────────

EMOJI_KEYWORDS = {
    # Money/finance
    "money": "💰", "cash": "💵", "save": "💰", "invest": "📈",
    "rich": "🤑", "expensive": "💸", "budget": "📊", "profit": "💹",
    "dollar": "💵", "earn": "💰", "income": "💰", "cost": "💸",
    # Emotions
    "amazing": "🤩", "incredible": "😱", "love": "❤️", "hate": "😤",
    "happy": "😊", "sad": "😢", "angry": "😡", "surprised": "😲",
    "crazy": "🤪", "wow": "😮", "funny": "😂", "scary": "😨",
    "beautiful": "😍", "awesome": "🔥", "perfect": "👌",
    # Actions
    "subscribe": "🔔", "like": "👍", "share": "📤", "comment": "💬",
    "click": "👆", "watch": "👀", "listen": "👂", "learn": "📚",
    "stop": "🛑", "wait": "⏳", "think": "🤔", "remember": "💭",
    # Objects
    "phone": "📱", "computer": "💻", "food": "🍕", "house": "🏠",
    "car": "🚗", "book": "📖", "music": "🎵", "video": "🎬",
    "coffee": "☕", "water": "💧", "brain": "🧠", "heart": "❤️",
    # Concepts
    "time": "⏰", "secret": "🤫", "warning": "⚠️", "tip": "💡",
    "fire": "🔥", "growth": "📈", "success": "🏆", "fail": "❌",
    "number": "🔢", "first": "1️⃣", "new": "✨", "free": "🆓",
    "important": "‼️", "question": "❓", "idea": "💡", "goal": "🎯",
    "world": "🌍", "power": "⚡", "king": "👑", "game": "🎮",
    "mistake": "❌", "wrong": "❌", "right": "✅", "yes": "✅",
    "no": "❌", "best": "🏆", "worst": "👎", "top": "🔝",
}


def insert_emojis_into_words(words: list[dict], style: str = "moderate") -> list[dict]:
    """
    Insert emojis after matching keywords in word list.

    Styles:
    - "none": no emojis
    - "minimal": emoji every 4-5 keyword matches
    - "moderate": emoji every 2-3 keyword matches
    - "heavy": emoji on every keyword match

    Mutates word dicts in place (adds emoji to text field).
    """
    if style == "none":
        return words

    interval = {"minimal": 5, "moderate": 3, "heavy": 1}.get(style, 3)
    match_count = 0

    for w in words:
        text_lower = re.sub(r"[^a-z]", "", w["text"].lower())
        emoji = EMOJI_KEYWORDS.get(text_lower)
        if emoji:
            match_count += 1
            if match_count % interval == 0:
                w["text"] = w["text"] + " " + emoji

    return words

# ── Caption Style Presets ──────────────────────────────────────────────────────

CAPTION_STYLES = {
    "viral": {
        "font": "Arial Bold",
        "font_size_portrait": 56,
        "font_size_landscape": 42,
        "primary_color": "&H00FFFFFF",       # white (ASS uses BGR, &HBBGGRR)
        "highlight_color": "&H0000FFFF",     # yellow
        "outline_color": "&H00000000",       # black
        "outline_width": 3,
        "shadow_depth": 1,
        "alignment": 5,                      # center-center (numpad position)
        "margin_v": 80,                      # vertical margin from bottom
        "words_per_group": 3,
    },
    "classic": {
        "font": "Arial",
        "font_size_portrait": 42,
        "font_size_landscape": 32,
        "primary_color": "&H00FFFFFF",
        "highlight_color": "&H00FFFFFF",     # no highlight
        "outline_color": "&H00000000",
        "outline_width": 2,
        "shadow_depth": 0,
        "alignment": 2,                      # bottom-center
        "margin_v": 40,
        "words_per_group": 8,
    },
    "bold": {
        "font": "Impact",
        "font_size_portrait": 64,
        "font_size_landscape": 48,
        "primary_color": "&H00FFFFFF",
        "highlight_color": "&H0000FF00",     # green
        "outline_color": "&H00000000",
        "outline_width": 4,
        "shadow_depth": 2,
        "alignment": 5,                      # center-center
        "margin_v": 60,
        "words_per_group": 2,
    },
    "neon": {
        "font": "Arial Bold",
        "font_size_portrait": 58,
        "font_size_landscape": 44,
        "primary_color": "&H00FFAAFF",       # pink/magenta
        "highlight_color": "&H0000FFFF",     # cyan
        "outline_color": "&H00330033",       # dark purple outline
        "outline_width": 3,
        "shadow_depth": 2,
        "alignment": 5,
        "margin_v": 70,
        "words_per_group": 3,
    },
    "minimal": {
        "font": "Arial",
        "font_size_portrait": 40,
        "font_size_landscape": 30,
        "primary_color": "&H00FFFFFF",       # white
        "highlight_color": "&H00FFFFFF",     # no highlight
        "outline_color": "&H00333333",       # subtle gray outline
        "outline_width": 1,
        "shadow_depth": 0,
        "alignment": 2,                      # bottom-center
        "margin_v": 30,
        "words_per_group": 10,               # long phrases
    },
    "karaoke": {
        "font": "Arial Bold",
        "font_size_portrait": 52,
        "font_size_landscape": 40,
        "primary_color": "&H00AAAAAA",       # gray (unspoken)
        "highlight_color": "&H0000FFFF",     # yellow (spoken)
        "outline_color": "&H00000000",
        "outline_width": 3,
        "shadow_depth": 1,
        "alignment": 2,                      # bottom-center
        "margin_v": 50,
        "words_per_group": 5,
    },
    "glow": {
        "font": "Arial Bold",
        "font_size_portrait": 60,
        "font_size_landscape": 46,
        "primary_color": "&H00FFFFFF",       # white
        "highlight_color": "&H0066CCFF",     # orange-gold
        "outline_color": "&H000066CC",       # dark orange outline
        "outline_width": 4,
        "shadow_depth": 3,
        "alignment": 5,
        "margin_v": 75,
        "words_per_group": 3,
    },
}


async def _load_custom_style(style_id: str) -> dict | None:
    """Load a custom caption style from the database by ID."""
    try:
        from backend.database import AsyncSessionLocal
        from backend.models.caption_style import CaptionStyle
        from sqlalchemy import select
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(CaptionStyle).where(CaptionStyle.id == style_id))
            s = result.scalar_one_or_none()
            if s:
                return {
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
                }
    except Exception as e:
        logger.warning(f"Failed to load custom caption style {style_id}: {e}")
    return None


def _format_ass_time(seconds: float) -> str:
    """Convert seconds to ASS time format: H:MM:SS.cc"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _build_ass_header(style_config: dict, aspect_ratio: str, resolution: tuple[int, int]) -> str:
    """Build ASS file header with style definitions."""
    style = style_config
    width, height = resolution

    font_size = style["font_size_portrait"] if aspect_ratio == "9:16" else style["font_size_landscape"]

    return f"""[Script Info]
Title: ViralMint Captions
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: {width}
PlayResY: {height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style['font']},{font_size},{style['primary_color']},&H000000FF,{style['outline_color']},&H80000000,-1,0,0,0,100,100,0,0,1,{style['outline_width']},{style['shadow_depth']},{style['alignment']},20,20,{style['margin_v']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _extract_word_timestamps(segments: list[dict]) -> list[dict]:
    """
    Extract flat list of words with timestamps from Whisper segments.
    Each segment may have 'words' (if word_timestamps=True was used).
    Falls back to splitting segment text evenly across segment duration.
    Validates all timestamps to prevent downstream crashes.
    """
    words = []
    last_end = 0.0  # track for monotonicity enforcement

    for seg in segments:
        if not isinstance(seg, dict):
            continue

        if "words" in seg and seg["words"]:
            # Whisper provided word-level timestamps
            for w in seg["words"]:
                if not isinstance(w, dict):
                    continue
                text = (w.get("word") or w.get("text") or "").strip()
                if not text:
                    continue
                try:
                    start = float(w.get("start", 0))
                    end = float(w.get("end", 0))
                except (TypeError, ValueError):
                    continue
                # Guard: end must be > start, timestamps must be non-negative
                if start < 0:
                    start = 0
                if end <= start:
                    end = start + 0.1  # minimum 100ms word duration
                # Enforce monotonicity — prevent overlapping timestamps
                if start < last_end:
                    start = last_end
                if end <= start:
                    end = start + 0.1
                last_end = end
                words.append({"text": text, "start": start, "end": end})
        else:
            # Fall back: split segment text evenly
            seg_text = seg.get("text", "")
            if not isinstance(seg_text, str):
                continue
            seg_words = seg_text.strip().split()
            if not seg_words:
                continue
            try:
                seg_start = max(float(seg.get("start", 0)), 0)
                seg_end = float(seg.get("end", seg_start + 1))
            except (TypeError, ValueError):
                continue
            if seg_end <= seg_start:
                seg_end = seg_start + len(seg_words) * 0.3  # ~300ms per word fallback
            duration = seg_end - seg_start
            per_word = duration / len(seg_words)
            for i, w in enumerate(seg_words):
                w_start = max(seg_start + i * per_word, last_end)
                w_end = w_start + per_word
                last_end = w_end
                words.append({"text": w, "start": w_start, "end": w_end})

    return [w for w in words if w.get("text")]


def _generate_ass_events(words: list[dict], style: dict) -> str:
    """
    Generate ASS dialogue events with word-by-word highlighting.
    Groups words into display groups, highlights the active word.
    """
    group_size = style.get("words_per_group", 3)
    highlight = style.get("highlight_color", "&H0000FFFF")
    primary = style.get("primary_color", "&H00FFFFFF")
    events = []

    # Group words
    groups = []
    for i in range(0, len(words), group_size):
        group = words[i:i + group_size]
        groups.append(group)

    for group in groups:
        if not group:
            continue
        group_start = group[0]["start"]
        group_end = group[-1]["end"]
        if group_end <= group_start:
            continue  # skip degenerate groups

        # For each word in the group, create a dialogue line where THAT word is highlighted
        for active_idx, active_word in enumerate(group):
            word_start = active_word["start"]
            word_end = active_word["end"]
            if word_end <= word_start:
                continue  # skip zero-duration words

            # Build text with override tags
            parts = []
            for j, w in enumerate(group):
                if j == active_idx:
                    # Highlighted word (active)
                    parts.append(f"{{\\1c{highlight}\\b1}}{w['text']}{{\\1c{primary}\\b0}}")
                else:
                    parts.append(w["text"])

            text = " ".join(parts)
            start_ts = _format_ass_time(word_start)
            end_ts = _format_ass_time(word_end)

            events.append(f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{text}")

    return "\n".join(events)


async def generate_captions_ass(
    segments: list[dict],
    style: str = "viral",
    aspect_ratio: str = "9:16",
    output_path: Path = None,
    emoji_style: str = "moderate",
) -> Path:
    """
    Generate ASS subtitle file with word-by-word animation.

    Args:
        segments: Whisper segments with word timestamps.
                  Each: {"start": float, "end": float, "text": str, "words": [...]}
        style: Caption style preset name.
        aspect_ratio: "9:16" or "16:9".
        output_path: Where to write the ASS file.
        emoji_style: "none" | "minimal" | "moderate" | "heavy"

    Returns:
        Path to the generated ASS file.
    """
    if output_path is None:
        output_path = settings.TMP_DIR / "captions.ass"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    style_config = CAPTION_STYLES.get(style) or await _load_custom_style(style) or CAPTION_STYLES["viral"]

    if aspect_ratio == "9:16":
        resolution = (1080, 1920)
    else:
        resolution = (1920, 1080)

    # Extract word-level timestamps
    words = _extract_word_timestamps(segments)
    if not words:
        logger.warning("No words found in segments — generating empty caption file")
        output_path.write_text("")
        return output_path

    # Auto-insert emojis based on keyword matching
    words = insert_emojis_into_words(words, emoji_style)

    # Build ASS file
    header = _build_ass_header(style_config, aspect_ratio, resolution)
    events = _generate_ass_events(words, style_config)

    content = header + events + "\n"
    output_path.write_text(content, encoding="utf-8")

    logger.info(f"ASS captions generated: {output_path} ({len(words)} words, style={style}, emoji={emoji_style})")
    return output_path


async def burn_captions(
    video_path: Path,
    ass_path: Path,
    output_path: Path = None,
) -> Path:
    """Burn ASS captions into video using FFmpeg."""
    if output_path is None:
        output_path = video_path.parent / f"{video_path.stem}_captioned.mp4"

    if not ass_path.exists() or ass_path.stat().st_size == 0:
        logger.warning("Empty or missing ASS file — returning original video")
        return video_path

    def _burn():
        # Escape path for FFmpeg filter (colons and backslashes)
        escaped_ass = str(ass_path.resolve()).replace("\\", "/").replace(":", "\\:")

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", f"ass={escaped_ass}",
            "-c:a", "copy",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            logger.warning(f"ASS caption burn failed: {result.stderr[:400]}")
            return video_path  # Return original on failure
        return output_path

    return await asyncio.to_thread(_burn)

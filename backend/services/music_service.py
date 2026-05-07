# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""
Background music selection and mixing.
Mixes royalty-free music under voiceover at configurable volume.
Auto-downloads royalty-free tracks from Pixabay if none are bundled.
"""
import asyncio
import logging
import subprocess
from pathlib import Path

import httpx

from backend.config import settings
from backend.core.exceptions import VideoGenerationError
from backend.services.video_utils import probe_duration

logger = logging.getLogger(__name__)

# Bundled royalty-free music directory
MUSIC_DIR = settings.STORAGE_ROOT / "music"

MUSIC_GENRES = {
    "lofi":       "lo-fi chill beats",
    "cinematic":  "dramatic orchestral",
    "upbeat":     "energetic electronic",
    "ambient":    "calm atmospheric",
    "corporate":  "business motivational",
    "jazz":       "smooth jazz relaxing",
    "hiphop":     "hip hop trap beats",
    "classical":  "classical piano orchestral",
    "edm":        "EDM dance electronic",
    "acoustic":   "acoustic guitar folk",
    "rnb":        "R&B soul smooth",
    "rock":       "rock energetic guitar",
}

# Pixabay royalty-free music search terms
PIXABAY_GENRE_QUERIES = {
    "lofi":       "lo fi chill",
    "cinematic":  "cinematic dramatic",
    "upbeat":     "upbeat energetic",
    "ambient":    "ambient calm",
    "corporate":  "corporate motivational",
    "jazz":       "jazz smooth",
    "hiphop":     "hip hop trap",
    "classical":  "classical piano",
    "edm":        "edm dance",
    "acoustic":   "acoustic guitar",
    "rnb":        "rnb soul",
    "rock":       "rock guitar",
}


async def select_music(genre: str = "lofi", duration: int = 60) -> Path | None:
    """
    Select a background music track matching the genre.
    1. Check bundled tracks in storage/music/
    2. If none found, try downloading from Pixabay (free, no API key needed)
    3. Returns None if nothing available (gracefully skipped by generator)
    """
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)

    # Look for bundled tracks matching genre
    for ext in ("mp3", "wav", "ogg", "m4a"):
        for track in MUSIC_DIR.glob(f"*{genre}*.{ext}"):
            if track.is_file() and track.stat().st_size > 0:
                logger.info(f"Selected bundled music: {track.name}")
                return track

    # Look for any track as fallback
    for ext in ("mp3", "wav", "ogg", "m4a"):
        for track in MUSIC_DIR.glob(f"*.{ext}"):
            if track.is_file() and track.stat().st_size > 0:
                logger.info(f"Selected fallback music: {track.name}")
                return track

    # No bundled tracks — try auto-downloading from Pixabay
    track = await _download_from_pixabay(genre)
    if track:
        return track

    logger.info("No background music available")
    return None


async def _download_from_pixabay(genre: str) -> Path | None:
    """
    Download a royalty-free music track from Pixabay.
    Pixabay audio is CC0 (no attribution required).
    Note: Pixabay API signups are currently closed to new users.
    Users can add .mp3 files manually to storage/music/ instead.
    """
    logger.info(f"No bundled music for genre '{genre}' — users can add .mp3 files to storage/music/")
    return None


async def mix_audio(
    voice_path: Path,
    music_path: Path,
    output_path: Path = None,
    music_volume_db: float = -20.0,
) -> Path:
    """
    Mix voice + background music using FFmpeg.
    Music is:
    - Lowered to music_volume_db (default -20dB)
    - Faded in over 1s at start
    - Faded out over 2s at end
    - Trimmed to match voice duration
    """
    if output_path is None:
        output_path = voice_path.parent / f"{voice_path.stem}_mixed.mp3"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not music_path or not music_path.exists():
        logger.warning("No music file provided — returning voice only")
        return voice_path

    def _mix():
        # Get voice duration
        voice_duration = probe_duration(voice_path, default=60.0)

        # FFmpeg filter: lower music volume, fade in/out, mix with voice
        fade_out_start = max(voice_duration - 2.0, 0)
        filter_complex = (
            f"[1:a]volume={music_volume_db}dB,"
            f"afade=t=in:d=1,"
            f"afade=t=out:st={fade_out_start:.1f}:d=2"
            f"[bg];"
            f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[out]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", str(voice_path),
            "-i", str(music_path),
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-c:a", "libmp3lame", "-b:a", "192k",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            logger.warning(f"Music mixing failed: {result.stderr[:400]}")
            return voice_path  # Return voice only on failure

        return output_path

    return await asyncio.to_thread(_mix)

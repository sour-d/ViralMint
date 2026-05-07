# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""
Viral clip extraction service.
Takes a long-form downloaded video and identifies the best 30-60s segments
for YouTube Shorts / TikTok / Reels.

Features:
- AI-powered clip window selection with platform-aware prompts
- Chunk-based extraction for large requests (splits video into time windows)
- Per-clip virality scoring (1-10)
- Parallel clip processing (extract + caption + thumbnail)
- Intermediate file cleanup
- Robust error handling with status tracking
"""
import asyncio
import json
import logging
import math
import re
from pathlib import Path
from uuid import uuid4

from backend.config import settings
from backend.core.ws_manager import ws_manager

logger = logging.getLogger(__name__)

# ── AI Prompts ────────────────────────────────────────────────────────────────

CLIP_SELECTION_PROMPT = """You are an expert viral short-form video editor who has produced thousands of clips with millions of views.

Your job: identify the best non-overlapping segments ({min_clip}–{max_clip} seconds each) from this transcript. Find up to {max_clips} quality clips. Only include segments that genuinely meet the criteria below — never pad with weak content.

SELECTION CRITERIA (in priority order):
1. HOOK STRENGTH: The first 2-3 seconds of the segment must grab attention immediately. Look for: surprising statements, bold claims, questions, emotional peaks, "did you know" moments.
2. STANDALONE VALUE: Each segment must make complete sense without the rest of the video. No dangling references, no "as I mentioned earlier".
3. INFORMATION DENSITY: Every 10 seconds should advance the narrative. Cut segments that meander or repeat.
4. CLEAN BOUNDARIES: Start at natural sentence beginnings (not mid-word). End at natural conclusions (not cliffhangers that need the next sentence).
5. EMOTIONAL ARC: Prefer segments with a clear setup → payoff structure. "Aha moments", revelations, or actionable advice.
6. QUOTABILITY: Would someone share this clip? Would it spark comments or debates?

WHAT TO AVOID:
- Intros ("hey guys, welcome to my channel")
- Outros ("don't forget to subscribe")
- Slow, repetitive sections with low information density
- Segments that reference visuals not captured in audio ("as you can see on screen")
- Incomplete thoughts or arguments that require context

Video title: {title}
Video duration: {duration}s
Video niche/topic: {niche}

Transcript with timestamps:
{segments_text}

Return ONLY valid JSON array, no markdown fences:
[
  {{
    "start": 45.2,
    "end": 102.8,
    "title": "Short punchy title for this clip (5-8 words)",
    "hook": "The exact first sentence that grabs attention",
    "reason": "Why this segment works as a viral clip (be specific)",
    "virality_score": 8.5
  }}
]

IMPORTANT:
- virality_score must be 1-10 (10 = guaranteed viral, 1 = boring)
- Each segment MUST be between {min_clip} and {max_clip} seconds
- Segments must NOT overlap
- Order by virality_score descending (best clip first)
- You MUST return at least 1 clip if there is any usable content"""

CLIP_METADATA_PROMPT = """Generate platform metadata for this viral short clip.

Clip title: {title}
Clip transcript:
{transcript_text}

Return ONLY valid JSON, no markdown fences:
{{
  "youtube_title": "Catchy YouTube Shorts title (under 70 chars, front-load keywords, use power words)",
  "youtube_description": "2-3 sentence description with relevant keywords for SEO",
  "youtube_tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "tiktok_title": "TikTok caption with hashtags (under 150 chars, hook-first)"
}}"""


# ── Clip count estimation ──────────────────────────────────────────────────────

def _estimate_realistic_clip_count(segments: list[dict], duration: int, requested_max: int) -> int:
    """
    Estimate how many clips can realistically be extracted, based on transcript
    content density rather than just video duration.

    A 30s clip needs ~60-80 words of transcript. We estimate from actual content.
    """
    if not segments or duration <= 0:
        return min(requested_max, 3)

    # Calculate speech density
    total_text = " ".join(s.get("text", "") for s in segments)
    word_count = len(total_text.split())
    words_per_second = word_count / max(duration, 1)

    # Speech coverage: what fraction of video has speech
    speech_duration = sum(s.get("end", 0) - s.get("start", 0) for s in segments)
    speech_coverage = speech_duration / max(duration, 1)

    # Estimate based on content density
    # A good 30s clip needs ~80 words; a 60s clip needs ~160 words
    avg_clip_words = 100  # ~40s clip average
    content_based_max = max(1, word_count // avg_clip_words)

    # Also cap based on duration (can't have overlapping clips)
    avg_clip_duration = 40  # seconds
    duration_based_max = max(1, duration // avg_clip_duration)

    # Use the more restrictive estimate
    realistic = min(content_based_max, duration_based_max, requested_max)

    logger.info(
        f"Clip count estimation: {word_count} words, {words_per_second:.1f} wps, "
        f"{speech_coverage:.0%} speech coverage → "
        f"content_max={content_based_max}, duration_max={duration_based_max}, "
        f"requested={requested_max}, final={realistic}"
    )

    return max(1, realistic)


# ── Main pipeline ──────────────────────────────────────────────────────────────

async def extract_viral_clips(
    video,
    user_settings,
    max_clips: int = 3,
    caption_style: str = "viral",
    whisper_quality: str = "balanced",
    force_retranscribe: bool = False,
    job_id: str = None,
    user_id: str = "local",
    min_duration: int = None,
    max_duration: int = None,
) -> list[dict]:
    """
    Full clip extraction pipeline.
    Returns list of dicts with video_path, title, metadata, status flags, etc.
    """
    # Step 1: Load or transcribe segments (10%)
    if job_id:
        await ws_manager.send_progress(job_id, 5, "Loading transcript...", user_id)
    segments = await _load_or_transcribe_segments(
        video, user_settings, whisper_quality=whisper_quality,
        force_retranscribe=force_retranscribe, job_id=job_id, user_id=user_id,
    )

    # Validate transcript quality
    _validate_transcript(segments, video)

    # Auto-scale max_clips based on actual content
    duration = video.duration_seconds or 0
    effective_max = _estimate_realistic_clip_count(segments, duration, max_clips)
    if effective_max < max_clips:
        logger.info(f"Scaled max_clips from {max_clips} to {effective_max} based on content analysis")

    # Step 2: AI selects best clip windows (15-30%)
    if job_id:
        await ws_manager.send_progress(job_id, 15, "AI analyzing transcript for viral moments...", user_id)

    # Use chunk-based extraction for large requests
    if effective_max > 8 and duration > 300:
        clip_windows = await _chunked_clip_selection(
            segments, video.title or "Untitled", duration,
            effective_max, user_settings,
            min_duration=min_duration, max_duration=max_duration,
            job_id=job_id, user_id=user_id,
        )
    else:
        clip_windows = await _select_clip_windows_with_retries(
            segments, video.title or "Untitled", duration,
            effective_max, user_settings,
            min_duration=min_duration, max_duration=max_duration,
            job_id=job_id, user_id=user_id,
        )

    if not clip_windows:
        seg_count = len(segments)
        total_text = len(" ".join(s.get("text", "") for s in segments))
        raise ValueError(
            f"AI could not identify suitable clip segments after multiple attempts "
            f"(video: {duration}s, {seg_count} segments, {total_text} chars of transcript). "
            f"This can happen if the video has minimal speech, lacks distinct moments, "
            f"or the transcript quality is poor. "
            f"Try: (1) re-analyze with higher Whisper quality, (2) use a different video, "
            f"or (3) set custom clip duration range."
        )

    logger.info(f"AI selected {len(clip_windows)} clip windows from {video.id[:8]}")

    # Step 3: Process all clips in PARALLEL (30-95%)
    if job_id:
        await ws_manager.send_progress(job_id, 30, f"Processing {len(clip_windows)} clips (extracting, captioning, thumbnails)...", user_id)

    results = await _process_clips_parallel(
        video=video,
        clip_windows=clip_windows,
        segments=segments,
        caption_style=caption_style,
        user_settings=user_settings,
        job_id=job_id,
        user_id=user_id,
    )

    if not results:
        raise ValueError(
            f"All {len(clip_windows)} clip extractions failed during video processing. "
            f"This may indicate a corrupt source video or FFmpeg issue. "
            f"Try re-downloading the video or check that the video file plays correctly."
        )

    logger.info(f"Successfully extracted {len(results)}/{len(clip_windows)} clips from {video.id[:8]}")
    return results


def _validate_transcript(segments: list[dict], video) -> None:
    """Validate transcript has enough speech content for clip extraction."""
    if not segments:
        raise ValueError(
            "No transcript available for clip extraction. "
            "The video may have no audio track or transcription failed. "
            "Try re-analyzing the video first."
        )

    total_text = " ".join(s.get("text", "") for s in segments).strip()
    if len(total_text) < 50:
        raise ValueError(
            f"Insufficient speech content for clip extraction "
            f"(only {len(total_text)} characters of transcript found across {len(segments)} segments). "
            f"This video may be mostly music/silence with very little speech. "
            f"Try re-analyzing with a higher Whisper quality setting."
        )

    # Check if segments cover enough of the video duration
    duration = video.duration_seconds or 0
    if duration > 0 and segments:
        last_seg_end = max(s.get("end", 0) for s in segments)
        coverage = last_seg_end / duration
        if coverage < 0.1:
            logger.warning(
                f"Transcript covers only {coverage:.0%} of video duration. "
                f"Clip selection may miss later segments."
            )


async def _load_or_transcribe_segments(video, user_settings, whisper_quality: str = "balanced", force_retranscribe: bool = False, job_id: str = None, user_id: str = "local") -> list[dict]:
    """Load segments from DB or run Whisper if needed."""
    # Try loading from DB first (skip if user wants to re-transcribe)
    if not force_retranscribe and video.transcript_segments_json:
        try:
            segments = json.loads(video.transcript_segments_json)
            if segments:
                logger.info(f"Using cached transcript segments for {video.id[:8]}")
                return segments
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Corrupt transcript_segments_json for {video.id[:8]}, re-transcribing")

    # Need to run Whisper
    audio_path = video.audio_path or video.video_path
    if not audio_path:
        logger.error(f"No audio/video path for {video.id[:8]}")
        return []
    if not Path(audio_path).exists():
        logger.error(f"Audio file not found: {audio_path} (video {video.id[:8]})")
        return []

    duration_min = round((video.duration_seconds or 0) / 60, 1)
    logger.info(f"Running Whisper for clip extraction on {video.id[:8]} (quality={whisper_quality})")
    if job_id:
        await ws_manager.send_progress(
            job_id, 7,
            f"Transcribing {duration_min}min audio (this may take a few minutes)...",
            user_id,
        )

    from backend.services.whisper_service import whisper_service

    try:
        await asyncio.to_thread(whisper_service.load, whisper_quality)
        transcript_data = await whisper_service.transcribe(audio_path)
    except Exception as e:
        logger.error(f"Whisper transcription failed for {video.id[:8]}: {e}")
        return []

    segments = transcript_data.get("segments", [])

    # Back-fill DB
    if segments:
        from backend.database import AsyncSessionLocal
        from backend.models.downloaded_video import DownloadedVideo
        from sqlalchemy import select
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(DownloadedVideo).where(DownloadedVideo.id == video.id)
                )
                row = result.scalar_one_or_none()
                if row:
                    row.transcript_segments_json = json.dumps(segments)
                    if not row.transcript:
                        row.transcript = transcript_data.get("text", "")
                        row.transcript_language = transcript_data.get("language")
                    await db.commit()
            logger.info(f"Back-filled transcript_segments_json for {video.id[:8]}")
        except Exception as e:
            logger.warning(f"Failed to back-fill transcript for {video.id[:8]}: {e}")

    return segments


# ── Clip selection strategies ──────────────────────────────────────────────────

async def _select_clip_windows_with_retries(
    segments, title, duration, max_clips, user_settings,
    min_duration=None, max_duration=None, job_id=None, user_id="local",
) -> list[dict]:
    """Try clip selection with progressively relaxed constraints."""
    # Attempt 1: normal constraints
    clip_windows = await _select_clip_windows(
        segments, title, duration, max_clips, user_settings,
        min_duration=min_duration, max_duration=max_duration,
    )
    if clip_windows:
        return clip_windows

    # Attempt 2: relaxed duration (10-90s)
    logger.info("No clips found with default constraints, retrying with relaxed duration (10-90s)...")
    if job_id:
        await ws_manager.send_progress(job_id, 20, "Retrying with relaxed duration constraints...", user_id)
    clip_windows = await _select_clip_windows(
        segments, title, duration, max_clips, user_settings,
        min_duration=10, max_duration=90,
    )
    if clip_windows:
        return clip_windows

    # Attempt 3: very permissive (5-120s) but keep reasonable clip count (halved, min 2)
    reduced_clips = max(2, max_clips // 2)
    logger.info(f"Still no clips, trying permissive extraction (5-120s, {reduced_clips} clips)...")
    if job_id:
        await ws_manager.send_progress(job_id, 25, "Last attempt with relaxed constraints...", user_id)
    clip_windows = await _select_clip_windows(
        segments, title, duration, reduced_clips, user_settings,
        min_duration=5, max_duration=120,
    )
    return clip_windows or []


async def _chunked_clip_selection(
    segments, title, duration, max_clips, user_settings,
    min_duration=None, max_duration=None, job_id=None, user_id="local",
) -> list[dict]:
    """
    Split the video into time chunks and run AI clip selection on each chunk
    in parallel. This solves the problem of truncated transcripts and AI
    struggling to output many clips in one call.

    For a 18-min video requesting 35 clips:
    - Split into 4 chunks of ~4.5min each
    - Ask each chunk for ~9 clips
    - Merge, deduplicate, and return top clips by virality score
    """
    # Calculate chunk parameters
    clips_per_ai_call = 8  # sweet spot for AI reliability
    num_chunks = max(2, math.ceil(max_clips / clips_per_ai_call))
    chunk_duration = duration / num_chunks
    clips_per_chunk = math.ceil(max_clips / num_chunks) + 1  # +1 for safety margin

    logger.info(
        f"Chunked extraction: {num_chunks} chunks of {chunk_duration:.0f}s, "
        f"{clips_per_chunk} clips/chunk, total target={max_clips}"
    )

    if job_id:
        await ws_manager.send_progress(
            job_id, 18,
            f"Analyzing {num_chunks} sections of the video in parallel...",
            user_id,
        )

    # Build tasks for each chunk
    async def _process_chunk(chunk_idx):
        chunk_start = chunk_idx * chunk_duration
        chunk_end = min((chunk_idx + 1) * chunk_duration, duration)

        # Filter segments to this chunk
        chunk_segments = [
            s for s in segments
            if s.get("end", 0) > chunk_start and s.get("start", 0) < chunk_end
        ]

        if not chunk_segments:
            return []

        # Check if chunk has enough content
        chunk_text = " ".join(s.get("text", "") for s in chunk_segments)
        if len(chunk_text.split()) < 30:  # less than ~15s of speech
            logger.debug(f"Chunk {chunk_idx+1}: skipping, only {len(chunk_text.split())} words")
            return []

        chunk_title = f"{title} (section {chunk_idx+1}/{num_chunks}, {chunk_start:.0f}s-{chunk_end:.0f}s)"

        windows = await _select_clip_windows(
            chunk_segments, chunk_title, chunk_end - chunk_start,
            clips_per_chunk, user_settings,
            min_duration=min_duration, max_duration=max_duration,
            time_offset=chunk_start,
        )
        return windows or []

    # Run all chunks in parallel
    chunk_tasks = [_process_chunk(i) for i in range(num_chunks)]
    chunk_results = await asyncio.gather(*chunk_tasks, return_exceptions=True)

    # Merge results
    all_windows = []
    for i, result in enumerate(chunk_results):
        if isinstance(result, Exception):
            logger.warning(f"Chunk {i+1} failed: {result}")
            continue
        logger.info(f"Chunk {i+1}: found {len(result)} clips")
        all_windows.extend(result)

    if not all_windows:
        # Fallback: try single-call extraction with reduced clip count
        logger.warning("All chunks returned 0 clips, falling back to single-call extraction")
        return await _select_clip_windows_with_retries(
            segments, title, duration, min(max_clips, 5), user_settings,
            min_duration=min_duration, max_duration=max_duration,
            job_id=job_id, user_id=user_id,
        )

    # Remove overlapping clips (keep higher virality score)
    all_windows.sort(key=lambda w: w.get("virality_score", 0), reverse=True)
    deduped = _remove_overlapping_clips(all_windows)

    # Return top clips by virality
    result = deduped[:max_clips]
    logger.info(f"Chunked extraction: {len(all_windows)} raw → {len(deduped)} deduped → {len(result)} final")
    return result


def _remove_overlapping_clips(windows: list[dict]) -> list[dict]:
    """Remove overlapping clips, keeping higher-scored ones (assumed pre-sorted by score desc)."""
    kept = []
    for w in windows:
        overlaps = False
        for k in kept:
            # Check if they overlap (with 2s tolerance)
            if w["start"] < k["end"] - 2 and w["end"] > k["start"] + 2:
                overlaps = True
                break
        if not overlaps:
            kept.append(w)
    return kept


async def _select_clip_windows(
    segments: list[dict],
    title: str,
    duration: int,
    max_clips: int,
    user_settings,
    min_duration: int = None,
    max_duration: int = None,
    time_offset: float = 0,
) -> list[dict]:
    """Use AI to identify the best clip windows from the transcript."""
    # Dynamic clip duration based on source video length (can be overridden)
    if min_duration and max_duration:
        min_clip_sec, max_clip_sec = min_duration, max_duration
    elif duration and duration < 120:
        min_clip_sec, max_clip_sec = 15, min(60, max(duration - 5, 20))
    elif duration and duration < 300:
        min_clip_sec, max_clip_sec = 20, 60
    else:
        min_clip_sec, max_clip_sec = 30, 60

    # Build segments text — scale budget based on clip count
    char_budget = min(20000, max(8000, max_clips * 1500))
    segments_text = _build_segments_text(segments, duration, max_chars=char_budget)

    # Infer niche from title
    niche = title if title != "Untitled" else "general content"

    prompt = CLIP_SELECTION_PROMPT.format(
        max_clips=max_clips,
        min_clip=min_clip_sec,
        max_clip=max_clip_sec,
        title=title,
        duration=duration,
        niche=niche,
        segments_text=segments_text,
    )

    from backend.core.ai_provider import get_ai_client
    ai = get_ai_client(user_settings)

    # Try up to 2 times if AI returns invalid response
    windows = None
    for attempt in range(2):
        try:
            # Scale max_tokens: ~200 tokens per clip JSON object + buffer
            token_limit = max(2000, min(max_clips * 250 + 500, 16000))
            response = await ai.chat(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=token_limit,
            )
            parsed = _parse_json_response(response)
            if parsed and isinstance(parsed, list):
                windows = parsed
                break
            elif parsed and isinstance(parsed, dict):
                # AI returned a single clip as dict instead of array
                windows = [parsed]
                break
            else:
                logger.warning(
                    f"AI clip selection attempt {attempt + 1}: invalid format (parsed={type(parsed).__name__}). "
                    f"Response length={len(response)}, first 300 chars: {response[:300]}"
                )
        except Exception as e:
            logger.warning(f"AI clip selection attempt {attempt + 1} failed: {e}")

    if not windows:
        logger.warning(f"AI clip selection returned no valid response after 2 attempts for '{title[:50]}'")
        return []

    logger.info(f"AI returned {len(windows)} raw clip candidates for '{title[:50]}'")

    # Validate and clean windows
    valid = []
    for w in windows:
        try:
            start = float(w.get("start", 0))
            end = float(w.get("end", 0))
        except (TypeError, ValueError):
            continue

        # Apply time offset for chunked extraction
        if time_offset > 0:
            start += time_offset
            end += time_offset

        # Clamp to valid range
        if start < 0:
            start = 0
        total_duration = duration + time_offset if time_offset > 0 else duration
        if total_duration and end > total_duration:
            end = total_duration

        if start >= end:
            continue

        # Re-validate length AFTER clamping — be lenient
        clip_len = end - start
        if clip_len < 5:
            logger.debug(f"Skipping clip {start:.1f}-{end:.1f} ({clip_len:.1f}s): under 5s minimum")
            continue
        if clip_len > max_clip_sec + 30:
            # Way too long — trim from end rather than discarding
            end = start + max_clip_sec
            clip_len = max_clip_sec
            logger.debug(f"Trimmed oversized clip to {start:.1f}-{end:.1f} ({clip_len:.1f}s)")
        if clip_len < min_clip_sec and clip_len >= 5:
            logger.debug(f"Accepting short clip {start:.1f}-{end:.1f} ({clip_len:.1f}s, below {min_clip_sec}s min)")

        w["start"] = round(start, 1)
        w["end"] = round(end, 1)
        # Ensure virality_score is present and valid
        try:
            score = float(w.get("virality_score", 5))
            w["virality_score"] = max(1, min(10, score))
        except (TypeError, ValueError):
            w["virality_score"] = 5.0
        valid.append(w)

    # Sort by virality score descending
    valid.sort(key=lambda w: w.get("virality_score", 0), reverse=True)
    return valid[:max_clips]


def _build_segments_text(segments: list[dict], duration: int, max_chars: int = 12000) -> str:
    """Build transcript text for AI, with intelligent handling of long videos."""
    if not segments:
        return ""

    # For very long videos (>30 min), sample from beginning, middle, and end
    total_text_len = sum(len(f"[{s['start']:.1f}s] {s.get('text', '')}") for s in segments)
    if total_text_len > max_chars * 2 and duration > 1800:
        # Sample strategy: first 25%, skip, middle 25%, skip, last 25%
        quarter = max(len(segments) // 4, 1)
        mid_start = len(segments) // 2 - quarter // 2
        sampled = (
            segments[:quarter]
            + [{"start": segments[quarter]["start"], "end": segments[quarter]["end"], "text": "... (segments omitted) ..."}]
            + segments[mid_start:mid_start + quarter]
            + [{"start": segments[-quarter]["start"], "end": segments[-quarter]["end"], "text": "... (segments omitted) ..."}]
            + segments[-quarter:]
        )
        lines = []
        char_count = 0
        for s in sampled:
            line = f"[{s['start']:.1f}s - {s['end']:.1f}s] {s.get('text', '')}"
            if char_count + len(line) > max_chars:
                lines.append(f"... (truncated at {s['start']:.0f}s of {duration}s total)")
                break
            lines.append(line)
            char_count += len(line)
        return "\n".join(lines)

    # Normal case: include all segments up to limit
    lines = []
    char_count = 0
    for s in segments:
        line = f"[{s['start']:.1f}s - {s['end']:.1f}s] {s.get('text', '')}"
        if char_count + len(line) > max_chars:
            lines.append(f"... (truncated at {s['start']:.0f}s of {duration}s total)")
            break
        lines.append(line)
        char_count += len(line)
    return "\n".join(lines)


async def _process_clips_parallel(
    video,
    clip_windows: list[dict],
    segments: list[dict],
    caption_style: str,
    user_settings,
    job_id: str = None,
    user_id: str = "local",
) -> list[dict]:
    """Process all clips in parallel: extract → caption → thumbnail → metadata."""
    from backend.services.ffmpeg_service import extract_clip, extract_thumbnail

    total = len(clip_windows)

    # Phase 1: Extract all clips in parallel
    if job_id:
        await ws_manager.send_progress(job_id, 35, f"Cutting {total} clips from source video...", user_id)

    async def _extract_one(i, window):
        clip_path = settings.GENERATED_DIR / f"clip_{video.id[:8]}_{uuid4().hex[:6]}.mp4"
        await extract_clip(
            Path(video.video_path), window["start"], window["end"],
            clip_path, vertical=True,
        )
        return clip_path

    extract_tasks = [_extract_one(i, w) for i, w in enumerate(clip_windows)]
    clip_paths = await asyncio.gather(*extract_tasks, return_exceptions=True)

    # Phase 2: Burn captions in parallel (on successfully extracted clips)
    if job_id:
        await ws_manager.send_progress(job_id, 55, f"Adding captions to {total} clips...", user_id)

    async def _caption_one(i, clip_path, window):
        if isinstance(clip_path, Exception):
            return clip_path, "extract_failed"

        clip_segments = _filter_and_offset_segments(segments, window["start"], window["end"])
        captioned_path, caption_status = await _burn_clip_captions(clip_path, clip_segments, caption_style)
        return captioned_path, caption_status

    caption_tasks = [_caption_one(i, cp, w) for i, (cp, w) in enumerate(zip(clip_paths, clip_windows))]
    caption_results = await asyncio.gather(*caption_tasks, return_exceptions=True)

    # Phase 3: Thumbnails + metadata in parallel
    if job_id:
        await ws_manager.send_progress(job_id, 75, f"Generating thumbnails and metadata...", user_id)

    results = []
    thumb_tasks = []
    meta_tasks = []

    for i, (cap_result, window) in enumerate(zip(caption_results, clip_windows)):
        if isinstance(cap_result, Exception):
            logger.error(f"Clip {i+1} processing failed: {cap_result}")
            continue

        captioned_path, caption_status = cap_result
        clip_segments = _filter_and_offset_segments(segments, window["start"], window["end"])

        # Adaptive thumbnail timestamp (30% through clip, max 5s)
        clip_dur = window["end"] - window["start"]
        thumb_ts = min(clip_dur * 0.3, 5.0)
        thumb_tasks.append(extract_thumbnail(captioned_path, timestamp=thumb_ts))

        transcript_text = " ".join(s["text"] for s in clip_segments)
        meta_tasks.append(_generate_clip_metadata(
            window.get("title", f"Clip {i+1}"),
            transcript_text, user_settings,
        ))

        results.append({
            "_index": i,
            "captioned_path": captioned_path,
            "caption_status": caption_status,
            "window": window,
            "clip_segments": clip_segments,
            "raw_clip_path": clip_paths[i] if not isinstance(clip_paths[i], Exception) else None,
        })

    # Run thumbnail + metadata in parallel
    all_thumbs = await asyncio.gather(*thumb_tasks, return_exceptions=True)
    all_metas = await asyncio.gather(*meta_tasks, return_exceptions=True)

    # Phase 4: Assemble final results + cleanup
    if job_id:
        await ws_manager.send_progress(job_id, 90, "Finalizing clips...", user_id)

    final_results = []
    for idx, r in enumerate(results):
        window = r["window"]
        captioned_path = r["captioned_path"]
        caption_status = r["caption_status"]

        # Thumbnail
        thumb_path = all_thumbs[idx] if idx < len(all_thumbs) else None
        if isinstance(thumb_path, Exception):
            logger.warning(f"Thumbnail extraction failed for clip {idx+1}: {thumb_path}")
            thumb_path = None

        # Metadata
        metadata = all_metas[idx] if idx < len(all_metas) else {}
        metadata_status = "ai_generated"
        if isinstance(metadata, Exception):
            logger.warning(f"Metadata generation failed for clip {idx+1}: {metadata}")
            metadata = _default_metadata(window.get("title", f"Clip {idx+1}"), "")
            metadata_status = "fallback"
        elif not metadata or not isinstance(metadata, dict):
            metadata = _default_metadata(window.get("title", f"Clip {idx+1}"), "")
            metadata_status = "fallback"

        transcript_text = " ".join(s["text"] for s in r["clip_segments"])

        # Cleanup intermediate files (raw clip before captioning)
        raw_path = r.get("raw_clip_path")
        if raw_path and isinstance(raw_path, Path) and raw_path != captioned_path:
            try:
                raw_path.unlink(missing_ok=True)
            except Exception:
                pass

        final_results.append({
            "video_path": captioned_path,
            "thumbnail_path": thumb_path,
            "title": window.get("title", f"Clip {idx+1}"),
            "transcript_text": transcript_text,
            "reason": window.get("reason", ""),
            "start": window["start"],
            "end": window["end"],
            "duration_seconds": int(window["end"] - window["start"]),
            "virality_score": window.get("virality_score", 5.0),
            "caption_status": caption_status,
            "metadata_status": metadata_status,
            **metadata,
        })

    return final_results


def _filter_and_offset_segments(segments: list[dict], clip_start: float, clip_end: float) -> list[dict]:
    """Filter segments to clip range and offset timestamps to start at 0."""
    filtered = []
    for s in segments:
        seg_start = s.get("start", 0)
        seg_end = s.get("end", 0)
        # Include if segment overlaps with clip range
        if seg_end > clip_start and seg_start < clip_end:
            adjusted = dict(s)
            adjusted["start"] = max(seg_start - clip_start, 0)
            adjusted["end"] = min(seg_end - clip_start, clip_end - clip_start)
            # Also adjust word timestamps if present
            if "words" in adjusted:
                adjusted["words"] = [
                    {**w, "start": max(w["start"] - clip_start, 0), "end": min(w["end"] - clip_start, clip_end - clip_start)}
                    for w in adjusted["words"]
                    if w.get("end", 0) > clip_start and w.get("start", 0) < clip_end
                ]
            filtered.append(adjusted)
    return filtered


async def _burn_clip_captions(clip_path: Path, segments: list[dict], style: str = "viral") -> tuple[Path, str]:
    """Burn captions onto a clip. Returns (output_path, status)."""
    if not segments:
        return clip_path, "no_segments"

    try:
        from backend.services.caption_service import generate_captions_ass, burn_captions
        ass_path = await generate_captions_ass(segments, style=style, aspect_ratio="9:16")
        captioned = await burn_captions(clip_path, ass_path)

        # Cleanup ASS file
        if ass_path and ass_path.exists():
            try:
                ass_path.unlink(missing_ok=True)
            except Exception:
                pass

        return captioned, "applied"
    except Exception as e:
        logger.warning(f"Caption burning failed for clip {clip_path.name}: {e}")
        return clip_path, "failed"


def _default_metadata(title: str, transcript_text: str) -> dict:
    """Default metadata when AI generation fails."""
    return {
        "youtube_title": title,
        "youtube_description": transcript_text[:200] if transcript_text else "",
        "youtube_tags": [],
        "tiktok_title": title,
    }


async def _generate_clip_metadata(title: str, transcript_text: str, user_settings) -> dict:
    """Generate YouTube/TikTok metadata for a clip via AI."""
    defaults = _default_metadata(title, transcript_text)

    try:
        from backend.core.ai_provider import get_ai_client
        ai = get_ai_client(user_settings)
        prompt = CLIP_METADATA_PROMPT.format(
            title=title,
            transcript_text=transcript_text[:2000],
        )
        response = await ai.chat(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=512,
        )
        parsed = _parse_json_response(response)
        if parsed and isinstance(parsed, dict):
            return {**defaults, **parsed}
    except Exception as e:
        logger.warning(f"Clip metadata generation failed for '{title[:30]}': {e}")

    return defaults


def _parse_json_response(text: str) -> any:
    """Extract JSON from AI response, handling markdown fences."""
    if not text:
        return None
    text = text.strip()
    # Remove markdown code fences
    match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON array or object in the text
        for pattern in [r'\[.*\]', r'\{.*\}']:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    continue
    return None

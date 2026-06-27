"""Anime Lo-fi — Script → Audio → Image-per-segment → Raw Video."""
import json
import logging
import random
import re
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from backend.config import settings
from backend.core.ai_provider import get_ai_client
from backend.services.tts_service import generate_tts, TTSProvider
from backend.services.whisper_service import whisper_service

logger = logging.getLogger(__name__)

STORAGE = Path("storage/anime_lofi")
AUDIO_DIR = STORAGE / "audio"
SEGMENTS_DIR = STORAGE / "segments"
VIDEOS_DIR = STORAGE / "videos"
OUTPUT_DIR = STORAGE / "output"

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
SEGMENT_DURATION = 3.5

COLORS = [
    "#1a1a2e", "#16213e", "#0f3460", "#533483",
    "#e94560", "#ff6b6b", "#c73866", "#6c5ce7",
    "#2d3436", "#636e72", "#0984e3", "#00b894",
    "#e17055", "#d63031", "#6c5ce7", "#a29bfe",
]


def _ensure_dirs():
    for d in (AUDIO_DIR, SEGMENTS_DIR, VIDEOS_DIR, OUTPUT_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ── Step 1: Structured Script (LLM segments) ──────────────────────────

import backend.services.anime_lofi_llm as n2llm


async def generate_script(
    user_idea: str,
    user_settings=None,
) -> dict:
    """Generate structured segments via the lo-fi anime LLM prompt.

    Returns ``{"segments": [...], "full_script": "..."}`` where each
    segment has *scene_number*, *voiceover*, *scene_description*, and
    *final_comfyui_prompt*.
    """
    _ensure_dirs()
    segments = await n2llm.generate_structured_script(
        user_idea=user_idea,
        user_settings=user_settings,
    )
    full_script = await n2llm.voiceover_text_from_segments(segments)
    return {"segments": segments, "full_script": full_script}


# ── Step 2: Audio ──────────────────────────────────────────────────────

async def generate_audio(
    script: str,
    voice: str = "en-US-AndrewMultilingualNeural",
    user_settings=None,
) -> dict:
    _ensure_dirs()
    api_key = ""
    provider = TTSProvider.EDGE_TTS
    if user_settings:
        if getattr(user_settings, "tts_provider", None) == "openai_tts":
            provider = TTSProvider.OPENAI_TTS
            api_key = getattr(user_settings, "openai_api_key", "") or settings.OPENAI_API_KEY

    clean_script = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", script).strip()
    audio_path = await generate_tts(
        text=clean_script,
        provider=provider,
        voice_id=voice,
        api_key=api_key,
    )

    filename = f"anime_lofi_audio_{uuid.uuid4().hex[:8]}.mp3"
    final_path = AUDIO_DIR / filename
    import shutil
    shutil.copy2(audio_path, final_path)

    return {"filename": filename, "path": str(final_path), "url": f"/api/anime-lofi/media/{filename}"}


# ── Step 3: Transcribe + Align to LLM segments ─────────────────────────

async def transcribe_audio(audio_filename: str, script_text: str) -> dict:
    """Transcribe audio with Whisper, return word-level timestamps + full transcript.

    For backward compatibility also returns segments grouped by duration.
    """
    audio_path = AUDIO_DIR / audio_filename
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    result = await whisper_service.transcribe(str(audio_path))
    words = []
    for seg in result.get("segments", []):
        for w in seg.get("words", []):
            words.append({
                "word": w.get("word", "").strip(),
                "start": w.get("start", 0),
                "end": w.get("end", 0),
            })

    if not words:
        words = _backup_word_split(script_text, result.get("text", ""))

    return {"words": words, "transcript": result.get("text", "")}


def align_segment_durations(segments: list[dict], words: list[dict]) -> list[dict]:
    """Map LLM segments to Whisper word timestamps, adding ``duration_sec``.

    Returns a new list of segment dicts enriched with ``duration_sec``.
    The mapping is done by word count proportion (LLM voiceover → Whisper words).
    """
    enriched = []
    word_idx = 0
    total_ws = len(words)

    for seg in segments:
        voiceover = seg.get("voiceover", "") or seg.get("text", "")
        seg_words = voiceover.split()
        count = len(seg_words)

        if count == 0 or word_idx >= total_ws:
            enriched.append({**seg, "duration_sec": 3.0})
            continue

        start = words[word_idx]["start"]
        end_idx = min(word_idx + count - 1, total_ws - 1)
        end = words[end_idx]["end"]
        dur = round(max(end - start, 1.5), 2)

        enriched.append({**seg, "duration_sec": dur})
        word_idx += count

    return enriched


# Legacy: transcribe + regroup into duration-based segments
async def transcribe_and_segment(audio_filename: str, script_text: str) -> dict:
    result = await transcribe_audio(audio_filename, script_text)
    words = result["words"]
    segments = _group_into_segments(words, target_dur=SEGMENT_DURATION)
    return {"segments": segments, "transcript": result["transcript"]}


def _backup_word_split(script_text: str, transcript_text: str) -> list[dict]:
    """Fallback: estimate ~3 words per second if Whisper returns no word timestamps."""
    text = transcript_text or script_text
    words = text.split()
    dur_per_word = 0.33
    result = []
    t = 0.0
    for w in words:
        result.append({"word": w, "start": t, "end": t + dur_per_word})
        t += dur_per_word
    return result


def _group_into_segments(words: list[dict], target_dur: float = 3.5) -> list[dict]:
    segments = []
    current = []
    current_start = 0.0

    for w in words:
        if not current:
            current_start = w["start"]
            current.append(w)
        else:
            duration = w["end"] - current_start
            if duration <= target_dur:
                current.append(w)
            else:
                segments.append({
                    "index": len(segments),
                    "text": " ".join(x["word"] for x in current),
                    "start": current_start,
                    "end": current[-1]["end"],
                    "duration": round(current[-1]["end"] - current_start, 2),
                })
                current_start = w["start"]
                current = [w]

    if current:
        segments.append({
            "index": len(segments),
            "text": " ".join(x["word"] for x in current),
            "start": current_start,
            "end": current[-1]["end"],
            "duration": round(current[-1]["end"] - current_start, 2),
        })

    return segments


# ── Step 4: Segment Images ─────────────────────────────────────────────

async def generate_segment_images(
    segments: list[dict],
    style_prompt: str = "",
    user_settings=None,
    on_progress=None,
) -> list[dict]:
    _ensure_dirs()

    from backend.services.anime_lofi_comfy import generate_all_segment_images as _comfy_gen

    try:
        return await _comfy_gen(segments, user_settings, on_progress=on_progress)
    except (FileNotFoundError, RuntimeError, ValueError) as e:
        logger.warning("ComfyUI image gen unavailable (%s), falling back to dummy images", e)
        # Fallback to dummy images
        result = []
        for i, seg in enumerate(segments):
            text = seg.get("voiceover") or seg.get("text") or ""
            img_filename = f"seg_dummy_{uuid.uuid4().hex[:8]}.png"
            img_path = SEGMENTS_DIR / img_filename
            _create_dummy_image(img_path, text[:80], i, len(segments))
            result.append({
                "index": i,
                "scene_number": seg.get("scene_number", i + 1),
                "filename": img_filename,
                "path": str(img_path),
                "url": f"/api/anime-lofi/media/{quote(img_filename)}",
                "segment_text": text,
                "duration": round(max(len(text.split()) / 3.0, 1.5), 2),
                "final_comfyui_prompt": seg.get("final_comfyui_prompt", ""),
            })
        return result


def _create_dummy_image(path: Path, text: str, index: int, total: int):
    """Create a dummy colored PNG with segment text overlay."""
    from PIL import Image, ImageDraw, ImageFont

    color = COLORS[index % len(COLORS)]
    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), color)
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
    except Exception:
        font = ImageFont.load_default()

    # Segment number top-right
    label = f"{index + 1} / {total}"
    bbox = draw.textbbox((0, 0), label, font=font)
    draw.text((VIDEO_WIDTH - bbox[2] - 40, 30), label, fill="white", font=font)

    # Centered text (word-wrapped roughly)
    words = text.split()
    lines = []
    line = ""
    for w in words:
        test = f"{line} {w}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] < VIDEO_WIDTH - 120:
            line = test
        else:
            lines.append(line)
            line = w
    if line:
        lines.append(line)

    y_start = VIDEO_HEIGHT // 2 - (len(lines) * 60) // 2
    for i, l in enumerate(lines):
        bbox = draw.textbbox((0, 0), l, font=font)
        x = (VIDEO_WIDTH - (bbox[2] - bbox[0])) // 2
        draw.text((x, y_start + i * 60), l, fill="white", font=font)

    # Dummy indicator
    try:
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
    except Exception:
        small = font
    draw.text((30, VIDEO_HEIGHT - 60), "🎨 [dummy image — replace with AI gen]", fill="#cccccc", font=small)

    img.save(str(path), "PNG")


# ── Step 5: Segment Videos (LTX img2vid) ───────────────────────────────

async def generate_segment_videos(
    images: list[dict],
    segments: list[dict],
    user_settings=None,
    on_progress=None,
) -> list[dict]:
    """Generate one LTX img2vid per segment using video_prompt + aligned duration."""
    _ensure_dirs()
    from backend.services.anime_lofi_comfy import generate_all_segment_videos as _comfy_vid_gen

    video_prompts = [s.get("video_prompt", "") for s in segments]
    durations = [s.get("duration_sec", 3.0) for s in segments]

    try:
        return await _comfy_vid_gen(
            images=images,
            video_prompts=video_prompts,
            durations=durations,
            user_settings=user_settings,
            on_progress=on_progress,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as e:
        logger.warning("ComfyUI video gen unavailable (%s), falling back to segment images", e)
        # Fallback: pass through images as "videos" (for backward compat)
        result = []
        for i, img in enumerate(images):
            dur = durations[i] if i < len(durations) else 3.0
            result.append({
                "index": i,
                "scene_number": img.get("scene_number", i + 1),
                "filename": img.get("filename", "").replace(".png", ".mp4"),
                "path": img.get("path", ""),
                "url": img.get("url", ""),
                "segment_text": img.get("segment_text", ""),
                "duration": dur,
                "video_prompt": segments[i].get("video_prompt", "") if i < len(segments) else "",
            })
        return result


# ── Step 6: Compilation Video (concat segment clips + audio) ───────────

async def render_compilation_video(
    videos: list[dict],
    audio_filename: str,
) -> dict:
    """Concatenate per-segment video clips and overlay the master audio track.

    *videos* — list of video metadata (``path``), one per segment.
    *audio_filename* — master audio file name in AUDIO_DIR.
    """
    _ensure_dirs()
    audio_path = AUDIO_DIR / audio_filename
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    concat_file = OUTPUT_DIR / f"concat_vids_{uuid.uuid4().hex[:8]}.txt"
    output_filename = f"anime_lofi_final_{uuid.uuid4().hex[:8]}.mp4"
    output_path = OUTPUT_DIR / output_filename

    # Use ffprobe to get actual video durations for concat demuxer
    concat_lines = []
    for i, vid in enumerate(videos):
        vid_path = Path(vid["path"])
        if not vid_path.exists():
            logger.warning("Video file not found, skipping: %s", vid_path)
            continue

        # Get actual duration via ffprobe
        probe = await asyncio_run_subprocess([
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(vid_path),
        ])
        if probe.returncode == 0:
            raw = (probe.stdout or b"").decode().strip()
            dur = float(raw) if raw else 0
        else:
            dur = vid.get("duration", 3.0)

        if dur <= 0:
            dur = vid.get("duration", 3.0)

        concat_lines.append(f"file '{vid_path.resolve()}'")
        concat_lines.append(f"duration {dur:.3f}")

        # Last entry needs a duplicate with tiny duration for concat demuxer
        if i == len(videos) - 1:
            concat_lines.append(f"file '{vid_path.resolve()}'")
            concat_lines.append("duration 0.001")

    if not concat_lines:
        raise RuntimeError("No valid video files to concatenate")

    concat_file.write_text("\n".join(concat_lines))

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-i", str(audio_path.resolve()),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        "-movflags", "+faststart",
        str(output_path.resolve()),
    ]

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-i", str(audio_path.resolve()),
        "-map", "0:v:0",       # video from concat (strips any audio from segment clips)
        "-map", "1:a:0",       # audio from master audio track
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        "-movflags", "+faststart",
        str(output_path.resolve()),
    ]

    logger.info("Rendering compilation video: %s", " ".join(cmd))
    proc = await asyncio_run_subprocess(cmd)
    if proc.returncode != 0:
        stderr = (proc.stderr or b"").decode()[:500]
        raise RuntimeError(f"FFmpeg compilation failed (code {proc.returncode}): {stderr}")

    concat_file.unlink(missing_ok=True)

    return {
        "filename": output_filename,
        "path": str(output_path),
        "url": f"/api/anime-lofi/media/{quote(output_filename)}",
    }


# ── Legacy: Raw Image-based Video ──────────────────────────────────────

async def render_raw_video(
    segments: list[dict],
    image_filenames: list[dict],
    audio_filename: str,
) -> dict:
    _ensure_dirs()
    audio_path = AUDIO_DIR / audio_filename
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    import subprocess as _sp
    probe = _sp.run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ], capture_output=True, text=True)
    total_dur = float(probe.stdout.strip())

    concat_file = OUTPUT_DIR / f"concat_{uuid.uuid4().hex[:8]}.txt"
    output_filename = f"anime_lofi_video_{uuid.uuid4().hex[:8]}.mp4"
    output_path = OUTPUT_DIR / output_filename

    # Map image filenames by index
    image_map = {img["index"]: img for img in image_filenames}

    # Collect durations and normalize to audio length
    raw_durations = []
    for seg in segments:
        img_info = image_map.get(seg.get("index") or (seg.get("scene_number", 1) - 1))
        if not img_info:
            continue
        dur = seg.get("duration") or img_info.get("duration", 3.5)
        raw_durations.append((dur, img_info))

    if not raw_durations:
        raise RuntimeError("No valid segment images to render")

    raw_sum = sum(d for d, _ in raw_durations)
    scale = total_dur / raw_sum if raw_sum > 0 else 1.0

    concat_lines = []
    for i, (dur, img_info) in enumerate(raw_durations):
        img_path = SEGMENTS_DIR / img_info["filename"]
        if not img_path.exists():
            continue
        scaled = dur * scale
        concat_lines.append(f"file '{img_path.resolve()}'")
        concat_lines.append(f"duration {scaled:.3f}")
        # Concat demuxer: last entry needs a duplicate with tiny duration
        # to display its full duration.
        if i == len(raw_durations) - 1:
            concat_lines.append(f"file '{img_path.resolve()}'")
            concat_lines.append("duration 0.001")

    concat_file.write_text("\n".join(concat_lines))

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-i", str(audio_path.resolve()),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-shortest",
        "-movflags", "+faststart",
        str(output_path.resolve()),
    ]

    logger.info("Rendering video: %s", " ".join(cmd))
    proc = await asyncio_run_subprocess(cmd)
    if proc.returncode != 0:
        stderr = (proc.stderr or b"").decode()[:500]
        raise RuntimeError(f"FFmpeg failed (code {proc.returncode}): {stderr}")

    concat_file.unlink(missing_ok=True)

    return {
        "filename": output_filename,
        "path": str(output_path),
        "url": f"/api/anime-lofi/media/{quote(output_filename)}",
    }


async def asyncio_run_subprocess(cmd: list[str]):
    import asyncio
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    proc.stdout = stdout
    proc.stderr = stderr
    return proc

"""Anime Lo-fi — Z-turbo txt2img + LTX img2vid via ComfyUI on RunPod."""
import asyncio
import copy
import json
import logging
import random
import uuid
from pathlib import Path
from urllib.parse import quote

import httpx

from backend.config import settings as app_settings
from backend.services.runpod_service import (
    get_comfy_base_url,
    get_pod_status,
    submit_comfy_workflow,
    wait_for_comfy_output,
    download_comfy_output,
    upload_to_comfy,
    free_comfy_memory,
)
from backend.core.api_keys import get_runpod_api_key, get_runpod_pod_id

logger = logging.getLogger(__name__)

WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / "workflows"
MAPPING_FILE = WORKFLOWS_DIR / "runpod_mapping_anime_lofi.json"
STORAGE = Path("storage/anime_lofi")
SEGMENTS_DIR = STORAGE / "segments"
VIDEOS_DIR = STORAGE / "videos"

# LTX struggles with short (<3s) or fractional durations.
# Always generate to the next multiple of 5s, then trim to actual target.
LTX_SEGMENT_BASE = 5


def _load_mapping() -> dict:
    with open(MAPPING_FILE, encoding="utf-8") as f:
        return json.load(f)


def _load_raw_workflow(filename: str) -> dict:
    path = WORKFLOWS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Workflow not found at {path}")
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not str(k).startswith("_")}


# ── TXT2IMG (Z-turbo) ─────────────────────────────────────────────────

def build_txt2img_workflow(prompt_text: str, seed: int | None = None) -> dict:
    mapping = _load_mapping()
    cfg = mapping["txt2img"]
    workflow = _load_raw_workflow(cfg["workflow_file"])

    prompt_nid = str(cfg["prompt_node_id"])
    prompt_key = cfg.get("prompt_input_key", "value")
    if prompt_nid in workflow:
        workflow[prompt_nid]["inputs"][prompt_key] = prompt_text

    seed_nid = str(cfg["seed_node_id"])
    seed_key = cfg.get("seed_input_key", "value")
    if seed_nid in workflow:
        workflow[seed_nid]["inputs"][seed_key] = seed if seed is not None else random.randint(0, 2**32 - 1)

    return workflow


async def generate_segment_image(prompt_text: str, user_settings=None) -> dict:
    api_key = get_runpod_api_key(user_settings)
    pod_id = get_runpod_pod_id(user_settings)
    if not api_key or not pod_id:
        raise RuntimeError("RunPod API key or pod ID not configured")

    status = await get_pod_status(api_key, pod_id)
    if not status.get("comfy_ready"):
        raise RuntimeError("ComfyUI is not ready on the pod")

    base_url = get_comfy_base_url(pod_id)
    workflow = build_txt2img_workflow(prompt_text)

    prompt_id = await submit_comfy_workflow(base_url, workflow)
    result = await wait_for_comfy_output(base_url, prompt_id)

    img_filename = f"zseg_{uuid.uuid4().hex[:8]}.png"
    img_path = SEGMENTS_DIR / img_filename
    img_path.parent.mkdir(parents=True, exist_ok=True)
    await download_comfy_output(base_url, result["item"], img_path)

    if app_settings.RUNPOD_FREE_MEMORY_AFTER_GENERATE:
        await free_comfy_memory(base_url)

    return {"filename": img_filename, "path": str(img_path), "url": f"/api/anime-lofi/media/{quote(img_filename)}"}


async def generate_all_segment_images(segments: list[dict], user_settings=None, on_progress=None) -> list[dict]:
    results = []
    total = len(segments)
    for i, seg in enumerate(segments):
        prompt = seg.get("final_comfyui_prompt", "") or seg.get("voiceover", "")
        try:
            img_info = await generate_segment_image(prompt, user_settings)
        except Exception as e:
            logger.error("Image gen failed for segment %s: %s", seg.get("scene_number"), e)
            img_info = _fallback_dummy(seg, i, total)
            if on_progress:
                await on_progress(i + 1, total, {**seg, "error": str(e)})

        results.append({
            "index": i,
            "scene_number": seg.get("scene_number", i + 1),
            "filename": img_info["filename"],
            "path": img_info["path"],
            "url": img_info["url"],
            "segment_text": seg.get("voiceover", ""),
            "duration": _estimate_duration(seg.get("voiceover", "")),
            "final_comfyui_prompt": prompt,
        })
        if on_progress:
            await on_progress(i + 1, total, seg)

    return results


# ── IMG2VID (LTX) ──────────────────────────────────────────────────────

def build_img2vid_workflow(
    image_filename: str,
    video_prompt: str,
    duration_sec: float,
    frame_rate: int = 25,
) -> dict:
    """Inject image, prompt, and duration into the LTX img2vid workflow."""
    mapping = _load_mapping()
    cfg = mapping["img2vid"]
    workflow = _load_raw_workflow(cfg["workflow_file"])

    # LoadImage node — set image filename
    load_nid = str(cfg["load_image_node_id"])
    load_key = cfg.get("load_image_input_key", "image")
    if load_nid in workflow:
        workflow[load_nid]["inputs"][load_key] = image_filename

    # Prompt node
    prompt_nid = str(cfg["prompt_node_id"])
    prompt_key = cfg.get("prompt_input_key", "value")
    if prompt_nid in workflow:
        workflow[prompt_nid]["inputs"][prompt_key] = video_prompt

    # Duration node (seconds)
    dur_nid = str(cfg["duration_node_id"])
    dur_key = cfg.get("duration_input_key", "value")
    if dur_nid in workflow:
        workflow[dur_nid]["inputs"][dur_key] = max(round(duration_sec), 1)

    # Frame rate node
    fps_nid = str(cfg["frame_rate_node_id"])
    fps_key = cfg.get("frame_rate_input_key", "value")
    if fps_nid in workflow:
        workflow[fps_nid]["inputs"][fps_key] = frame_rate

    return workflow


async def _trim_video(input_path: Path, target_duration: float) -> Path:
    """Trim video to *target_duration* seconds using ffmpeg."""
    trimmed_path = input_path.with_stem(f"{input_path.stem}_trimmed")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path.resolve()),
        "-t", str(target_duration),
        "-c", "copy",
        "-map", "0:v:0",
        "-map", "0:a:0?",
        str(trimmed_path.resolve()),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.warning("Trim failed for %s (%.1fs): %s", input_path.name, target_duration, (stderr or b"")[:200])
        return input_path
    input_path.unlink(missing_ok=True)
    return trimmed_path


async def generate_segment_video(
    image_path: str,
    video_prompt: str,
    user_settings=None,
    duration_sec: float = 5.0,
) -> dict:
    """Upload image, run LTX img2vid — rounds *duration_sec* up to next
    multiple of ``LTX_SEGMENT_BASE`` (5s), then trim to actual target.

    Returns local file info with *url*, *filename*, *path*.
    """
    api_key = get_runpod_api_key(user_settings)
    pod_id = get_runpod_pod_id(user_settings)
    if not api_key or not pod_id:
        raise RuntimeError("RunPod API key or pod ID not configured")

    status = await get_pod_status(api_key, pod_id)
    if not status.get("comfy_ready"):
        raise RuntimeError("ComfyUI is not ready on the pod")

    base_url = get_comfy_base_url(pod_id)

    # 1. Upload segment image to ComfyUI's input directory
    remote_name = await upload_to_comfy(base_url, Path(image_path))

    # 2. Round duration up to next multiple of LTX_SEGMENT_BASE (5s)
    #    LTX is unreliable for short/fractional durations; we trim later.
    gen_duration = max(
        ((int(duration_sec) + LTX_SEGMENT_BASE - 1) // LTX_SEGMENT_BASE) * LTX_SEGMENT_BASE,
        LTX_SEGMENT_BASE,
    )
    workflow = build_img2vid_workflow(remote_name, video_prompt, gen_duration)
    prompt_id = await submit_comfy_workflow(base_url, workflow)
    result = await wait_for_comfy_output(base_url, prompt_id)

    # 3. Download output video
    vid_filename = f"zseg_vid_{uuid.uuid4().hex[:8]}.mp4"
    vid_path = VIDEOS_DIR / vid_filename
    vid_path.parent.mkdir(parents=True, exist_ok=True)
    await download_comfy_output(base_url, result["item"], vid_path)

    if app_settings.RUNPOD_FREE_MEMORY_AFTER_GENERATE:
        await free_comfy_memory(base_url)

    return {
        "filename": vid_path.name,
        "path": str(vid_path),
        "url": f"/api/anime-lofi/media/{quote(vid_path.name)}",
    }


async def generate_all_segment_videos(
    images: list[dict],
    video_prompts: list[str],
    durations: list[float],
    user_settings=None,
    on_progress=None,
) -> list[dict]:
    """Generate one LTX img2vid per segment.

    *images* — list of image metadata from txt2img step.
    *video_prompts* — ``video_prompt`` from each LLM segment.
    *durations* — per-segment duration in seconds (from audio transcription).

    Returns list of video metadata dicts (same order as input).
    """
    results = []
    total = len(images)
    for i, img in enumerate(images):
        prompt = video_prompts[i] if i < len(video_prompts) else ""
        dur = durations[i] if i < len(durations) else 3.0
        try:
            vid_info = await generate_segment_video(img["path"], prompt, user_settings, duration_sec=dur)
        except Exception as e:
            logger.error("Video gen failed for segment %s: %s", img.get("scene_number"), e)
            vid_info = {
                "filename": img["filename"].replace(".png", ".mp4"),
                "path": img["path"].replace(".png", ".mp4"),
                "url": img["url"].replace(".png", ".mp4"),
            }
            if on_progress:
                await on_progress(i + 1, total, {**img, "error": str(e)})

        results.append({
            "index": i,
            "scene_number": img.get("scene_number", i + 1),
            "filename": vid_info["filename"],
            "path": vid_info["path"],
            "url": vid_info["url"],
            "segment_text": img.get("segment_text", ""),
            "duration": dur,
            "video_prompt": prompt,
        })
        if on_progress:
            await on_progress(i + 1, total, img)

    return results


# ── TTS (Higgs v3 Voice Clone) ────────────────────────────────────────

AUDIO_DIR = STORAGE / "audio"
REFERENCE_AUDIO = WORKFLOWS_DIR / "en-reference-audio.mp3"


def build_tts_workflow(text: str, seed: int | None = None) -> dict:
    """Inject voiceover text and seed into the Higgs v3 Voice Clone workflow."""
    mapping = _load_mapping()
    cfg = mapping["tts"]
    workflow = _load_raw_workflow(cfg["workflow_file"])

    prompt_nid = str(cfg["prompt_node_id"])
    prompt_key = cfg.get("prompt_input_key", "text")
    if prompt_nid in workflow:
        workflow[prompt_nid]["inputs"][prompt_key] = text

    seed_nid = str(cfg["seed_node_id"])
    seed_key = cfg.get("seed_input_key", "seed")
    if seed_nid in workflow:
        workflow[seed_nid]["inputs"][seed_key] = seed if seed is not None else random.randint(0, 2**32 - 1)

    return workflow


async def generate_audio_on_runpod(text: str, user_settings=None) -> dict:
    """Generate TTS audio via Higgs v3 Voice Clone on the RunPod ComfyUI pod.

    Uploads the reference audio file, builds the workflow, submits it,
    waits for the result, and downloads the MP3.
    """
    api_key = get_runpod_api_key(user_settings)
    pod_id = get_runpod_pod_id(user_settings)
    if not api_key or not pod_id:
        raise RuntimeError("RunPod API key or pod ID not configured")

    status = await get_pod_status(api_key, pod_id)
    if not status.get("comfy_ready"):
        raise RuntimeError("ComfyUI is not ready on the pod")

    base_url = get_comfy_base_url(pod_id)

    # 1. Upload reference audio to ComfyUI's input directory
    if REFERENCE_AUDIO.exists():
        await upload_to_comfy(base_url, REFERENCE_AUDIO)

    # 2. Build and submit TTS workflow
    workflow = build_tts_workflow(text)
    prompt_id = await submit_comfy_workflow(base_url, workflow)

    # 3. Wait for audio output
    result = await wait_for_comfy_output(base_url, prompt_id)

    # 4. Download the MP3
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    audio_filename = f"anime_lofi_audio_{uuid.uuid4().hex[:8]}.mp3"
    audio_path = AUDIO_DIR / audio_filename
    await download_comfy_output(base_url, result["item"], audio_path)

    if app_settings.RUNPOD_FREE_MEMORY_AFTER_GENERATE:
        await free_comfy_memory(base_url)

    return {
        "filename": audio_filename,
        "path": str(audio_path),
        "url": f"/api/anime-lofi/media/{quote(audio_filename)}",
    }


# ── Helpers ────────────────────────────────────────────────────────────

def _estimate_duration(text: str, words_per_sec: float = 3.0) -> float:
    return max(len(text.split()) / words_per_sec, 1.5)


def _fallback_dummy(seg: dict, index: int, total: int) -> dict:
    from backend.services.anime_lofi_service import _create_dummy_image
    img_filename = f"zseg_fallback_{uuid.uuid4().hex[:8]}.png"
    img_path = SEGMENTS_DIR / img_filename
    img_path.parent.mkdir(parents=True, exist_ok=True)
    _create_dummy_image(img_path, seg.get("voiceover", "")[:80], index, total)
    return {"filename": img_filename, "path": str(img_path), "url": f"/api/anime-lofi/media/{quote(img_filename)}"}

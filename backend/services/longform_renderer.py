# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Render individual long-form storyboard scenes."""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Callable, Awaitable, Optional
from uuid import uuid4

from backend.config import settings
from backend.services import ffmpeg_service, prompt_synth_service, runpod_service
from backend.services.pexels_service import (
    search_videos, search_photos, download_clip, download_photo, trim_and_normalize_clip,
)
from backend.services.longform_planner import ltx_stock_image_query, MAX_LTX_SCENE_S

logger = logging.getLogger(__name__)


def _dims(aspect_ratio: str) -> tuple[int, int]:
    return (1080, 1920) if aspect_ratio == "9:16" else (1920, 1080)


async def render_scene(
    scene: dict,
    project: dict,
    assets_by_id: dict,
    master_audio_path: Path,
    aspect_ratio: str,
    pexels_api_key: str = "",
    runpod_base_url: str | None = None,
    on_progress: Optional[Callable[[float, str], Awaitable[None]]] = None,
) -> tuple[Path, Path | None]:
    """Render one storyboard scene. Returns (video_path, start_frame_image_path)."""
    stype = scene.get("type", "stock")
    duration = max(0.1, float(scene["end_s"]) - float(scene["start_s"]))
    tw, th = _dims(aspect_ratio)
    out = settings.TMP_DIR / f"lf_scene_{scene['id']}_{uuid4().hex[:8]}.mp4"
    start_frame: Path | None = None

    if stype in ("kenburns", "user_image", "screenshot"):
        start_frame = await _kenburns_start_frame(scene, assets_by_id)
        video = await _render_kenburns(scene, assets_by_id, duration, aspect_ratio, out, tw, th)
        return video, start_frame
    if stype == "user_video":
        start_frame = await _user_video_start_frame(scene, assets_by_id)
        video = await _render_user_video(scene, assets_by_id, duration, aspect_ratio, out, tw, th)
        return video, start_frame
    if stype == "stock":
        video, start_frame = await _render_stock(
            scene, duration, aspect_ratio, out, tw, th, pexels_api_key,
        )
        return video, start_frame
    if stype == "ltx":
        if not runpod_base_url:
            raise RuntimeError("RunPod pod not ready for LTX generation")
        video, start_frame = await _render_ltx(
            scene, assets_by_id, master_audio_path, duration, aspect_ratio, out, tw, th,
            runpod_base_url, pexels_api_key, on_progress,
        )
        return video, start_frame
    raise ValueError(f"Unknown scene type: {stype}")


async def _kenburns_start_frame(scene, assets_by_id) -> Path:
    src = scene.get("source") or {}
    aid = src.get("asset_id")
    if not aid or aid not in assets_by_id:
        raise ValueError(f"Missing asset for scene {scene['id']}")
    return Path(assets_by_id[aid]["file_path"])


async def _user_video_start_frame(scene, assets_by_id) -> Path | None:
    from backend.services.ffmpeg_service import extract_thumbnail
    src = scene.get("source") or {}
    aid = src.get("asset_id")
    if not aid or aid not in assets_by_id:
        return None
    video = Path(assets_by_id[aid]["file_path"])
    trim_in = float(src.get("trim_in_s", 0))
    thumb = settings.TMP_DIR / f"lf_uv_thumb_{uuid4().hex[:8]}.jpg"
    return await extract_thumbnail(video, thumb, timestamp=max(0.1, trim_in))


async def _render_kenburns(scene, assets_by_id, duration, aspect_ratio, out, tw, th):
    src = scene.get("source") or {}
    aid = src.get("asset_id")
    if not aid or aid not in assets_by_id:
        raise ValueError(f"Missing asset for scene {scene['id']}")
    img = Path(assets_by_id[aid]["file_path"])
    return await ffmpeg_service.generate_silent_kenburns_segment(img, duration, aspect_ratio, out)


async def _render_user_video(scene, assets_by_id, duration, aspect_ratio, out, tw, th):
    src = scene.get("source") or {}
    aid = src.get("asset_id")
    if not aid or aid not in assets_by_id:
        raise ValueError(f"Missing video asset for scene {scene['id']}")
    video = Path(assets_by_id[aid]["file_path"])
    trim_in = float(src.get("trim_in_s", 0))
    trim_out = trim_in + duration
    tmp = settings.TMP_DIR / f"lf_uv_{uuid4().hex[:8]}.mp4"
    await ffmpeg_service.extract_clip(video, trim_in, trim_out, tmp, vertical=(aspect_ratio == "9:16"))
    muted = await ffmpeg_service.mute_video(tmp)
    return await ffmpeg_service.normalize_segment(muted, duration, tw, th, out)


async def _render_stock(scene, duration, aspect_ratio, out, tw, th, pexels_api_key):
    src = scene.get("source") or {}
    query = src.get("query") or "cinematic broll"
    orientation = "portrait" if aspect_ratio == "9:16" else "landscape"
    if not pexels_api_key:
        raise RuntimeError("Pexels API key not configured for stock scenes")
    results = await search_videos(query, orientation=orientation, per_page=5, api_key=pexels_api_key)
    if not results:
        raise RuntimeError(f"No stock footage found for: {query}")
    pick = results[0]
    raw = settings.TMP_DIR / f"lf_stock_{uuid4().hex[:8]}.mp4"
    await download_clip(pick["download_url"], raw)
    from backend.services.ffmpeg_service import extract_thumbnail
    thumb = settings.TMP_DIR / f"lf_stock_thumb_{uuid4().hex[:8]}.jpg"
    start_frame = await extract_thumbnail(raw, thumb, timestamp=0.5)
    trimmed = await trim_and_normalize_clip(raw, duration, tw, th)
    video = await ffmpeg_service.normalize_segment(trimmed, duration, tw, th, out)
    return video, start_frame


async def _resolve_ltx_start_image(
    scene: dict,
    aspect_ratio: str,
    pexels_api_key: str,
    assets_by_id: dict,
) -> Path:
    """Download a contextual Pexels stock photo for LTX (not user portraits)."""
    src = scene.get("source") or {}
    cached_url = src.get("stock_image_download_url")
    if cached_url:
        out = settings.TMP_DIR / f"ltx_stock_{uuid4().hex[:8]}.jpg"
        return await download_photo(cached_url, out)

    if not pexels_api_key:
        raise RuntimeError("Pexels API key required for LTX scenes (stock photo start frame)")

    text = scene.get("transcript") or scene.get("narration_hint") or ""
    query = src.get("stock_image_query") or ltx_stock_image_query("", text)
    orientation = "portrait" if aspect_ratio == "9:16" else "landscape"
    photos = await search_photos(query, orientation=orientation, per_page=5, api_key=pexels_api_key)
    if not photos:
        raise RuntimeError(f"No stock photo found for LTX scene: {query}")

    out = settings.TMP_DIR / f"ltx_stock_{uuid4().hex[:8]}.jpg"
    await download_photo(photos[0]["download_url"], out)
    logger.info("DEBUG:: LTX start frame from Pexels | scene=%s query=%s", scene.get("id"), query)
    return out


async def _render_ltx(
    scene, assets_by_id, master_audio_path, duration, aspect_ratio, out, tw, th,
    runpod_base_url, pexels_api_key, on_progress,
):
    src = scene.get("source") or {}
    ltx_gen_s = min(duration, MAX_LTX_SCENE_S)
    length_seconds = min(max(int(math.ceil(ltx_gen_s)), 1), int(MAX_LTX_SCENE_S))
    audio_slice = await ffmpeg_service.slice_audio(
        master_audio_path, float(scene["start_s"]), float(scene["start_s"] + ltx_gen_s),
    )
    image_path = await _resolve_ltx_start_image(scene, aspect_ratio, pexels_api_key, assets_by_id)
    prompt = src.get("prompt") or scene.get("transcript") or scene.get("narration_hint") or ""
    if "lip sync" not in prompt.lower() and "lip-sync" not in prompt.lower():
        prompt = f"{prompt}. Ambient cinematic B-roll motion, slow camera movement, no lip sync."

    if not prompt.strip():
        features = await prompt_synth_service.analyze_audio(audio_slice, length_seconds)
        synth = await prompt_synth_service.synthesize_prompt(image_path, features, length_seconds)
        prompt = synth.get("prompt") or prompt

    ltx_out = settings.TMP_DIR / f"lf_ltx_{uuid4().hex[:8]}.mp4"
    await runpod_service.run_comfy_img2vid(
        base_url=runpod_base_url,
        prompt=prompt,
        start_image_path=image_path,
        length_seconds=length_seconds,
        output_path=ltx_out,
        audio_path=audio_slice,
        on_progress=on_progress,
    )
    muted = await ffmpeg_service.mute_video(ltx_out)
    ltx_part = settings.TMP_DIR / f"lf_ltx_part_{uuid4().hex[:8]}.mp4"
    ltx_norm = await ffmpeg_service.normalize_segment(muted, ltx_gen_s, tw, th, ltx_part)

    if duration > ltx_gen_s + 0.01:
        tail_dur = duration - ltx_gen_s
        tail_scene = {
            **scene,
            "start_s": float(scene["start_s"]) + ltx_gen_s,
            "end_s": float(scene["end_s"]),
            "type": "stock",
            "source": {"query": scene.get("visual_keywords_en") or src.get("stock_image_query") or "cinematic broll"},
        }
        tail_out = settings.TMP_DIR / f"lf_ltx_tail_{uuid4().hex[:8]}.mp4"
        tail_video, _ = await _render_stock(tail_scene, tail_dur, aspect_ratio, tail_out, tw, th, pexels_api_key)
        await ffmpeg_service.stitch_clips([ltx_norm, tail_video], out, transition="none")
        return out, image_path

    video = await ffmpeg_service.normalize_segment(ltx_norm, duration, tw, th, out)
    return video, image_path

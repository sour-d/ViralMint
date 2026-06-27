"""Niche 1 — Podcast Quote Shorts step-by-step API."""
import logging
from pathlib import Path
from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select

from backend.database import AsyncSessionLocal
from backend.models.user_settings import UserSettings
from backend.services.niche1_service import (
    list_base_images, generate_image_variation,
    generate_script, generate_audio_for_user,
    generate_lipsync, finalize_video,
    load_memory, OUTPUT_DIR, VARIANTS_DIR, BASE_DIR,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/niche1", tags=["niche1"])


async def _get_user_settings():
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(UserSettings).where(UserSettings.user_id == "local")
        )
        return result.scalar_one_or_none()


@router.get("/base-images")
async def api_list_base_images():
    """List available base images."""
    return {"images": await list_base_images()}


@router.get("/history")
async def api_history():
    """Show generation history."""
    return load_memory()


@router.get("/topics")
async def api_topics():
    """List available script topics."""
    from backend.services.niche1_service import TOPICS
    return {"topics": TOPICS}


@router.post("/generate-image")
async def api_generate_image(
    body: dict = Body(...),
):
    """Step 1: Generate an image variation from a base image."""
    base_filename = body.get("base_filename", "")
    description = body.get("description", "")
    if not base_filename:
        raise HTTPException(400, detail="base_filename is required")

    user_settings = await _get_user_settings()
    try:
        result = await generate_image_variation(
            base_filename=base_filename,
            description=description,
            user_settings=user_settings,
        )
        return {"ok": True, **result}
    except FileNotFoundError as e:
        raise HTTPException(404, detail=str(e))
    except Exception as e:
        logger.error(f"Image variation failed: {e}")
        raise HTTPException(500, detail=str(e))


@router.post("/generate-script")
async def api_generate_script(
    body: dict = Body(default_factory=dict),
):
    """Step 2: Generate an emotional quote script."""
    topic = body.get("topic", "")
    instructions = body.get("custom_instructions", "")
    user_settings = await _get_user_settings()

    try:
        result = await generate_script(
            topic=topic or None,
            user_settings=user_settings,
            custom_instructions=instructions,
        )
        return {"ok": True, **result}
    except Exception as e:
        logger.error(f"Script generation failed: {e}")
        raise HTTPException(500, detail=str(e))


@router.post("/generate-audio")
async def api_generate_audio(
    body: dict = Body(...),
):
    """Step 3: Generate TTS audio from script."""
    script = body.get("script", "")
    if not script:
        raise HTTPException(400, detail="script is required")

    user_settings = await _get_user_settings()
    try:
        result = await generate_audio_for_user(
            script=script,
            user_settings=user_settings,
        )
        return {"ok": True, **result}
    except Exception as e:
        logger.error(f"Audio generation failed: {e}")
        raise HTTPException(500, detail=str(e))


@router.post("/generate-video")
async def api_generate_video(
    body: dict = Body(...),
):
    """Step 4: Generate lip-sync video via RunPod ComfyUI."""
    image = body.get("image_filename", "")
    audio = body.get("audio_filename", "")
    if not image or not audio:
        raise HTTPException(400, detail="image_filename and audio_filename required")

    user_settings = await _get_user_settings()
    try:
        result = await generate_lipsync(
            image_filename=image,
            audio_filename=audio,
            user_settings=user_settings,
        )
        return {"ok": True, **result}
    except RuntimeError as e:
        raise HTTPException(503, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(404, detail=str(e))
    except Exception as e:
        logger.error(f"Lip-sync failed: {e}")
        raise HTTPException(500, detail=str(e))


@router.post("/finalize")
async def api_finalize(
    body: dict = Body(...),
):
    """Step 5: Add captions and background music."""
    video_filename = body.get("video_filename", "")
    script = body.get("script", "")
    if not video_filename:
        raise HTTPException(400, detail="video_filename is required")

    user_settings = await _get_user_settings()
    try:
        result = await finalize_video(
            video_filename=video_filename,
            script=script,
            user_settings=user_settings,
        )
        return {"ok": True, **result}
    except FileNotFoundError as e:
        raise HTTPException(404, detail=str(e))
    except Exception as e:
        logger.error(f"Finalize failed: {e}")
        raise HTTPException(500, detail=str(e))


@router.get("/media/{filename:path}")
async def serve_media(filename: str):
    """Serve generated files (images, audio, video)."""
    # Sanitize to prevent path traversal
    safe_name = Path(filename).name
    for directory in (OUTPUT_DIR, VARIANTS_DIR, BASE_DIR):
        path = directory / safe_name
        if path.exists():
            media_type = {
                ".mp4": "video/mp4",
                ".mp3": "audio/mpeg",
                ".wav": "audio/wav",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
            }.get(path.suffix.lower(), "application/octet-stream")
            return FileResponse(str(path), media_type=media_type)
    raise HTTPException(404, detail=f"File not found: {filename}")

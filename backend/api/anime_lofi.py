"""Anime Lo-fi — Script → Audio → Image-per-segment → Raw Video API."""
import logging
from pathlib import Path
from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse

from backend.database import AsyncSessionLocal
from backend.models.user_settings import UserSettings
from backend.services.anime_lofi_service import (
    generate_script, generate_audio, transcribe_audio, transcribe_and_segment,
    align_segment_durations, generate_segment_images, generate_segment_videos,
    render_raw_video, render_compilation_video,
    AUDIO_DIR, SEGMENTS_DIR, OUTPUT_DIR,
)
from sqlalchemy import select

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/anime-lofi", tags=["anime-lofi"])


async def _get_user_settings():
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(UserSettings).where(UserSettings.user_id == "local")
        )
        return result.scalar_one_or_none()


@router.post("/generate-script")
async def api_generate_script(body: dict = Body(default_factory=dict)):
    user_idea = body.get("user_idea", "")
    if not user_idea:
        raise HTTPException(400, detail="user_idea is required")
    user_settings = await _get_user_settings()
    try:
        result = await generate_script(
            user_idea=user_idea,
            user_settings=user_settings,
        )
        return {"ok": True, **result}
    except ValueError as e:
        raise HTTPException(422, detail=str(e))
    except Exception as e:
        logger.error(f"Script gen failed: {e}")
        raise HTTPException(500, detail=str(e))


@router.post("/generate-audio")
async def api_generate_audio(body: dict = Body(...)):
    script = body.get("script", "")
    if not script:
        raise HTTPException(400, detail="script is required")
    user_settings = await _get_user_settings()
    try:
        result = await generate_audio(script=script, user_settings=user_settings)
        return {"ok": True, **result}
    except Exception as e:
        logger.error(f"Audio gen failed: {e}")
        raise HTTPException(500, detail=str(e))


@router.post("/transcribe")
async def api_transcribe(body: dict = Body(...)):
    audio_filename = body.get("audio_filename", "")
    script = body.get("script", "")
    if not audio_filename or not script:
        raise HTTPException(400, detail="audio_filename and script required")
    try:
        result = await transcribe_and_segment(
            audio_filename=audio_filename, script_text=script,
        )
        return {"ok": True, **result}
    except FileNotFoundError as e:
        raise HTTPException(404, detail=str(e))
    except Exception as e:
        logger.error(f"Transcribe failed: {e}")
        raise HTTPException(500, detail=str(e))


@router.post("/transcribe-and-align")
async def api_transcribe_align(body: dict = Body(...)):
    """Transcribe audio and align word timestamps to LLM segments."""
    audio_filename = body.get("audio_filename", "")
    script_text = body.get("script", "")
    llm_segments = body.get("segments", [])
    if not audio_filename or not script_text or not llm_segments:
        raise HTTPException(400, detail="audio_filename, script, and segments required")
    try:
        result = await transcribe_audio(
            audio_filename=audio_filename, script_text=script_text,
        )
        enriched = align_segment_durations(
            segments=llm_segments, words=result["words"],
        )
        return {"ok": True, "segments": enriched, "transcript": result["transcript"]}
    except FileNotFoundError as e:
        raise HTTPException(404, detail=str(e))
    except Exception as e:
        logger.error(f"Transcribe+align failed: {e}")
        raise HTTPException(500, detail=str(e))


@router.post("/generate-images")
async def api_generate_images(body: dict = Body(...)):
    segments = body.get("segments", [])
    style_prompt = body.get("style_prompt", "")
    if not segments:
        raise HTTPException(400, detail="segments is required")
    user_settings = await _get_user_settings()
    try:
        result = await generate_segment_images(
            segments=segments,
            style_prompt=style_prompt,
            user_settings=user_settings,
        )
        return {"ok": True, "images": result}
    except Exception as e:
        logger.error(f"Image gen failed: {e}")
        raise HTTPException(500, detail=str(e))


@router.post("/generate-images-async")
async def api_generate_images_async(body: dict = Body(...)):
    """Start background image generation for segments, returns immediately with a job_id."""
    from backend.agents.job_helper import create_job
    from backend.core.task_runner import run_anime_lofi_generate_images, dispatch

    segments = body.get("segments", [])
    style_prompt = body.get("style_prompt", "")
    if not segments:
        raise HTTPException(400, detail="segments is required")

    payload = {"segments": segments, "style_prompt": style_prompt}
    job = await create_job("anime_lofi_generate_images", "local", payload)
    dispatch(run_anime_lofi_generate_images(job_id=job.id, user_id="local"))

    return {
        "ok": True,
        "job_id": job.id,
        "message": f"Generating {len(segments)} images in the background.",
    }


@router.get("/generate-images-status/{job_id}")
async def api_generate_images_status(job_id: str):
    """Poll job status and result for async image generation."""
    from backend.database import AsyncSessionLocal
    from backend.models.job import Job
    from sqlalchemy import select
    import json

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(404, detail="Job not found")

    resp = {
        "status": job.status,
        "progress_pct": job.progress_pct,
        "current_step": job.current_step,
        "error_message": job.error_message,
    }

    if job.status == "success" and job.output_json:
        try:
            data = json.loads(job.output_json)
            resp["images"] = data.get("images", [])
        except (json.JSONDecodeError, TypeError):
            pass

    return resp


@router.post("/generate-videos-async")
async def api_generate_videos_async(body: dict = Body(...)):
    """Start background LTX video generation for segments, returns immediately."""
    from backend.agents.job_helper import create_job
    from backend.core.task_runner import run_anime_lofi_generate_videos, dispatch

    images = body.get("images", [])
    segments = body.get("segments", [])
    if not images or not segments:
        raise HTTPException(400, detail="images and segments required")

    payload = {"images": images, "segments": segments}
    job = await create_job("anime_lofi_generate_videos", "local", payload)
    dispatch(run_anime_lofi_generate_videos(job_id=job.id, user_id="local"))

    return {
        "ok": True,
        "job_id": job.id,
        "message": f"Generating {len(images)} segment videos in the background.",
    }


@router.get("/generate-videos-status/{job_id}")
async def api_generate_videos_status(job_id: str):
    """Poll job status and result for async video generation."""
    from backend.database import AsyncSessionLocal
    from backend.models.job import Job
    from sqlalchemy import select
    import json

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(404, detail="Job not found")

    resp = {
        "status": job.status,
        "progress_pct": job.progress_pct,
        "current_step": job.current_step,
        "error_message": job.error_message,
    }

    if job.status == "success" and job.output_json:
        try:
            data = json.loads(job.output_json)
            resp["videos"] = data.get("videos", [])
        except (json.JSONDecodeError, TypeError):
            pass

    return resp


@router.post("/render-video")
async def api_render_video(body: dict = Body(...)):
    segments = body.get("segments", [])
    images = body.get("images", [])
    audio_filename = body.get("audio_filename", "")
    if not segments or not images or not audio_filename:
        raise HTTPException(400, detail="segments, images, and audio_filename required")
    try:
        result = await render_raw_video(
            segments=segments,
            image_filenames=images,
            audio_filename=audio_filename,
        )
        return {"ok": True, **result}
    except FileNotFoundError as e:
        raise HTTPException(404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(500, detail=str(e))
    except Exception as e:
        logger.error(f"Render failed: {e}")
        raise HTTPException(500, detail=str(e))


@router.post("/retry-video")
async def api_retry_video(body: dict = Body(...)):
    """Regenerate a single segment video (runs as async job for timeout safety)."""
    from backend.agents.job_helper import create_job
    from backend.core.task_runner import run_anime_lofi_generate_videos, dispatch

    image = body.get("image")
    segment = body.get("segment")
    if not image or not segment:
        raise HTTPException(400, detail="image and segment required")

    payload = {"images": [image], "segments": [segment]}
    job = await create_job("anime_lofi_generate_videos", "local", payload)
    dispatch(run_anime_lofi_generate_videos(job_id=job.id, user_id="local"))

    return {"ok": True, "job_id": job.id}


@router.post("/retry-image")
async def api_retry_image(body: dict = Body(...)):
    """Regenerate a single segment image (runs as async job)."""
    from backend.agents.job_helper import create_job
    from backend.core.task_runner import run_anime_lofi_generate_images, dispatch

    segment = body.get("segment")
    if not segment:
        raise HTTPException(400, detail="segment required")

    payload = {"segments": [segment], "style_prompt": ""}
    job = await create_job("anime_lofi_generate_images", "local", payload)
    dispatch(run_anime_lofi_generate_images(job_id=job.id, user_id="local"))

    return {"ok": True, "job_id": job.id}


@router.post("/render-video-compilation")
async def api_render_video_compilation(body: dict = Body(...)):
    """Concatenate per-segment video clips + overlay master audio."""
    videos = body.get("videos", [])
    audio_filename = body.get("audio_filename", "")
    if not videos or not audio_filename:
        raise HTTPException(400, detail="videos and audio_filename required")
    try:
        result = await render_compilation_video(
            videos=videos, audio_filename=audio_filename,
        )
        return {"ok": True, **result}
    except FileNotFoundError as e:
        raise HTTPException(404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(500, detail=str(e))
    except Exception as e:
        logger.error(f"Compilation failed: {e}")
        raise HTTPException(500, detail=str(e))


@router.get("/media/{filename:path}")
async def serve_media(filename: str):
    safe_name = Path(filename).name
    from backend.services.anime_lofi_service import VIDEOS_DIR
    for directory in (OUTPUT_DIR, SEGMENTS_DIR, VIDEOS_DIR, AUDIO_DIR):
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

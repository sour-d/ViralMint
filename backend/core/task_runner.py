# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""
Lightweight in-process task runner.
All tasks run as asyncio background tasks in the same event loop.
"""
import asyncio
import json
import logging

logger = logging.getLogger(__name__)

_task_semaphore = asyncio.Semaphore(3)


async def _run_with_limit(coro):
    try:
        async with _task_semaphore:
            await coro
    except Exception as e:
        logger.error("Unhandled exception in background task: %s", e, exc_info=True)


def dispatch(coro):
    logger.debug("Dispatching async task: %s", coro.__qualname__ if hasattr(coro, '__qualname__') else type(coro).__name__)
    asyncio.create_task(_run_with_limit(coro))


async def run_anime_lofi_generate_videos(
    job_id: str,
    user_id: str = "local",
):
    import json as _json
    from backend.agents.job_helper import update_job_status
    from backend.core.ws_manager import ws_manager
    from backend.services.anime_lofi_service import generate_segment_videos
    from backend.models.user_settings import UserSettings
    from backend.database import AsyncSessionLocal
    from backend.models.job import Job
    from sqlalchemy import select

    try:
        async with AsyncSessionLocal() as db:
            jresult = await db.execute(select(Job).where(Job.id == job_id))
            job_row = jresult.scalar_one_or_none()
            if not job_row or not job_row.input_json:
                raise RuntimeError("Job has no input data")
            payload = _json.loads(job_row.input_json)

        images = payload.get("images", [])
        segments = payload.get("segments", [])

        async with AsyncSessionLocal() as db:
            uresult = await db.execute(
                select(UserSettings).where(UserSettings.user_id == user_id)
            )
            user_settings = uresult.scalar_one_or_none()

        await ws_manager.send({
            "type": "job_started",
            "job_id": job_id,
            "job_type": "anime_lofi_generate_videos",
            "message": f"Generating {len(images)} segment videos…",
        }, user_id)

        total = len(images)

        async def on_progress(current, _total, seg):
            pct = int(current / total * 100)
            step = f"Video {current} / {total}"
            await update_job_status(job_id, "running", progress_pct=pct, current_step=step)
            await ws_manager.send_progress(job_id, pct, step, user_id)

        videos = await generate_segment_videos(
            images=images,
            segments=segments,
            user_settings=user_settings,
            on_progress=on_progress,
        )

        result = {"ok": True, "videos": videos}
        await update_job_status(job_id, "success", progress_pct=100, output_data=result)
        await ws_manager.send({
            "type": "job_complete",
            "job_id": job_id,
            "result": result,
        }, user_id)

    except Exception as e:
        err = str(e)
        await update_job_status(job_id, "failed", error_message=err)
        await ws_manager.send({"type": "job_failed", "job_id": job_id, "error": err}, user_id)


async def run_anime_lofi_generate_images(
    job_id: str,
    user_id: str = "local",
):
    import json as _json
    from backend.agents.job_helper import update_job_status
    from backend.core.ws_manager import ws_manager
    from backend.services.anime_lofi_service import generate_segment_images
    from backend.models.user_settings import UserSettings
    from backend.database import AsyncSessionLocal
    from backend.models.job import Job
    from sqlalchemy import select

    try:
        async with AsyncSessionLocal() as db:
            jresult = await db.execute(select(Job).where(Job.id == job_id))
            job_row = jresult.scalar_one_or_none()
            if not job_row or not job_row.input_json:
                raise RuntimeError("Job has no input data")
            payload = _json.loads(job_row.input_json)

        segments = payload.get("segments", [])
        style_prompt = payload.get("style_prompt", "")

        async with AsyncSessionLocal() as db:
            uresult = await db.execute(
                select(UserSettings).where(UserSettings.user_id == user_id)
            )
            user_settings = uresult.scalar_one_or_none()

        await ws_manager.send({
            "type": "job_started",
            "job_id": job_id,
            "job_type": "anime_lofi_generate_images",
            "message": f"Generating {len(segments)} images…",
        }, user_id)

        total = len(segments)

        async def on_progress(current, _total, seg):
            pct = int(current / total * 100)
            step = f"Image {current} / {total}"
            await update_job_status(job_id, "running", progress_pct=pct, current_step=step)
            await ws_manager.send_progress(job_id, pct, step, user_id)

        images = await generate_segment_images(
            segments=segments,
            style_prompt=style_prompt,
            user_settings=user_settings,
            on_progress=on_progress,
        )

        result = {"ok": True, "images": images}
        await update_job_status(job_id, "success", progress_pct=100, output_data=result)
        await ws_manager.send({
            "type": "job_complete",
            "job_id": job_id,
            "result": result,
        }, user_id)

    except Exception as e:
        err = str(e)
        await update_job_status(job_id, "failed", error_message=err)
        await ws_manager.send({"type": "job_failed", "job_id": job_id, "error": err}, user_id)


async def run_install_runpod_models(
    job_id: str,
    user_id: str = "local",
):
    """Queue custom nodes + model downloads on the pod via ComfyUI-Manager."""
    import json as _json
    from backend.agents.job_helper import update_job_status
    from backend.core.ws_manager import ws_manager
    from backend.core.api_keys import get_runpod_api_key, get_runpod_pod_id
    from backend.services import runpod_service
    from backend.services.runpod_setup import setup_pod
    from backend.models.user_settings import UserSettings
    from backend.models.job import Job
    from backend.database import AsyncSessionLocal
    from sqlalchemy import select

    try:
        workflow_type = None
        async with AsyncSessionLocal() as db:
            jresult = await db.execute(select(Job).where(Job.id == job_id))
            job_row = jresult.scalar_one_or_none()
            if job_row and job_row.input_json:
                payload = _json.loads(job_row.input_json)
                workflow_type = payload.get("workflow_type")

        if workflow_type not in ("ltx", "z-turbo", "ltx-img2vid", "tts", None):
            workflow_type = None

        await ws_manager.send({
            "type": "job_started",
            "job_id": job_id,
            "job_type": "runpod_install_models",
            "message": f"Setting up ComfyUI {'(' + workflow_type + ')' if workflow_type else ''}…",
        }, user_id)

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(UserSettings).where(UserSettings.user_id == user_id)
            )
            user_settings = result.scalar_one_or_none()

        api_key = get_runpod_api_key(user_settings)
        stored_pod_id = get_runpod_pod_id(user_settings)
        status = await runpod_service.get_pod_status(api_key, stored_pod_id)
        if not status.get("comfy_ready"):
            raise RuntimeError("ComfyUI is not ready on the pod")

        base_url = runpod_service.get_comfy_base_url(status["pod_id"])

        async def on_progress(pct, step):
            await update_job_status(job_id, "running", progress_pct=pct, current_step=step)
            await ws_manager.send_progress(job_id, pct, step, user_id)

        result = await setup_pod(base_url, on_progress=on_progress, workflow=workflow_type)
        if result.get("skipped"):
            await update_job_status(job_id, "success", progress_pct=100, current_step=result.get("message", "Already set up"), output_data=result)
            await ws_manager.send({"type": "job_complete", "job_id": job_id, "result": result}, user_id)
            return
        if result.get("ok"):
            await update_job_status(job_id, "success", progress_pct=100, current_step=result.get("message", "Done"), output_data=result)
            await ws_manager.send({"type": "job_complete", "job_id": job_id, "result": result}, user_id)
        else:
            err = result.get("message") or "Pod setup failed"
            await update_job_status(job_id, "failed", error_message=err, output_data=result)
            await ws_manager.send({"type": "job_failed", "job_id": job_id, "error": err}, user_id)
    except Exception as e:
        from backend.agents.job_helper import update_job_status as _update
        await _update(job_id, "failed", error_message=str(e))
        await ws_manager.send({"type": "job_failed", "job_id": job_id, "error": str(e)}, user_id)

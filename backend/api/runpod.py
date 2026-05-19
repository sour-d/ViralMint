# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""REST /api/runpod — RunPod Pod status and deploy."""
import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from backend.database import AsyncSessionLocal
from backend.models.user_settings import UserSettings
from backend.core.api_keys import get_runpod_api_key, get_runpod_pod_id
from backend.services import runpod_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/runpod", tags=["runpod"])


async def _get_user_settings() -> UserSettings | None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(UserSettings).where(UserSettings.user_id == "local")
        )
        return result.scalar_one_or_none()


async def _save_pod_id(pod_id: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(UserSettings).where(UserSettings.user_id == "local")
        )
        s = result.scalar_one_or_none()
        if not s:
            s = UserSettings(user_id="local")
            db.add(s)
        s.runpod_pod_id = pod_id
        await db.commit()


@router.get("/status")
async def runpod_status():
    """Return RunPod pod + ComfyUI readiness for the AI Video page."""
    user_settings = await _get_user_settings()
    api_key = get_runpod_api_key(user_settings)
    stored_pod_id = get_runpod_pod_id(user_settings)
    status = await runpod_service.get_pod_status(api_key, stored_pod_id)

    # Sync stored pod id if we discovered one by name
    if status.get("pod_id") and status["pod_id"] != stored_pod_id:
        await _save_pod_id(status["pod_id"])

    return status


@router.post("/deploy")
async def runpod_deploy():
    """Create or reuse the managed ComfyUI GPU pod."""
    user_settings = await _get_user_settings()
    api_key = get_runpod_api_key(user_settings)
    if not api_key:
        raise HTTPException(
            503,
            detail="RunPod API key not configured. Add it in Settings or RUNPOD_API_KEY in .env",
        )

    stored_pod_id = get_runpod_pod_id(user_settings)
    status = await runpod_service.get_pod_status(api_key, stored_pod_id)

    if status["pod_state"] == "running":
        if status.get("pod_id"):
            await _save_pod_id(status["pod_id"])
        return {
            "pod_id": status["pod_id"],
            "pod_state": "running",
            "message": status["message"],
            "already_running": True,
        }

    if status["pod_state"] == "starting" and status.get("pod_id"):
        return {
            "pod_id": status["pod_id"],
            "pod_state": "starting",
            "message": status["message"],
            "already_running": True,
        }

    try:
        existing = await runpod_service.resolve_pod(api_key, stored_pod_id)

        if existing and existing.get("desiredStatus") == "RUNNING":
            pod_id = existing["id"]
            await _save_pod_id(pod_id)
            return {
                "pod_id": pod_id,
                "pod_state": "running",
                "message": "Found existing pod.",
                "already_running": True,
            }

        if existing and existing.get("desiredStatus") == "EXITED":
            pod_id = existing["id"]
            await runpod_service.start_pod(api_key, pod_id)
            await _save_pod_id(pod_id)
            return {
                "pod_id": pod_id,
                "pod_state": "starting",
                "message": "Resuming stopped pod. ComfyUI may take a few minutes to start.",
                "already_running": False,
            }

        if existing and existing.get("desiredStatus") not in ("TERMINATED",):
            pod_id = existing["id"]
            await _save_pod_id(pod_id)
            return {
                "pod_id": pod_id,
                "pod_state": "starting",
                "message": "Existing pod is starting.",
                "already_running": True,
            }

        pod = await runpod_service.create_pod(api_key)
        pod_id = pod.get("id")
        if not pod_id:
            raise HTTPException(502, detail="RunPod did not return a pod ID")
        await _save_pod_id(pod_id)
        logger.info("RunPod pod created: %s", pod_id)
        return {
            "pod_id": pod_id,
            "pod_state": "starting",
            "message": "Pod deployed. ComfyUI may take up to 30 minutes on first boot.",
            "already_running": False,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("RunPod deploy failed: %s", e, exc_info=True)
        raise HTTPException(502, detail=f"RunPod deploy failed: {e}") from e

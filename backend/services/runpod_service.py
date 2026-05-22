# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""RunPod Pod management and ComfyUI workflow execution."""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import httpx
from sqlalchemy import select

from backend.config import settings as app_settings
from backend.database import AsyncSessionLocal
from backend.models.job import Job
from backend.runpod import pod_config
from backend.services import runpod_manager as mgr
from backend.services.runpod_setup import assess_pod

logger = logging.getLogger(__name__)

RUNPOD_REST_BASE = "https://rest.runpod.io/v1"
WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / "workflows"
SETUP_JOB_TYPE = "runpod_install_models"


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def get_comfy_base_url(pod_id: str) -> str:
    return f"https://{pod_id}-{pod_config.COMFY_PORT}.proxy.runpod.net"


async def list_pods(api_key: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{RUNPOD_REST_BASE}/pods", headers=_auth_headers(api_key))
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        return data.get("pods", data) if isinstance(data, dict) else []


async def get_pod(api_key: str, pod_id: str) -> Optional[dict]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{RUNPOD_REST_BASE}/pods/{pod_id}",
            headers=_auth_headers(api_key),
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()


async def start_pod(api_key: str, pod_id: str) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{RUNPOD_REST_BASE}/pods/{pod_id}/start",
            headers=_auth_headers(api_key),
        )
        resp.raise_for_status()
        return resp.json() if resp.content else {"id": pod_id}


async def create_pod(api_key: str) -> dict:
    body = {
        "name": pod_config.POD_NAME,
        "imageName": pod_config.IMAGE_NAME,
        "gpuTypeIds": pod_config.GPU_TYPE_IDS,
        "gpuCount": pod_config.GPU_COUNT,
        "containerDiskInGb": pod_config.CONTAINER_DISK_GB,
        "volumeInGb": pod_config.VOLUME_GB,
        "volumeMountPath": pod_config.VOLUME_MOUNT_PATH,
        "ports": pod_config.PORTS,
        "cloudType": pod_config.CLOUD_TYPE,
        "supportPublicIp": pod_config.SUPPORT_PUBLIC_IP,
        "interruptible": False,
    }
    if getattr(pod_config, "TEMPLATE_ID", None):
        body["templateId"] = pod_config.TEMPLATE_ID
    volume_id = (app_settings.RUNPOD_NETWORK_VOLUME_ID or "").strip()
    if volume_id:
        body["networkVolumeId"] = volume_id
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{RUNPOD_REST_BASE}/pods",
            headers=_auth_headers(api_key),
            json=body,
        )
        if not resp.is_success:
            detail = resp.text[:500]
            logger.error("RunPod create pod failed: %s %s", resp.status_code, detail)
            resp.raise_for_status()
        return resp.json()


def find_pod_by_name(pods: list[dict], name: str = pod_config.POD_NAME) -> Optional[dict]:
    matches = [p for p in pods if p.get("name") == name]
    return matches[-1] if matches else None


async def resolve_pod(api_key: str, stored_pod_id: str = "") -> Optional[dict]:
    if stored_pod_id:
        pod = await get_pod(api_key, stored_pod_id)
        if pod:
            return pod
    return find_pod_by_name(await list_pods(api_key))


async def check_comfy_health(base_url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            return (await client.get(f"{base_url.rstrip('/')}/system_stats")).is_success
    except Exception as e:
        logger.debug("ComfyUI health check failed for %s: %s", base_url, e)
        return False


async def get_active_setup_job() -> Optional[dict]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Job)
            .where(Job.user_id == "local")
            .where(Job.job_type == SETUP_JOB_TYPE)
            .where(Job.status.in_(("running", "pending")))
            .order_by(Job.created_at.desc())
            .limit(1)
        )
        job = result.scalar_one_or_none()
    if not job:
        return None
    return {
        "job_id": job.id,
        "status": job.status,
        "progress_pct": float(job.progress_pct or 0),
        "current_step": job.current_step,
    }


def _activity_line(
    *,
    message: str,
    pod_state: str,
    setup_job: Optional[dict],
    manager_queue: Optional[dict],
) -> str:
    if setup_job and setup_job.get("current_step"):
        step = str(setup_job["current_step"]).strip()
        pct = setup_job.get("progress_pct")
        if pct and float(pct) > 0:
            return f"{step} ({int(float(pct))}%)"
        return step
    queue_line = mgr.queue_activity_line(manager_queue)
    if queue_line:
        return queue_line
    if pod_state == "starting":
        return "Pod is starting — waiting for ComfyUI on port 8188…"
    return message


def _status_message(
    pod_state: str,
    comfy_ready: bool,
    *,
    nodes_ready: bool,
    models_ready: bool,
    nodes_status: dict,
    models_status: dict,
) -> str:
    if pod_state == "none":
        return "No pod deployed. Click Deploy Pod to start ComfyUI."
    if pod_state == "stopped":
        return "Pod is stopped. Click Deploy Pod to start again."
    if pod_state == "starting":
        return "Pod is starting. First boot may take up to 30 minutes."
    if not comfy_ready:
        return "Pod is running. Waiting for ComfyUI on port 8188…"
    if nodes_ready and models_ready:
        return "Ready to generate videos."
    if not nodes_ready:
        missing = nodes_status.get("missing_class_types", [])
        msg = "ComfyUI is up. Click Setup pod to install nodes and models."
        if missing:
            msg += f" Missing nodes: {', '.join(missing[:3])}"
            if len(missing) > 3:
                msg += "…"
        return msg
    missing = [m["filename"] for m in models_status.get("missing", [])]
    msg = "Nodes ready. Click Setup pod to download models."
    if missing:
        msg += f" Missing: {', '.join(missing[:3])}"
        if len(missing) > 3:
            msg += "…"
    return msg


def _empty_status() -> dict:
    return {
        "configured": False,
        "pod_id": None,
        "pod_name": pod_config.POD_NAME,
        "pod_state": "none",
        "desired_status": None,
        "comfy_ready": False,
        "comfy_url": None,
        "message": "Add your RunPod API key in Settings or .env",
        "activity_line": "Add your RunPod API key in Settings or .env",
        "can_deploy": False,
        "can_generate": False,
        "can_setup": False,
        "custom_nodes_ready": False,
        "custom_nodes_status": {"ready": False, "missing_class_types": [], "packs_needed": []},
        "models_ready": False,
        "models_status": {"ready": False, "missing": [], "present": []},
        "setup_job": None,
        "manager_queue": None,
        "setup_in_progress": False,
        "network_volume_attached": False,
        "cost_per_hr": None,
    }


async def get_pod_status(api_key: str, stored_pod_id: str = "") -> dict:
    if not api_key:
        return _empty_status()

    pod = await resolve_pod(api_key, stored_pod_id)
    pod_id = pod.get("id") if pod else stored_pod_id or None
    pod_state = _pod_state_from_pod(pod)
    comfy_url = get_comfy_base_url(pod_id) if pod_id else None
    comfy_ready = bool(comfy_url and pod_state == "running" and await check_comfy_health(comfy_url))

    nodes_ready = models_ready = False
    nodes_status: dict = {"ready": False, "missing_class_types": [], "packs_needed": []}
    models_status: dict = {"ready": False, "missing": [], "present": []}

    if comfy_ready and comfy_url:
        try:
            assessment = await assess_pod(comfy_url)
            nodes_ready = assessment["custom_nodes_ready"]
            models_ready = assessment["models_ready"]
            nodes_status = assessment["custom_nodes_status"]
            models_status = assessment["models_status"]
        except Exception as e:
            logger.debug("Pod assessment failed: %s", e)

    message = _status_message(
        pod_state, comfy_ready,
        nodes_ready=nodes_ready, models_ready=models_ready,
        nodes_status=nodes_status, models_status=models_status,
    )
    setup_job = await get_active_setup_job()
    manager_queue = await mgr.queue_status(comfy_url) if comfy_ready and comfy_url else None
    setup_in_progress = bool(
        setup_job or pod_state == "starting"
        or (comfy_ready and (not nodes_ready or not models_ready))
    )

    return {
        "configured": True,
        "pod_id": pod_id,
        "pod_name": pod.get("name", pod_config.POD_NAME) if pod else pod_config.POD_NAME,
        "pod_state": pod_state,
        "desired_status": pod.get("desiredStatus") if pod else None,
        "comfy_ready": comfy_ready,
        "custom_nodes_ready": nodes_ready,
        "custom_nodes_status": nodes_status,
        "models_ready": models_ready,
        "models_status": models_status,
        "activity_line": _activity_line(
            message=message, pod_state=pod_state,
            setup_job=setup_job, manager_queue=manager_queue,
        ),
        "setup_job": setup_job,
        "manager_queue": manager_queue,
        "setup_in_progress": setup_in_progress,
        "network_volume_attached": bool((app_settings.RUNPOD_NETWORK_VOLUME_ID or "").strip()),
        "comfy_url": comfy_url,
        "message": message,
        "can_deploy": pod_state in ("none", "stopped"),
        "can_generate": comfy_ready and nodes_ready and models_ready,
        "can_setup": comfy_ready and (not nodes_ready or not models_ready),
        "can_install_models": comfy_ready and (not nodes_ready or not models_ready),
        "cost_per_hr": pod.get("costPerHr") if pod else None,
    }


def _pod_state_from_pod(pod: Optional[dict]) -> str:
    if not pod:
        return "none"
    desired = (pod.get("desiredStatus") or "").upper()
    if desired == "RUNNING":
        return "running"
    if desired in ("EXITED", "TERMINATED"):
        return "stopped"
    return "starting"


def load_workflow_template() -> dict:
    mapping = load_workflow_mapping()
    path = WORKFLOWS_DIR / mapping.get("workflow_file", "video_ltx2_3_ia2v-api.json")
    if not path.exists():
        raise FileNotFoundError(f"Workflow file not found: {path}")
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not str(k).startswith("_")}


def load_workflow_mapping() -> dict:
    with open(WORKFLOWS_DIR / "runpod_mapping.json", encoding="utf-8") as f:
        return json.load(f)


def build_workflow(
    prompt: str,
    length_seconds: int,
    start_image_filename: str,
    audio_filename: Optional[str] = None,
) -> dict:
    mapping = load_workflow_mapping()
    if not mapping.get("prompt_node_id") or mapping.get("prompt_node_id") == "REPLACE_ME":
        raise ValueError("Edit backend/workflows/runpod_mapping.json with your ComfyUI node IDs.")

    if mapping.get("audio_required") and not audio_filename:
        raise ValueError("Reference audio is required for this workflow.")

    workflow = copy.deepcopy(load_workflow_template())
    prompt_id = str(mapping["prompt_node_id"])
    prompt_key = mapping.get("prompt_input_key", "value")
    if prompt_id in workflow:
        workflow[prompt_id]["inputs"][prompt_key] = prompt

    length_id = str(mapping["length_node_id"])
    length_key = mapping.get("length_input_key", "value")
    if length_id in workflow:
        workflow[length_id]["inputs"][length_key] = float(length_seconds)

    image_node_id = mapping.get("start_image_node_id")
    if image_node_id and image_node_id in workflow:
        workflow[image_node_id]["inputs"][mapping.get("start_image_input_key", "image")] = start_image_filename

    audio_node_id = mapping.get("audio_node_id")
    if audio_filename and audio_node_id and audio_node_id in workflow:
        workflow[audio_node_id]["inputs"][mapping.get("audio_input_key", "audio")] = audio_filename

    return workflow


def resolve_media_path(media_url: str) -> Path:
    if media_url.startswith("/api/media/"):
        path = app_settings.TMP_DIR / Path(media_url).name
    else:
        path = Path(media_url)
    if not path.exists():
        raise FileNotFoundError(f"Media file not found: {media_url}")
    return path


async def upload_to_comfy(base_url: str, file_path: Path) -> str:
    async with httpx.AsyncClient(timeout=300) as client:
        with open(file_path, "rb") as f:
            resp = await client.post(
                f"{base_url.rstrip('/')}/upload/image",
                files={"image": (file_path.name, f, "application/octet-stream")},
                data={"overwrite": "true"},
            )
        resp.raise_for_status()
        return resp.json().get("name") or file_path.name


async def submit_comfy_workflow(base_url: str, workflow: dict) -> str:
    body = {"prompt": workflow, "client_id": str(uuid.uuid4())}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(f"{base_url.rstrip('/')}/prompt", json=body)
        if not resp.is_success:
            raise RuntimeError(f"ComfyUI /prompt failed: {resp.status_code} {resp.text[:300]}")
        prompt_id = resp.json().get("prompt_id")
        if not prompt_id:
            raise RuntimeError("ComfyUI did not return prompt_id")
        return prompt_id


async def wait_for_comfy_output(
    base_url: str,
    prompt_id: str,
    poll_interval: float = 2.0,
    max_wait: float = 1800.0,
) -> dict[str, Any]:
    elapsed = 0.0
    async with httpx.AsyncClient(timeout=30) as client:
        while elapsed < max_wait:
            resp = await client.get(f"{base_url.rstrip('/')}/history/{prompt_id}")
            if resp.is_success and prompt_id in resp.json():
                entry = resp.json()[prompt_id]
                for node_out in entry.get("outputs", {}).values():
                    for kind in ("videos", "gifs", "images"):
                        items = node_out.get(kind, [])
                        if items:
                            return {"outputs": entry["outputs"], "item": items[0], "kind": kind}
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    raise RuntimeError(f"ComfyUI workflow error: {status.get('messages', [])}")
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
    raise TimeoutError(f"ComfyUI job timed out after {max_wait}s")


async def download_comfy_output(base_url: str, item: dict, dest: Path) -> Path:
    params = {
        "filename": item["filename"],
        "subfolder": item.get("subfolder", ""),
        "type": item.get("type", "output"),
    }
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.get(f"{base_url.rstrip('/')}/view", params=params)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
    return dest


async def run_comfy_img2vid(
    base_url: str,
    prompt: str,
    start_image_path: Path,
    length_seconds: int,
    output_path: Path,
    audio_path: Optional[Path] = None,
    on_progress: Optional[Callable[[float, str], Awaitable[None]]] = None,
) -> Path:
    if on_progress:
        await on_progress(10, "Uploading start image…")
    image_name = await upload_to_comfy(base_url, start_image_path)
    if not audio_path or not audio_path.exists():
        raise ValueError("Reference audio file is missing")
    if on_progress:
        await on_progress(15, "Uploading reference audio…")
    audio_name = await upload_to_comfy(base_url, audio_path)
    workflow = build_workflow(prompt, length_seconds, image_name, audio_name)

    if on_progress:
        await on_progress(20, "Submitting workflow…")
    prompt_id = await submit_comfy_workflow(base_url, workflow)

    if on_progress:
        await on_progress(30, "Generating video on RunPod…")
    result = await wait_for_comfy_output(base_url, prompt_id)

    if on_progress:
        await on_progress(90, "Downloading output…")
    return await download_comfy_output(base_url, result["item"], output_path)

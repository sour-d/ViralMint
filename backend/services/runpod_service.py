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

from backend.config import settings as app_settings
from backend.runpod import pod_config
from backend.services.runpod_models import check_models_present, fetch_comfy_model_lists

logger = logging.getLogger(__name__)

RUNPOD_REST_BASE = "https://rest.runpod.io/v1"
WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / "workflows"


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
    if not matches:
        return None
    return matches[-1]


async def resolve_pod(api_key: str, stored_pod_id: str = "") -> Optional[dict]:
    if stored_pod_id:
        pod = await get_pod(api_key, stored_pod_id)
        if pod:
            return pod
    pods = await list_pods(api_key)
    return find_pod_by_name(pods)


async def check_comfy_health(base_url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{base_url.rstrip('/')}/system_stats")
            return resp.is_success
    except Exception as e:
        logger.debug("ComfyUI health check failed for %s: %s", base_url, e)
        return False


def _pod_state_from_pod(pod: Optional[dict]) -> str:
    if not pod:
        return "none"
    desired = (pod.get("desiredStatus") or "").upper()
    if desired == "RUNNING":
        return "running"
    if desired in ("EXITED", "TERMINATED"):
        return "stopped"
    return "starting"


async def get_pod_status(api_key: str, stored_pod_id: str = "") -> dict:
    configured = bool(api_key)
    if not configured:
        return {
            "configured": False,
            "pod_id": None,
            "pod_name": pod_config.POD_NAME,
            "pod_state": "none",
            "desired_status": None,
            "comfy_ready": False,
            "comfy_url": None,
            "message": "Add your RunPod API key in Settings or .env",
            "can_deploy": False,
            "can_generate": False,
            "can_install_models": False,
            "models_ready": False,
            "models_status": {"ready": False, "missing": [], "present": []},
            "network_volume_attached": False,
            "cost_per_hr": None,
        }

    pod = await resolve_pod(api_key, stored_pod_id)
    pod_id = pod.get("id") if pod else stored_pod_id or None
    pod_state = _pod_state_from_pod(pod)
    desired = pod.get("desiredStatus") if pod else None
    comfy_url = get_comfy_base_url(pod_id) if pod_id else None
    comfy_ready = False
    models_ready = False
    models_status: dict = {"ready": False, "missing": [], "present": []}
    message = ""

    if pod_state == "none":
        message = "No pod deployed. Click Deploy Pod to start ComfyUI."
    elif pod_state == "stopped":
        message = "Pod is stopped. Click Deploy Pod to start again."
    elif pod_state == "starting":
        message = "Pod is starting. First boot may take up to 30 minutes."
    elif pod_state == "running":
        if comfy_url and await check_comfy_health(comfy_url):
            comfy_ready = True
            try:
                lists = await fetch_comfy_model_lists(comfy_url)
                models_status = check_models_present(lists)
                models_ready = models_status["ready"]
            except Exception as e:
                logger.debug("Model check failed: %s", e)
            if models_ready:
                message = "ComfyUI and models are ready. You can generate videos."
            else:
                missing = [m["filename"] for m in models_status.get("missing", [])]
                message = (
                    "ComfyUI is up. Click Install models to download via ComfyUI-Manager "
                    "(or attach a network volume that already has the LTX files)."
                )
                if missing:
                    message += f" Missing: {', '.join(missing[:3])}"
                    if len(missing) > 3:
                        message += "…"
        else:
            message = "Pod is running. Waiting for ComfyUI to respond on port 8188…"

    volume_attached = bool((app_settings.RUNPOD_NETWORK_VOLUME_ID or "").strip())

    return {
        "configured": True,
        "pod_id": pod_id,
        "pod_name": pod.get("name", pod_config.POD_NAME) if pod else pod_config.POD_NAME,
        "pod_state": pod_state,
        "desired_status": desired,
        "comfy_ready": comfy_ready,
        "models_ready": models_ready,
        "models_status": models_status,
        "network_volume_attached": volume_attached,
        "comfy_url": comfy_url,
        "message": message,
        "can_deploy": pod_state in ("none", "stopped"),
        "can_generate": comfy_ready and models_ready,
        "can_install_models": comfy_ready and not models_ready,
        "cost_per_hr": pod.get("costPerHr") if pod else None,
    }


def load_workflow_template() -> dict:
    mapping = load_workflow_mapping()
    filename = mapping.get("workflow_file", "video_ltx2_3_ia2v-api.json")
    path = WORKFLOWS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Workflow file not found: {path}")
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not str(k).startswith("_")}


def load_workflow_mapping() -> dict:
    path = WORKFLOWS_DIR / "runpod_mapping.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def mapping_is_configured(mapping: dict) -> bool:
    for key in ("prompt_node_id", "length_node_id"):
        val = mapping.get(key, "")
        if not val or val == "REPLACE_ME":
            return False
    return True


def build_workflow(
    prompt: str,
    length_seconds: int,
    start_image_filename: str,
    audio_filename: Optional[str] = None,
) -> dict:
    mapping = load_workflow_mapping()
    if not mapping_is_configured(mapping):
        raise ValueError(
            "RunPod workflow mapping is not configured. "
            "Edit backend/workflows/runpod_mapping.json with your ComfyUI node IDs."
        )

    if mapping.get("audio_required") and not audio_filename:
        raise ValueError(
            "This workflow requires reference audio. Upload an audio file in the AI Video page."
        )

    workflow = copy.deepcopy(load_workflow_template())
    prompt_id = str(mapping["prompt_node_id"])
    prompt_key = mapping.get("prompt_input_key", "text")
    if prompt_id in workflow:
        workflow[prompt_id]["inputs"][prompt_key] = prompt

    length_id = str(mapping["length_node_id"])
    length_key = mapping.get("length_input_key", "length")
    if length_id in workflow:
        workflow[length_id]["inputs"][length_key] = float(length_seconds)

    image_node_id = mapping.get("start_image_node_id")
    image_key = mapping.get("start_image_input_key", "image")
    if image_node_id and image_node_id in workflow:
        workflow[image_node_id]["inputs"][image_key] = start_image_filename
    else:
        for node in workflow.values():
            if node.get("class_type") == "LoadImage":
                node["inputs"]["image"] = start_image_filename

    audio_node_id = mapping.get("audio_node_id")
    audio_key = mapping.get("audio_input_key", "audio")
    if audio_filename and audio_node_id and audio_node_id in workflow:
        workflow[audio_node_id]["inputs"][audio_key] = audio_filename

    return workflow


def resolve_media_path(media_url: str) -> Path:
    """Resolve /api/media/{filename} to a local path."""
    if media_url.startswith("/api/media/"):
        filename = Path(media_url).name
        path = app_settings.TMP_DIR / filename
    else:
        path = Path(media_url)
    if not path.exists():
        raise FileNotFoundError(f"Start image not found: {media_url}")
    return path


async def upload_file_to_comfy(base_url: str, file_path: Path) -> str:
    """Upload image or audio to the ComfyUI input folder (saved under original filename)."""
    async with httpx.AsyncClient(timeout=300) as client:
        with open(file_path, "rb") as f:
            files = {"image": (file_path.name, f, "application/octet-stream")}
            data = {"overwrite": "true"}
            resp = await client.post(
                f"{base_url.rstrip('/')}/upload/image",
                files=files,
                data=data,
            )
        resp.raise_for_status()
        result = resp.json()
        return result.get("name") or file_path.name


async def upload_image_to_comfy(base_url: str, image_path: Path) -> str:
    return await upload_file_to_comfy(base_url, image_path)


async def upload_audio_to_comfy(base_url: str, audio_path: Path) -> str:
    return await upload_file_to_comfy(base_url, audio_path)


async def submit_comfy_workflow(base_url: str, workflow: dict) -> str:
    client_id = str(uuid.uuid4())
    body = {"prompt": workflow, "client_id": client_id}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(f"{base_url.rstrip('/')}/prompt", json=body)
        if not resp.is_success:
            raise RuntimeError(f"ComfyUI /prompt failed: {resp.status_code} {resp.text[:300]}")
        data = resp.json()
        prompt_id = data.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI did not return prompt_id: {data}")
        return prompt_id


async def wait_for_comfy_output(
    base_url: str,
    prompt_id: str,
    poll_interval: float = 2.0,
    max_wait: float = 1800.0,
) -> dict[str, Any]:
    """Poll ComfyUI history until outputs appear or timeout."""
    elapsed = 0.0
    async with httpx.AsyncClient(timeout=30) as client:
        while elapsed < max_wait:
            resp = await client.get(f"{base_url.rstrip('/')}/history/{prompt_id}")
            if resp.is_success:
                history = resp.json()
                if prompt_id in history:
                    entry = history[prompt_id]
                    outputs = entry.get("outputs", {})
                    for node_out in outputs.values():
                        for kind in ("videos", "gifs", "images"):
                            items = node_out.get(kind, [])
                            if items:
                                return {"outputs": outputs, "item": items[0], "kind": kind}
                    status = entry.get("status", {})
                    if status.get("status_str") == "error":
                        msgs = status.get("messages", [])
                        raise RuntimeError(f"ComfyUI workflow error: {msgs}")
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
    raise TimeoutError(f"ComfyUI job timed out after {max_wait}s")


async def download_comfy_output(
    base_url: str,
    item: dict,
    dest: Path,
) -> Path:
    """Download output file from ComfyUI /view endpoint."""
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
    """Full pipeline: upload image → build workflow → prompt → download video."""
    if on_progress:
        await on_progress(10, "Uploading start image to ComfyUI…")

    uploaded_name = await upload_image_to_comfy(base_url, start_image_path)
    if not audio_path or not audio_path.exists():
        raise ValueError("Reference audio file is missing")
    if on_progress:
        await on_progress(15, "Uploading reference audio to ComfyUI…")
    audio_name = await upload_audio_to_comfy(base_url, audio_path)
    workflow = build_workflow(prompt, length_seconds, uploaded_name, audio_name)

    if on_progress:
        await on_progress(20, "Submitting workflow…")

    prompt_id = await submit_comfy_workflow(base_url, workflow)

    if on_progress:
        await on_progress(30, "Generating video on RunPod…")

    result = await wait_for_comfy_output(base_url, prompt_id)
    item = result["item"]

    if on_progress:
        await on_progress(90, "Downloading output…")

    return await download_comfy_output(base_url, item, output_path)

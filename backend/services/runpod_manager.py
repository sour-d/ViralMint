# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Shared ComfyUI-Manager HTTP helpers for RunPod pods."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Awaitable, Callable, Optional

import httpx

logger = logging.getLogger(__name__)

# RunPod images may expose Manager under /manager or /api/manager
_PATH_PREFIXES = ("", "/api")


def _urls(base_url: str, path: str) -> list[str]:
    base = base_url.rstrip("/")
    return [f"{base}{prefix}{path}" for prefix in _PATH_PREFIXES]


async def get_json(base_url: str, path: str, *, timeout: float = 30) -> Optional[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        for url in _urls(base_url, path):
            try:
                resp = await client.get(url)
                if resp.is_success:
                    data = resp.json()
                    if isinstance(data, dict):
                        return data
            except Exception:
                continue
    return None


async def post_json(
    base_url: str,
    path: str,
    payload: dict[str, Any],
    *,
    timeout: float = 60,
) -> tuple[bool, int, str]:
    """Returns (success, status_code, detail)."""
    last_code = 0
    last_detail = ""
    async with httpx.AsyncClient(timeout=timeout) as client:
        for url in _urls(base_url, path):
            try:
                resp = await client.post(url, json=payload)
                last_code = resp.status_code
                last_detail = (resp.text or "")[:500]
                if resp.is_success:
                    return True, resp.status_code, last_detail
                if resp.status_code == 403:
                    return False, 403, last_detail
                logger.info(
                    "DEBUG:: POST %s -> %s %s",
                    url,
                    resp.status_code,
                    last_detail[:120],
                )
            except Exception as exc:
                last_detail = str(exc)
                logger.warning("DEBUG:: POST %s failed: %s", url, exc)
    if last_code:
        return False, last_code, last_detail
    return False, 0, last_detail or "connection error (no HTTP response)"


async def get_ok(base_url: str, path: str, *, timeout: float = 30) -> bool:
    async with httpx.AsyncClient(timeout=timeout) as client:
        for url in _urls(base_url, path):
            try:
                resp = await client.get(url)
                if resp.is_success or resp.status_code == 201:
                    return True
            except Exception:
                continue
    return False


async def manager_available(base_url: str) -> bool:
    for probe in ("/manager/version", "/manager/status"):
        if await get_ok(base_url, probe, timeout=10):
            return True
    return False


async def queue_status(base_url: str) -> Optional[dict[str, Any]]:
    return await get_json(base_url, "/manager/queue/status", timeout=10)


def queue_activity_line(queue: Optional[dict]) -> Optional[str]:
    if not queue:
        return None
    total = int(queue.get("total_count") or 0)
    done = int(queue.get("done_count") or 0)
    in_progress = int(queue.get("in_progress_count") or 0)
    if total == 0 and not queue.get("is_processing"):
        return None
    if done >= total and not queue.get("is_processing") and in_progress == 0:
        return None
    if queue.get("is_processing") or in_progress > 0:
        return f"ComfyUI-Manager queue: {done}/{total} done, installing…"
    if done < total:
        return f"ComfyUI-Manager queue: {done}/{total} tasks pending"
    return None


async def queue_start(base_url: str) -> bool:
    return await get_ok(base_url, "/manager/queue/start")


# RunPod ComfyUI paths (runpod/comfyui:latest, runpod-slim layout)
MANAGER_CONFIG_PATHS = (
    "/workspace/runpod-slim/ComfyUI/user/__manager/config.ini",
    "/workspace/runpod-slim/ComfyUI/user/default/ComfyUI-Manager/config.ini",
    "/workspace/runpod-slim/ComfyUI/custom_nodes/ComfyUI-Manager/config.ini",
)

SECURITY_LEVEL_INSTRUCTIONS = (
    "ComfyUI-Manager blocked the install (security_level is too strict). "
    "On the pod, edit user/__manager/config.ini and set security_level = normal "
    "or weak under [default], then restart ComfyUI. Paths: "
    + " or ".join(MANAGER_CONFIG_PATHS)
    + ". See https://github.com/ltdrdata/ComfyUI-Manager#security-policy"
)

def is_security_block(code: int, detail: str) -> bool:
    text = (detail or "").lower()
    return code in (403, 404) and (
        "security" in text or "security_level" in text or "not allowed" in text
    )


async def wait_for_manager_queue(
    base_url: str,
    *,
    timeout: float = 7200.0,
    poll_interval: float = 5.0,
    on_tick: Optional[Callable[[dict[str, Any]], Awaitable[None]]] = None,
) -> bool:
    """Poll until Manager queue is idle or timeout (seconds)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        queue = await queue_status(base_url)
        if queue is None:
            await asyncio.sleep(poll_interval)
            continue
        if on_tick:
            await on_tick(queue)
        total = int(queue.get("total_count") or 0)
        done = int(queue.get("done_count") or 0)
        processing = bool(queue.get("is_processing"))
        if total == 0 and not processing:
            return True
        if total > 0 and done >= total and not processing:
            return True
        await asyncio.sleep(poll_interval)
    logger.warning("DEBUG:: Manager queue wait timed out after %ss", timeout)
    return False


async def comfy_post_json(
    base_url: str,
    path: str,
    payload: dict[str, Any],
    *,
    timeout: float = 60,
) -> tuple[bool, Optional[dict[str, Any]], str]:
    """POST JSON to ComfyUI; returns (ok, parsed_json, error_detail)."""
    ok, code, detail = await _comfy_post(
        base_url, path, json_body=payload, timeout=timeout,
    )
    if not ok:
        return False, None, detail or f"HTTP {code}"
    try:
        data = json.loads(detail) if detail else {}
        if isinstance(data, dict):
            return True, data, ""
    except json.JSONDecodeError:
        pass
    return True, {}, ""


async def runpod_missing_model_filenames(
    base_url: str,
    entries: list[dict[str, Any]],
) -> Optional[set[str]]:
    """
    Filenames still absent on disk per RunpodDirect check_missing_models.
    None if RunpodDirect is unavailable.
    """
    if not await runpod_direct_available(base_url):
        return None

    models_payload = [
        {
            "filename": e["filename"],
            "directory": e.get("folder") or "checkpoints",
        }
        for e in entries
    ]
    ok, data, _ = await comfy_post_json(
        base_url,
        "/server_download/check_missing_models",
        {"models": models_payload, "verify_hashes": False},
        timeout=120,
    )
    if not ok or not data:
        return None

    missing: set[str] = set()
    for item in data.get("missing") or []:
        if isinstance(item, dict) and item.get("filename"):
            missing.add(str(item["filename"]))
    return missing


async def comfy_get(base_url: str, path: str, *, timeout: float = 30) -> Optional[Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.get(f"{base_url.rstrip('/')}{path}")
            if resp.is_success:
                return resp.json()
        except Exception:
            pass
    return None


async def _comfy_post(
    base_url: str,
    path: str,
    *,
    json_body: Optional[dict[str, Any]] = None,
    content: Optional[str] = None,
    timeout: Optional[float] = None,
) -> tuple[bool, int, str]:
    """POST to ComfyUI (not Manager). Returns (success, status_code, detail)."""
    url = f"{base_url.rstrip('/')}{path}"
    client_timeout = timeout if timeout is not None else 60.0
    async with httpx.AsyncClient(timeout=client_timeout) as client:
        try:
            if json_body is not None:
                resp = await client.post(url, json=json_body)
            else:
                resp = await client.post(url, content=content or "")
            if resp.is_success:
                return True, resp.status_code, (resp.text or "")[:500]
            return False, resp.status_code, (resp.text or "")[:500]
        except httpx.TimeoutException:
            return False, 0, "timeout"
        except Exception as exc:
            logger.warning("DEBUG:: POST %s failed: %s", path, exc)
            return False, 0, str(exc)


async def runpod_direct_available(base_url: str) -> bool:
    """True when ComfyUI-RunpodDirect is installed (powers UI 'Download to Pod')."""
    return await get_ok(base_url, "/server_download/hf_token_status", timeout=8)


async def wait_for_runpod_download(
    base_url: str,
    download_id: str,
    *,
    timeout: float = 7200.0,
    poll_interval: float = 5.0,
) -> tuple[bool, str]:
    """Poll RunpodDirect until download completes or fails."""
    encoded = download_id.replace(" ", "%20")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = await comfy_get(
            base_url,
            f"/server_download/status/{encoded}",
            timeout=15,
        )
        if isinstance(data, dict):
            status = str(data.get("status") or "")
            if status == "completed":
                return True, ""
            if status == "error":
                return False, str(data.get("error") or "RunpodDirect download failed")
            if status in ("queued", "downloading", "paused"):
                await asyncio.sleep(poll_interval)
                continue
        await asyncio.sleep(poll_interval)
    return False, "RunpodDirect download timed out"


async def download_model_runpod_direct(
    base_url: str,
    entry: dict[str, Any],
    url: str,
    *,
    hf_token: str = "",
) -> tuple[bool, str]:
    """
    Download via ComfyUI-RunpodDirect (same as UI 'Download to Pod').
    POST /server_download/start then poll status.
    """
    if not await runpod_direct_available(base_url):
        return False, "runpod_direct_unavailable"

    save_path = entry.get("folder") or "checkpoints"
    filename = entry["filename"]
    payload: dict[str, Any] = {
        "url": url,
        "save_path": save_path,
        "filename": filename,
    }
    if hf_token:
        payload["token"] = hf_token

    ok, code, detail = await _comfy_post(
        base_url,
        "/server_download/start",
        json_body=payload,
        timeout=120,
    )
    if not ok:
        detail_lower = (detail or "").lower()
        if code == 400 and "already exists" in detail_lower:
            logger.info("DEBUG:: RunpodDirect skip existing: %s", filename)
            return True, ""
        if code == 404:
            return False, "runpod_direct_unavailable"
        return False, detail or f"RunpodDirect start failed ({code})"

    download_id = f"{save_path}/{filename}"
    logger.info("DEBUG:: RunpodDirect queued: %s", download_id)
    return await wait_for_runpod_download(base_url, download_id)


async def enable_comfy_model_download(base_url: str) -> bool:
    """Enable Comfy.ModelDownloadEnabled (same gate as UI 'Download to Pod')."""
    ok, _, _ = await _comfy_post(
        base_url,
        "/settings/Comfy.ModelDownloadEnabled",
        content="true",
        timeout=30,
    )
    if ok:
        logger.info("DEBUG:: ComfyUI model download enabled")
    return ok


async def download_model_comfy(
    base_url: str,
    entry: dict[str, Any],
    url: str,
    *,
    hf_token: str = "",
) -> tuple[bool, str]:
    """Fallback: ComfyUI core POST /download_model or /models/download."""
    folder = entry.get("folder") or "checkpoints"
    filename = entry["filename"]
    payloads = [
        {"url": url, "save_dir": folder, "filename": filename},
        {"url": url, "model_type": folder, "filename": filename},
    ]
    if hf_token:
        for payload in payloads:
            payload["token"] = hf_token

    await enable_comfy_model_download(base_url)

    for path in ("/download_model", "/models/download"):
        for payload in payloads:
            ok, code, detail = await _comfy_post(
                base_url,
                path,
                json_body=payload,
                timeout=7200.0,
            )
            if ok:
                logger.info("DEBUG:: ComfyUI %s done: %s", path, filename)
                return True, ""
            if code == 404:
                break
            if code == 403:
                return False, (
                    "ComfyUI model download disabled on pod. "
                    "Enable Comfy.ModelDownloadEnabled in ComfyUI settings."
                )
            if code not in (404, 400, 422):
                return False, detail or f"ComfyUI {path} failed ({code})"

    return False, "comfy_download_unavailable"


async def download_model_on_pod(
    base_url: str,
    entry: dict[str, Any],
    url: str,
    *,
    hf_token: str = "",
) -> tuple[bool, str]:
    """
    Download a model on the pod. Order matches RunPod UI:
    1. ComfyUI-RunpodDirect /server_download/start
    2. ComfyUI /download_model
    3. Caller may fall back to ComfyUI-Manager install_model
    """
    ok, err = await download_model_runpod_direct(
        base_url, entry, url, hf_token=hf_token,
    )
    if ok:
        return True, ""
    if err != "runpod_direct_unavailable":
        return False, err

    ok, err = await download_model_comfy(base_url, entry, url, hf_token=hf_token)
    if ok:
        return True, ""
    return False, err


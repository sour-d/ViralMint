# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Check and install ComfyUI models on a RunPod pod."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

import httpx

from backend.config import settings as app_settings

logger = logging.getLogger(__name__)

MANIFEST_PATH = Path(__file__).resolve().parent.parent / "runpod" / "models_manifest.json"

# Same endpoints ComfyUI-Manager uses when the UI offers "Download missing models"
MANAGER_INSTALL_PATHS = (
    "/manager/queue/install_model",
    "/api/manager/queue/install_model",
)


def load_models_manifest() -> dict:
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return json.load(f)


async def fetch_comfy_model_lists(base_url: str) -> dict[str, list[str]]:
    """Return model filenames grouped by ComfyUI folder key."""
    out: dict[str, list[str]] = {}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{base_url.rstrip('/')}/models")
        if resp.is_success:
            data = resp.json()
            if isinstance(data, dict):
                for key, val in data.items():
                    if isinstance(val, list):
                        out[key] = [str(v) for v in val]
                return out
        resp = await client.get(f"{base_url.rstrip('/')}/object_info")
        if resp.is_success:
            info = resp.json()
            for node in info.values():
                if not isinstance(node, dict):
                    continue
                inp = node.get("input", {}).get("required", {})
                for field in ("ckpt_name", "lora_name", "unet_name"):
                    if field in inp and isinstance(inp[field], list) and inp[field]:
                        opts = inp[field][0]
                        if isinstance(opts, list):
                            out.setdefault(field, [str(x) for x in opts])
    return out


def check_models_present(model_lists: dict[str, list[str]], manifest: Optional[dict] = None) -> dict:
    manifest = manifest or load_models_manifest()
    present = []
    missing = []

    all_names: set[str] = set()
    for files in model_lists.values():
        all_names.update(files)

    for entry in manifest.get("models", []):
        name = entry["filename"]
        folder = entry.get("folder", "")
        found = name in all_names
        if not found and folder in model_lists:
            found = name in model_lists.get(folder, [])
        item = {"filename": name, "folder": folder, "hf_url": entry.get("hf_url")}
        if found:
            present.append(item)
        else:
            missing.append(item)

    return {
        "ready": len(missing) == 0,
        "present": present,
        "missing": missing,
        "total": len(manifest.get("models", [])),
    }


def _hf_auth_url(url: str) -> str:
    """Append HuggingFace token for gated files when configured."""
    token = (app_settings.RUNPOD_HF_TOKEN or os.getenv("HF_TOKEN") or "").strip()
    if not token or "huggingface.co" not in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}token={token}"


async def manager_is_available(base_url: str) -> bool:
    """True when ComfyUI-Manager is installed (same stack as the missing-models UI)."""
    probes = ("/manager/version", "/manager/status", "/api/manager/version")
    async with httpx.AsyncClient(timeout=10) as client:
        for path in probes:
            try:
                resp = await client.get(f"{base_url.rstrip('/')}{path}")
                if resp.is_success:
                    return True
            except Exception:
                continue
    return False


def _manager_install_payload(entry: dict) -> dict[str, str]:
    """Build ModelMetadata for POST /manager/queue/install_model."""
    folder = entry.get("folder") or "checkpoints"
    filename = entry["filename"]
    return {
        "name": filename,
        "type": folder,
        "filename": filename,
        "url": _hf_auth_url(entry.get("hf_url") or ""),
        "save_path": folder,
    }


async def queue_manager_install(base_url: str, entry: dict) -> tuple[bool, str]:
    """
    Queue a model install via ComfyUI-Manager (same path as importing a workflow
    and clicking download on the missing-models dialog).
    """
    payload = _manager_install_payload(entry)
    if not payload["url"]:
        return False, "no hf_url in manifest"

    async with httpx.AsyncClient(timeout=60) as client:
        for path in MANAGER_INSTALL_PATHS:
            try:
                resp = await client.post(
                    f"{base_url.rstrip('/')}{path}",
                    json=payload,
                )
                if resp.is_success:
                    logger.info(
                        "DEBUG:: model install queued via %s: %s",
                        path,
                        entry["filename"],
                    )
                    return True, path
                if resp.status_code == 403:
                    return False, (
                        "ComfyUI-Manager blocked the URL (security level). "
                        "Open ComfyUI → Manager settings and lower security, or "
                        "use URLs from model-list.json."
                    )
            except Exception as exc:
                logger.debug("Manager install %s failed: %s", path, exc)
                continue
    return False, "ComfyUI-Manager install_model API not reachable"


async def enable_comfy_model_downloads(base_url: str) -> bool:
    """Enable built-in ComfyUI /download_model when present (newer ComfyUI builds)."""
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(
                f"{base_url.rstrip('/')}/settings/Comfy.ModelDownloadEnabled",
                content="true",
            )
            return resp.is_success
        except Exception:
            return False


async def queue_comfy_download(base_url: str, entry: dict) -> bool:
    """
    Use ComfyUI core POST /download_model (if enabled on the pod image).
    Falls back silently when the endpoint is not shipped yet.
    """
    url = _hf_auth_url(entry.get("hf_url") or "")
    folder = entry.get("folder") or "checkpoints"
    if not url:
        return False

    await enable_comfy_model_downloads(base_url)
    body: dict[str, str] = {
        "url": url,
        "save_dir": folder,
        "filename": entry["filename"],
    }
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            resp = await client.post(
                f"{base_url.rstrip('/')}/download_model",
                json=body,
            )
            if resp.is_success:
                logger.info("DEBUG:: model download via /download_model: %s", entry["filename"])
                return True
        except Exception as exc:
            logger.debug("Comfy /download_model failed: %s", exc)
    return False


async def install_missing_models(
    base_url: str,
    on_progress: Optional[Callable[[float, str], Awaitable[None]]] = None,
) -> dict[str, Any]:
    """
    Queue downloads for missing models using ComfyUI on the pod.

    Priority:
    1. ComfyUI-Manager ``/manager/queue/install_model`` (same as missing-models UI)
    2. ComfyUI ``/download_model`` when the image includes it
    """
    manifest = load_models_manifest()
    lists = await fetch_comfy_model_lists(base_url)
    check = check_models_present(lists, manifest)
    if check["ready"]:
        return {"installed": 0, "skipped": "all_present", "missing": [], "method": None}

    has_manager = await manager_is_available(base_url)
    queued: list[str] = []
    failed: list[dict] = []
    method = "comfyui-manager" if has_manager else "comfyui-download"

    for i, entry in enumerate(check["missing"]):
        name = entry["filename"]
        if on_progress:
            await on_progress(
                int(10 + (80 * i / max(len(check["missing"]), 1))),
                f"Queueing download: {name}…",
            )

        ok = False
        err = ""
        if has_manager:
            ok, err = await queue_manager_install(base_url, entry)
        if not ok:
            ok = await queue_comfy_download(base_url, entry)
            if ok:
                method = "comfyui-download"

        if ok:
            queued.append(name)
        else:
            failed.append({**entry, "error": err or "no download API on pod"})

    if queued:
        msg = (
            "Downloads queued via ComfyUI (same as the missing-models prompt in the UI). "
            "Poll status until all models appear — large files can take 30–90+ minutes."
        )
    elif not has_manager:
        msg = (
            "ComfyUI-Manager is not available on this pod. Enable it on the template, "
            "or open ComfyUI in the browser, import the workflow, and use the built-in "
            "missing-models download dialog."
        )
    else:
        msg = "Could not queue downloads. Check ComfyUI Manager security settings on the pod."

    return {
        "installed": len(queued),
        "queued": queued,
        "failed": failed,
        "method": method if queued else None,
        "manager_available": has_manager,
        "message": msg,
    }

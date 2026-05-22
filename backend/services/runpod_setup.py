# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""ComfyUI pod readiness checks and setup (custom nodes + models via Manager)."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from backend.config import settings as app_settings
from backend.services import runpod_manager as mgr

logger = logging.getLogger(__name__)

MODELS_MANIFEST = Path(__file__).resolve().parent.parent / "runpod" / "models_manifest.json"
NODES_MANIFEST = Path(__file__).resolve().parent.parent / "runpod" / "custom_nodes_manifest.json"
WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / "workflows"

CORE_CLASS_TYPES = frozenset({
    "ResizeImageMaskNode", "ResizeImagesByLongerEdge", "TrimAudioDuration",
    "LoadImage", "LoadAudio", "SaveVideo", "CLIPTextEncode", "KSamplerSelect",
    "CFGGuider", "SamplerCustomAdvanced", "VAEDecodeTiled", "CheckpointLoaderSimple",
    "LoraLoader", "LoraLoaderModelOnly", "LatentUpscaleModelLoader", "CreateVideo",
    "PrimitiveInt", "PrimitiveFloat", "PrimitiveBoolean", "PrimitiveStringMultiline",
    "RandomNoise", "ManualSigmas", "SolidMask", "SetLatentNoiseMask", "PreviewAny",
})


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _hf_url(url: str) -> str:
    token = (app_settings.RUNPOD_HF_TOKEN or os.getenv("HF_TOKEN") or "").strip()
    if not token or "huggingface.co" not in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}token={token}"


def workflow_class_types(workflow_file: str = "video_ltx2_3_ia2v-api.json") -> set[str]:
    with open(WORKFLOWS_DIR / workflow_file, encoding="utf-8") as f:
        workflow = json.load(f)
    return {
        node["class_type"]
        for node in workflow.values()
        if isinstance(node, dict) and "class_type" in node
    }


async def assess_pod(base_url: str) -> dict[str, Any]:
    """Check custom nodes and models in one pass (single object_info + /models)."""
    registered: set[str] = set()
    model_lists: dict[str, list[str]] = {}

    info = await mgr.comfy_get(base_url, "/object_info")
    if isinstance(info, dict):
        registered = set(info.keys())

    models_data = await mgr.comfy_get(base_url, "/models")
    if isinstance(models_data, dict):
        for key, val in models_data.items():
            if isinstance(val, list):
                model_lists[key] = [str(v) for v in val]

    nodes = _check_nodes(registered)
    models = _check_models(model_lists)
    return {
        "custom_nodes_ready": nodes["ready"],
        "custom_nodes_status": nodes,
        "models_ready": models["ready"],
        "models_status": models,
    }


def _check_nodes(registered: set[str], required: Optional[set[str]] = None) -> dict:
    required = required or workflow_class_types()
    missing_types: list[str] = []
    missing_core: list[str] = []
    for class_type in sorted(required):
        if class_type in registered:
            continue
        if class_type in CORE_CLASS_TYPES:
            missing_core.append(class_type)
        else:
            missing_types.append(class_type)

    manifest = _load_json(NODES_MANIFEST)
    packs_needed: dict[str, dict] = {}
    for class_type in missing_types:
        for pack in manifest.get("packs", []):
            prefixes = pack.get("class_type_prefixes") or []
            if any(class_type.startswith(p) for p in prefixes):
                packs_needed[pack["id"]] = pack
            elif class_type in (pack.get("class_types") or []):
                packs_needed[pack["id"]] = pack

    return {
        "ready": not missing_types and not missing_core,
        "missing_class_types": missing_types,
        "missing_core_class_types": missing_core,
        "packs_needed": list(packs_needed.values()),
    }


def _check_models(model_lists: dict[str, list[str]]) -> dict:
    manifest = _load_json(MODELS_MANIFEST)
    all_names = {name for files in model_lists.values() for name in files}
    present, missing = [], []

    for entry in manifest.get("models", []):
        name = entry["filename"]
        folder = entry.get("folder", "")
        found = name in all_names or name in model_lists.get(folder, [])
        item = {"filename": name, "folder": folder, "hf_url": entry.get("hf_url")}
        (present if found else missing).append(item)

    return {"ready": not missing, "present": present, "missing": missing, "total": len(manifest.get("models", []))}


async def _installed_pack_ids(base_url: str) -> set[str]:
    data = await mgr.comfy_get(base_url, "/customnode/installed")
    ids: set[str] = set()
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("id"):
                ids.add(str(item["id"]))
    elif isinstance(data, dict):
        for key, item in data.items():
            if isinstance(item, dict) and item.get("id"):
                ids.add(str(item["id"]))
            else:
                ids.add(str(key))
    return ids


async def _queue_node_pack(base_url: str, pack: dict) -> tuple[bool, str]:
    payload = {
        "id": pack["id"],
        "title": pack.get("title", pack["id"]),
        "name": pack.get("name", pack["id"]),
        "author": pack.get("author", ""),
        "reference": pack.get("reference", ""),
        "files": pack.get("files", []),
        "install_type": pack.get("install_type", "git-clone"),
        "description": pack.get("description", ""),
    }
    ok, code, _ = await mgr.post_json(base_url, "/manager/queue/install", payload)
    if ok:
        logger.info("DEBUG:: custom node queued: %s", pack["id"])
        return True, ""
    if code == 403:
        return False, "ComfyUI-Manager security level blocked install"
    return False, "Could not queue custom node install"


async def _queue_model(base_url: str, entry: dict) -> tuple[bool, str]:
    url = _hf_url(entry.get("hf_url") or "")
    if not url:
        return False, "no hf_url in manifest"
    payload = {
        "name": entry["filename"],
        "type": entry.get("folder") or "checkpoints",
        "filename": entry["filename"],
        "url": url,
        "save_path": entry.get("folder") or "checkpoints",
    }
    ok, code, _ = await mgr.post_json(base_url, "/manager/queue/install_model", payload)
    if ok:
        logger.info("DEBUG:: model queued: %s", entry["filename"])
        return True, ""
    if code == 403:
        return False, "ComfyUI-Manager blocked model URL (security level)"
    return False, "Could not queue model install"


async def setup_pod(
    base_url: str,
    on_progress: Optional[Callable[[float, str], Awaitable[None]]] = None,
) -> dict[str, Any]:
    """Install missing custom node packs, then queue missing models."""
    if not await mgr.manager_available(base_url):
        return {
            "ok": False,
            "message": "ComfyUI-Manager is not available on this pod.",
            "custom_nodes": {"skipped": "manager_unavailable"},
            "models": {"skipped": "manager_unavailable"},
        }

    nodes_out = await _setup_nodes(base_url, on_progress)
    models_out = await _setup_models(base_url, on_progress)

    parts = [m for m in (nodes_out.get("message"), models_out.get("message")) if m]
    return {
        "ok": not nodes_out.get("failed") and not models_out.get("failed"),
        "message": " ".join(parts) or "Setup complete.",
        "custom_nodes": nodes_out,
        "models": models_out,
    }


async def _setup_nodes(
    base_url: str,
    on_progress: Optional[Callable[[float, str], Awaitable[None]]] = None,
) -> dict[str, Any]:
    info = await mgr.comfy_get(base_url, "/object_info")
    registered = set(info.keys()) if isinstance(info, dict) else set()
    check = _check_nodes(registered)

    if check["ready"]:
        return {"queued": [], "failed": [], "message": "Custom nodes already present."}
    if check["missing_core_class_types"]:
        return {
            "queued": [],
            "failed": [],
            "message": (
                "Pod ComfyUI is too old for: "
                + ", ".join(check["missing_core_class_types"])
            ),
        }

    installed = await _installed_pack_ids(base_url)
    queued, failed = [], []
    packs = check["packs_needed"]

    for i, pack in enumerate(packs):
        if pack["id"] in installed:
            continue
        if on_progress:
            await on_progress(5 + int(35 * i / max(len(packs), 1)), f"Queueing {pack.get('title', pack['id'])}…")
        ok, err = await _queue_node_pack(base_url, pack)
        if ok:
            queued.append(pack["id"])
        else:
            failed.append({"id": pack["id"], "error": err})

    if queued:
        await mgr.queue_start(base_url)

    if queued:
        msg = "Custom nodes queued — restart ComfyUI on the pod when the queue finishes."
    elif failed:
        msg = "Could not queue some custom node installs."
    else:
        msg = "Custom nodes installed but not loaded — restart ComfyUI on the pod."

    return {"queued": queued, "failed": failed, "message": msg}


async def _setup_models(
    base_url: str,
    on_progress: Optional[Callable[[float, str], Awaitable[None]]] = None,
) -> dict[str, Any]:
    models_data = await mgr.comfy_get(base_url, "/models")
    model_lists = {}
    if isinstance(models_data, dict):
        for key, val in models_data.items():
            if isinstance(val, list):
                model_lists[key] = [str(v) for v in val]

    check = _check_models(model_lists)
    if check["ready"]:
        return {"queued": [], "failed": [], "message": "All models already present."}

    queued, failed = [], []
    for i, entry in enumerate(check["missing"]):
        name = entry["filename"]
        if on_progress:
            await on_progress(45 + int(50 * i / max(len(check["missing"]), 1)), f"Queueing {name}…")
        ok, err = await _queue_model(base_url, entry)
        if ok:
            queued.append(name)
        else:
            failed.append({**entry, "error": err})

    if queued:
        await mgr.queue_start(base_url)
        msg = "Model downloads queued (30–90+ min for large files)."
    elif failed:
        msg = "Could not queue some model downloads."
    else:
        msg = "No models queued."

    return {"queued": queued, "failed": failed, "message": msg}

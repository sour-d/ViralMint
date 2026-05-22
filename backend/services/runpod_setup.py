# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""ComfyUI pod readiness checks and setup (nodes via Manager, models via ComfyUI core)."""
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
WORKFLOW_UI_JSON = WORKFLOWS_DIR / "video_ltx2_3_ia2v.json"

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


def _manifest_model_entries() -> list[dict[str, Any]]:
    return list(_load_json(MODELS_MANIFEST).get("models", []))


def _workflow_model_urls() -> dict[str, dict[str, str]]:
    """URLs embedded in the UI workflow (same source as 'Download to Pod' dialog)."""
    if not WORKFLOW_UI_JSON.is_file():
        return {}
    try:
        data = json.loads(WORKFLOW_UI_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    found: dict[str, dict[str, str]] = {}

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            models = obj.get("models")
            if isinstance(models, list):
                for item in models:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name") or item.get("filename")
                    url = item.get("url")
                    directory = item.get("directory") or item.get("folder")
                    if name and url:
                        found[str(name)] = {
                            "hf_url": str(url),
                            "folder": str(directory or "checkpoints"),
                        }
            for value in obj.values():
                walk(value)
        elif isinstance(obj, list):
            for value in obj:
                walk(value)

    walk(data)
    return found


def _resolve_model_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Prefer workflow-embedded URLs, then manifest hf_url."""
    merged = dict(entry)
    by_name = _workflow_model_urls()
    wf = by_name.get(entry["filename"])
    if wf:
        merged["hf_url"] = wf.get("hf_url") or merged.get("hf_url")
        merged["folder"] = wf.get("folder") or merged.get("folder")
    return merged


def workflow_class_types(workflow_file: str = "video_ltx2_3_ia2v-api.json") -> set[str]:
    with open(WORKFLOWS_DIR / workflow_file, encoding="utf-8") as f:
        workflow = json.load(f)
    return {
        node["class_type"]
        for node in workflow.values()
        if isinstance(node, dict) and "class_type" in node
    }


async def filter_missing_model_entries(
    base_url: str,
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Only entries not already on the pod (Comfy /models + RunpodDirect disk check)."""
    models_data = await mgr.comfy_get(base_url, "/models")
    model_lists: dict[str, list[str]] = {}
    if isinstance(models_data, dict):
        for key, val in models_data.items():
            if isinstance(val, list):
                model_lists[key] = [str(v) for v in val]

    check = _check_models(model_lists)
    if check["ready"]:
        return []

    manifest_by_name = {m["filename"]: m for m in entries}
    comfy_missing = {m["filename"] for m in check["missing"]}
    candidates = [
        _resolve_model_entry(manifest_by_name[name])
        for name in comfy_missing
        if name in manifest_by_name
    ]

    on_disk_missing = await mgr.runpod_missing_model_filenames(base_url, candidates)
    if on_disk_missing is None:
        return candidates

    return [e for e in candidates if e["filename"] in on_disk_missing]


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
    if not models["ready"]:
        still_missing = await filter_missing_model_entries(
            base_url,
            [_resolve_model_entry(m) for m in _manifest_model_entries()],
        )
        if not still_missing:
            models = {
                **models,
                "ready": True,
                "missing": [],
                "present": models.get("present", []) + models.get("missing", []),
            }
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


def _pack_install_payload(pack: dict) -> dict[str, Any]:
    """Fields required by ComfyUI-Manager queue/install (see manager_server.py)."""
    return {
        "id": pack["id"],
        "title": pack.get("title", pack["id"]),
        "name": pack.get("name", pack["id"]),
        "author": pack.get("author", ""),
        "reference": pack.get("reference", ""),
        "files": pack.get("files", []),
        "install_type": pack.get("install_type", "git-clone"),
        "description": pack.get("description", ""),
        "version": "unknown",
        "selected_version": "unknown",
        "channel": "default",
        "mode": "cache",
        "ui_id": pack["id"],
    }


async def _queue_node_pack(base_url: str, pack: dict) -> tuple[bool, str]:
    payload = _pack_install_payload(pack)
    ok, code, detail = await mgr.post_json(base_url, "/manager/queue/install", payload)
    if ok:
        logger.info("DEBUG:: custom node queued: %s", pack["id"])
        return True, ""
    if code == 403 or mgr.is_security_block(code, detail):
        return False, mgr.SECURITY_LEVEL_INSTRUCTIONS
    return False, f"Could not queue custom node install (HTTP {code}): {detail}"


def _manager_model_payload(entry: dict, url: str) -> dict[str, str]:
    """Payload for Manager install_model (requires base + whitelist match)."""
    folder = entry.get("folder") or "checkpoints"
    return {
        "name": entry.get("name") or entry["filename"],
        "type": entry.get("type") or folder,
        "base": entry.get("base") or "LTX-2.3",
        "save_path": entry.get("save_path") or "default",
        "filename": entry["filename"],
        "url": url,
    }


async def _download_model(base_url: str, entry: dict) -> tuple[bool, str]:
    """Download via ComfyUI core (same as UI 'Download to Pod'); Manager as fallback."""
    resolved = _resolve_model_entry(entry)
    url = _hf_url(resolved.get("hf_url") or "")
    if not url:
        return False, "no download URL in manifest or workflow"

    hf_token = (app_settings.RUNPOD_HF_TOKEN or os.getenv("HF_TOKEN") or "").strip()
    ok, err = await mgr.download_model_on_pod(base_url, resolved, url, hf_token=hf_token)
    if ok:
        return True, ""
    if err not in ("comfy_download_unavailable", "runpod_direct_unavailable"):
        return False, err

    payload = _manager_model_payload(resolved, url)
    ok, code, detail = await mgr.post_json(
        base_url, "/manager/queue/install_model", payload,
    )
    if ok:
        logger.info("DEBUG:: model queued via Manager fallback: %s", entry["filename"])
        return True, "manager_queued"
    if code == 403 or mgr.is_security_block(code, detail):
        return False, mgr.SECURITY_LEVEL_INSTRUCTIONS
    return False, (
        f"ComfyUI download unavailable and Manager install failed ({code}): {detail}"
    )


async def setup_pod(
    base_url: str,
    on_progress: Optional[Callable[[float, str], Awaitable[None]]] = None,
) -> dict[str, Any]:
    """Install models via ComfyUI core; custom nodes via ComfyUI-Manager queue."""
    if on_progress:
        await on_progress(2, "Checking pod…")

    assessment = await assess_pod(base_url)
    if assessment["custom_nodes_ready"] and assessment["models_ready"]:
        return {
            "ok": True,
            "skipped": True,
            "message": "Pod already set up — all models and custom nodes are present.",
            "custom_nodes": {"skipped": True, "message": "Custom nodes already present."},
            "models": {"skipped": True, "message": "All models already present."},
        }

    models_out = await _setup_models(base_url, on_progress)

    nodes_out: dict[str, Any]
    if not await mgr.manager_available(base_url):
        nodes_out = {
            "queued": [],
            "failed": [],
            "message": "ComfyUI-Manager not available — install custom nodes manually.",
        }
    else:
        nodes_out = await _setup_nodes(base_url, on_progress, start_queue=False)
        if nodes_out.get("queued"):
            if on_progress:
                await on_progress(92, "Starting custom node install queue…")
            await mgr.queue_start(base_url)

    skipped = bool(
        models_out.get("skipped")
        and (nodes_out.get("skipped") or not nodes_out.get("queued"))
    )
    ok = not nodes_out.get("failed") and not models_out.get("failed")
    parts = [m for m in (models_out.get("message"), nodes_out.get("message")) if m]
    if nodes_out.get("queued"):
        parts.append("Restart ComfyUI after custom node installs finish.")
    if models_out.get("downloaded"):
        parts.append("Large model downloads may take 30–90+ minutes.")
    return {
        "ok": ok,
        "skipped": skipped,
        "message": " ".join(parts) or "Setup complete.",
        "custom_nodes": nodes_out,
        "models": models_out,
    }


async def cleanup_pod(
    base_url: str,
    *,
    remove_models: bool = True,
    remove_nodes: bool = True,
) -> dict[str, Any]:
    """
    Remove LTX workflow custom nodes (Manager uninstall) and list model paths to delete.
    Model files are not deleted remotely (no ComfyUI API); paths are returned for manual removal.
    """
    nodes_out: dict[str, Any] = {"uninstalled": [], "skipped": True, "message": "Skipped."}
    models_out: dict[str, Any] = {"paths": [], "skipped": True, "message": "Skipped."}

    if remove_nodes and await mgr.manager_available(base_url):
        installed = await _installed_pack_ids(base_url)
        manifest = _load_json(NODES_MANIFEST)
        uninstalled, failed = [], []
        for pack in manifest.get("packs", []):
            if pack["id"] not in installed:
                continue
            payload = _pack_install_payload(pack)
            ok, code, detail = await mgr.post_json(
                base_url, "/manager/queue/uninstall", payload,
            )
            if ok:
                uninstalled.append(pack["id"])
            else:
                failed.append({"id": pack["id"], "error": detail or f"HTTP {code}"})
        if uninstalled:
            await mgr.queue_start(base_url)
        nodes_out = {
            "uninstalled": uninstalled,
            "failed": failed,
            "message": (
                f"Queued uninstall for {len(uninstalled)} custom node pack(s)."
                if uninstalled
                else "No workflow custom nodes to uninstall."
            ),
        }
    elif remove_nodes:
        nodes_out = {
            "uninstalled": [],
            "failed": [],
            "message": "ComfyUI-Manager not available — uninstall nodes manually.",
        }

    if remove_models:
        paths = []
        for entry in _manifest_model_entries():
            folder = entry.get("folder") or "checkpoints"
            paths.append(
                f"/workspace/runpod-slim/ComfyUI/models/{folder}/{entry['filename']}"
            )
        models_out = {
            "paths": paths,
            "skipped": False,
            "message": (
                "Delete these model files on the pod (RunPod file browser or terminal). "
                "ViralMint cannot remove large files via API."
            ),
        }

    return {
        "ok": not nodes_out.get("failed", []),
        "message": " ".join(
            m for m in (nodes_out.get("message"), models_out.get("message")) if m
        ),
        "custom_nodes": nodes_out,
        "models": models_out,
    }


async def _setup_nodes(
    base_url: str,
    on_progress: Optional[Callable[[float, str], Awaitable[None]]] = None,
    *,
    start_queue: bool = True,
) -> dict[str, Any]:
    info = await mgr.comfy_get(base_url, "/object_info")
    registered = set(info.keys()) if isinstance(info, dict) else set()
    check = _check_nodes(registered)

    if check["ready"]:
        return {
            "queued": [],
            "failed": [],
            "skipped": True,
            "message": "Custom nodes already present.",
        }
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
            await on_progress(
                10 + int(35 * i / max(len(packs), 1)),
                f"Queueing {pack.get('title', pack['id'])}…",
            )
        ok, err = await _queue_node_pack(base_url, pack)
        if ok:
            queued.append(pack["id"])
        else:
            failed.append({"id": pack["id"], "error": err})

    if queued and start_queue:
        await mgr.queue_start(base_url)

    if queued:
        msg = f"Queued {len(queued)} custom node pack(s)."
    elif failed:
        msg = "Could not queue some custom node installs."
    else:
        msg = "Custom nodes installed but not loaded — restart ComfyUI on the pod."

    return {"queued": queued, "failed": failed, "message": msg}


async def _setup_models(
    base_url: str,
    on_progress: Optional[Callable[[float, str], Awaitable[None]]] = None,
) -> dict[str, Any]:
    all_entries = [_resolve_model_entry(m) for m in _manifest_model_entries()]
    to_download = await filter_missing_model_entries(base_url, all_entries)
    if not to_download:
        return {
            "downloaded": [],
            "queued": [],
            "failed": [],
            "skipped": True,
            "message": "All models already present.",
        }

    downloaded, queued, failed = [], [], []
    for i, full_entry in enumerate(to_download):
        name = full_entry["filename"]
        if on_progress:
            await on_progress(
                5 + int(80 * i / max(len(to_download), 1)),
                f"Downloading {name}…",
            )
        ok, err = await _download_model(base_url, full_entry)
        if ok:
            if err == "manager_queued":
                queued.append(name)
            else:
                downloaded.append(name)
        else:
            failed.append({**full_entry, "error": err})

    if queued:
        await mgr.queue_start(base_url)

    if downloaded:
        msg = f"Downloaded {len(downloaded)} model(s) on the pod."
    elif queued:
        msg = f"Queued {len(queued)} model(s) via ComfyUI-Manager fallback."
    elif failed:
        first_err = failed[0].get("error", "") if failed else ""
        names = ", ".join(f["filename"] for f in failed[:3])
        msg = f"Could not download: {names}."
        if first_err:
            msg += f" {first_err}"
    else:
        msg = "No models to download."

    return {
        "downloaded": downloaded,
        "queued": queued,
        "failed": failed,
        "skipped": not downloaded and not queued and not failed,
        "message": msg,
    }

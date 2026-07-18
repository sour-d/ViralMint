# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""REST /api/runpod — RunPod Pod status and deploy."""
import logging
import json
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select

from backend.database import AsyncSessionLocal
from backend.models.user_settings import UserSettings
from backend.core.api_keys import get_runpod_api_key, get_runpod_pod_id
from backend.services import runpod_service
from backend.services.runpod_setup import MODELS_MANIFEST, NODES_MANIFEST

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/runpod", tags=["runpod"])
WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / "workflows"
WORKFLOW_FILES = {
    "api": "video_ltx2_3_ia2v-api.json",
    "ui": "video_ltx2_3_ia2v.json",
    "mapping": "runpod_mapping.json",
}


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


@router.get("/workflow")
async def runpod_workflow(type: str = "ltx"):
    """Return workflow metadata for the ComfyUI setup tab.

    Accepts ``type=ltx`` (LTX audio→video), ``type=ltx-img2vid`` (LTX image→video),
    ``type=z-turbo`` (Z-turbo txt2img), or ``type=tts`` (Higgs v3 TTS).
    """
    # Shared model list helper
    def _manifest_models(workflow_tag: str) -> list[dict]:
        models = []
        try:
            with open(MODELS_MANIFEST, encoding="utf-8") as f:
                models = list((json.load(f) or {}).get("models", []))
            models = [m for m in models if workflow_tag in (m.get("workflows") or [])]
        except Exception:
            models = []
        return [{"filename": m["filename"], "folder": m.get("folder", "checkpoints")} for m in models if m.get("filename")]

    def _manifest_node_packs() -> list[dict]:
        packs = []
        try:
            with open(NODES_MANIFEST, encoding="utf-8") as f:
                packs = list((json.load(f) or {}).get("packs", []))
        except Exception:
            packs = []
        return [{"id": p.get("id"), "title": p.get("title", p.get("id"))} for p in packs if p.get("id")]

    if type == "z-turbo":
        anime_lofi_mapping = WORKFLOWS_DIR / "runpod_mapping_anime_lofi.json"
        if not anime_lofi_mapping.exists():
            return {
                "kind": "z-turbo",
                "workflow_file": "anime_lofi_txt2img.json",
                "mapping_file": "runpod_mapping_anime_lofi.json",
                "audio_required": False,
                "required_models": [],
                "required_node_packs": [],
                "configured": False,
                "download_urls": {
                    "workflow": "/api/runpod/workflow/download?kind=anime_lofi_txt2img",
                    "mapping": "/api/runpod/workflow/download?kind=anime_lofi_mapping",
                },
            }
        with open(anime_lofi_mapping, encoding="utf-8") as f:
            mapping = json.load(f)
        return {
            "kind": "z-turbo",
            "workflow_file": mapping.get("txt2img", {}).get("workflow_file", "anime_lofi_txt2img.json"),
            "mapping_file": "runpod_mapping_anime_lofi.json",
            "audio_required": False,
            "required_models": mapping.get("required_models", []),
            "required_node_packs": mapping.get("required_node_packs", []),
            "configured": all(
                mapping.get("txt2img", {}).get(k) and mapping["txt2img"][k] != "REPLACE_ME"
                for k in ("prompt_node_id", "seed_node_id", "save_image_node_id")
            ),
            "download_urls": {
                "workflow": "/api/runpod/workflow/download?kind=anime_lofi_txt2img",
                "mapping": "/api/runpod/workflow/download?kind=anime_lofi_mapping",
            },
        }

    # LTX image→video workflow
    if type == "ltx-img2vid":
        wf_file = "anime_lofi_img2vid.json"
        wf_path = WORKFLOWS_DIR / wf_file
        wf_ok = wf_path.exists()
        return {
            "kind": "ltx-img2vid",
            "workflow_file": wf_file if wf_ok else None,
            "mapping_file": "runpod_mapping_anime_lofi.json",
            "audio_required": False,
            "configured": wf_ok,
            "required_models": _manifest_models("ltx-img2vid"),
            "required_node_packs": _manifest_node_packs(),
            "download_urls": {
                "workflow": f"/api/runpod/workflow/download?kind=anime_lofi_img2vid" if wf_ok else None,
                "mapping": "/api/runpod/workflow/download?kind=anime_lofi_mapping",
            },
        }

    # TTS (Higgs v3 Voice Clone) workflow
    if type == "tts":
        anime_lofi_mapping = WORKFLOWS_DIR / "runpod_mapping_anime_lofi.json"
        if not anime_lofi_mapping.exists():
            return {
                "kind": "tts",
                "workflow_file": "higgs-text-to-audio-with-clone-api.json",
                "mapping_file": "runpod_mapping_anime_lofi.json",
                "audio_required": True,
                "required_models": [],
                "required_node_packs": [],
                "configured": False,
                "download_urls": {
                    "workflow": "/api/runpod/workflow/download?kind=higgs_tts",
                    "mapping": "/api/runpod/workflow/download?kind=anime_lofi_mapping",
                },
            }
        with open(anime_lofi_mapping, encoding="utf-8") as f:
            mapping = json.load(f)
        return {
            "kind": "tts",
            "workflow_file": mapping.get("tts", {}).get("workflow_file", "higgs-text-to-audio-with-clone-api.json"),
            "mapping_file": "runpod_mapping_anime_lofi.json",
            "audio_required": True,
            "required_models": [],
            "required_node_packs": mapping.get("required_node_packs", []),
            "configured": all(
                mapping.get("tts", {}).get(k) and mapping["tts"][k] != "REPLACE_ME"
                for k in ("prompt_node_id", "save_audio_node_id", "reference_audio_node_id")
            ),
            "download_urls": {
                "workflow": "/api/runpod/workflow/download?kind=higgs_tts",
                "mapping": "/api/runpod/workflow/download?kind=anime_lofi_mapping",
            },
        }

    # Default: LTX audio→video workflow
    mapping = runpod_service.load_workflow_mapping()
    mapping_configured = all(
        mapping.get(k) and str(mapping[k]) != "REPLACE_ME"
        for k in ("prompt_node_id",)
    )

    return {
        "kind": "ltx",
        "workflow_file": mapping.get("workflow_file", WORKFLOW_FILES["api"]),
        "ui_workflow_file": WORKFLOW_FILES["ui"],
        "mapping_file": WORKFLOW_FILES["mapping"],
        "audio_required": bool(mapping.get("audio_required", False)),
        "configured": mapping_configured,
        "download_urls": {
            "api": "/api/runpod/workflow/download?kind=api",
            "ui": "/api/runpod/workflow/download?kind=ui",
            "mapping": "/api/runpod/workflow/download?kind=mapping",
        },
        "required_models": _manifest_models("ltx"),
        "required_node_packs": _manifest_node_packs(),
    }


@router.get("/workflow/download")
async def runpod_workflow_download(kind: str = "api"):
    """Download a workflow, UI export, or mapping file."""
    ANIME_LOFI_FILES = {
        "anime_lofi_txt2img": "anime_lofi_txt2img.json",
        "anime_lofi_img2vid": "anime_lofi_img2vid.json",
        "anime_lofi_mapping": "runpod_mapping_anime_lofi.json",
        "higgs_tts": "higgs-text-to-audio-with-clone-api.json",
    }
    filename = WORKFLOW_FILES.get(kind) or ANIME_LOFI_FILES.get(kind)
    if not filename:
        raise HTTPException(400, detail="Invalid kind. Options: api, ui, mapping, anime_lofi_txt2img, anime_lofi_img2vid, anime_lofi_mapping, higgs_tts")

    path = WORKFLOWS_DIR / filename
    if not path.is_file():
        raise HTTPException(404, detail=f"File not found: {filename}")

    return FileResponse(
        path,
        media_type="application/json",
        filename=filename,
    )


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


@router.post("/setup")
@router.post("/install-models")
async def runpod_setup(type: str = "all"):
    """Queue missing models and custom nodes for the given workflow type.

    Accepts ``type=ltx``, ``type=z-turbo``, or ``type=all`` (default).
    """
    from backend.agents.job_helper import create_job
    from backend.core.task_runner import run_install_runpod_models, dispatch

    if type not in ("ltx", "z-turbo", "ltx-img2vid", "tts", "all"):
        raise HTTPException(400, detail="type must be ltx, ltx-img2vid, z-turbo, or all")

    user_settings = await _get_user_settings()
    api_key = get_runpod_api_key(user_settings)
    if not api_key:
        raise HTTPException(503, detail="RunPod API key not configured")

    stored_pod_id = get_runpod_pod_id(user_settings)
    status = await runpod_service.get_pod_status(api_key, stored_pod_id)
    if not status.get("comfy_ready"):
        raise HTTPException(503, detail="ComfyUI is not ready on the pod")

    wf_label = {"ltx": "LTX", "ltx-img2vid": "LTX img2vid", "z-turbo": "Z-turbo", "tts": "Higgs TTS", "all": "all"}[type]

    job = await create_job("runpod_install_models", "local", {"workflow_type": type})
    dispatch(run_install_runpod_models(job_id=job.id, user_id="local"))
    return {
        "job_id": job.id,
        "type": type,
        "message": (
            f"Setup started for {wf_label} — models download via ComfyUI, "
            f"custom nodes via ComfyUI-Manager. Restart ComfyUI after node installs. "
            f"Large models may take 30–90+ minutes."
        ),
    }


@router.post("/free-memory")
async def runpod_free_memory():
    """Unload ComfyUI models and clear execution cache on the pod (frees GPU VRAM)."""
    user_settings = await _get_user_settings()
    api_key = get_runpod_api_key(user_settings)
    if not api_key:
        raise HTTPException(503, detail="RunPod API key not configured")

    stored_pod_id = get_runpod_pod_id(user_settings)
    status = await runpod_service.get_pod_status(api_key, stored_pod_id)
    if not status.get("comfy_ready"):
        raise HTTPException(503, detail="ComfyUI is not ready on the pod")

    base_url = runpod_service.get_comfy_base_url(status["pod_id"])
    ok = await runpod_service.free_comfy_memory(base_url)
    if not ok:
        raise HTTPException(502, detail="ComfyUI /free failed — check pod logs")
    return {"ok": True, "message": "GPU memory released on pod (models unloaded until next generate)."}


@router.post("/cleanup")
async def runpod_cleanup(body: dict = Body(default_factory=dict)):
    """
    Uninstall LTX workflow custom nodes via Manager; return model file paths to delete manually.
    Requires body: {"confirm": "REMOVE_LTX"}.
    """
    from backend.services.runpod_setup import cleanup_pod

    payload = body or {}
    if payload.get("confirm") != "REMOVE_LTX":
        raise HTTPException(
            400,
            detail='Send {"confirm": "REMOVE_LTX"} to confirm removal of LTX workflow setup.',
        )

    user_settings = await _get_user_settings()
    api_key = get_runpod_api_key(user_settings)
    if not api_key:
        raise HTTPException(503, detail="RunPod API key not configured")

    stored_pod_id = get_runpod_pod_id(user_settings)
    status = await runpod_service.get_pod_status(api_key, stored_pod_id)
    if not status.get("comfy_ready"):
        raise HTTPException(503, detail="ComfyUI is not ready on the pod")

    base_url = runpod_service.get_comfy_base_url(status["pod_id"])
    result = await cleanup_pod(
        base_url,
        remove_models=payload.get("remove_models", True),
        remove_nodes=payload.get("remove_nodes", True),
    )
    if not result.get("ok"):
        raise HTTPException(502, detail=result.get("message", "Cleanup failed"))
    return result


@router.get("/models-status")
async def runpod_models_status(type: str = "all"):
    """Return model download status for a specific workflow (ltx / z-turbo / all).

    Returns ``{ present: [...], missing: [...], total: N, present_count: M }``.
    """
    from backend.services.runpod_setup import assess_pod, _manifest_model_entries

    user_settings = await _get_user_settings()
    api_key = get_runpod_api_key(user_settings)
    stored_pod_id = get_runpod_pod_id(user_settings)
    if not api_key or not stored_pod_id:
        return {"present": [], "missing": _manifest_model_entries(type), "total": 0, "present_count": 0}

    status = await runpod_service.get_pod_status(api_key, stored_pod_id)
    if not status.get("comfy_ready"):
        entries = _manifest_model_entries(type if type != "all" else None)
        return {"present": [], "missing": entries, "total": len(entries), "present_count": 0}

    wf = type if type != "all" else None
    base_url = runpod_service.get_comfy_base_url(status["pod_id"])
    assessment = await assess_pod(base_url, workflow=wf)
    ms = assessment.get("models_status", {})
    present = ms.get("present", [])
    missing = ms.get("missing", [])
    return {
        "present": present,
        "missing": missing,
        "total": ms.get("total", len(present) + len(missing)),
        "present_count": len(present),
    }


@router.post("/delete-models")
async def runpod_delete_models(type: str = "all"):
    """Return file paths of models for the given workflow on the pod (manual deletion)."""
    from backend.services.runpod_setup import _manifest_model_entries

    if type not in ("ltx", "z-turbo", "ltx-img2vid", "tts", "all"):
        raise HTTPException(400, detail="type must be ltx, ltx-img2vid, z-turbo, tts, or all")

    wf = type if type != "all" else None
    entries = _manifest_model_entries(workflow=wf)
    paths = [
        f"/workspace/runpod-slim/ComfyUI/models/{e.get('folder', 'checkpoints')}/{e['filename']}"
        for e in entries
    ]

    wf_label = {"ltx": "LTX", "ltx-img2vid": "LTX img2vid", "z-turbo": "Z-turbo", "tts": "Higgs TTS", "all": "all"}[type]
    return {
        "ok": True,
        "workflow": type,
        "paths": paths,
        "message": (
            f"Delete these {wf_label} model files on the pod (RunPod file browser or terminal). "
            "ViralMint cannot remove large files via API."
        ),
    }

# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Long-form video project API."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agents.job_helper import create_job
from backend.core.task_runner import dispatch, run_longform_assemble, run_longform_generate_all, run_longform_plan
from backend.database import get_db
from backend.models.longform import LongFormAsset, LongFormProject
from backend.services import ffmpeg_service
from backend.services.longform_orchestrator import (
    attach_preview_urls,
    get_scene_segment_path,
    load_assets,
    resolve_media_url,
    save_storyboard,
    scene_audio_preview_path,
    scene_segment_path,
    scene_start_frame_path,
    storyboard_from_project,
    update_scene_in_board,
)
from backend.services.longform_planner import recompute_scene_previews

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/longform", tags=["longform"])


class AssetInput(BaseModel):
    url: str
    kind: str = "image"
    caption: Optional[str] = None


class CreateProjectBody(BaseModel):
    topic: str
    master_audio_url: str
    assets: list[AssetInput] = Field(default_factory=list)
    aspect_ratio: str = "9:16"


class UpdateStoryboardBody(BaseModel):
    scenes: list[dict]


class UpdateSceneBody(BaseModel):
    type: Optional[str] = None
    source: Optional[dict] = None
    start_s: Optional[float] = None
    end_s: Optional[float] = None
    narration_hint: Optional[str] = None


@router.post("/projects")
async def create_project(body: CreateProjectBody, db: AsyncSession = Depends(get_db)):
    audio_path = resolve_media_url(body.master_audio_url)
    if not audio_path.exists():
        raise HTTPException(400, "Master audio file not found")

    project = LongFormProject(
        topic=body.topic,
        master_audio_path=str(audio_path),
        aspect_ratio=body.aspect_ratio,
        status="draft",
    )
    db.add(project)
    await db.flush()

    for a in body.assets:
        fp = resolve_media_url(a.url)
        if not fp.exists():
            continue
        asset = LongFormAsset(
            project_id=project.id,
            kind=a.kind if a.kind in ("image", "video") else ("video" if fp.suffix.lower() in (".mp4", ".mov", ".webm") else "image"),
            file_path=str(fp),
            media_url=a.url,
            caption=a.caption,
        )
        db.add(asset)

    await db.commit()
    await db.refresh(project)
    return {"project_id": project.id, "status": project.status}


@router.post("/projects/{project_id}/plan")
async def plan_project(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LongFormProject).where(LongFormProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")

    job = await create_job("longform_plan", "local", {"project_id": project_id})
    project.status = "planning"
    await db.commit()
    dispatch(run_longform_plan(job.id, project_id, "local"))
    return {"job_id": job.id, "project_id": project_id, "status": "planning"}


@router.get("/projects/{project_id}/storyboard")
async def get_storyboard(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LongFormProject).where(LongFormProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    board = storyboard_from_project(project)
    if not board:
        return {"project_id": project_id, "status": project.status, "storyboard": None}
    attach_preview_urls(board, project_id)
    assets = await load_assets(db, project_id)
    return {
        "project_id": project_id,
        "status": project.status,
        "topic": project.topic,
        "aspect_ratio": project.aspect_ratio,
        "total_duration_s": project.total_duration_s,
        "final_video_id": project.final_video_id,
        "assets": assets,
        "storyboard": board,
    }


@router.put("/projects/{project_id}/storyboard")
async def update_storyboard(project_id: str, body: UpdateStoryboardBody, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LongFormProject).where(LongFormProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    board = storyboard_from_project(project)
    board["scenes"] = body.scenes
    assets = await load_assets(db, project_id)
    board = recompute_scene_previews(board, assets)
    attach_preview_urls(board, project_id)
    save_storyboard(project, board)
    await db.commit()
    return {"storyboard": board}


@router.put("/projects/{project_id}/scenes/{scene_id}")
async def update_scene(
    project_id: str, scene_id: str, body: UpdateSceneBody, db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(LongFormProject).where(LongFormProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    assets = await load_assets(db, project_id)
    updates = body.model_dump(exclude_none=True)
    board = await update_scene_in_board(project, scene_id, updates, assets)
    await db.commit()
    return {"scene_id": scene_id, "storyboard": board}


@router.get("/projects/{project_id}/scenes/{scene_id}/audio-preview")
async def scene_audio_preview(project_id: str, scene_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LongFormProject).where(LongFormProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    board = storyboard_from_project(project)
    scene = next((s for s in board.get("scenes", []) if s["id"] == scene_id), None)
    if not scene:
        raise HTTPException(404, "Scene not found")

    out = scene_audio_preview_path(project_id, scene_id)
    if not out.exists():
        await ffmpeg_service.slice_audio(
            Path(project.master_audio_path),
            float(scene["start_s"]),
            float(scene["end_s"]),
            out,
        )
    return FileResponse(out, media_type="audio/mpeg")


@router.get("/projects/{project_id}/scenes/{scene_id}/start-frame-preview")
async def scene_start_frame_preview(project_id: str, scene_id: str, db: AsyncSession = Depends(get_db)):
    """Serve the still image used as input (stock photo, user asset, or clip thumbnail)."""
    from fastapi.responses import RedirectResponse

    frame_path = scene_start_frame_path(project_id, scene_id)
    if frame_path.exists():
        return FileResponse(frame_path)

    result = await db.execute(select(LongFormProject).where(LongFormProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")

    board = storyboard_from_project(project)
    scene = next((s for s in board.get("scenes", []) if s["id"] == scene_id), None)
    if not scene:
        raise HTTPException(404, "Scene not found")

    src = scene.get("source") or {}
    thumb = src.get("preview_thumb_url") or ""
    if thumb.startswith("http://") or thumb.startswith("https://"):
        return RedirectResponse(thumb)

    assets = await load_assets(db, project_id)
    asset_by_id = {a["id"]: a for a in assets}
    stype = scene.get("type", "")
    aid = src.get("asset_id") or src.get("start_image_asset_id")
    if aid and aid in asset_by_id:
        path = Path(asset_by_id[aid]["file_path"])
        if path.exists():
            return FileResponse(path)

    raise HTTPException(404, "Start frame preview not available")


@router.get("/projects/{project_id}/scenes/{scene_id}/visual-preview")
async def scene_visual_preview(project_id: str, scene_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LongFormProject).where(LongFormProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")

    seg = await get_scene_segment_path(project_id, scene_id)
    if seg:
        return FileResponse(seg, media_type="video/mp4")

    board = storyboard_from_project(project)
    scene = next((s for s in board.get("scenes", []) if s["id"] == scene_id), None)
    if not scene:
        raise HTTPException(404, "Scene not found")

    url = scene.get("visual_preview_url") or ""
    if url.startswith("/api/media/"):
        path = resolve_media_url(url)
        if path.exists():
            if path.suffix.lower() in (".mp4", ".mov", ".webm"):
                return FileResponse(path, media_type="video/mp4")
            return FileResponse(path)
    raise HTTPException(404, "Visual preview not available")


@router.post("/projects/{project_id}/scenes/{scene_id}/generate")
async def generate_scene(project_id: str, scene_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LongFormProject).where(LongFormProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    job = await create_job("longform_scene", "local", {"project_id": project_id, "scene_id": scene_id})
    dispatch(run_longform_generate_all(job.id, project_id, "local", scene_ids=[scene_id]))
    return {"job_id": job.id, "scene_id": scene_id}


@router.post("/projects/{project_id}/generate-all")
async def generate_all(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LongFormProject).where(LongFormProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    job = await create_job("longform_generate", "local", {"project_id": project_id})
    project.status = "rendering"
    await db.commit()
    dispatch(run_longform_generate_all(job.id, project_id, "local"))
    return {"job_id": job.id, "project_id": project_id}


@router.post("/projects/{project_id}/assemble")
async def assemble_project(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LongFormProject).where(LongFormProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    job = await create_job("longform_assemble", "local", {"project_id": project_id})
    dispatch(run_longform_assemble(job.id, project_id, "local"))
    return {"job_id": job.id, "project_id": project_id}

# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Long-form project persistence and storyboard helpers."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models.longform import LongFormAsset, LongFormProject
from backend.services import runpod_service
from backend.services.longform_planner import recompute_scene_previews

logger = logging.getLogger(__name__)


def resolve_media_url(url: str) -> Path:
    return runpod_service.resolve_media_path(url)


def storyboard_from_project(project: LongFormProject) -> dict:
    if not project.storyboard_json:
        return {}
    return json.loads(project.storyboard_json)


def save_storyboard(project: LongFormProject, board: dict):
    project.storyboard_json = json.dumps(board)


async def load_assets(db: AsyncSession, project_id: str) -> list[dict]:
    result = await db.execute(
        select(LongFormAsset).where(LongFormAsset.project_id == project_id)
    )
    rows = result.scalars().all()
    out = []
    for r in rows:
        cat = json.loads(r.catalog_json) if r.catalog_json else {}
        out.append({
            "id": r.id,
            "kind": r.kind,
            "file_path": r.file_path,
            "media_url": r.media_url,
            "caption": r.caption,
            "catalog": cat,
        })
    return out


def scene_start_frame_path(project_id: str, scene_id: str) -> Path:
    d = settings.TMP_DIR / "longform" / project_id
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{scene_id}_start.jpg"


def save_start_frame(project_id: str, scene_id: str, source: Path) -> Path:
    """Persist the still image used as input for this scene."""
    dest = scene_start_frame_path(project_id, scene_id)
    import shutil
    shutil.copy2(str(source), str(dest))
    return dest


def attach_preview_urls(board: dict, project_id: str) -> dict:
    """Add API preview URLs to each scene."""
    for scene in board.get("scenes", []):
        sid = scene["id"]
        scene["audio_preview_url"] = f"/api/longform/projects/{project_id}/scenes/{sid}/audio-preview"
        scene["start_frame_preview_url"] = (
            f"/api/longform/projects/{project_id}/scenes/{sid}/start-frame-preview"
        )
        if scene.get("render_status") == "done":
            scene["rendered_video_url"] = (
                f"/api/longform/projects/{project_id}/scenes/{sid}/visual-preview"
            )
        # Legacy field — point at start frame before render, rendered video after
        if scene.get("render_status") == "done" and scene.get("rendered_video_url"):
            scene["visual_preview_url"] = scene["rendered_video_url"]
        elif src_thumb := (scene.get("source") or {}).get("preview_thumb_url"):
            scene["visual_preview_url"] = src_thumb
    return board


async def get_scene_segment_path(project_id: str, scene_id: str) -> Optional[Path]:
    """Path to rendered segment MP4 if exists."""
    p = settings.TMP_DIR / "longform" / project_id / f"{scene_id}.mp4"
    return p if p.exists() else None


def scene_segment_path(project_id: str, scene_id: str) -> Path:
    d = settings.TMP_DIR / "longform" / project_id
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{scene_id}.mp4"


def scene_audio_preview_path(project_id: str, scene_id: str) -> Path:
    d = settings.TMP_DIR / "longform" / project_id / "audio_previews"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{scene_id}.mp3"


async def update_scene_in_board(
    project: LongFormProject,
    scene_id: str,
    updates: dict,
    assets: list[dict],
) -> dict:
    board = storyboard_from_project(project)
    for scene in board.get("scenes", []):
        if scene["id"] == scene_id:
            if "source" in updates and isinstance(updates["source"], dict):
                scene["source"] = {**(scene.get("source") or {}), **updates["source"]}
                if scene.get("type") == "ltx" and "stock_image_query" in updates["source"]:
                    scene["source"].pop("stock_image_download_url", None)
                    scene["source"].pop("preview_thumb_url", None)
                updates = {k: v for k, v in updates.items() if k != "source"}
            scene.update(updates)
            if updates.get("type") == "ltx" or scene.get("type") == "ltx":
                scene["render_status"] = "pending"
                scene["rendered_video_url"] = None
                scene["visual_status"] = "placeholder"
            elif "type" in updates or "source" in updates:
                scene["render_status"] = "pending"
                scene["rendered_video_url"] = None
            break
    board = recompute_scene_previews(board, assets)
    attach_preview_urls(board, project.id)
    save_storyboard(project, board)
    return board

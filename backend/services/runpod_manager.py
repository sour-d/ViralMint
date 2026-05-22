# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Shared ComfyUI-Manager HTTP helpers for RunPod pods."""
from __future__ import annotations

import logging
from typing import Any, Optional

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
    """Returns (success, status_code, path_tried)."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        for url in _urls(base_url, path):
            try:
                resp = await client.post(url, json=payload)
                if resp.is_success:
                    return True, resp.status_code, path
                if resp.status_code == 403:
                    return False, 403, path
            except Exception as exc:
                logger.debug("POST %s failed: %s", path, exc)
    return False, 0, path


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
    if queue.get("is_processing") or in_progress > 0:
        return f"ComfyUI-Manager queue: {done}/{total} done, installing…"
    if done < total:
        return f"ComfyUI-Manager queue: {done}/{total} tasks pending"
    return None


async def queue_start(base_url: str) -> bool:
    return await get_ok(base_url, "/manager/queue/start")


async def comfy_get(base_url: str, path: str, *, timeout: float = 30) -> Optional[Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.get(f"{base_url.rstrip('/')}{path}")
            if resp.is_success:
                return resp.json()
        except Exception:
            pass
    return None

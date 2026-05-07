# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""
Agent 2: Multi-platform scout + virality scoring.
Runs all platforms in parallel via asyncio.gather.
If one platform fails, logs warning + continues with others.
"""
import asyncio
import json
import logging
from datetime import datetime

from sqlalchemy import select
from backend.database import AsyncSessionLocal
from backend.models.scout_result import ScoutResult
from backend.models.user_settings import UserSettings
from backend.core.ws_manager import ws_manager
from backend.agents.job_helper import update_job_status
from backend.config import settings

logger = logging.getLogger(__name__)


PLATFORM_LIMITS = {
    "youtube": 50,
    "tiktok": 30,
    "douyin": 30,
}

# Default limit for any platform not listed above
DEFAULT_SEARCH_LIMIT = 15

# Platforms that can be scouted via yt-dlp search (no API key needed)
# Maps platform name → yt-dlp search prefix
# Note: bilisearch requires cookies (412), so Bilibili falls back to ytsearch
YTDLP_SEARCH_PLATFORMS = {
    "soundcloud": "scsearch",
    "niconico": "nicosearch",
}

# Universal fallback: search YouTube for "{platform} {niche}" content
# This catches Bilibili, Instagram, Vimeo, etc. — surprisingly effective
# because creators often cross-post or discuss other platforms' content
FALLBACK_SEARCH_PREFIX = "ytsearch"


def compute_virality_score(video: dict) -> float:
    """
    Virality score 0-100.
    Weights: engagement rate 30%, view velocity (VPH) 25%, recency 20%,
             raw views 15%, raw likes 10%.
    Also computes views_per_hour and outlier_score as side data on the dict.
    """
    likes = max(video.get("likes", 0), 0)
    views = max(video.get("views", 1), 1)
    comments = max(video.get("comments", 0), 0)

    upload_date = video.get("upload_date")
    if upload_date and isinstance(upload_date, datetime):
        hours_old = max((datetime.utcnow() - upload_date).total_seconds() / 3600, 1)
        days_old = max(hours_old / 24, 1)
    else:
        hours_old = 720  # assume 30 days
        days_old = 30

    engagement_rate = (likes + comments * 2) / views
    recency_bonus = 1.0 / (1 + days_old / 30)
    views_score = min(views / 1_000_000, 1.0)
    likes_score = min(likes / 100_000, 1.0)

    # View velocity — views per hour, normalized (10K VPH = max score)
    vph = views / hours_old
    vph_score = min(vph / 10_000, 1.0)

    # Store VPH on the dict for DB storage
    video["views_per_hour"] = round(vph, 1)

    # Outlier score — how many x above channel average
    channel_avg = video.get("channel_avg_views")
    if not channel_avg or channel_avg < 1:
        subs = video.get("subscriber_count", 0) or 0
        channel_avg = max(subs * 0.03, 100) if subs > 0 else None
    if channel_avg and channel_avg > 0:
        video["outlier_score"] = round(views / channel_avg, 1)

    raw = (
        engagement_rate * 0.30
        + vph_score * 0.25
        + recency_bonus * 0.20
        + views_score * 0.15
        + likes_score * 0.10
    )
    return round(min(raw * 100, 100.0), 2)


class ScoutAgent:
    async def run(
        self,
        job_id: str,
        niche: str,
        platforms: list[str],
        user_id: str = "local",
    ):
        """Run scout across all specified platforms in parallel."""
        logger.info("SCOUT START | job=%s niche=%r platforms=%s", job_id[:8], niche, platforms)
        await update_job_status(job_id, "running", progress_pct=0, current_step="Starting scout...")
        await ws_manager.send_progress(job_id, 0, "Starting scout...", user_id)

        # Load user settings for credentials
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            result = await db.execute(
                select(UserSettings).where(UserSettings.user_id == user_id)
            )
            user_settings = result.scalar_one_or_none()

        # Build platform tasks
        tasks = []
        for platform in platforms:
            tasks.append(self._scout_platform(platform, niche, user_settings))

        # Run all in parallel
        platform_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect all results, with AI-assisted retry for failures/empty results
        all_results = []
        for i, result in enumerate(platform_results):
            platform = platforms[i]
            if isinstance(result, Exception):
                logger.warning(f"Scout failed for {platform}: {result}")
                await ws_manager.send_constraint_warning(
                    constraint=f"{platform}_scout",
                    message=f"Scout failed for {platform}: {result}",
                    severity="warning",
                    user_id=user_id,
                )
                # AI fallback: try raw HTTP search when library-based approach throws
                try:
                    fallback = await self._ai_raw_search_fallback(platform, niche, user_settings)
                    if fallback:
                        logger.info(f"AI raw search fallback recovered {len(fallback)} results for {platform}")
                        result = fallback
                    else:
                        continue
                except Exception as fb_err:
                    logger.debug(f"AI raw search fallback failed for {platform}: {fb_err}")
                    continue

            # AI-assisted retry: if platform returned 0 results, refine search terms
            if result is not None and len(result) == 0:
                try:
                    from backend.core.ai_retry import ai_refine_search
                    refined_niche = await ai_refine_search(platform, niche, user_settings)
                    if refined_niche:
                        logger.info(f"Retrying {platform} scout with refined niche: '{refined_niche}'")
                        await ws_manager.send_progress(job_id, 0, f"Refining search for {platform}...", user_id)
                        retry_result = await self._scout_platform(platform, refined_niche, user_settings)
                        if retry_result and not isinstance(retry_result, Exception):
                            result = retry_result
                            logger.info(f"AI-refined search found {len(result)} results on {platform}")
                except Exception as retry_err:
                    logger.debug(f"AI search refinement retry failed for {platform}: {retry_err}")

            if result:
                all_results.extend(result)

            pct = ((i + 1) / len(platforms)) * 80
            await ws_manager.send_progress(job_id, pct, f"Scouted {platform}", user_id)

        logger.info("SCOUT collected %d raw results from %d platforms", len(all_results), len(platforms))

        # Enrich YouTube results with real outlier detection (batch channel baselines)
        await self._enrich_with_outlier_scores(all_results, platforms, user_settings)

        # Score all results (now with real channel_avg_views populated)
        for r in all_results:
            r["virality_score"] = compute_virality_score(r)

        # Sort by virality
        all_results.sort(key=lambda r: r["virality_score"], reverse=True)

        # Save to DB
        await ws_manager.send_progress(job_id, 90, "Saving results...", user_id)
        saved_results = await self._save_results(all_results, job_id, niche, user_id)

        # If all results were duplicates, fetch existing results for this niche to show the user
        results_to_send = saved_results
        if not saved_results and all_results:
            results_to_send = await self._fetch_existing_results(niche, user_id, limit=50)

        # Send results over WS grouped by platform
        for platform in platforms:
            platform_items = [r for r in results_to_send if r["platform"] == platform]
            if platform_items:
                await ws_manager.send({
                    "type": "scout_results",
                    "job_id": job_id,
                    "platform": platform,
                    "total": len(platform_items),
                    "results": platform_items,
                }, user_id)

        # Complete — report both total found and new (non-duplicate) count
        new_count = len(saved_results)
        total_count = len(all_results)
        if new_count == total_count:
            step_msg = f"Found {total_count} results"
        elif new_count == 0:
            step_msg = f"Found {total_count} results (all previously scouted)"
        else:
            step_msg = f"Found {total_count} results ({new_count} new)"

        await update_job_status(
            job_id, "success",
            progress_pct=100,
            current_step=step_msg,
            output_data={"total_results": total_count, "new_results": new_count},
        )
        await ws_manager.send({
            "type": "job_complete",
            "job_id": job_id,
            "result": {"total_results": total_count, "new_results": new_count},
        }, user_id)

    async def _scout_platform(self, platform: str, niche: str, user_settings) -> list[dict]:
        """Scout a single platform. Keys are BYOK (per-user → .env fallback)."""
        from backend.core.api_keys import get_youtube_api_key
        logger.info("SCOUT platform=%s | niche=%r", platform, niche)
        if platform == "youtube":
            youtube_key = get_youtube_api_key(user_settings)
            if not youtube_key:
                logger.warning("YouTube API key not configured — skipping YouTube scout")
                return []
            from backend.services.youtube_scout import search_youtube
            return await search_youtube(niche, youtube_key, PLATFORM_LIMITS["youtube"])

        elif platform == "tiktok":
            # Try TikHub API first (env key)
            if settings.TIKHUB_API_KEY:
                from backend.services.tikhub_client import search_tiktok
                return await search_tiktok(niche, settings.TIKHUB_API_KEY, PLATFORM_LIMITS["tiktok"])
            # Fall back to user's session cookie
            from backend.core.crypto import decrypt_safe
            cookie = ""
            if user_settings and user_settings.tiktok_cookie_encrypted:
                cookie = decrypt_safe(user_settings.tiktok_cookie_encrypted)
            if cookie:
                from backend.services.tiktok_downloader_svc import scout_tiktok_trending
                return await scout_tiktok_trending(cookie, niche, PLATFORM_LIMITS["tiktok"])
            logger.warning("TikTok: no API key or cookie configured")
            return []

        elif platform == "douyin":
            if settings.TIKHUB_API_KEY:
                from backend.services.tikhub_client import search_douyin
                return await search_douyin(niche, settings.TIKHUB_API_KEY, PLATFORM_LIMITS["douyin"])
            from backend.core.crypto import decrypt_safe
            cookie = ""
            if user_settings and user_settings.douyin_cookie_encrypted:
                cookie = decrypt_safe(user_settings.douyin_cookie_encrypted)
            if cookie:
                from backend.services.tiktok_downloader_svc import scout_douyin_trending
                return await scout_douyin_trending(cookie, niche, PLATFORM_LIMITS["douyin"])
            logger.warning("Douyin: no API key or cookie configured")
            return []

        else:
            # Generic fallback: use yt-dlp search if the platform supports it
            return await self._scout_via_ytdlp_search(platform, niche)

    async def _ai_raw_search_fallback(self, platform: str, niche: str, user_settings) -> list[dict]:
        """
        AI-powered fallback: when the normal scout path fails (library error, API change),
        do a raw HTTP search to the platform's public search endpoint and let AI parse
        the response. Works for any platform without needing API keys.
        """
        import httpx
        from backend.core.ai_retry import ai_parse_api_response

        # Platform-specific public search URLs (no auth needed, HTML/JSON responses)
        search_urls = {
            "youtube": f"https://www.youtube.com/results?search_query={niche}&sp=CAMSAhAB",
            "tiktok": f"https://www.tiktok.com/api/search/general/full/?keyword={niche}&search_source=normal_search",
        }

        url = search_urls.get(platform)
        if not url:
            return []

        try:
            from backend.core.http_utils import get_default_headers
            headers = get_default_headers()
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code != 200:
                    logger.debug(f"Raw search fallback got {resp.status_code} for {platform}")
                    return []
                raw_text = resp.text[:6000]

            logger.info(f"AI raw search fallback: fetched {len(raw_text)} chars from {platform}")
            ai_results = await ai_parse_api_response(raw_text, platform, niche, user_settings)

            if not ai_results:
                return []

            # Convert AI output to our standard format
            results = []
            for item in ai_results:
                video_id = item.get("aweme_id") or item.get("video_id", "")
                if not video_id:
                    continue
                results.append({
                    "platform": platform,
                    "video_id": video_id,
                    "video_url": item.get("video_url") or self._build_video_url(platform, video_id, item),
                    "embed_url": None,
                    "title": (item.get("desc") or item.get("title") or "")[:200],
                    "description": item.get("desc") or item.get("description") or "",
                    "author": item.get("author", {}).get("nickname") or item.get("author", {}).get("unique_id") or "Unknown",
                    "author_url": "",
                    "thumbnail_url": "",
                    "views": item.get("statistics", {}).get("play_count", 0) or item.get("views", 0),
                    "likes": item.get("statistics", {}).get("digg_count", 0) or item.get("likes", 0),
                    "comments": item.get("statistics", {}).get("comment_count", 0) or item.get("comments", 0),
                    "shares": item.get("statistics", {}).get("share_count", 0) or item.get("shares", 0),
                    "duration_seconds": item.get("video", {}).get("duration") or item.get("duration_seconds"),
                    "upload_date": None,
                })

            return results

        except Exception as e:
            logger.debug(f"AI raw search fallback error for {platform}: {e}")
            return []

    @staticmethod
    def _build_video_url(platform: str, video_id: str, item: dict) -> str:
        """Build a video URL from platform + video_id."""
        if platform == "youtube":
            return f"https://youtube.com/watch?v={video_id}"
        elif platform == "tiktok":
            author = item.get("author", {}).get("unique_id", "")
            if author:
                return f"https://www.tiktok.com/@{author}/video/{video_id}"
            return f"https://www.tiktok.com/video/{video_id}"
        elif platform == "douyin":
            return f"https://www.douyin.com/video/{video_id}"
        return ""

    async def _enrich_with_outlier_scores(self, results: list[dict], platforms: list[str], user_settings) -> None:
        """
        Batch-fetch channel baselines for YouTube results and compute real outlier scores.
        This replaces the naive subscriber-based heuristic with actual median view data.
        """
        if "youtube" not in platforms:
            return

        youtube_results = [r for r in results if r.get("platform") == "youtube"]
        if not youtube_results:
            return

        from backend.core.api_keys import get_youtube_api_key
        api_key = get_youtube_api_key(user_settings)
        if not api_key:
            return

        # Extract unique channel IDs from author_url
        import re
        channel_ids = set()
        for r in youtube_results:
            match = re.search(r'/channel/(UC[\w-]+)', r.get("author_url", ""))
            if match:
                channel_ids.add(match.group(1))

        if not channel_ids:
            return

        # Limit to 15 unique channels to avoid excessive API calls
        channel_ids = list(channel_ids)[:15]

        try:
            from backend.services.outlier_detection_service import (
                batch_get_channel_baselines,
                enrich_scout_results_with_outliers,
            )
            baselines = await batch_get_channel_baselines(channel_ids, api_key)
            if baselines:
                enrich_scout_results_with_outliers(youtube_results, baselines)
                logger.info("SCOUT enriched %d YouTube results with outlier scores from %d channels",
                           len(youtube_results), len(baselines))
        except Exception as e:
            logger.warning(f"Outlier enrichment failed (non-fatal): {e}")

    async def _scout_via_ytdlp_search(self, platform: str, niche: str) -> list[dict]:
        """
        Generic scout using yt-dlp's built-in search extractors.
        Works for SoundCloud, Niconico natively.
        For all other platforms, searches YouTube for "{platform} {niche}" content
        which is surprisingly effective since creators cross-post and discuss content.
        """
        import asyncio

        search_prefix = YTDLP_SEARCH_PLATFORMS.get(platform)
        if search_prefix:
            search_niche = niche
        else:
            # Fallback: search YouTube for content about/from this platform
            search_prefix = FALLBACK_SEARCH_PREFIX
            search_niche = f"{platform} {niche}"
            logger.info(f"No native search for '{platform}' — searching YouTube for '{search_niche}'")

        limit = PLATFORM_LIMITS.get(platform, DEFAULT_SEARCH_LIMIT)
        search_query = f"{search_prefix}{limit}:{search_niche}"

        def _search():
            import yt_dlp
            opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": True,
                "socket_timeout": 20,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(search_query, download=False)

        try:
            info = await asyncio.to_thread(_search)
        except Exception as e:
            logger.warning(f"yt-dlp search failed for {platform} ({search_prefix}): {e}")
            return []

        if not info:
            return []

        entries = info.get("entries") or []
        results = []
        for entry in entries:
            if not entry:
                continue

            video_url = entry.get("url") or entry.get("webpage_url", "")
            video_id = entry.get("id", "")

            # Build full URL if needed
            if video_url and not video_url.startswith("http"):
                video_url = entry.get("webpage_url", video_url)

            # Parse upload_date
            upload_date = None
            raw_date = entry.get("upload_date")
            if raw_date and len(str(raw_date)) == 8:
                try:
                    upload_date = datetime.strptime(str(raw_date), "%Y%m%d")
                except ValueError:
                    pass

            results.append({
                "platform": platform,
                "video_id": video_id,
                "video_url": video_url,
                "title": entry.get("title", ""),
                "description": (entry.get("description") or "")[:500],
                "author": entry.get("uploader") or entry.get("channel", ""),
                "author_url": entry.get("uploader_url") or entry.get("channel_url", ""),
                "thumbnail_url": entry.get("thumbnail") or (entry.get("thumbnails", [{}])[0].get("url") if entry.get("thumbnails") else None),
                "views": entry.get("view_count", 0) or 0,
                "likes": entry.get("like_count", 0) or 0,
                "comments": entry.get("comment_count", 0) or 0,
                "shares": 0,
                "duration_seconds": entry.get("duration"),
                "upload_date": upload_date,
            })

        logger.info(f"yt-dlp search for '{niche}' on {platform}: found {len(results)} results")
        return results

    async def _save_results(
        self, results: list[dict], job_id: str, niche: str, user_id: str
    ) -> list[dict]:
        """Save scout results to DB, skipping duplicates by video_id+platform."""
        logger.debug("SCOUT saving %d results to DB (niche=%r)", len(results), niche)
        saved = []
        async with AsyncSessionLocal() as db:
            # Load existing video_ids to deduplicate
            existing_result = await db.execute(
                select(ScoutResult.video_id, ScoutResult.platform)
                .where(ScoutResult.user_id == user_id)
            )
            existing = {(row[0], row[1]) for row in existing_result.fetchall()}

            for r in results:
                key = (r["video_id"], r["platform"])
                if key in existing:
                    continue
                existing.add(key)
                sr = ScoutResult(
                    user_id=user_id,
                    job_id=job_id,
                    platform=r["platform"],
                    video_id=r["video_id"],
                    video_url=r["video_url"],
                    embed_url=r.get("embed_url"),
                    title=r.get("title"),
                    description=r.get("description"),
                    author=r.get("author"),
                    author_url=r.get("author_url"),
                    thumbnail_url=r.get("thumbnail_url"),
                    views=r.get("views", 0),
                    likes=r.get("likes", 0),
                    comments=r.get("comments", 0),
                    shares=r.get("shares", 0),
                    duration_seconds=r.get("duration_seconds"),
                    upload_date=r.get("upload_date"),
                    virality_score=r.get("virality_score", 0),
                    views_per_hour=r.get("views_per_hour"),
                    outlier_score=r.get("outlier_score"),
                    subscriber_count=r.get("subscriber_count"),
                    channel_avg_views=r.get("channel_avg_views"),
                    niche=niche,
                )
                db.add(sr)
                await db.flush()
                saved.append({
                    "id": sr.id,
                    "platform": sr.platform,
                    "video_id": sr.video_id,
                    "video_url": sr.video_url,
                    "embed_url": sr.embed_url,
                    "title": sr.title,
                    "author": sr.author,
                    "author_url": sr.author_url,
                    "thumbnail_url": sr.thumbnail_url,
                    "views": sr.views,
                    "likes": sr.likes,
                    "comments": sr.comments,
                    "shares": sr.shares,
                    "duration_seconds": sr.duration_seconds,
                    "upload_date": sr.upload_date.isoformat() if sr.upload_date else None,
                    "virality_score": sr.virality_score,
                    "views_per_hour": sr.views_per_hour,
                    "outlier_score": sr.outlier_score,
                })
            await db.commit()
        logger.info("SCOUT saved %d new results (skipped %d duplicates)", len(saved), len(results) - len(saved))
        return saved

    async def _fetch_existing_results(self, niche: str, user_id: str, limit: int = 50) -> list[dict]:
        """Fetch existing scout results for a niche (used when all new results are duplicates)."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ScoutResult)
                .where(ScoutResult.user_id == user_id, ScoutResult.niche == niche)
                .order_by(ScoutResult.created_at.desc())
                .limit(limit)
            )
            results = result.scalars().all()
            return [
                {
                    "id": sr.id,
                    "platform": sr.platform,
                    "video_id": sr.video_id,
                    "video_url": sr.video_url,
                    "embed_url": sr.embed_url,
                    "title": sr.title,
                    "author": sr.author,
                    "author_url": sr.author_url,
                    "thumbnail_url": sr.thumbnail_url,
                    "views": sr.views,
                    "likes": sr.likes,
                    "comments": sr.comments,
                    "shares": sr.shares,
                    "duration_seconds": sr.duration_seconds,
                    "upload_date": sr.upload_date.isoformat() if sr.upload_date else None,
                    "virality_score": sr.virality_score,
                    "views_per_hour": sr.views_per_hour,
                    "outlier_score": sr.outlier_score,
                }
                for sr in results
            ]

# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""FastAPI application factory."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from backend.config import settings
from backend.core.logging_config import setup_logging
from backend.core import plugins
from backend.database import init_db

# Pillow 11 removed the legacy resampling constants (Image.ANTIALIAS, .BICUBIC, ...).
# moviepy 1.0.3 still uses Image.ANTIALIAS internally. Re-add the constants as
# aliases of the new Resampling enum so resize/clip operations don't crash.
# Drop this shim if/when we move to moviepy 2.x.
try:
    from PIL import Image as _PIL_Image
    if not hasattr(_PIL_Image, "ANTIALIAS"):
        _PIL_Image.ANTIALIAS = _PIL_Image.Resampling.LANCZOS
        _PIL_Image.BICUBIC = _PIL_Image.Resampling.BICUBIC
        _PIL_Image.LINEAR = _PIL_Image.Resampling.BILINEAR
        _PIL_Image.NEAREST = _PIL_Image.Resampling.NEAREST
except Exception:
    pass
from backend.api import anime_lofi, runpod as runpod_router

# Initialize logging before anything else
setup_logging(debug=settings.DEBUG)


async def _cleanup_orphaned_jobs():
    """Mark jobs stuck in pending/running as failed — they were lost on server restart."""
    from datetime import datetime
    from sqlalchemy import select, update
    from backend.database import AsyncSessionLocal
    from backend.models.job import Job
    import logging
    logger = logging.getLogger(__name__)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Job).where(Job.status.in_(["pending", "running"]))
        )
        orphans = result.scalars().all()
        if orphans:
            for job in orphans:
                job.status = "failed"
                job.error_message = "Server restarted while job was in progress"
                job.completed_at = datetime.utcnow()
            await db.commit()
            logger.info(f"Cleaned up {len(orphans)} orphaned job(s)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup + shutdown lifecycle."""
    await init_db()

    try:
        await _cleanup_orphaned_jobs()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Orphaned job cleanup failed: {e}")

    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="ViralMint API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.DEBUG else None,
        redoc_url=None,
    )

    # CORS — allow frontend dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_URL, "http://localhost:5173", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register API routers
    app.include_router(anime_lofi.router, prefix="/api")
    app.include_router(runpod_router.router, prefix="/api")

    # Load proprietary overlay (no-op if not installed) and register plugin routers.
    overlay = plugins.load_overlay()
    if overlay:
        import logging
        logging.getLogger(__name__).info(f"Loaded overlay package: {overlay}")
    for plugin_router in plugins.get_routers():
        app.include_router(plugin_router, prefix="/api")

    # Serve built frontend (production) — SPA with catch-all fallback.
    import os as _os
    dist = Path(_os.environ.get("VIRALMINT_FRONTEND_DIST", "frontend/dist"))
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=str(dist / "assets")), name="static_assets")

        @app.get("/{full_path:path}")
        async def serve_spa(request: Request, full_path: str):
            file_path = dist / full_path
            if full_path and file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(dist / "index.html")

    return app


app = create_app()

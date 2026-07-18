# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event, text
from backend.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args={"check_same_thread": False},  # SQLite only
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable WAL mode for concurrent reads + faster writes."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")   # Wait up to 5s on lock contention
    cursor.execute("PRAGMA cache_size=-64000")   # 64MB cache
    cursor.execute("PRAGMA temp_store=MEMORY")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Create all tables. Called once at startup from run.py."""
    from backend.models import user_settings, job  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _add_column_if_missing(conn, "user_settings", "ai_provider", "VARCHAR(20)")
        await _add_column_if_missing(conn, "user_settings", "ai_model", "VARCHAR(100)")
        await _add_column_if_missing(conn, "user_settings", "ai_api_key_encrypted", "TEXT")
        await _add_column_if_missing(conn, "user_settings", "runpod_api_key_encrypted", "TEXT")
        await _add_column_if_missing(conn, "user_settings", "runpod_pod_id", "VARCHAR(64)")
        await _add_column_if_missing(conn, "jobs", "job_type", "VARCHAR(64)")
        await _add_column_if_missing(conn, "jobs", "current_step", "VARCHAR(200)")
        await _add_column_if_missing(conn, "jobs", "progress_pct", "INTEGER")
        await _add_column_if_missing(conn, "jobs", "input_json", "TEXT")
        await _add_column_if_missing(conn, "jobs", "output_data", "TEXT")
        await _add_column_if_missing(conn, "jobs", "error_message", "TEXT")

    await _migrate_deprecated_models()
    await _cleanup_zombie_jobs()


async def _cleanup_zombie_jobs():
    """Mark jobs stuck at running/pending as failed — they can't recover after restart."""
    try:
        async with AsyncSessionLocal() as db:
            from backend.models.job import Job
            from sqlalchemy import update
            result = await db.execute(
                update(Job)
                .where(Job.status.in_(["running", "pending"]))
                .values(status="failed", error_message="Server restarted — job did not complete")
            )
            if result.rowcount > 0:
                logger.warning(f"Marked {result.rowcount} zombie jobs as failed from previous session")
            await db.commit()
    except Exception as e:
        logger.warning(f"Zombie job cleanup failed: {e}")


async def _migrate_deprecated_models():
    """Replace deprecated model slugs with their current equivalents."""
    try:
        async with AsyncSessionLocal() as db:
            from backend.models.user_settings import UserSettings
            from sqlalchemy import update
            result = await db.execute(
                update(UserSettings)
                .where(UserSettings.ai_model == "openrouter/owl-alpha")
                .values(ai_model="openrouter/free")
            )
            if result.rowcount > 0:
                logger.info(f"Migrated {result.rowcount} user(s) from openrouter/owl-alpha to openrouter/free")
            await db.commit()
    except Exception as e:
        logger.warning(f"Model migration failed: {e}")


async def _add_column_if_missing(conn, table: str, column: str, col_type: str):
    """SQLite-safe column addition — no-op if already exists."""
    try:
        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
    except Exception:
        pass  # Column already exists — expected for idempotent migrations

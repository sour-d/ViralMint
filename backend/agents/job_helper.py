# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Utility for creating job records in the database."""
import json
from backend.database import AsyncSessionLocal
from backend.models.job import Job


async def create_job(job_type: str, user_id: str = "local", input_data: dict = None) -> Job:
    """Create a new Job row and return it."""
    async with AsyncSessionLocal() as db:
        job = Job(
            user_id=user_id,
            job_type=job_type,
            status="pending",
            input_json=json.dumps(input_data) if input_data else None,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        return job


async def update_job_status(
    job_id: str,
    status: str,
    progress_pct: float = None,
    current_step: str = None,
    error_message: str = None,
    output_data: dict = None,
):
    """Update a job's status and optional fields."""
    from datetime import datetime
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            return
        job.status = status
        if progress_pct is not None:
            # Prevent progress regression (e.g. 95% → 50%) unless explicitly restarting
            is_restart = status == "running" and progress_pct == 0
            if is_restart or progress_pct >= (job.progress_pct or 0):
                job.progress_pct = progress_pct
        if current_step is not None:
            job.current_step = current_step
        if error_message is not None:
            job.error_message = error_message
        if output_data is not None:
            job.output_json = json.dumps(output_data)
        if status == "running" and not job.started_at:
            job.started_at = datetime.utcnow()
        if status in ("success", "failed", "cancelled"):
            job.completed_at = datetime.utcnow()
        await db.commit()

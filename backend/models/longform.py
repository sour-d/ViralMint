# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Long-form video project models."""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, String, Text, Float, DateTime, ForeignKey

from backend.database import Base


class LongFormProject(Base):
    __tablename__ = "longform_projects"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), default="local", index=True)
    topic = Column(Text, nullable=False)
    master_audio_path = Column(Text, nullable=False)
    aspect_ratio = Column(String(10), default="9:16")
    status = Column(String(30), default="draft", index=True)
    # draft | planning | storyboard_ready | rendering | done | failed
    total_duration_s = Column(Float, nullable=True)
    narrative_json = Column(Text, nullable=True)
    storyboard_json = Column(Text, nullable=True)
    final_video_id = Column(String(36), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LongFormAsset(Base):
    __tablename__ = "longform_assets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id = Column(String(36), ForeignKey("longform_projects.id"), index=True)
    kind = Column(String(20), nullable=False)  # image | video
    file_path = Column(Text, nullable=False)
    media_url = Column(Text, nullable=False)
    caption = Column(Text, nullable=True)
    catalog_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

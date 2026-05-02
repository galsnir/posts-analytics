"""ORM models."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Post(Base):
    """A single versioned post row.

    A "post" in the business sense is identified by ``(post_id, topic)``; the
    same logical post may appear with multiple ``version`` rows, and even
    multiple rows for the same ``version`` (the source data is not strictly
    deduplicated). Only the latest version per post is considered the current
    state, with ties on ``version`` broken by the most recent ``timestamp``.

    Missing numeric values are stored as ``-1`` (per the source data
    convention) and treated as ``0`` in aggregations.
    """

    __tablename__ = "posts"
    __table_args__ = (
        Index("ix_posts_lookup", "post_id", "topic", "version", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    likes: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)
    shares: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)
    comments: Mapped[int] = mapped_column(Integer, nullable=False, default=-1)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)

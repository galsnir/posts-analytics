"""Pydantic response models."""
from __future__ import annotations

from pydantic import BaseModel, Field


class TopicStats(BaseModel):
    topic: str
    num_posts: int = Field(..., description="Number of distinct posts (latest version) on this topic.")
    total_likes: int = Field(..., description="Sum of likes across latest versions; missing values (-1) count as 0.")
    total_shares: int
    total_comments: int


class StatsResponse(BaseModel):
    topics: list[TopicStats]

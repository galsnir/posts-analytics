"""Aggregation logic for the /stats endpoint."""
from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import Post
from app.schemas import TopicStats


def _zero_if_missing(column):
    """Treat the sentinel value ``-1`` as ``0`` when summing."""
    return case((column == -1, 0), else_=column)


def compute_topic_stats(session: Session) -> list[TopicStats]:
    """Return per-topic aggregate stats using only the latest version of each post.

    A "post" is uniquely identified by ``(post_id, topic)``. For each such
    pair we keep the row with the highest ``version`` (ties broken by the
    most recent ``timestamp``) and aggregate per topic.
    """

    # Latest row per (post_id, topic): use a window function so it works on
    # any SQL backend that supports them (e.g. Postgres, MySQL 8+).
    row_number = func.row_number().over(
        partition_by=(Post.post_id, Post.topic),
        order_by=(Post.version.desc(), Post.timestamp.desc()),
    ).label("rn")

    ranked = select(
        Post.post_id,
        Post.topic,
        Post.likes,
        Post.shares,
        Post.comments,
        row_number,
    ).subquery("ranked")

    latest = (
        select(
            ranked.c.topic.label("topic"),
            ranked.c.likes.label("likes"),
            ranked.c.shares.label("shares"),
            ranked.c.comments.label("comments"),
        )
        .where(ranked.c.rn == 1)
        .subquery("latest")
    )

    stmt = (
        select(
            latest.c.topic,
            func.count().label("num_posts"),
            func.coalesce(func.sum(_zero_if_missing(latest.c.likes)), 0).label("total_likes"),
            func.coalesce(func.sum(_zero_if_missing(latest.c.shares)), 0).label("total_shares"),
            func.coalesce(func.sum(_zero_if_missing(latest.c.comments)), 0).label("total_comments"),
        )
        .group_by(latest.c.topic)
        .order_by(latest.c.topic)
    )

    rows = session.execute(stmt).all()
    return [
        TopicStats(
            topic=row.topic,
            num_posts=int(row.num_posts),
            total_likes=int(row.total_likes),
            total_shares=int(row.total_shares),
            total_comments=int(row.total_comments),
        )
        for row in rows
    ]

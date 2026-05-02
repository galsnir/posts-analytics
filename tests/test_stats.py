"""End-to-end tests for the /stats endpoint.

The fixtures bootstrap a real Postgres instance (in a Docker container),
create a fresh schema, and load the CSV through the same loader the app
ships with. Then we hit the API via FastAPI's TestClient.
"""
from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.loader import load_csv
from app.models import Post


# Hardcoded expected aggregates — independently computed from the CSV by
# taking, per (post_id, topic), the row with the highest (version, timestamp)
# and treating -1 as 0 in sums.
EXPECTED_TOPIC_STATS = {
    "finance": {"num_posts": 8, "total_likes": 259, "total_shares": 96, "total_comments": 21},
    "health":  {"num_posts": 10, "total_likes": 159, "total_shares": 181, "total_comments": 68},
    "news":    {"num_posts": 11, "total_likes": 295, "total_shares": 127, "total_comments": 62},
    "sports":  {"num_posts": 6, "total_likes": 55,  "total_shares": 77,  "total_comments": 66},
    "tech":    {"num_posts": 6, "total_likes": 182, "total_shares": 107, "total_comments": 55},
}


def test_stats_endpoint_returns_expected_aggregates(
    db_session: Session, client: TestClient, csv_path
) -> None:
    inserted = load_csv(db_session, csv_path)
    assert inserted == 50

    response = client.get("/stats")
    assert response.status_code == 200

    payload = response.json()
    assert "topics" in payload
    by_topic = {t["topic"]: t for t in payload["topics"]}

    assert set(by_topic) == set(EXPECTED_TOPIC_STATS), (
        f"Unexpected topic set in response: {sorted(by_topic)}"
    )

    for topic, expected in EXPECTED_TOPIC_STATS.items():
        actual = by_topic[topic]
        for field, value in expected.items():
            assert actual[field] == value, (
                f"{topic}.{field}: expected {value}, got {actual[field]}"
            )


def test_only_latest_version_is_used(db_session: Session, client: TestClient) -> None:
    """An older version with high counts must be ignored in favour of the newer one."""
    db_session.add_all([
        Post(post_id=1, topic="alpha", likes=1000, shares=1000, comments=1000,
             version=1, timestamp=datetime(2024, 1, 1)),
        Post(post_id=1, topic="alpha", likes=5, shares=7, comments=9,
             version=2, timestamp=datetime(2024, 2, 1)),
    ])
    db_session.commit()

    resp = client.get("/stats")
    assert resp.status_code == 200
    topics = {t["topic"]: t for t in resp.json()["topics"]}

    assert topics["alpha"] == {
        "topic": "alpha",
        "num_posts": 1,
        "total_likes": 5,
        "total_shares": 7,
        "total_comments": 9,
    }


def test_minus_one_is_treated_as_missing(db_session: Session, client: TestClient) -> None:
    """-1 sentinel values must contribute 0 to the sums but still count the post."""
    db_session.add_all([
        Post(post_id=10, topic="beta", likes=-1, shares=-1, comments=-1,
             version=1, timestamp=datetime(2024, 1, 1)),
        Post(post_id=11, topic="beta", likes=4, shares=-1, comments=8,
             version=1, timestamp=datetime(2024, 1, 2)),
    ])
    db_session.commit()

    resp = client.get("/stats")
    topics = {t["topic"]: t for t in resp.json()["topics"]}

    assert topics["beta"] == {
        "topic": "beta",
        "num_posts": 2,
        "total_likes": 4,
        "total_shares": 0,
        "total_comments": 8,
    }


def test_same_post_id_across_topics_counted_separately(
    db_session: Session, client: TestClient
) -> None:
    """A given post_id used under two topics counts once per topic."""
    db_session.add_all([
        Post(post_id=42, topic="x", likes=1, shares=2, comments=3,
             version=1, timestamp=datetime(2024, 1, 1)),
        Post(post_id=42, topic="y", likes=10, shares=20, comments=30,
             version=1, timestamp=datetime(2024, 1, 1)),
    ])
    db_session.commit()

    resp = client.get("/stats")
    topics = {t["topic"]: t for t in resp.json()["topics"]}

    assert topics["x"]["num_posts"] == 1
    assert topics["y"]["num_posts"] == 1
    assert topics["x"]["total_likes"] == 1
    assert topics["y"]["total_likes"] == 10


def test_empty_database_returns_empty_topic_list(client: TestClient) -> None:
    resp = client.get("/stats")
    assert resp.status_code == 200
    assert resp.json() == {"topics": []}

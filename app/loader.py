"""Load mock post data from a CSV file into the database."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Iterable

from sqlalchemy.orm import Session

from app.models import Post


REQUIRED_COLUMNS = {"post_id", "topic", "likes", "shares", "comments", "version", "timestamp"}


def _parse_row(row: dict[str, str]) -> Post:
    return Post(
        post_id=int(row["post_id"]),
        topic=row["topic"].strip(),
        likes=int(row["likes"]),
        shares=int(row["shares"]),
        comments=int(row["comments"]),
        version=int(row["version"]),
        timestamp=datetime.fromisoformat(row["timestamp"]),
    )


def iter_posts_from_csv(csv_path: str | Path) -> Iterable[Post]:
    path = Path(csv_path)
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or not REQUIRED_COLUMNS.issubset(reader.fieldnames):
            missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
            raise ValueError(f"CSV is missing required columns: {sorted(missing)}")
        for row in reader:
            yield _parse_row(row)


def load_csv(session: Session, csv_path: str | Path) -> int:
    """Insert every row from ``csv_path`` into the ``posts`` table.

    Returns the number of rows inserted.
    """
    posts = list(iter_posts_from_csv(csv_path))
    session.add_all(posts)
    session.commit()
    return len(posts)

"""Manual data loader.

Creates the schema (idempotent) and inserts every row from a CSV into the
``posts`` table. Reads ``DATABASE_URL`` from the environment, defaulting to
the docker-compose Postgres in this repo.

Usage:
    python scripts/load_csv.py [path/to/mock_posts.csv]
"""
from __future__ import annotations

import sys
from pathlib import Path

from app.database import create_all, get_engine
from app.loader import load_csv
from sqlalchemy.orm import Session


DEFAULT_CSV = Path(__file__).resolve().parent.parent / "tests" / "data" / "mock_posts.csv"


def main() -> None:
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CSV
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    create_all()
    with Session(get_engine()) as session:
        inserted = load_csv(session, csv_path)
    print(f"Inserted {inserted} rows from {csv_path}")


if __name__ == "__main__":
    main()

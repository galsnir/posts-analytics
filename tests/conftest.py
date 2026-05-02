"""Pytest fixtures.

Each test session starts a real Postgres instance in a Docker container
(via testcontainers), points the app at it, and creates a fresh schema.
Each test then gets a clean database (all rows deleted) to keep tests
independent without paying the cost of restarting the container.
"""
from __future__ import annotations

import os
import time
from collections.abc import Iterator
from pathlib import Path

# Auto-detect Colima's docker socket so `pytest` works as a single command on
# macOS setups where Docker Desktop isn't installed. No-op on Docker Desktop,
# OrbStack, or Linux Docker (where DOCKER_HOST is either unset and the daemon
# is at the default socket, or already set by the user).
if "DOCKER_HOST" not in os.environ:
    _colima_sock = Path.home() / ".colima" / "default" / "docker.sock"
    if _colima_sock.exists():
        os.environ["DOCKER_HOST"] = f"unix://{_colima_sock}"
        os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import Engine  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from testcontainers.postgres import PostgresContainer  # noqa: E402

from app import database  # noqa: E402
from app.database import Base, get_session, reset_engine  # noqa: E402
from app.main import create_app  # noqa: E402


CSV_PATH = Path(__file__).parent / "data" / "mock_posts.csv"


def _wait_until_reachable(engine: Engine, timeout: float = 60.0) -> None:
    """Poll the engine until a real TCP connection succeeds.

    On some setups (notably Colima) the host port forward becomes reachable
    a moment after testcontainers' log-based readiness check fires, so we
    add an explicit connect-with-retry here before issuing DDL.
    """
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except OperationalError as err:
            last_err = err
            time.sleep(0.5)
    raise RuntimeError(f"Postgres never became reachable: {last_err}")


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("postgres:16-alpine", driver="psycopg") as pg:
        yield pg


@pytest.fixture(scope="session")
def engine(postgres_container: PostgresContainer):
    url = postgres_container.get_connection_url()
    os.environ["DATABASE_URL"] = url
    eng = reset_engine(url)
    _wait_until_reachable(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db_session(engine) -> Iterator[Session]:
    """A clean database for each test."""
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE posts RESTART IDENTITY"))

    assert database._SessionLocal is not None
    with database._SessionLocal() as session:
        yield session


@pytest.fixture()
def client(engine, db_session) -> Iterator[TestClient]:
    """A FastAPI test client wired to the same database as ``db_session``."""
    app = create_app()

    def _override_session() -> Iterator[Session]:
        assert database._SessionLocal is not None
        with database._SessionLocal() as s:
            yield s

    app.dependency_overrides[get_session] = _override_session
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def csv_path() -> Path:
    return CSV_PATH

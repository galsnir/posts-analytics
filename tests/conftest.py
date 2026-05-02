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

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from testcontainers.postgres import PostgresContainer

from app import database
from app.database import Base, get_session, reset_engine
from app.main import create_app


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

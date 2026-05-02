"""Pytest fixtures.

Each test session starts a real Postgres instance in a Docker container
(via testcontainers), points the app at it, and creates a fresh schema.
Each test then gets a clean database (all rows deleted) to keep tests
independent without paying the cost of restarting the container.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path


def _bootstrap_docker_env() -> None:
    """Make ``pytest`` work as a single command across common Docker setups.

    Runs before any ``docker``/``testcontainers`` import so the side effects
    are visible to those libraries.

    Handles three real-world quirks without overriding anything the user
    already configured:

    * Auto-detects a Colima socket at ``~/.colima/default/docker.sock`` if
      ``DOCKER_HOST`` is not set (transparent for Docker Desktop users).
    * Sidesteps a stale ``docker-credential-desktop`` reference in
      ``~/.docker/config.json`` by pointing ``DOCKER_CONFIG`` at an empty
      config when the credential helper binary is missing.
    * Disables the testcontainers "ryuk" reaper, which wants to pull an
      extra image and isn't strictly necessary for a short test run.
    """
    os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

    if "DOCKER_HOST" not in os.environ:
        colima_sock = Path.home() / ".colima" / "default" / "docker.sock"
        if colima_sock.exists():
            os.environ["DOCKER_HOST"] = f"unix://{colima_sock}"

    if "DOCKER_CONFIG" not in os.environ:
        cfg_path = Path.home() / ".docker" / "config.json"
        try:
            cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
        except (OSError, json.JSONDecodeError):
            cfg = {}
        creds_store = cfg.get("credsStore")
        if creds_store and shutil.which(f"docker-credential-{creds_store}") is None:
            empty = Path(tempfile.gettempdir()) / "posts-analytics-docker-config"
            empty.mkdir(exist_ok=True)
            (empty / "config.json").write_text("{}")
            os.environ["DOCKER_CONFIG"] = str(empty)


_bootstrap_docker_env()


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

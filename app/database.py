"""Database engine and session management.

The database URL is read from the ``DATABASE_URL`` environment variable so the
same code works in local development, docker-compose, and the test suite (which
spins up an ephemeral Postgres container).
"""
from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/posts"


class Base(DeclarativeBase):
    """Base class for all ORM models."""


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _build_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, future=True)


def get_engine() -> Engine:
    """Return a process-wide engine, creating it lazily from ``DATABASE_URL``."""
    global _engine, _SessionLocal
    if _engine is None:
        url = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
        _engine = _build_engine(url)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def reset_engine(url: str | None = None) -> Engine:
    """(Re)create the engine. Useful for tests that want to point at a fresh DB."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    target_url = url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    _engine = _build_engine(target_url)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def get_session() -> Iterator[Session]:
    """FastAPI dependency that yields a SQLAlchemy session."""
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None
    with _SessionLocal() as session:
        yield session


def create_all() -> None:
    """Create all tables. Safe to call multiple times."""
    Base.metadata.create_all(get_engine())

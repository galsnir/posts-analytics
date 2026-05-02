"""FastAPI application exposing the /stats endpoint."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session

from app.database import create_all, get_session
from app.schemas import StatsResponse
from app.stats import compute_topic_stats


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    create_all()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Posts Analytics", version="0.1.0", lifespan=lifespan)

    @app.get("/stats", response_model=StatsResponse)
    def get_stats(session: Session = Depends(get_session)) -> StatsResponse:
        return StatsResponse(topics=compute_topic_stats(session))

    return app


app = create_app()

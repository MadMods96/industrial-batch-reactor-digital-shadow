"""FastAPI application. Fitting never happens inside a request."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from htpp.api.routes_chat import router as chat_router
from htpp.api.routes_data import router as data_router
from htpp.api.routes_models import router as models_router
from htpp.api.routes_simulate import router as simulate_router
from htpp.api.ws_live import router as ws_router
from htpp.config import settings
from htpp.store.db import connect, migrate

log = logging.getLogger("htpp.api")


async def _scheduled_tick() -> None:
    from htpp.api.ws_live import broadcast_tick
    from htpp.batches.assemble import assemble
    from htpp.ingest.incremental import incremental_tick

    try:
        await incremental_tick()
        assemble()
        await broadcast_tick()
    except Exception:
        log.exception("scheduled ingest tick failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate(connect()).close()
    scheduler = None
    if os.environ.get("HTPP_DISABLE_SCHEDULER") != "1":
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            _scheduled_tick,
            "interval",
            minutes=settings.incremental_cron_minutes,
            id="incremental",
            next_run_time=datetime.now(timezone.utc),
        )
        scheduler.start()
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    app = FastAPI(title="HTPP Digital Shadow", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        origin = request.headers.get("origin")
        headers = {}
        if origin in settings.cors_origins:
            headers["Access-Control-Allow-Origin"] = origin
            headers["Access-Control-Allow-Credentials"] = "true"
            headers["Vary"] = "Origin"
        log.exception("unhandled %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Request failed",
                    "detail": f"{type(exc).__name__}: {exc}",
                }
            },
            headers=headers,
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(data_router, prefix="/api")
    app.include_router(models_router, prefix="/api")
    app.include_router(simulate_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")
    app.include_router(ws_router)
    return app


app = create_app()

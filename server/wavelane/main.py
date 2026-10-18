"""Wavelane application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from . import __version__
from .api.routers import auth, catalog, imports, library, playlists, stream, upload, wave
from .config import Settings, get_settings
from .db import dispose_engine, get_session_factory, init_models
from .services.audio_analysis import get_analyzer

logger = logging.getLogger("wavelane")

DESCRIPTION = """
Wavelane streaming backend.

**Wave** is the personalised endless radio: `GET /wave/next` returns the next
tracks with the reason each was chosen, and `POST /wave/feedback` makes the
stream react immediately. Mood, character and language are set through
`PUT /wave/settings`.

Ordinary listening also trains the wave — report playback to
`POST /library/plays` and the taste profile updates itself.
"""


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    # These are chatty at DEBUG and say nothing useful here.
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("multipart").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    settings.ensure_directories()

    # create_all is the development path; Alembic owns the schema in production.
    await init_models()

    analyzer = get_analyzer()
    if not analyzer.dsp_available:
        logger.warning(
            "ffmpeg was not found: audio analysis falls back to metadata priors. "
            "Install ffmpeg or set WAVELANE_FFMPEG_PATH to enable tempo/key/energy "
            "detection."
        )

    factory = get_session_factory()
    async with factory() as session:
        from .models import Track, User

        users = await session.scalar(select(func.count()).select_from(User))
        tracks = await session.scalar(select(func.count()).select_from(Track))
    logger.info(
        "Wavelane %s ready — %s user(s), %s track(s), storage at %s",
        __version__,
        users or 0,
        tracks or 0,
        settings.storage_root,
    )

    try:
        yield
    finally:
        await dispose_engine()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        description=DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # The client needs these to drive a seek bar.
        expose_headers=["Content-Range", "Accept-Ranges", "X-Track-Duration-Ms"],
    )

    for module in (auth, catalog, wave, library, playlists, upload, imports, stream):
        app.include_router(module.router, prefix=settings.api_prefix)

    @app.exception_handler(IntegrityError)
    async def _integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        # Usually a unique-constraint race; a 409 is the honest answer.
        logger.warning("integrity error on %s: %s", request.url.path, exc.orig)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "this record conflicts with one that already exists"},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Pydantic puts the original exception object in ``ctx``, which json
        # cannot encode; jsonable_encoder turns it into a string for us.
        return JSONResponse(
            status_code=422,
            content={"detail": "invalid request", "errors": jsonable_encoder(exc.errors())},
        )

    @app.get("/health", tags=["meta"], summary="Liveness probe")
    async def health() -> dict[str, object]:
        analyzer = get_analyzer()
        return {
            "status": "ok",
            "version": __version__,
            "dsp_analysis": analyzer.dsp_available,
        }

    @app.get("/", tags=["meta"], include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "name": settings.app_name,
            "version": __version__,
            "api": settings.api_prefix,
            "docs": "/docs",
        }

    return app


app = create_app()

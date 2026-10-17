"""Audio streaming and image serving."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Annotated

import anyio
from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse, StreamingResponse

from ...models import Track, User
from ...services.security import AuthError, create_stream_token, decode_token, token_user_id
from ...services.storage import CONTENT_TYPES, StorageError
from ...services.streaming import (
    RangeNotSatisfiable,
    iter_file_range,
    parse_range,
    streaming_headers,
)
from ..deps import (
    AppSettings,
    CurrentUser,
    DbSession,
    FileStorage,
    OptionalUser,
)

router = APIRouter(tags=["streaming"])


def _stat_or_none(path: Path) -> os.stat_result | None:
    try:
        result = path.stat()
    except OSError:
        return None
    return result if os.path.isfile(path) else None

# Covers are content-addressed, so a long cache is safe: a different image is a
# different URL.
IMAGE_CACHE_SECONDS = 60 * 60 * 24 * 30


async def _resolve_listener(
    db: DbSession,
    settings: AppSettings,
    track_id: uuid.UUID,
    user: User | None,
    token: str | None,
) -> User:
    """Accept either a Bearer access token or a per-track stream token.

    Qt's media backend and HTML <audio> both fetch the URL themselves and will
    not attach an Authorization header, so a short-lived token in the query
    string is the only way to keep the endpoint authenticated.
    """
    if user is not None:
        return user

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(token, expected_type="stream", settings=settings)
        listener_id = token_user_id(payload)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    if payload.get("trk") != str(track_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="this stream token is for a different track",
        )

    listener = await db.get(User, listener_id)
    if listener is None or not listener.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="account unavailable"
        )
    return listener


@router.get(
    "/tracks/{track_id}/stream-token",
    summary="Short-lived token for playing one track",
)
async def stream_token(
    track_id: uuid.UUID, db: DbSession, user: CurrentUser, settings: AppSettings
) -> dict[str, object]:
    track = await db.get(Track, track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="track not found")
    token = create_stream_token(user.id, track_id, settings)
    return {
        "token": token,
        "url": f"{settings.api_prefix}/stream/{track_id}?token={token}",
        "expires_in": settings.stream_token_ttl_seconds,
    }


@router.get("/stream/{track_id}", summary="Stream audio (supports Range requests)")
async def stream_track(
    track_id: uuid.UUID,
    request: Request,
    db: DbSession,
    settings: AppSettings,
    storage: FileStorage,
    user: OptionalUser,
    token: Annotated[str | None, Query(description="Stream token")] = None,
) -> Response:
    await _resolve_listener(db, settings, track_id, user, token)

    track = await db.get(Track, track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="track not found")

    try:
        path = storage.audio_path(track.storage_path)
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc

    # One stat off the event loop answers both "does it exist" and "how big".
    stat_result = await anyio.to_thread.run_sync(_stat_or_none, path)
    if stat_result is None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="the audio file for this track is missing from storage",
        )

    file_size = stat_result.st_size
    try:
        byte_range = parse_range(request.headers.get("range"), file_size)
    except RangeNotSatisfiable:
        return Response(
            status_code=status.HTTP_416_RANGE_NOT_SATISFIABLE,
            headers={"Content-Range": f"bytes */{file_size}"},
        )

    content_type = CONTENT_TYPES.get(track.container or "", "application/octet-stream")
    headers = streaming_headers(
        byte_range,
        file_size,
        content_type=content_type,
        filename=f"{track.title}.{(track.container or 'audio')}",
    )
    headers["X-Track-Duration-Ms"] = str(track.duration_ms)

    status_code = (
        status.HTTP_206_PARTIAL_CONTENT
        if byte_range is not None and not byte_range.is_full
        else status.HTTP_200_OK
    )

    if request.method == "HEAD":
        return Response(status_code=status_code, headers=headers)

    return StreamingResponse(
        iter_file_range(path, byte_range, settings.stream_chunk_bytes, file_size),
        status_code=status_code,
        headers=headers,
        media_type=content_type,
    )


@router.head("/stream/{track_id}", include_in_schema=False)
async def stream_track_head(
    track_id: uuid.UUID,
    request: Request,
    db: DbSession,
    settings: AppSettings,
    storage: FileStorage,
    user: OptionalUser,
    token: Annotated[str | None, Query()] = None,
) -> Response:
    return await stream_track(
        track_id, request, db, settings, storage, user, token
    )


@router.get("/covers/{path:path}", summary="Album cover image")
async def get_cover(path: str, storage: FileStorage) -> FileResponse:
    return _image_response(storage.cover_path, path)


@router.get("/avatars/{path:path}", summary="User avatar image")
async def get_avatar(path: str, storage: FileStorage) -> FileResponse:
    return _image_response(storage.avatar_path, path)


def _image_response(resolver, path: str) -> FileResponse:
    try:
        resolved = resolver(path)
    except StorageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not resolved.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="image not found")
    return FileResponse(
        resolved,
        headers={"Cache-Control": f"public, max-age={IMAGE_CACHE_SECONDS}, immutable"},
    )

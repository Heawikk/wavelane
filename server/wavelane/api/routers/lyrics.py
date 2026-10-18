"""Song lyrics: anyone signed in reads them, administrators write them."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Response, status

from ...models import Track
from ...schemas.lyrics import LyricLineOut, LyricsIn, LyricsOut
from ...services.lyrics import LyricsError, parse_lyrics, validate_text
from ..deps import AdminUser, CurrentUser, DbSession

router = APIRouter(tags=["lyrics"])


async def _track(db: DbSession, track_id: uuid.UUID) -> Track:
    track = await db.get(Track, track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="track not found")
    return track


def _out(track: Track, *, with_text: bool) -> LyricsOut:
    parsed = parse_lyrics(track.lyrics)
    return LyricsOut(
        track_id=track.id,
        kind=parsed.kind,
        lines=[LyricLineOut(time_ms=ln.time_ms, text=ln.text) for ln in parsed.lines],
        text=track.lyrics if with_text and parsed.kind != "none" else None,
    )


@router.get(
    "/tracks/{track_id}/lyrics",
    response_model=LyricsOut,
    summary="The lyrics of a track (kind \"none\" if it has none)",
)
async def get_lyrics(track_id: uuid.UUID, db: DbSession, user: CurrentUser) -> LyricsOut:
    return _out(await _track(db, track_id), with_text=user.is_admin)


@router.put(
    "/tracks/{track_id}/lyrics",
    response_model=LyricsOut,
    summary="Set the lyrics of a track (administrator)",
)
async def put_lyrics(
    track_id: uuid.UUID, payload: LyricsIn, db: DbSession, admin: AdminUser
) -> LyricsOut:
    track = await _track(db, track_id)
    try:
        track.lyrics = validate_text(payload.text)
    except LyricsError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    await db.flush()
    return _out(track, with_text=True)


@router.delete(
    "/tracks/{track_id}/lyrics",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove the lyrics of a track (administrator)",
)
async def delete_lyrics(track_id: uuid.UUID, db: DbSession, admin: AdminUser) -> Response:
    track = await _track(db, track_id)
    track.lyrics = None
    await db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

"""Numbers for the administrator's dashboard."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select

from ...models import Album, Artist, Track
from ...schemas.admin import AdminStats
from ...services.catalog import count_query, ready_tracks
from ...services.lyrics import parse_lyrics
from ..deps import AdminUser, DbSession

router = APIRouter(tags=["admin"])


@router.get(
    "/admin/stats",
    response_model=AdminStats,
    summary="How many tracks there are, and how many have words (admin)",
)
async def admin_stats(admin: AdminUser, db: DbSession) -> AdminStats:
    tracks = await count_query(db, ready_tracks())
    storage_bytes = await db.scalar(select(func.coalesce(func.sum(Track.file_size), 0))) or 0
    artists = await db.scalar(select(func.count()).select_from(Artist)) or 0
    albums = await db.scalar(select(func.count()).select_from(Album)) or 0

    # Whether text is synced depends on how it parses, which only the parser knows.
    plain = synced = 0
    texts = await db.scalars(
        ready_tracks().with_only_columns(Track.lyrics).where(Track.lyrics.is_not(None))
    )
    for text in texts.all():
        kind = parse_lyrics(text).kind
        if kind == "synced":
            synced += 1
        elif kind == "plain":
            plain += 1

    return AdminStats(
        tracks=tracks,
        artists=artists,
        albums=albums,
        storage_bytes=int(storage_bytes),
        with_lyrics=plain + synced,
        synced_lyrics=synced,
        plain_lyrics=plain,
        without_lyrics=max(0, tracks - plain - synced),
    )

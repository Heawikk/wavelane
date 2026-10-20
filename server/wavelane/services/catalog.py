"""Catalogue queries shared by several routers."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Album,
    Artist,
    Genre,
    Track,
    TrackArtist,
    TrackGenre,
    TrackReaction,
    TrackStatus,
)
from ..schemas.catalog import TrackOut
from ..utils import normalize_name


async def reaction_map(
    session: AsyncSession, user_id: uuid.UUID | None, track_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """track_id -> "like"/"dislike" for one user, in a single query."""
    if user_id is None or not track_ids:
        return {}
    rows = await session.execute(
        select(TrackReaction.track_id, TrackReaction.kind).where(
            TrackReaction.user_id == user_id, TrackReaction.track_id.in_(track_ids)
        )
    )
    return {row[0]: row[1] for row in rows}


async def serialize_tracks(
    session: AsyncSession,
    tracks: Sequence[Track],
    user_id: uuid.UUID | None = None,
    *,
    include_features: bool = False,
) -> list[TrackOut]:
    reactions = await reaction_map(session, user_id, [track.id for track in tracks])
    out: list[TrackOut] = []
    for track in tracks:
        kind = reactions.get(track.id)
        out.append(
            TrackOut.from_track(
                track,
                liked=kind == "like" if user_id else None,
                disliked=kind == "dislike" if user_id else None,
                include_features=include_features,
            )
        )
    return out


def ready_tracks() -> Select[tuple[Track]]:
    return select(Track).where(Track.status == TrackStatus.READY)


async def count_query(session: AsyncSession, query: Select[tuple]) -> int:
    subquery = query.order_by(None).subquery()
    return int(await session.scalar(select(func.count()).select_from(subquery)) or 0)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def _search_terms(query: str) -> tuple[str, str]:
    """Return (normalised needle, LIKE pattern)."""
    needle = normalize_name(query)
    return needle, f"%{needle}%"


def track_matches(pattern: str):
    """The condition for "the title, an artist or the album of this track contains the text"."""
    return or_(
        Track.normalized_title.like(pattern),
        Track.artist_links.any(
            TrackArtist.artist_id.in_(
                select(Artist.id).where(Artist.normalized_name.like(pattern)).scalar_subquery()
            )
        ),
        Track.album_id.in_(
            select(Album.id).where(Album.normalized_title.like(pattern)).scalar_subquery()
        ),
    )


def search_pattern(query: str) -> str | None:
    """The LIKE pattern for a search text, or None when there is nothing to look for."""
    needle, pattern = _search_terms(query)
    return pattern if needle else None


async def search_tracks(
    session: AsyncSession, query: str, limit: int = 20, offset: int = 0
) -> list[Track]:
    needle, pattern = _search_terms(query)
    if not needle:
        return []

    # Rank exact prefix matches above substring matches, then by popularity.
    # A dedicated full-text index (tsvector / FTS5) is the next step here; the
    # normalised columns keep this usable and portable until then.
    statement = (
        ready_tracks()
        .where(track_matches(pattern))
        .order_by(
            Track.normalized_title.like(f"{needle}%").desc(),
            Track.play_count.desc(),
            Track.title,
        )
        .limit(limit)
        .offset(offset)
    )
    rows = await session.scalars(statement)
    return list(rows)


async def search_artists(
    session: AsyncSession, query: str, limit: int = 10
) -> list[Artist]:
    needle, pattern = _search_terms(query)
    if not needle:
        return []
    rows = await session.scalars(
        select(Artist)
        .where(Artist.normalized_name.like(pattern))
        .order_by(
            Artist.normalized_name.like(f"{needle}%").desc(),
            Artist.play_count.desc(),
            Artist.name,
        )
        .limit(limit)
    )
    return list(rows)


async def search_albums(session: AsyncSession, query: str, limit: int = 10) -> list[Album]:
    needle, pattern = _search_terms(query)
    if not needle:
        return []
    # An artist's name finds their albums (the ones filed under them, and the ones they are
    # on) as well as albums with that word in the title.
    matching_artists = select(Artist.id).where(Artist.normalized_name.like(pattern))
    owned = Album.artist_id.in_(matching_artists.scalar_subquery())
    appears_on = Album.id.in_(
        select(Track.album_id)
        .join(TrackArtist, TrackArtist.track_id == Track.id)
        .where(
            Track.album_id.is_not(None),
            TrackArtist.artist_id.in_(matching_artists.scalar_subquery()),
        )
    )
    rows = await session.scalars(
        select(Album)
        .where(or_(Album.normalized_title.like(pattern), owned, appears_on))
        .order_by(
            Album.normalized_title.like(f"{needle}%").desc(),
            Album.release_year.desc().nullslast(),
            Album.title,
        )
        .limit(limit)
    )
    return list(rows)


async def tracks_for_genre(
    session: AsyncSession, slug: str, limit: int = 50, offset: int = 0
) -> list[Track]:
    rows = await session.scalars(
        ready_tracks()
        .where(
            Track.genre_links.any(
                TrackGenre.genre_id.in_(
                    select(Genre.id)
                    .where(or_(Genre.slug == slug, Genre.parent_slug == slug))
                    .scalar_subquery()
                )
            )
        )
        .order_by(Track.play_count.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows)


async def recompute_artist_counters(session: AsyncSession, artist_id: uuid.UUID) -> None:
    """Resync the denormalised counters after an edit or delete."""
    artist = await session.get(Artist, artist_id)
    if artist is None:
        return
    artist.track_count = int(
        await session.scalar(
            select(func.count())
            .select_from(TrackArtist)
            .where(TrackArtist.artist_id == artist_id)
        )
        or 0
    )
    artist.play_count = int(
        await session.scalar(
            select(func.coalesce(func.sum(Track.play_count), 0))
            .select_from(Track)
            .join(TrackArtist, TrackArtist.track_id == Track.id)
            .where(TrackArtist.artist_id == artist_id)
        )
        or 0
    )

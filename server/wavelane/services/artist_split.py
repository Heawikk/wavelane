"""Breaking up artists that are really a list: "A, B, C" becomes A, B and C.

Before commas were understood in a credit, a track by several artists made one artist whose
name was all of theirs, with a page and a track count of its own. This finds those and puts the
real artists in their place on every track, on the albums filed under them and among the
artists a listener follows.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Album, Artist, ArtistReaction, Track, TrackArtist
from ..utils import now_utc
from .catalog import recompute_artist_counters
from .credits import split_artist_name
from .editing import get_or_create_artist

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SplitReport:
    #: Artists that were really lists.
    combined: int = 0
    #: Artists that did not exist yet and were created from the pieces.
    created: int = 0
    tracks_changed: int = 0
    albums_moved: int = 0
    albums_merged: int = 0
    #: A few "A, B" -> [A, B] examples, for showing what happened.
    examples: list[tuple[str, list[str]]] = field(default_factory=list)


async def split_combined_artists(session: AsyncSession) -> SplitReport:
    """Split every artist whose name lists several. The caller commits (or rolls back)."""
    report = SplitReport()
    candidates = (
        await session.scalars(select(Artist).where(Artist.name.contains(",")).order_by(Artist.name))
    ).all()

    touched: set[uuid.UUID] = set()
    for artist in candidates:
        names = split_artist_name(artist.name)
        if names == [artist.name.strip()]:
            continue

        before = await session.scalar(select(func.count()).select_from(Artist))
        pieces = [await get_or_create_artist(session, name) for name in names]
        report.created += int(await session.scalar(select(func.count()).select_from(Artist)) or 0) - int(
            before or 0
        )
        report.combined += 1
        if len(report.examples) < 8:
            report.examples.append((artist.name, [piece.name for piece in pieces]))

        track_ids = list(
            await session.scalars(
                select(TrackArtist.track_id).where(TrackArtist.artist_id == artist.id)
            )
        )
        for track_id in track_ids:
            await _replace_in_track(session, track_id, artist.id, [p.id for p in pieces])
        report.tracks_changed += len(track_ids)

        await _move_albums(session, artist, pieces[0], report)
        await _move_follows(session, artist, pieces)

        touched.update(piece.id for piece in pieces)
        session.expunge(artist)
        await session.execute(delete(Artist).where(Artist.id == artist.id))

    await session.flush()
    for artist_id in touched:
        await recompute_artist_counters(session, artist_id)
    await session.flush()
    logger.info(
        "split %s combined artist(s): %s track(s) changed, %s album(s) moved, %s merged",
        report.combined,
        report.tracks_changed,
        report.albums_moved,
        report.albums_merged,
    )
    return report


async def _replace_in_track(
    session: AsyncSession, track_id: uuid.UUID, old_id: uuid.UUID, new_ids: list[uuid.UUID]
) -> None:
    """Put the pieces where the combined artist stood in the track's credits, in the same role."""
    rows = list(
        await session.scalars(
            select(TrackArtist).where(TrackArtist.track_id == track_id).order_by(TrackArtist.position)
        )
    )
    credits: dict[uuid.UUID, object] = {}
    for row in rows:
        for artist_id in new_ids if row.artist_id == old_id else [row.artist_id]:
            credits.setdefault(artist_id, row.role)

    for row in rows:
        await session.delete(row)
    await session.flush()
    for position, (artist_id, role) in enumerate(credits.items()):
        session.add(TrackArtist(track_id=track_id, artist_id=artist_id, role=role, position=position))
    await session.flush()


async def _move_albums(
    session: AsyncSession, artist: Artist, owner: Artist, report: SplitReport
) -> None:
    """Albums filed under the combined artist go under its first piece, merging with a twin."""
    albums = list(await session.scalars(select(Album).where(Album.artist_id == artist.id)))
    for album in albums:
        twin = await session.scalar(
            select(Album).where(
                Album.artist_id == owner.id, Album.normalized_title == album.normalized_title
            )
        )
        if twin is None:
            album.artist_id = owner.id
            await session.flush()
            report.albums_moved += 1
            continue

        await session.execute(update(Track).where(Track.album_id == album.id).values(album_id=twin.id))
        twin.cover_path = twin.cover_path or album.cover_path
        twin.release_year = twin.release_year or album.release_year
        twin.release_date = twin.release_date or album.release_date
        twin.total_tracks = max(twin.total_tracks, album.total_tracks)
        session.expunge(album)
        await session.execute(delete(Album).where(Album.id == album.id))
        report.albums_merged += 1


async def _move_follows(session: AsyncSession, artist: Artist, pieces: list[Artist]) -> None:
    """Following "A, B" means following A and B; banning it says nothing sure about either."""
    reactions = list(
        await session.scalars(select(ArtistReaction).where(ArtistReaction.artist_id == artist.id))
    )
    for reaction in reactions:
        if reaction.kind == "follow":
            for piece in pieces:
                taken = await session.get(ArtistReaction, (reaction.user_id, piece.id))
                if taken is None:
                    session.add(
                        ArtistReaction(
                            user_id=reaction.user_id,
                            artist_id=piece.id,
                            kind="follow",
                            created_at=reaction.created_at or now_utc(),
                        )
                    )
        await session.delete(reaction)
    await session.flush()

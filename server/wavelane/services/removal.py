"""Deleting tracks, and reclaiming audio files nothing refers to any more."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Album, Artist, PlaylistTrack, Track
from ..models.library import Playlist
from ..utils import now_utc
from .catalog import recompute_artist_counters
from .storage import Storage

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DeleteStats:
    deleted: int = 0
    albums_removed: int = 0
    artists_removed: int = 0
    #: Audio files to unlink once the transaction has committed.
    paths: list[str] = field(default_factory=list)


async def delete_tracks(session: AsyncSession, track_ids: Sequence[uuid.UUID]) -> DeleteStats:
    """Remove tracks and tidy what they leave behind.

    Reactions, play history, queue entries and playlist rows go with the track
    through database cascades. What does not cascade is everything that was only
    there because of the track: an album with no tracks left, an artist with no
    tracks or albums, and the stored totals of any playlist that held it.

    The audio files are *not* touched here. The caller deletes them after the
    commit, because a rolled-back transaction must not leave rows pointing at
    files that are already gone.
    """
    stats = DeleteStats()
    tracks = list(
        (await session.scalars(select(Track).where(Track.id.in_(list(track_ids))))).unique()
    )
    if not tracks:
        return stats

    ids = [track.id for track in tracks]
    artist_ids = {link.artist_id for track in tracks for link in track.artist_links}
    album_ids = {track.album_id for track in tracks if track.album_id}
    stats.paths = [track.storage_path for track in tracks]

    playlist_ids = set(
        await session.scalars(
            select(PlaylistTrack.playlist_id).where(PlaylistTrack.track_id.in_(ids)).distinct()
        )
    )

    for track in tracks:
        await session.delete(track)
    await session.flush()
    stats.deleted = len(tracks)

    stats.albums_removed, gone_ids = await prune_empty(session, artist_ids, album_ids)
    stats.artists_removed = len(gone_ids)
    for artist_id in artist_ids - gone_ids:
        await recompute_artist_counters(session, artist_id)

    for playlist_id in playlist_ids:
        await _refresh_playlist(session, playlist_id)

    return stats


async def prune_empty(
    session: AsyncSession, artist_ids: Iterable[uuid.UUID], album_ids: Iterable[uuid.UUID]
) -> tuple[int, set[uuid.UUID]]:
    """Remove the albums with no tracks and the artists with no tracks and no albums left.

    Only the ones named are looked at, so this is for tidying up after an edit or a delete that
    touched them. Returns how many albums went and the ids of the artists that did.
    """
    albums_removed = 0
    album_ids = {album_id for album_id in album_ids if album_id}
    if album_ids:
        empty_albums = await session.scalars(
            select(Album).where(Album.id.in_(album_ids), ~Album.tracks.any())
        )
        for album in empty_albums.unique():
            await session.delete(album)
            albums_removed += 1
        await session.flush()

    gone_ids: set[uuid.UUID] = set()
    artist_ids = set(artist_ids)
    if artist_ids:
        gone = await session.scalars(
            select(Artist).where(
                Artist.id.in_(artist_ids),
                ~Artist.track_links.any(),
                ~Artist.albums.any(),
            )
        )
        for artist in gone.unique():
            gone_ids.add(artist.id)
            await session.delete(artist)
        await session.flush()
    return albums_removed, gone_ids


async def _refresh_playlist(session: AsyncSession, playlist_id: uuid.UUID) -> None:
    playlist = await session.get(Playlist, playlist_id)
    if playlist is None:
        return
    row = await session.execute(
        select(func.count(), func.coalesce(func.sum(Track.duration_ms), 0))
        .select_from(PlaylistTrack)
        .join(Track, Track.id == PlaylistTrack.track_id)
        .where(PlaylistTrack.playlist_id == playlist_id)
    )
    count, duration = row.one()
    playlist.track_count = int(count or 0)
    playlist.duration_ms = int(duration or 0)
    playlist.updated_at = now_utc()


def unlink_audio(storage: Storage, paths: Sequence[str]) -> int:
    """Delete audio files, tolerating the ones Windows will not release."""
    removed = 0
    for path in paths:
        try:
            storage.delete_audio(path)
            removed += 1
        except OSError as exc:
            # Typically the file is being played right now. It stays as an
            # orphan; cleanup_orphans() reclaims it on request.
            logger.warning("could not delete %s: %s", path, exc)
    return removed


async def cleanup_orphans(
    session: AsyncSession, storage: Storage, keep: Iterable[str] = ()
) -> tuple[int, int]:
    """Delete audio files no track refers to. Returns (files removed, bytes freed).

    ``keep`` lists files that are unreferenced on purpose: new files staged
    while a conflict waits for an answer.

    This is a manual, explicit action and refuses to run on an empty catalogue.
    Without that guard, recreating the database for a fresh start would make the
    next clean-up treat the whole music library as orphaned and delete it.
    """
    known = set(await session.scalars(select(Track.storage_path)))
    if not known:
        raise ValueError("the catalogue is empty; refusing to treat every file as an orphan")
    known |= set(keep)

    root = storage.settings.audio_dir
    removed = freed = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in known:
            continue
        try:
            size = path.stat().st_size
            path.unlink()
        except OSError as exc:
            logger.warning("could not remove orphan %s: %s", relative, exc)
            continue
        removed += 1
        freed += size
    return removed, freed

"""Library actions: reactions, playlists, play reporting."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Album,
    Artist,
    ArtistReaction,
    FeedbackKind,
    PlaybackContext,
    PlayEvent,
    Playlist,
    PlaylistTrack,
    SavedAlbum,
    Track,
    TrackArtist,
    TrackReaction,
)
from ..utils import clamp, now_utc
from ..wave.engine import WaveEngine

# A play is only counted once the listener has actually stayed with the track.
PLAY_COUNT_THRESHOLD = 0.30
PLAY_COUNT_MIN_MS = 30_000
# Below this, leaving is a rejection rather than a play.
SKIP_THRESHOLD = 0.35


@dataclass(slots=True)
class PlayOutcome:
    recorded: bool
    completion: float
    counted_as: str


async def set_track_reaction(
    session: AsyncSession, user_id: uuid.UUID, track: Track, kind: str
) -> str | None:
    """Set, switch or clear a like/dislike. Returns the resulting state.

    Sending the reaction that is already set clears it, which is what a toggle
    button in the client needs.
    """
    existing = await session.get(TrackReaction, (user_id, track.id))
    engine = WaveEngine(session)

    if existing is not None and existing.kind == kind:
        await session.delete(existing)
        if kind == "like":
            await engine.feedback(
                user_id, track, FeedbackKind.UNLIKE, persist_reaction=False
            )
        await session.flush()
        return None

    if existing is not None:
        existing.kind = kind
        existing.created_at = now_utc()
    else:
        session.add(
            TrackReaction(
                user_id=user_id, track_id=track.id, kind=kind, created_at=now_utc()
            )
        )

    # The reaction row is written above, so the engine must not write it again.
    await engine.feedback(
        user_id,
        track,
        FeedbackKind.LIKE if kind == "like" else FeedbackKind.DISLIKE,
        persist_reaction=False,
    )
    await session.flush()
    return kind


async def set_artist_reaction(
    session: AsyncSession, user_id: uuid.UUID, artist_id: uuid.UUID, kind: str
) -> str | None:
    existing = await session.get(ArtistReaction, (user_id, artist_id))
    if existing is not None and existing.kind == kind:
        await session.delete(existing)
        await session.flush()
        return None
    if existing is not None:
        existing.kind = kind
        existing.created_at = now_utc()
    else:
        session.add(
            ArtistReaction(
                user_id=user_id, artist_id=artist_id, kind=kind, created_at=now_utc()
            )
        )
    await session.flush()
    return kind


async def toggle_saved_album(
    session: AsyncSession, user_id: uuid.UUID, album_id: uuid.UUID
) -> bool:
    existing = await session.get(SavedAlbum, (user_id, album_id))
    if existing is not None:
        await session.delete(existing)
        await session.flush()
        return False
    session.add(SavedAlbum(user_id=user_id, album_id=album_id, created_at=now_utc()))
    await session.flush()
    return True


async def record_play(
    session: AsyncSession,
    user_id: uuid.UUID,
    track: Track,
    *,
    ms_played: int,
    completed: bool,
    skipped: bool,
    context_type: PlaybackContext = PlaybackContext.UNKNOWN,
    context_id: uuid.UUID | None = None,
    started_at: datetime | None = None,
) -> PlayOutcome:
    """Log a listening event and let it train the wave.

    This is where ordinary listening — not just explicit likes — shapes the
    recommendations, which is what makes the stream improve on its own.
    """
    duration = track.duration_ms or 0
    completion = clamp(ms_played / duration) if duration > 0 else 0.0
    if completed:
        completion = max(completion, 0.95)

    session.add(
        PlayEvent(
            user_id=user_id,
            track_id=track.id,
            started_at=started_at or now_utc(),
            ms_played=ms_played,
            completion=completion,
            completed=completed,
            skipped=skipped,
            context_type=context_type,
            context_id=context_id,
        )
    )

    counted = completion >= PLAY_COUNT_THRESHOLD or ms_played >= PLAY_COUNT_MIN_MS
    if counted:
        track.play_count += 1
        await _bump_artist_plays(session, track)

    engine = WaveEngine(session)
    if completed or completion >= 0.85:
        await engine.feedback(user_id, track, FeedbackKind.COMPLETE, completion=completion)
        counted_as = "complete"
    elif skipped or completion < SKIP_THRESHOLD:
        await engine.feedback(user_id, track, FeedbackKind.SKIP, completion=completion)
        counted_as = "skip"
    else:
        counted_as = "partial"

    await session.flush()
    return PlayOutcome(recorded=True, completion=completion, counted_as=counted_as)


async def _bump_artist_plays(session: AsyncSession, track: Track) -> None:
    for link in track.artist_links:
        artist = await session.get(Artist, link.artist_id)
        if artist is not None:
            artist.play_count += 1


async def library_stats(session: AsyncSession, user_id: uuid.UUID) -> dict[str, int]:
    async def count(statement) -> int:
        return int(await session.scalar(statement) or 0)

    liked = await count(
        select(func.count())
        .select_from(TrackReaction)
        .where(TrackReaction.user_id == user_id, TrackReaction.kind == "like")
    )
    disliked = await count(
        select(func.count())
        .select_from(TrackReaction)
        .where(TrackReaction.user_id == user_id, TrackReaction.kind == "dislike")
    )
    playlists = await count(
        select(func.count()).select_from(Playlist).where(Playlist.owner_id == user_id)
    )
    saved = await count(
        select(func.count()).select_from(SavedAlbum).where(SavedAlbum.user_id == user_id)
    )
    followed = await count(
        select(func.count())
        .select_from(ArtistReaction)
        .where(ArtistReaction.user_id == user_id, ArtistReaction.kind == "follow")
    )
    plays = await count(
        select(func.count()).select_from(PlayEvent).where(PlayEvent.user_id == user_id)
    )
    listened = await count(
        select(func.coalesce(func.sum(PlayEvent.ms_played), 0)).where(
            PlayEvent.user_id == user_id
        )
    )
    return {
        "liked_tracks": liked,
        "disliked_tracks": disliked,
        "playlists": playlists,
        "saved_albums": saved,
        "followed_artists": followed,
        "tracks_played": plays,
        "listening_ms": listened,
    }


# ---------------------------------------------------------------------------
# Playlists
# ---------------------------------------------------------------------------


async def create_playlist(
    session: AsyncSession,
    owner_id: uuid.UUID,
    *,
    title: str,
    description: str | None = None,
    is_public: bool = False,
    track_ids: list[uuid.UUID] | None = None,
) -> Playlist:
    playlist = Playlist(
        owner_id=owner_id,
        title=title.strip(),
        description=description,
        is_public=is_public,
    )
    session.add(playlist)
    await session.flush()
    if track_ids:
        await add_playlist_tracks(session, playlist, track_ids, added_by_id=owner_id)
    return playlist


async def add_playlist_tracks(
    session: AsyncSession,
    playlist: Playlist,
    track_ids: list[uuid.UUID],
    *,
    position: int | None = None,
    added_by_id: uuid.UUID | None = None,
) -> int:
    tracks = await session.scalars(select(Track).where(Track.id.in_(track_ids)))
    found = {track.id: track for track in tracks}
    # Preserve the order the caller asked for, skipping ids that do not exist.
    ordered = [found[tid] for tid in track_ids if tid in found]
    if not ordered:
        return 0

    existing = list(
        await session.scalars(
            select(PlaylistTrack)
            .where(PlaylistTrack.playlist_id == playlist.id)
            .order_by(PlaylistTrack.position)
        )
    )
    insert_at = len(existing) if position is None else max(0, min(position, len(existing)))

    new_items = [
        PlaylistTrack(
            playlist_id=playlist.id,
            track_id=track.id,
            position=0,  # renumbered below
            added_at=now_utc(),
            added_by_id=added_by_id,
        )
        for track in ordered
    ]
    merged = existing[:insert_at] + new_items + existing[insert_at:]
    for item in new_items:
        session.add(item)

    # Positions carry a uniqueness constraint, so clear them before renumbering
    # to avoid colliding with rows that have not moved yet.
    await _renumber(session, merged)
    await _refresh_playlist_totals(session, playlist)
    return len(new_items)


async def remove_playlist_track(
    session: AsyncSession, playlist: Playlist, track_id: uuid.UUID
) -> bool:
    items = list(
        await session.scalars(
            select(PlaylistTrack)
            .where(PlaylistTrack.playlist_id == playlist.id)
            .order_by(PlaylistTrack.position)
        )
    )
    remaining = [item for item in items if item.track_id != track_id]
    if len(remaining) == len(items):
        return False

    for item in items:
        if item.track_id == track_id:
            await session.delete(item)
    await session.flush()

    await _renumber(session, remaining)
    await _refresh_playlist_totals(session, playlist)
    return True


async def reorder_playlist(
    session: AsyncSession, playlist: Playlist, track_ids: list[uuid.UUID]
) -> None:
    items = list(
        await session.scalars(
            select(PlaylistTrack).where(PlaylistTrack.playlist_id == playlist.id)
        )
    )
    by_track: dict[uuid.UUID, list[PlaylistTrack]] = {}
    for item in items:
        by_track.setdefault(item.track_id, []).append(item)

    ordered: list[PlaylistTrack] = []
    for track_id in track_ids:
        bucket = by_track.get(track_id)
        if bucket:
            ordered.append(bucket.pop(0))
    # Anything the client left out keeps its relative order at the end.
    leftovers = [item for bucket in by_track.values() for item in bucket]
    leftovers.sort(key=lambda item: item.position)
    await _renumber(session, ordered + leftovers)
    await _refresh_playlist_totals(session, playlist)


async def _renumber(session: AsyncSession, items: list[PlaylistTrack]) -> None:
    """Assign 0..n-1 without tripping the (playlist_id, position) constraint."""
    for offset, item in enumerate(items):
        item.position = -(offset + 1)
    await session.flush()
    for offset, item in enumerate(items):
        item.position = offset
    await session.flush()


async def _refresh_playlist_totals(session: AsyncSession, playlist: Playlist) -> None:
    row = await session.execute(
        select(func.count(), func.coalesce(func.sum(Track.duration_ms), 0))
        .select_from(PlaylistTrack)
        .join(Track, Track.id == PlaylistTrack.track_id)
        .where(PlaylistTrack.playlist_id == playlist.id)
    )
    count, duration = row.one()
    playlist.track_count = int(count or 0)
    playlist.duration_ms = int(duration or 0)
    playlist.updated_at = now_utc()
    await session.flush()


async def clear_playlist(session: AsyncSession, playlist: Playlist) -> None:
    await session.execute(
        delete(PlaylistTrack).where(PlaylistTrack.playlist_id == playlist.id)
    )
    await _refresh_playlist_totals(session, playlist)


async def liked_tracks(
    session: AsyncSession, user_id: uuid.UUID, limit: int = 50, offset: int = 0
) -> list[Track]:
    rows = await session.scalars(
        select(Track)
        .join(TrackReaction, TrackReaction.track_id == Track.id)
        .where(TrackReaction.user_id == user_id, TrackReaction.kind == "like")
        .order_by(TrackReaction.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows)


async def saved_albums(
    session: AsyncSession, user_id: uuid.UUID, limit: int = 50, offset: int = 0
) -> list[Album]:
    rows = await session.scalars(
        select(Album)
        .join(SavedAlbum, SavedAlbum.album_id == Album.id)
        .where(SavedAlbum.user_id == user_id)
        .order_by(SavedAlbum.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows)


async def followed_artists(
    session: AsyncSession, user_id: uuid.UUID, limit: int = 100
) -> list[Artist]:
    rows = await session.scalars(
        select(Artist)
        .join(ArtistReaction, ArtistReaction.artist_id == Artist.id)
        .where(ArtistReaction.user_id == user_id, ArtistReaction.kind == "follow")
        .order_by(ArtistReaction.created_at.desc())
        .limit(limit)
    )
    return list(rows)


async def play_history(
    session: AsyncSession, user_id: uuid.UUID, limit: int = 50, offset: int = 0
) -> list[PlayEvent]:
    rows = await session.scalars(
        select(PlayEvent)
        .where(PlayEvent.user_id == user_id)
        .order_by(PlayEvent.started_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows)


async def artist_top_tracks(
    session: AsyncSession, artist_id: uuid.UUID, limit: int = 10
) -> list[Track]:
    rows = await session.scalars(
        select(Track)
        .join(TrackArtist, TrackArtist.track_id == Track.id)
        .where(TrackArtist.artist_id == artist_id)
        .order_by(Track.play_count.desc())
        .limit(limit)
    )
    return list(rows)

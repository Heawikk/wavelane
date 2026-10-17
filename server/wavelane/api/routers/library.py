"""The signed-in user's library: reactions, history, playback reporting."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from ...models import Album, Artist, Track
from ...schemas.catalog import AlbumBrief, ArtistBrief, TrackOut
from ...schemas.common import Message, Page
from ...schemas.library import (
    ArtistReactionRequest,
    HistoryEntry,
    LibraryStats,
    PlayReport,
    PlayReportResult,
    ReactionOut,
    ReactionRequest,
)
from ...services.catalog import serialize_tracks
from ...services.library import (
    followed_artists,
    library_stats,
    liked_tracks,
    play_history,
    record_play,
    saved_albums,
    set_artist_reaction,
    set_track_reaction,
    toggle_saved_album,
)
from ..deps import CurrentUser, DbSession, PageParams

router = APIRouter(prefix="/library", tags=["library"])


@router.get("/stats", response_model=LibraryStats, summary="Library totals")
async def stats(user: CurrentUser, db: DbSession) -> LibraryStats:
    return LibraryStats.model_validate(await library_stats(db, user.id))


# ---------------------------------------------------------------------------
# Track reactions
# ---------------------------------------------------------------------------


@router.put(
    "/tracks/{track_id}/reaction",
    response_model=ReactionOut,
    summary="Like or dislike a track (sending the same value clears it)",
)
async def react_to_track(
    track_id: uuid.UUID, payload: ReactionRequest, user: CurrentUser, db: DbSession
) -> ReactionOut:
    track = await db.get(Track, track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="track not found")
    kind = await set_track_reaction(db, user.id, track, payload.kind)
    return ReactionOut(track_id=track_id, kind=kind)


@router.get("/liked", response_model=Page[TrackOut], summary="Liked tracks")
async def get_liked(
    user: CurrentUser, db: DbSession, page: PageParams
) -> Page[TrackOut]:
    tracks = await liked_tracks(db, user.id, limit=page.limit, offset=page.offset)
    items = await serialize_tracks(db, tracks, user.id)
    return Page(items=items, limit=page.limit, offset=page.offset)


# ---------------------------------------------------------------------------
# Artists and albums
# ---------------------------------------------------------------------------


@router.put(
    "/artists/{artist_id}/reaction",
    response_model=Message,
    summary="Follow or ban an artist",
)
async def react_to_artist(
    artist_id: uuid.UUID,
    payload: ArtistReactionRequest,
    user: CurrentUser,
    db: DbSession,
) -> Message:
    artist = await db.get(Artist, artist_id)
    if artist is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artist not found")
    kind = await set_artist_reaction(db, user.id, artist_id, payload.kind)
    if kind is None:
        return Message(detail="reaction cleared")
    return Message(
        detail="artist followed" if kind == "follow"
        else "artist banned; the wave will not play them"
    )


@router.get("/artists", response_model=list[ArtistBrief], summary="Followed artists")
async def get_followed(user: CurrentUser, db: DbSession) -> list[ArtistBrief]:
    artists = await followed_artists(db, user.id)
    return [ArtistBrief.model_validate(artist) for artist in artists]


@router.put(
    "/albums/{album_id}", response_model=Message, summary="Save or unsave an album"
)
async def save_album(album_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Message:
    album = await db.get(Album, album_id)
    if album is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="album not found")
    saved = await toggle_saved_album(db, user.id, album_id)
    return Message(detail="album saved" if saved else "album removed from library")


@router.get("/albums", response_model=Page[AlbumBrief], summary="Saved albums")
async def get_saved_albums(
    user: CurrentUser, db: DbSession, page: PageParams
) -> Page[AlbumBrief]:
    albums = await saved_albums(db, user.id, limit=page.limit, offset=page.offset)
    return Page(
        items=[AlbumBrief.model_validate(album) for album in albums],
        limit=page.limit,
        offset=page.offset,
    )


# ---------------------------------------------------------------------------
# Playback reporting
# ---------------------------------------------------------------------------


@router.post(
    "/plays",
    response_model=PlayReportResult,
    summary="Report that a track was played, skipped or finished",
)
async def report_play(
    payload: PlayReport, user: CurrentUser, db: DbSession
) -> PlayReportResult:
    track = await db.get(Track, payload.track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="track not found")

    outcome = await record_play(
        db,
        user.id,
        track,
        ms_played=payload.ms_played,
        completed=payload.completed,
        skipped=payload.skipped,
        context_type=payload.context_type,
        context_id=payload.context_id,
        started_at=payload.started_at,
    )
    return PlayReportResult(
        recorded=outcome.recorded,
        completion=outcome.completion,
        counted_as=outcome.counted_as,
    )


@router.get("/history", response_model=Page[HistoryEntry], summary="Listening history")
async def get_history(
    user: CurrentUser, db: DbSession, page: PageParams
) -> Page[HistoryEntry]:
    events = await play_history(db, user.id, limit=page.limit, offset=page.offset)
    tracks = await serialize_tracks(db, [event.track for event in events], user.id)
    by_id = {item.id: item for item in tracks}

    items = [
        HistoryEntry(
            track=by_id[event.track_id],
            started_at=event.started_at,
            ms_played=event.ms_played,
            completion=event.completion,
            completed=event.completed,
            skipped=event.skipped,
            context_type=event.context_type,
        )
        for event in events
        if event.track_id in by_id
    ]
    return Page(items=items, limit=page.limit, offset=page.offset)

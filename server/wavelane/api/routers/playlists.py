"""Playlist CRUD and track ordering."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import or_, select

from ...models import Playlist, User
from ...schemas.common import Message, Page
from ...schemas.library import (
    PlaylistBrief,
    PlaylistCreate,
    PlaylistOut,
    PlaylistReorder,
    PlaylistTracksAdd,
    PlaylistUpdate,
)
from ...services.catalog import serialize_tracks
from ...services.library import (
    add_playlist_tracks,
    clear_playlist,
    create_playlist,
    remove_playlist_track,
    reorder_playlist,
)
from ..deps import CurrentUser, DbSession, OptionalUser, PageParams

router = APIRouter(prefix="/playlists", tags=["playlists"])


async def _load_playlist(
    db: DbSession, playlist_id: uuid.UUID, user: User | None, *, write: bool
) -> Playlist:
    playlist = await db.get(Playlist, playlist_id)
    if playlist is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="playlist not found"
        )

    is_owner = user is not None and playlist.owner_id == user.id
    if write:
        if not is_owner and not (user is not None and user.is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="only the owner can change this playlist",
            )
    elif not playlist.is_public and not is_owner:
        # Don't confirm that a private playlist exists.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="playlist not found"
        )
    return playlist


async def _to_out(db: DbSession, playlist: Playlist, user: User | None) -> PlaylistOut:
    owner = await db.get(User, playlist.owner_id)
    tracks = await serialize_tracks(
        db,
        [item.track for item in playlist.items],
        user.id if user else None,
    )
    return PlaylistOut(
        id=playlist.id,
        title=playlist.title,
        description=playlist.description,
        cover_path=playlist.cover_path,
        is_public=playlist.is_public,
        track_count=playlist.track_count,
        duration_ms=playlist.duration_ms,
        created_at=playlist.created_at,
        updated_at=playlist.updated_at,
        owner_id=playlist.owner_id,
        owner_name=owner.display_name if owner else None,
        tracks=tracks,
    )


@router.get("", response_model=Page[PlaylistBrief], summary="Your playlists")
async def list_playlists(
    user: CurrentUser, db: DbSession, page: PageParams
) -> Page[PlaylistBrief]:
    rows = await db.scalars(
        select(Playlist)
        .where(Playlist.owner_id == user.id)
        .order_by(Playlist.updated_at.desc())
        .limit(page.limit)
        .offset(page.offset)
    )
    return Page(
        items=[PlaylistBrief.model_validate(p) for p in rows],
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/public", response_model=Page[PlaylistBrief], summary="Public playlists")
async def list_public_playlists(
    db: DbSession, page: PageParams, user: OptionalUser
) -> Page[PlaylistBrief]:
    condition = Playlist.is_public.is_(True)
    if user is not None:
        condition = or_(condition, Playlist.owner_id == user.id)
    rows = await db.scalars(
        select(Playlist)
        .where(condition)
        .order_by(Playlist.updated_at.desc())
        .limit(page.limit)
        .offset(page.offset)
    )
    return Page(
        items=[PlaylistBrief.model_validate(p) for p in rows],
        limit=page.limit,
        offset=page.offset,
    )


@router.post(
    "", response_model=PlaylistOut, status_code=status.HTTP_201_CREATED,
    summary="Create a playlist",
)
async def create(
    payload: PlaylistCreate, user: CurrentUser, db: DbSession
) -> PlaylistOut:
    playlist = await create_playlist(
        db,
        user.id,
        title=payload.title,
        description=payload.description,
        is_public=payload.is_public,
        track_ids=payload.track_ids,
    )
    await db.refresh(playlist, ["items"])
    return await _to_out(db, playlist, user)


@router.get("/{playlist_id}", response_model=PlaylistOut, summary="One playlist")
async def get_playlist(
    playlist_id: uuid.UUID, db: DbSession, user: OptionalUser
) -> PlaylistOut:
    playlist = await _load_playlist(db, playlist_id, user, write=False)
    await db.refresh(playlist, ["items"])
    return await _to_out(db, playlist, user)


@router.patch("/{playlist_id}", response_model=PlaylistOut, summary="Rename or share")
async def update_playlist(
    playlist_id: uuid.UUID,
    payload: PlaylistUpdate,
    db: DbSession,
    user: CurrentUser,
) -> PlaylistOut:
    playlist = await _load_playlist(db, playlist_id, user, write=True)
    if payload.title:
        playlist.title = payload.title.strip()
    if payload.description is not None:
        playlist.description = payload.description
    if payload.is_public is not None:
        playlist.is_public = payload.is_public
    await db.flush()
    await db.refresh(playlist, ["items"])
    return await _to_out(db, playlist, user)


@router.delete("/{playlist_id}", response_model=Message, summary="Delete a playlist")
async def delete_playlist(
    playlist_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> Message:
    playlist = await _load_playlist(db, playlist_id, user, write=True)
    title = playlist.title
    await db.delete(playlist)
    await db.flush()
    return Message(detail=f'playlist "{title}" deleted')


@router.post(
    "/{playlist_id}/tracks", response_model=PlaylistOut, summary="Add tracks"
)
async def add_tracks(
    playlist_id: uuid.UUID,
    payload: PlaylistTracksAdd,
    db: DbSession,
    user: CurrentUser,
) -> PlaylistOut:
    playlist = await _load_playlist(db, playlist_id, user, write=True)
    added = await add_playlist_tracks(
        db,
        playlist,
        payload.track_ids,
        position=payload.position,
        added_by_id=user.id,
    )
    if added == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="none of the given track ids exist",
        )
    await db.refresh(playlist, ["items"])
    return await _to_out(db, playlist, user)


@router.delete(
    "/{playlist_id}/tracks/{track_id}", response_model=PlaylistOut, summary="Remove a track"
)
async def remove_track(
    playlist_id: uuid.UUID,
    track_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
) -> PlaylistOut:
    playlist = await _load_playlist(db, playlist_id, user, write=True)
    removed = await remove_playlist_track(db, playlist, track_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="track is not in this playlist"
        )
    await db.refresh(playlist, ["items"])
    return await _to_out(db, playlist, user)


@router.put(
    "/{playlist_id}/order", response_model=PlaylistOut, summary="Reorder the playlist"
)
async def reorder(
    playlist_id: uuid.UUID,
    payload: PlaylistReorder,
    db: DbSession,
    user: CurrentUser,
) -> PlaylistOut:
    playlist = await _load_playlist(db, playlist_id, user, write=True)
    await reorder_playlist(db, playlist, payload.track_ids)
    await db.refresh(playlist, ["items"])
    return await _to_out(db, playlist, user)


@router.delete(
    "/{playlist_id}/tracks", response_model=Message, summary="Remove every track"
)
async def clear(playlist_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Message:
    playlist = await _load_playlist(db, playlist_id, user, write=True)
    await clear_playlist(db, playlist)
    return Message(detail="playlist emptied")

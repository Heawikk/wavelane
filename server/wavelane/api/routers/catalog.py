"""Browsing the catalogue: tracks, artists, albums, genres, search."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

import anyio
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select

from ...models import Album, Artist, Genre, Track, TrackArtist, TrackGenre
from ...schemas.catalog import (
    AlbumBrief,
    AlbumOut,
    AlbumUpdate,
    ArtistBrief,
    ArtistOut,
    ArtistUpdate,
    GenreOut,
    TrackOut,
    TrackUpdate,
)
from ...schemas.common import Page
from ...schemas.library import SearchResults
from ...schemas.upload import DeleteResult, DeleteTracksRequest
from ...services.catalog import (
    count_query,
    ready_tracks,
    search_albums,
    search_artists,
    search_pattern,
    search_tracks,
    serialize_tracks,
    track_matches,
    tracks_for_genre,
)
from ...services.editing import EditError, set_track_album, set_track_artists
from ...services.storage import looks_like_image
from ...services.removal import delete_tracks, unlink_audio
from ...utils import normalize_name, slugify
from ..deps import (
    AdminUser,
    CurrentUser,
    DbSession,
    FileStorage,
    OptionalUser,
    PageParams,
    get_current_user,
)

# Nothing in the catalogue is public: browsing it needs an account, like streaming does.
router = APIRouter(tags=["catalogue"], dependencies=[Depends(get_current_user)])

TrackSort = Literal["popular", "recent", "title", "duration"]


def _apply_track_sort(query, sort: TrackSort):
    if sort == "recent":
        return query.order_by(Track.created_at.desc())
    if sort == "title":
        return query.order_by(Track.title)
    if sort == "duration":
        return query.order_by(Track.duration_ms.desc())
    return query.order_by(Track.play_count.desc(), Track.title)


# ---------------------------------------------------------------------------
# Tracks
# ---------------------------------------------------------------------------


@router.get("/tracks", response_model=Page[TrackOut], summary="List tracks")
async def list_tracks(
    db: DbSession,
    page: PageParams,
    user: OptionalUser,
    sort: TrackSort = "popular",
    genre: Annotated[str | None, Query(description="Genre slug filter")] = None,
    q: Annotated[
        str | None, Query(max_length=200, description="Only tracks matching this text")
    ] = None,
) -> Page[TrackOut]:
    query = ready_tracks()
    if q:
        pattern = search_pattern(q)
        if pattern is not None:
            query = query.where(track_matches(pattern))
    if genre:
        query = query.where(
            Track.genre_links.any(
                TrackGenre.genre_id.in_(
                    select(Genre.id).where(Genre.slug == genre).scalar_subquery()
                )
            )
        )
    total = await count_query(db, query)
    rows = await db.scalars(
        _apply_track_sort(query, sort).limit(page.limit).offset(page.offset)
    )
    items = await serialize_tracks(db, list(rows), user.id if user else None)
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/tracks/{track_id}", response_model=TrackOut, summary="One track")
async def get_track(track_id: uuid.UUID, db: DbSession, user: OptionalUser) -> TrackOut:
    track = await db.get(Track, track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="track not found")
    items = await serialize_tracks(
        db, [track], user.id if user else None, include_features=True
    )
    return items[0]


@router.patch("/tracks/{track_id}", response_model=TrackOut, summary="Fix track metadata")
async def update_track(
    track_id: uuid.UUID,
    payload: TrackUpdate,
    db: DbSession,
    user: CurrentUser,
) -> TrackOut:
    track = await db.get(Track, track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="track not found")
    if not user.is_admin and track.uploaded_by_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only the uploader or an administrator can edit this track",
        )

    if payload.title:
        track.title = payload.title.strip()
        track.normalized_title = normalize_name(track.title)
    for field in ("track_number", "disc_number", "explicit", "lyrics", "isrc"):
        value = getattr(payload, field)
        if value is not None:
            setattr(track, field, value)

    if payload.genres is not None:
        await _replace_genres(db, track, payload.genres)

    try:
        if payload.artists is not None or payload.featured_artists is not None:
            await set_track_artists(db, track, payload.artists, payload.featured_artists)
        if payload.album is not None or payload.release_year is not None:
            await set_track_album(db, track, payload.album, payload.release_year)
    except EditError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    await db.flush()
    items = await serialize_tracks(db, [track], user.id, include_features=True)
    return items[0]


async def _replace_genres(db, track: Track, genres: list[str]) -> None:
    # Work through the loaded collection rather than inserting rows directly:
    # delete-orphan turns the clear() into row deletions, and appending keeps
    # the in-memory collection correct so the response shows the new genres.
    track.genre_links.clear()
    await db.flush()
    for name in genres:
        slug = slugify(name)
        if not slug:
            continue
        genre = await db.scalar(select(Genre).where(Genre.slug == slug))
        if genre is None:
            genre = Genre(name=name.strip(), slug=slug)
            db.add(genre)
            await db.flush()
        track.genre_links.append(TrackGenre(genre=genre))
    await db.flush()


@router.post(
    "/tracks/bulk-delete",
    response_model=DeleteResult,
    summary="Delete several tracks and their files (administrator)",
)
async def bulk_delete_tracks(
    payload: DeleteTracksRequest, db: DbSession, admin: AdminUser, storage: FileStorage
) -> DeleteResult:
    return await _delete(db, storage, payload.track_ids)


@router.delete(
    "/tracks/{track_id}",
    response_model=DeleteResult,
    summary="Delete a track and its file (administrator)",
)
async def delete_track(
    track_id: uuid.UUID, db: DbSession, admin: AdminUser, storage: FileStorage
) -> DeleteResult:
    result = await _delete(db, storage, [track_id])
    if result.deleted == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="track not found")
    return result


async def _delete(db, storage, track_ids: list[uuid.UUID]) -> DeleteResult:
    stats = await delete_tracks(db, track_ids)
    # Commit before touching the disk: if the transaction failed, rows must not
    # be left pointing at files that are already gone.
    await db.commit()
    removed = await anyio.to_thread.run_sync(unlink_audio, storage, stats.paths)
    return DeleteResult(
        deleted=stats.deleted,
        files_removed=removed,
        albums_removed=stats.albums_removed,
        artists_removed=stats.artists_removed,
    )


# ---------------------------------------------------------------------------
# Artists
# ---------------------------------------------------------------------------


@router.get("/artists", response_model=Page[ArtistOut], summary="List artists")
async def list_artists(
    db: DbSession,
    page: PageParams,
    sort: Literal["popular", "name"] = "popular",
    q: Annotated[str | None, Query(max_length=200, description="Only names containing this")] = None,
) -> Page[ArtistOut]:
    query = select(Artist)
    if q:
        pattern = search_pattern(q)
        if pattern is not None:
            query = query.where(Artist.normalized_name.like(pattern))
    total = await count_query(db, query)
    ordering = (
        (Artist.normalized_name,) if sort == "name" else (Artist.play_count.desc(), Artist.name)
    )
    rows = await db.scalars(query.order_by(*ordering).limit(page.limit).offset(page.offset))
    return Page(
        items=[ArtistOut.model_validate(a) for a in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/artists/{artist_id}", response_model=ArtistOut, summary="One artist")
async def get_artist(artist_id: uuid.UUID, db: DbSession) -> ArtistOut:
    artist = await db.get(Artist, artist_id)
    if artist is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artist not found")
    return ArtistOut.model_validate(artist)


@router.get(
    "/artists/{artist_id}/tracks",
    response_model=Page[TrackOut],
    summary="An artist's tracks",
)
async def artist_tracks(
    artist_id: uuid.UUID, db: DbSession, page: PageParams, user: OptionalUser
) -> Page[TrackOut]:
    query = ready_tracks().where(
        Track.artist_links.any(TrackArtist.artist_id == artist_id)
    )
    total = await count_query(db, query)
    rows = await db.scalars(
        query.order_by(Track.play_count.desc()).limit(page.limit).offset(page.offset)
    )
    items = await serialize_tracks(db, list(rows), user.id if user else None)
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get(
    "/artists/{artist_id}/albums",
    response_model=list[AlbumBrief],
    summary="An artist's albums",
)
async def artist_albums(artist_id: uuid.UUID, db: DbSession) -> list[AlbumBrief]:
    rows = await db.scalars(
        select(Album)
        .where(Album.artist_id == artist_id)
        .order_by(Album.release_year.desc().nullslast(), Album.title)
    )
    return [AlbumBrief.model_validate(album) for album in rows]


@router.patch("/artists/{artist_id}", response_model=ArtistOut, summary="Edit an artist")
async def update_artist(
    artist_id: uuid.UUID, payload: ArtistUpdate, db: DbSession, admin: AdminUser
) -> ArtistOut:
    artist = await db.get(Artist, artist_id)
    if artist is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artist not found")
    if payload.name:
        name = " ".join(payload.name.split())
        normalized = normalize_name(name)
        taken = await db.scalar(
            select(Artist.id).where(Artist.normalized_name == normalized, Artist.id != artist.id)
        )
        if taken is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="another artist already has this name",
            )
        artist.name = name
        artist.normalized_name = normalized
    if payload.bio is not None:
        artist.bio = payload.bio.strip() or None
    if payload.country is not None:
        artist.country = payload.country.upper() or None
    await db.flush()
    return ArtistOut.model_validate(artist)


# A photo is shrunk by the client before it is sent; this is only the ceiling.
MAX_ARTIST_IMAGE_BYTES = 1_500_000


@router.post(
    "/artists/{artist_id}/image",
    response_model=ArtistOut,
    summary="Set an artist's picture (administrator)",
)
async def set_artist_image(
    artist_id: uuid.UUID,
    db: DbSession,
    admin: AdminUser,
    storage: FileStorage,
    image: UploadFile = File(..., description="PNG, JPEG or WebP"),
) -> ArtistOut:
    artist = await db.get(Artist, artist_id)
    if artist is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artist not found")

    data = await image.read(MAX_ARTIST_IMAGE_BYTES + 1)
    await image.close()
    if len(data) > MAX_ARTIST_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="the picture is too large"
        )
    # What the upload claims to be is not enough: only real PNG, JPEG and WebP files are kept.
    if not looks_like_image(data):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="the picture must be a PNG, JPEG or WebP image",
        )
    artist.image_path = await anyio.to_thread.run_sync(
        storage.save_cover, data, image.content_type
    )
    await db.flush()
    return ArtistOut.model_validate(artist)


@router.delete(
    "/artists/{artist_id}/image",
    response_model=ArtistOut,
    summary="Remove an artist's picture (administrator)",
)
async def remove_artist_image(
    artist_id: uuid.UUID, db: DbSession, admin: AdminUser
) -> ArtistOut:
    artist = await db.get(Artist, artist_id)
    if artist is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artist not found")
    artist.image_path = None
    await db.flush()
    return ArtistOut.model_validate(artist)


# ---------------------------------------------------------------------------
# Albums
# ---------------------------------------------------------------------------


@router.get("/albums", response_model=Page[AlbumOut], summary="List albums")
async def list_albums(db: DbSession, page: PageParams) -> Page[AlbumOut]:
    total = int(await db.scalar(select(func.count()).select_from(Album)) or 0)
    rows = await db.scalars(
        select(Album)
        .order_by(Album.release_year.desc().nullslast(), Album.title)
        .limit(page.limit)
        .offset(page.offset)
    )
    return Page(
        items=[AlbumOut.model_validate(a) for a in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/albums/{album_id}", response_model=AlbumOut, summary="One album")
async def get_album(album_id: uuid.UUID, db: DbSession) -> AlbumOut:
    album = await db.get(Album, album_id)
    if album is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="album not found")
    return AlbumOut.model_validate(album)


@router.get(
    "/albums/{album_id}/tracks", response_model=list[TrackOut], summary="An album's tracks"
)
async def album_tracks(
    album_id: uuid.UUID, db: DbSession, user: OptionalUser
) -> list[TrackOut]:
    rows = await db.scalars(
        ready_tracks()
        .where(Track.album_id == album_id)
        .order_by(Track.disc_number, Track.track_number, Track.title)
    )
    return await serialize_tracks(db, list(rows), user.id if user else None)


@router.patch("/albums/{album_id}", response_model=AlbumOut, summary="Edit an album")
async def update_album(
    album_id: uuid.UUID, payload: AlbumUpdate, db: DbSession, admin: AdminUser
) -> AlbumOut:
    album = await db.get(Album, album_id)
    if album is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="album not found")
    if payload.title:
        album.title = payload.title.strip()
        album.normalized_title = normalize_name(album.title)
    if payload.album_type is not None:
        album.album_type = payload.album_type
    if payload.release_year is not None:
        album.release_year = payload.release_year
    if payload.label is not None:
        album.label = payload.label
    await db.flush()
    return AlbumOut.model_validate(album)


# ---------------------------------------------------------------------------
# Genres and search
# ---------------------------------------------------------------------------


@router.get("/genres", response_model=list[GenreOut], summary="All genres in the catalogue")
async def list_genres(db: DbSession) -> list[GenreOut]:
    rows = await db.scalars(select(Genre).order_by(Genre.name))
    return [GenreOut.model_validate(genre) for genre in rows]


@router.get(
    "/genres/{slug}/tracks", response_model=list[TrackOut], summary="Tracks in a genre"
)
async def genre_tracks(
    slug: str, db: DbSession, page: PageParams, user: OptionalUser
) -> list[TrackOut]:
    tracks = await tracks_for_genre(db, slug, limit=page.limit, offset=page.offset)
    return await serialize_tracks(db, tracks, user.id if user else None)


@router.get("/search", response_model=SearchResults, summary="Search the catalogue")
async def search(
    db: DbSession,
    user: OptionalUser,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> SearchResults:
    tracks = await search_tracks(db, q, limit=limit)
    return SearchResults(
        query=q,
        tracks=await serialize_tracks(db, tracks, user.id if user else None),
        artists=[
            ArtistBrief.model_validate(a) for a in await search_artists(db, q, limit=20)
        ],
        albums=[
            AlbumBrief.model_validate(a) for a in await search_albums(db, q, limit=40)
        ],
    )

"""Correcting the catalogue by hand: who a track is by, and which album it is on."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Album, Artist, Track, TrackArtist
from ..models.enums import ArtistRole
from ..utils import normalize_name


class EditError(ValueError):
    """The edit asked for something that cannot be done."""


def _clean_names(names: Iterable[str]) -> list[str]:
    """Trimmed, non-empty, without repeats (names that normalise alike count as one)."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in names:
        name = " ".join(raw.split())
        key = normalize_name(name)
        if name and key not in seen:
            seen.add(key)
            out.append(name)
    return out


async def get_or_create_artist(db: AsyncSession, name: str) -> Artist:
    normalized = normalize_name(name)
    artist = await db.scalar(select(Artist).where(Artist.normalized_name == normalized))
    if artist is None:
        artist = Artist(name=name, normalized_name=normalized, sort_name=name)
        db.add(artist)
        await db.flush()
    return artist


async def set_track_artists(
    db: AsyncSession,
    track: Track,
    main: list[str] | None,
    featured: list[str] | None,
) -> None:
    """Replace the artists of a track; a part that is left out (None) stays as it was."""
    links = list(track.artist_links)
    main_names = (
        _clean_names(main)
        if main is not None
        else [link.artist.name for link in links if link.role == ArtistRole.MAIN]
    )
    featured_names = (
        _clean_names(featured)
        if featured is not None
        else [link.artist.name for link in links if link.role == ArtistRole.FEATURED]
    )
    if not main_names:
        raise EditError("a track needs at least one artist")

    old_main_ids = {link.artist_id for link in links if link.role == ArtistRole.MAIN}

    main_artists = [await get_or_create_artist(db, name) for name in main_names]
    main_ids = {artist.id for artist in main_artists}
    featured_artists = [
        artist
        for artist in [await get_or_create_artist(db, name) for name in featured_names]
        if artist.id not in main_ids
    ]

    # Clearing and flushing first keeps a delete-orphan collection from trying to insert a row
    # that still exists (the same artist in the same role).
    # Remixers, composers and the like are not edited here, so they are put back as they were.
    others = [
        (link.artist, link.role)
        for link in links
        if link.role not in (ArtistRole.MAIN, ArtistRole.FEATURED)
    ]
    track.artist_links.clear()
    await db.flush()
    position = 0
    groups = [(ArtistRole.MAIN, main_artists), (ArtistRole.FEATURED, featured_artists)]
    groups += [(role, [artist]) for artist, role in others]
    for role, group in groups:
        for artist in group:
            track.artist_links.append(TrackArtist(artist=artist, role=role, position=position))
            position += 1
    await db.flush()

    # The counters on the artists follow who is a main artist of what.
    for artist in main_artists:
        if artist.id not in old_main_ids:
            artist.track_count += 1
    for artist_id in old_main_ids - main_ids:
        gone = await db.get(Artist, artist_id)
        if gone is not None:
            gone.track_count = max(0, gone.track_count - 1)
    await db.flush()


async def set_track_album(
    db: AsyncSession, track: Track, title: str | None, year: int | None
) -> None:
    """Move a track to the album called `title` (an empty title takes it off any album)."""
    current = track.album

    if title is not None:
        title = " ".join(title.split())
        if not title:
            if current is not None:
                # Without an album the artwork has to live on the track itself.
                track.cover_path = track.cover_path or current.cover_path
                track.album = None
            current = None
        elif current is None or normalize_name(title) != current.normalized_title:
            owner = next(
                (link.artist for link in track.artist_links if link.role == ArtistRole.MAIN),
                None,
            )
            if owner is None:
                raise EditError("a track needs an artist before it can be put on an album")
            normalized = normalize_name(title)
            album = await db.scalar(
                select(Album).where(
                    Album.artist_id == owner.id, Album.normalized_title == normalized
                )
            )
            if album is None:
                album = Album(
                    title=title,
                    normalized_title=normalized,
                    artist_id=owner.id,
                    # The artwork came with the file, so it goes along to the new album.
                    cover_path=(current.cover_path if current else None) or track.cover_path,
                    release_year=current.release_year if current else None,
                )
                db.add(album)
                await db.flush()
            track.album = album
            track.cover_path = None if album.cover_path else track.cover_path
            current = album

    if year is not None and current is not None:
        current.release_year = year
    await db.flush()

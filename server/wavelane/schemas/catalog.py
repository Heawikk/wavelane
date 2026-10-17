"""Catalogue response models."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import Field, computed_field

from ..models.enums import AlbumType, AnalysisSource, ArtistRole, TrackStatus
from .common import ORMModel


class GenreOut(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    parent_slug: str | None = None


class ArtistBrief(ORMModel):
    id: uuid.UUID
    name: str
    image_path: str | None = None


class ArtistOut(ArtistBrief):
    sort_name: str | None = None
    bio: str | None = None
    country: str | None = None
    track_count: int = 0
    listener_count: int = 0
    play_count: int = 0
    created_at: datetime | None = None


class ArtistCredit(ORMModel):
    """An artist plus the role they played on a given track."""

    id: uuid.UUID
    name: str
    role: ArtistRole = ArtistRole.MAIN
    position: int = 0

    @classmethod
    def from_link(cls, link) -> ArtistCredit:
        return cls(
            id=link.artist_id,
            name=link.artist.name,
            role=link.role,
            position=link.position,
        )


class AlbumBrief(ORMModel):
    id: uuid.UUID
    title: str
    cover_path: str | None = None
    release_year: int | None = None
    album_type: AlbumType = AlbumType.ALBUM


class AlbumOut(AlbumBrief):
    artist: ArtistBrief | None = None
    release_date: date | None = None
    label: str | None = None
    total_tracks: int = 0
    created_at: datetime | None = None


class AudioFeatureOut(ORMModel):
    tempo_bpm: float = 0.0
    energy: float = 0.5
    valence: float = 0.5
    danceability: float = 0.5
    acousticness: float = 0.5
    instrumentalness: float = 0.5
    brightness: float = 0.5
    loudness: float = 0.5
    dynamics: float = 0.5
    vocalness: float = 0.5
    language: str = "unknown"
    musical_key: int | None = None
    musical_mode: int | None = None
    source: AnalysisSource = AnalysisSource.METADATA


class TrackOut(ORMModel):
    id: uuid.UUID
    title: str
    duration_ms: int
    track_number: int | None = None
    disc_number: int = 1
    explicit: bool = False
    lossless: bool = False
    container: str | None = None
    codec: str | None = None
    bitrate_kbps: int | None = None
    sample_rate: int | None = None
    status: TrackStatus = TrackStatus.READY
    play_count: int = 0
    like_count: int = 0
    album: AlbumBrief | None = None
    artists: list[ArtistCredit] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    features: AudioFeatureOut | None = None
    # Filled in by the API for the requesting user.
    liked: bool | None = None
    disliked: bool | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def artist_name(self) -> str:
        """Flat display string, so simple clients need no joining logic."""
        main = [a.name for a in self.artists if a.role == ArtistRole.MAIN]
        featured = [a.name for a in self.artists if a.role == ArtistRole.FEATURED]
        base = ", ".join(main) or "Unknown Artist"
        if featured:
            return f"{base} feat. {', '.join(featured)}"
        return base

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cover_path(self) -> str | None:
        return self.album.cover_path if self.album else None

    @classmethod
    def from_track(
        cls,
        track,
        *,
        liked: bool | None = None,
        disliked: bool | None = None,
        include_features: bool = False,
    ) -> TrackOut:
        return cls(
            id=track.id,
            title=track.title,
            duration_ms=track.duration_ms,
            track_number=track.track_number,
            disc_number=track.disc_number,
            explicit=track.explicit,
            lossless=track.lossless,
            container=track.container,
            codec=track.codec,
            bitrate_kbps=track.bitrate_kbps,
            sample_rate=track.sample_rate,
            status=track.status,
            play_count=track.play_count,
            like_count=track.like_count,
            album=AlbumBrief.model_validate(track.album) if track.album else None,
            artists=sorted(
                (ArtistCredit.from_link(link) for link in track.artist_links),
                key=lambda credit: credit.position,
            ),
            genres=[link.genre.slug for link in track.genre_links if link.genre],
            features=(
                AudioFeatureOut.model_validate(track.features)
                if include_features and track.features
                else None
            ),
            liked=liked,
            disliked=disliked,
        )


class TrackUpdate(ORMModel):
    """Editable catalogue fields, for fixing bad tags after upload."""

    title: str | None = Field(default=None, min_length=1, max_length=400)
    track_number: int | None = Field(default=None, ge=0, le=999)
    disc_number: int | None = Field(default=None, ge=1, le=99)
    explicit: bool | None = None
    lyrics: str | None = None
    isrc: str | None = Field(default=None, max_length=20)
    genres: list[str] | None = None


class ArtistUpdate(ORMModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    bio: str | None = None
    country: str | None = Field(default=None, min_length=2, max_length=2)


class AlbumUpdate(ORMModel):
    title: str | None = Field(default=None, min_length=1, max_length=400)
    album_type: AlbumType | None = None
    release_year: int | None = Field(default=None, ge=1860, le=2200)
    label: str | None = Field(default=None, max_length=300)

"""Catalogue: artists, albums, tracks, genres and audio features."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, JsonType, TimestampMixin, uuid_pk
from .enums import AlbumType, AnalysisSource, ArtistRole, TrackStatus

if TYPE_CHECKING:
    from .user import User


class Genre(Base, TimestampMixin):
    __tablename__ = "genres"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    # Parent genre lets us roll "melodic techno" up into "electronic" when scoring.
    parent_slug: Mapped[str | None] = mapped_column(String(120), index=True)

    track_links: Mapped[list[TrackGenre]] = relationship(
        back_populates="genre", cascade="all, delete-orphan"
    )


class Artist(Base, TimestampMixin):
    __tablename__ = "artists"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    normalized_name: Mapped[str] = mapped_column(
        String(300), unique=True, index=True, nullable=False
    )
    sort_name: Mapped[str | None] = mapped_column(String(300), index=True)
    bio: Mapped[str | None] = mapped_column(Text)
    image_path: Mapped[str | None] = mapped_column(String(500))
    country: Mapped[str | None] = mapped_column(String(2))
    # Denormalised counters maintained by services, so hot reads stay cheap.
    track_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    listener_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    play_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    albums: Mapped[list[Album]] = relationship(
        back_populates="artist", cascade="all, delete-orphan"
    )
    track_links: Mapped[list[TrackArtist]] = relationship(
        back_populates="artist", cascade="all, delete-orphan"
    )


class Album(Base, TimestampMixin):
    __tablename__ = "albums"
    __table_args__ = (
        UniqueConstraint("artist_id", "normalized_title", name="uq_albums_artist_title"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    title: Mapped[str] = mapped_column(String(400), nullable=False, index=True)
    normalized_title: Mapped[str] = mapped_column(String(400), nullable=False, index=True)
    artist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("artists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    album_type: Mapped[AlbumType] = mapped_column(
        Enum(AlbumType, native_enum=False, length=20), default=AlbumType.ALBUM, nullable=False
    )
    release_date: Mapped[date | None] = mapped_column(Date)
    release_year: Mapped[int | None] = mapped_column(Integer, index=True)
    cover_path: Mapped[str | None] = mapped_column(String(500))
    label: Mapped[str | None] = mapped_column(String(300))
    total_tracks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    artist: Mapped[Artist] = relationship(back_populates="albums", lazy="joined")
    tracks: Mapped[list[Track]] = relationship(
        back_populates="album", cascade="all, delete-orphan", order_by="Track.track_number"
    )


class Track(Base, TimestampMixin):
    __tablename__ = "tracks"
    __table_args__ = (
        Index("ix_tracks_album_position", "album_id", "disc_number", "track_number"),
        Index("ix_tracks_popularity", "play_count"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    title: Mapped[str] = mapped_column(String(400), nullable=False, index=True)
    normalized_title: Mapped[str] = mapped_column(String(400), nullable=False, index=True)
    album_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("albums.id", ondelete="SET NULL"), index=True
    )
    track_number: Mapped[int | None] = mapped_column(Integer)
    disc_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # --- file ---------------------------------------------------------------
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    file_size: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    container: Mapped[str | None] = mapped_column(String(20))
    codec: Mapped[str | None] = mapped_column(String(30))
    bitrate_kbps: Mapped[int | None] = mapped_column(Integer)
    sample_rate: Mapped[int | None] = mapped_column(Integer)
    channels: Mapped[int | None] = mapped_column(Integer)
    lossless: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- editorial ----------------------------------------------------------
    explicit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    lyrics: Mapped[str | None] = mapped_column(Text)
    isrc: Mapped[str | None] = mapped_column(String(20), index=True)
    status: Mapped[TrackStatus] = mapped_column(
        Enum(TrackStatus, native_enum=False, length=20),
        default=TrackStatus.PENDING,
        nullable=False,
        index=True,
    )

    # --- counters -----------------------------------------------------------
    play_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    like_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skip_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    complete_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    album: Mapped[Album | None] = relationship(back_populates="tracks", lazy="joined")
    artist_links: Mapped[list[TrackArtist]] = relationship(
        back_populates="track",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="TrackArtist.position",
    )
    genre_links: Mapped[list[TrackGenre]] = relationship(
        back_populates="track", cascade="all, delete-orphan", lazy="selectin"
    )
    features: Mapped[AudioFeature | None] = relationship(
        back_populates="track", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    uploaded_by: Mapped[User | None] = relationship(foreign_keys=[uploaded_by_id])

    @property
    def main_artists(self) -> list[Artist]:
        return [link.artist for link in self.artist_links if link.role == ArtistRole.MAIN]

    @property
    def artist_display(self) -> str:
        return ", ".join(link.artist.name for link in self.artist_links)

    @property
    def skip_rate(self) -> float:
        served = self.skip_count + self.complete_count
        return self.skip_count / served if served else 0.0


class TrackArtist(Base):
    """Many-to-many between tracks and artists, carrying role and billing order."""

    __tablename__ = "track_artists"

    track_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True
    )
    artist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[ArtistRole] = mapped_column(
        Enum(ArtistRole, native_enum=False, length=20),
        default=ArtistRole.MAIN,
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    track: Mapped[Track] = relationship(back_populates="artist_links")
    artist: Mapped[Artist] = relationship(back_populates="track_links", lazy="joined")


class TrackGenre(Base):
    __tablename__ = "track_genres"

    track_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True
    )
    genre_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True
    )
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    track: Mapped[Track] = relationship(back_populates="genre_links")
    genre: Mapped[Genre] = relationship(back_populates="track_links", lazy="joined")


class AudioFeature(Base):
    """Per-track sonic descriptors; the wave engine scores candidates against these.

    Every 0..1 field is normalised so plain cosine distance between two tracks is
    meaningful. The ordered canonical form lives in ``vector`` (see wave/features.py)
    so scoring can work on numpy arrays without touching the ORM attributes.
    """

    __tablename__ = "audio_features"

    track_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True
    )

    tempo_bpm: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    energy: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    valence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    danceability: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    acousticness: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    instrumentalness: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    brightness: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    loudness: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    dynamics: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    vocalness: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)

    language: Mapped[str] = mapped_column(
        String(20), default="unknown", nullable=False, index=True
    )
    musical_key: Mapped[int | None] = mapped_column(Integer)
    musical_mode: Mapped[int | None] = mapped_column(Integer)

    vector: Mapped[list[float]] = mapped_column(JsonType, default=list, nullable=False)
    source: Mapped[AnalysisSource] = mapped_column(
        Enum(AnalysisSource, native_enum=False, length=20),
        default=AnalysisSource.METADATA,
        nullable=False,
    )
    analyzer_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    analyzed_at: Mapped[datetime | None] = mapped_column()

    track: Mapped[Track] = relationship(back_populates="features")

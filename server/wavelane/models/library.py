"""User library: reactions, playlists and the play-event log."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
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

from .base import Base, TimestampMixin, uuid_pk
from .catalog import Album, Artist, Track
from .enums import PlaybackContext
from .user import User


class TrackReaction(Base):
    """Like or dislike. One row per (user, track) so the two are mutually exclusive."""

    __tablename__ = "track_reactions"
    __table_args__ = (Index("ix_track_reactions_user_kind", "user_id", "kind"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    track_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), primary_key=True
    )
    # "like" | "dislike"
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    track: Mapped[Track] = relationship(lazy="joined")

    @property
    def is_like(self) -> bool:
        return self.kind == "like"


class ArtistReaction(Base):
    """Follow or ban an artist. A ban removes the artist from wave candidates."""

    __tablename__ = "artist_reactions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    artist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True
    )
    # "follow" | "ban"
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    artist: Mapped[Artist] = relationship(lazy="joined")


class SavedAlbum(Base):
    __tablename__ = "saved_albums"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    album_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("albums.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    album: Mapped[Album] = relationship(lazy="joined")


class Playlist(Base, TimestampMixin):
    __tablename__ = "playlists"

    id: Mapped[uuid.UUID] = uuid_pk()
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    cover_path: Mapped[str | None] = mapped_column(String(500))
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    track_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    owner: Mapped[User] = relationship()
    items: Mapped[list[PlaylistTrack]] = relationship(
        back_populates="playlist",
        cascade="all, delete-orphan",
        order_by="PlaylistTrack.position",
    )


class PlaylistTrack(Base):
    __tablename__ = "playlist_tracks"
    __table_args__ = (
        UniqueConstraint("playlist_id", "position", name="uq_playlist_tracks_position"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    playlist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    track_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    added_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    playlist: Mapped[Playlist] = relationship(back_populates="items")
    track: Mapped[Track] = relationship(lazy="joined")


class PlayEvent(Base):
    """Append-only listening log. This is the primary training signal for the wave.

    ``ms_played`` plus ``completed`` tell us far more than a play count does: a
    track abandoned after four seconds is a negative signal, the same track
    played to the end is a strong positive one.
    """

    __tablename__ = "play_events"
    __table_args__ = (
        Index("ix_play_events_user_time", "user_id", "started_at"),
        Index("ix_play_events_track_time", "track_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    track_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ms_played: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    skipped: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    context_type: Mapped[PlaybackContext] = mapped_column(
        Enum(PlaybackContext, native_enum=False, length=20),
        default=PlaybackContext.UNKNOWN,
        nullable=False,
    )
    context_id: Mapped[uuid.UUID | None] = mapped_column(index=True)

    track: Mapped[Track] = relationship(lazy="joined")

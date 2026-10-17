"""Persistent state for the Wave personalised-radio engine."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, JsonType, uuid_pk
from .catalog import Track
from .enums import WaveCharacter, WaveLanguage, WaveMood


class WaveSettings(Base):
    """The knobs the user turns in the UI: mood, character, language."""

    __tablename__ = "wave_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    mood: Mapped[WaveMood] = mapped_column(
        Enum(WaveMood, native_enum=False, length=20), default=WaveMood.ANY, nullable=False
    )
    character: Mapped[WaveCharacter] = mapped_column(
        Enum(WaveCharacter, native_enum=False, length=20),
        default=WaveCharacter.ANY,
        nullable=False,
    )
    language: Mapped[WaveLanguage] = mapped_column(
        Enum(WaveLanguage, native_enum=False, length=20),
        default=WaveLanguage.ANY,
        nullable=False,
    )
    # 0 = play it safe, 1 = surprise me. Drives the exploration share.
    diversity: Mapped[float] = mapped_column(Float, default=0.3, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TasteProfile(Base):
    """Long-term user taste, updated incrementally from every listening event.

    Two vectors are kept: what the user gravitates towards and what they push
    away. Scoring uses the difference, which keeps a disliked-but-similar genre
    from sneaking in just because it is close to the positive centroid.
    """

    __tablename__ = "taste_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    positive_vector: Mapped[list[float]] = mapped_column(JsonType, default=list, nullable=False)
    negative_vector: Mapped[list[float]] = mapped_column(JsonType, default=list, nullable=False)
    # slug -> affinity in roughly -1..1
    genre_affinity: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict, nullable=False)
    # artist uuid (as str) -> affinity in roughly -1..1
    artist_affinity: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict, nullable=False)
    # decade bucket (as str, e.g. "1990") -> affinity
    era_affinity: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict, nullable=False)
    language_affinity: Mapped[dict[str, Any]] = mapped_column(
        JsonType, default=dict, nullable=False
    )

    positive_weight: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    negative_weight: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Accumulated signal weight below which the vectors are too noisy to rank
    # with, and popularity is the better guess. Two explicit likes clear it;
    # so do six tracks played to the end.
    COLD_START_WEIGHT = 6.0

    @property
    def is_cold(self) -> bool:
        """Whether there is enough signal to personalise at all.

        Measured in accumulated weight, not event count: an explicit like says
        far more about taste than a track that merely finished playing, and
        counting events alike would keep a user who has liked five things
        pinned to the popularity ranking.
        """
        return (self.positive_weight + self.negative_weight) < self.COLD_START_WEIGHT


class WaveSession(Base):
    """One continuous listening session of the wave.

    ``session_vector`` adapts fast (within the session) while the taste profile
    adapts slowly, so a single dislike changes the next few tracks without
    rewriting the user's long-term profile.
    """

    __tablename__ = "wave_sessions"
    __table_args__ = (Index("ix_wave_sessions_user_active", "user_id", "is_active"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    settings_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JsonType, default=dict, nullable=False
    )
    session_vector: Mapped[list[float]] = mapped_column(JsonType, default=list, nullable=False)
    # Artist ids served in this session, newest last — used for the diversity rule.
    recent_artist_ids: Mapped[list[str]] = mapped_column(JsonType, default=list, nullable=False)
    banned_artist_ids: Mapped[list[str]] = mapped_column(JsonType, default=list, nullable=False)

    served_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skip_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    queue: Mapped[list[WaveQueueItem]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="WaveQueueItem.position",
    )


class WaveQueueItem(Base):
    """A planned or already-served track, with the reason it was chosen.

    Keeping the reason makes the engine debuggable and lets the client show
    "because you like X" style hints.
    """

    __tablename__ = "wave_queue_items"
    __table_args__ = (Index("ix_wave_queue_session_position", "session_id", "position"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wave_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    track_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    # "queued" | "served" | "played" | "skipped" | "dropped"
    state: Mapped[str] = mapped_column(String(12), default="queued", nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reason: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    served_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    session: Mapped[WaveSession] = relationship(back_populates="queue")
    track: Mapped[Track] = relationship(lazy="joined")

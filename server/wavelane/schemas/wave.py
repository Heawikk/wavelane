"""Schemas for the Wave endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from ..models.enums import FeedbackKind, WaveCharacter, WaveLanguage, WaveMood
from .catalog import TrackOut
from .common import ORMModel


class WaveSettingsOut(ORMModel):
    mood: WaveMood = WaveMood.ANY
    character: WaveCharacter = WaveCharacter.ANY
    language: WaveLanguage = WaveLanguage.ANY
    diversity: float = 0.3
    updated_at: datetime | None = None


class WaveSettingsUpdate(ORMModel):
    mood: WaveMood | None = None
    character: WaveCharacter | None = None
    language: WaveLanguage | None = None
    diversity: float | None = Field(
        default=None, ge=0.0, le=1.0,
        description="0 keeps close to known taste, 1 explores aggressively.",
    )


class WaveReasonFactor(ORMModel):
    factor: str
    value: float


class WaveReason(ORMModel):
    score: float
    source: str
    top_factors: list[WaveReasonFactor] = Field(default_factory=list)
    components: dict[str, float] = Field(default_factory=dict)


class WaveTrack(ORMModel):
    track: TrackOut
    position: int
    score: float
    reason: WaveReason
    stream_url: str


class WaveBatch(ORMModel):
    session_id: uuid.UUID
    settings: WaveSettingsOut
    items: list[WaveTrack] = Field(default_factory=list)
    generated_at: datetime


class WaveFeedbackRequest(ORMModel):
    track_id: uuid.UUID
    kind: FeedbackKind
    completion: float | None = Field(
        default=None, ge=0.0, le=1.0,
        description="Fraction of the track heard; makes a skip count properly.",
    )


class WaveFeedbackResult(ORMModel):
    applied: bool
    kind: str
    weight: float
    skip_streak: int = 0


class TasteProfileOut(ORMModel):
    event_count: int
    is_cold: bool
    positive: dict[str, float] | None = None
    negative: dict[str, float] | None = None
    top_genres: list[dict[str, Any]] = Field(default_factory=list)
    languages: dict[str, float] = Field(default_factory=dict)
    updated_at: datetime | None = None

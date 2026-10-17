"""Turning listening signals into an updated taste profile.

Two timescales run in parallel. The long-term profile is a weight-saturating
running average, so a thousand plays never freeze it but one odd evening cannot
rewrite it either. The session vector moves fast, which is what makes a dislike
audibly change the next few tracks.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    ArtistRole,
    AudioFeature,
    FeedbackKind,
    TasteProfile,
    Track,
    WaveSession,
)
from ..utils import clamp, now_utc
from .features import FEATURE_COUNT, NEUTRAL_VECTOR, canonical_genre, coerce_vector

logger = logging.getLogger(__name__)

# How strongly each signal moves the long-term profile.
SIGNAL_WEIGHTS: dict[FeedbackKind, float] = {
    FeedbackKind.LIKE: 3.0,
    FeedbackKind.COMPLETE: 1.0,
    FeedbackKind.SKIP: -1.2,
    FeedbackKind.DISLIKE: -4.0,
    FeedbackKind.UNLIKE: -0.4,
    FeedbackKind.BAN_ARTIST: -3.0,
}

# Past this, new events replace old ones instead of being averaged in — the
# profile keeps adapting forever rather than converging and going stale.
MAX_PROFILE_WEIGHT = 60.0

# The session reacts far faster than the profile; that is the whole point.
SESSION_LEARNING_RATE = 0.35

# A skip only counts against a track if the listener barely heard it. Walking
# away at 80% is not a rejection.
SKIP_COMPLETION_THRESHOLD = 0.35

AFFINITY_SCALE = 0.06
MAX_TRACKED_ARTISTS = 400
MAX_TRACKED_GENRES = 120


@dataclass(slots=True)
class FeedbackOutcome:
    kind: FeedbackKind
    weight: float
    applied: bool
    reason: str = ""


async def get_or_create_profile(session: AsyncSession, user_id: uuid.UUID) -> TasteProfile:
    profile = await session.get(TasteProfile, user_id)
    if profile is None:
        profile = TasteProfile(
            user_id=user_id,
            positive_vector=[],
            negative_vector=[],
            genre_affinity={},
            artist_affinity={},
            era_affinity={},
            language_affinity={},
            updated_at=now_utc(),
        )
        session.add(profile)
        await session.flush()
    return profile


async def apply_feedback(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    track: Track,
    kind: FeedbackKind,
    completion: float | None = None,
    wave_session: WaveSession | None = None,
) -> FeedbackOutcome:
    """Fold one listening signal into the profile and the live session."""
    weight = SIGNAL_WEIGHTS.get(kind, 0.0)

    if kind is FeedbackKind.SKIP:
        if completion is not None and completion > SKIP_COMPLETION_THRESHOLD:
            # Heard most of it, then moved on: not a rejection, just a nudge.
            weight *= 0.3
        if wave_session is not None:
            wave_session.skip_streak += 1
    elif kind in (FeedbackKind.LIKE, FeedbackKind.COMPLETE) and wave_session is not None:
        wave_session.skip_streak = 0

    profile = await get_or_create_profile(session, user_id)
    features = await _load_features(session, track)
    vector = coerce_vector(features.vector if features else None)

    if weight == 0.0:
        return FeedbackOutcome(kind=kind, weight=0.0, applied=False, reason="zero weight")

    if weight > 0:
        updated, new_weight = _blend(
            coerce_vector(profile.positive_vector) if profile.positive_vector else None,
            profile.positive_weight,
            vector,
            weight,
        )
        profile.positive_vector = [float(x) for x in updated]
        profile.positive_weight = new_weight
    else:
        updated, new_weight = _blend(
            coerce_vector(profile.negative_vector) if profile.negative_vector else None,
            profile.negative_weight,
            vector,
            abs(weight),
        )
        profile.negative_vector = [float(x) for x in updated]
        profile.negative_weight = new_weight

    _update_affinities(profile, track, features, weight)

    profile.event_count += 1
    profile.updated_at = now_utc()

    if wave_session is not None:
        _update_session_vector(wave_session, vector, weight)
        if kind is FeedbackKind.BAN_ARTIST:
            _ban_track_artists(wave_session, track)
        wave_session.last_active_at = now_utc()

    _update_track_counters(track, kind, completion)
    return FeedbackOutcome(kind=kind, weight=weight, applied=True)


async def _load_features(session: AsyncSession, track: Track) -> AudioFeature | None:
    features = getattr(track, "features", None)
    if features is not None:
        return features
    return await session.scalar(
        select(AudioFeature).where(AudioFeature.track_id == track.id)
    )


def _blend(
    current: np.ndarray | None,
    current_weight: float,
    vector: np.ndarray,
    weight: float,
) -> tuple[np.ndarray, float]:
    """Running average with a weight ceiling.

    Below the ceiling this is an exact weighted mean; at the ceiling it becomes
    an exponential moving average with rate ``weight / MAX_PROFILE_WEIGHT``.
    """
    if current is None or current_weight <= 0 or not np.any(current):
        return vector.copy(), min(weight, MAX_PROFILE_WEIGHT)

    effective_weight = min(current_weight, MAX_PROFILE_WEIGHT)
    total = effective_weight + weight
    blended = (current * effective_weight + vector * weight) / total
    return np.clip(blended, 0.0, 1.0), min(total, MAX_PROFILE_WEIGHT)


def _update_session_vector(
    wave_session: WaveSession, vector: np.ndarray, weight: float
) -> None:
    current = coerce_vector(wave_session.session_vector)
    if not np.any(wave_session.session_vector):
        current = vector.copy() if weight > 0 else NEUTRAL_VECTOR.copy()

    rate = SESSION_LEARNING_RATE * clamp(abs(weight) / 3.0, 0.25, 1.0)
    if weight > 0:
        updated = (1.0 - rate) * current + rate * vector
    else:
        # Reflect away from what was just rejected.
        updated = current + rate * (current - vector)

    wave_session.session_vector = [float(x) for x in np.clip(updated, 0.0, 1.0)]


def _update_affinities(
    profile: TasteProfile,
    track: Track,
    features: AudioFeature | None,
    weight: float,
) -> None:
    step = clamp(abs(weight) * AFFINITY_SCALE, 0.0, 0.5)
    sign = 1.0 if weight > 0 else -1.0

    genre_affinity = dict(profile.genre_affinity or {})
    for link in getattr(track, "genre_links", []) or []:
        slug = getattr(link.genre, "slug", None)
        if not slug:
            continue
        for key in {slug, canonical_genre(slug)}:
            genre_affinity[key] = _nudge(genre_affinity.get(key, 0.0), sign, step)
    profile.genre_affinity = _trim(genre_affinity, MAX_TRACKED_GENRES)

    artist_affinity = dict(profile.artist_affinity or {})
    for link in getattr(track, "artist_links", []) or []:
        # A feature credit says less about taste than a main credit does.
        scale = 1.0 if link.role == ArtistRole.MAIN else 0.5
        key = str(link.artist_id)
        artist_affinity[key] = _nudge(artist_affinity.get(key, 0.0), sign, step * scale)
    profile.artist_affinity = _trim(artist_affinity, MAX_TRACKED_ARTISTS)

    album = getattr(track, "album", None)
    year = getattr(album, "release_year", None) if album else None
    if year:
        era_affinity = dict(profile.era_affinity or {})
        decade = str((year // 10) * 10)
        era_affinity[decade] = _nudge(era_affinity.get(decade, 0.0), sign, step * 0.6)
        profile.era_affinity = era_affinity

    if features is not None and features.language and features.language != "unknown":
        language_affinity = dict(profile.language_affinity or {})
        language_affinity[features.language] = _nudge(
            language_affinity.get(features.language, 0.0), sign, step * 0.8
        )
        profile.language_affinity = language_affinity


def _nudge(current: float, sign: float, step: float) -> float:
    """Move towards +-1 with diminishing returns, so affinity saturates smoothly."""
    current = clamp(float(current), -1.0, 1.0)
    return round(clamp(current + sign * step * (1.0 - abs(current)), -1.0, 1.0), 4)


def _trim(affinity: dict[str, Any], limit: int) -> dict[str, Any]:
    """Keep the dictionary bounded: drop the entries closest to indifferent."""
    if len(affinity) <= limit:
        return affinity
    ranked = sorted(affinity.items(), key=lambda kv: abs(float(kv[1])), reverse=True)
    return dict(ranked[:limit])


def _ban_track_artists(wave_session: WaveSession, track: Track) -> None:
    banned = list(wave_session.banned_artist_ids or [])
    for link in getattr(track, "artist_links", []) or []:
        if link.role != ArtistRole.MAIN:
            continue
        key = str(link.artist_id)
        if key not in banned:
            banned.append(key)
    wave_session.banned_artist_ids = banned[-200:]


def _update_track_counters(
    track: Track, kind: FeedbackKind, completion: float | None
) -> None:
    if kind is FeedbackKind.LIKE:
        track.like_count += 1
    elif kind is FeedbackKind.UNLIKE:
        track.like_count = max(0, track.like_count - 1)
    elif kind is FeedbackKind.SKIP:
        if completion is None or completion <= SKIP_COMPLETION_THRESHOLD:
            track.skip_count += 1
    elif kind is FeedbackKind.COMPLETE:
        track.complete_count += 1


def profile_snapshot(profile: TasteProfile) -> dict[str, Any]:
    """Human-readable view of a profile, for the API and for debugging."""
    from .features import vector_to_dict

    positive = coerce_vector(profile.positive_vector)
    negative = coerce_vector(profile.negative_vector)
    top_genres = sorted(
        (profile.genre_affinity or {}).items(), key=lambda kv: -float(kv[1])
    )[:8]
    return {
        "event_count": profile.event_count,
        "is_cold": profile.is_cold,
        "positive": vector_to_dict(positive) if np.any(profile.positive_vector) else None,
        "negative": vector_to_dict(negative) if np.any(profile.negative_vector) else None,
        "top_genres": [{"slug": slug, "affinity": float(value)} for slug, value in top_genres],
        "languages": {k: float(v) for k, v in (profile.language_affinity or {}).items()},
        "updated_at": profile.updated_at,
    }


__all__ = [
    "FEATURE_COUNT",
    "MAX_PROFILE_WEIGHT",
    "SIGNAL_WEIGHTS",
    "FeedbackOutcome",
    "apply_feedback",
    "get_or_create_profile",
    "profile_snapshot",
]

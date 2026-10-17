"""Scoring weights and the per-candidate score computation.

Kept apart from the engine so the ranking maths can be unit-tested without a
database, and so the weights are in one place when they need tuning.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from ..models.enums import WaveCharacter, WaveMood
from ..utils import clamp
from .features import (
    FEATURE_COUNT,
    coerce_vector,
    cosine_similarity,
    mood_arrays,
    weighted_distance,
)


@dataclass(frozen=True, slots=True)
class ScoringWeights:
    """How much each signal contributes before penalties."""

    taste: float = 1.00
    mood: float = 0.70
    genre: float = 0.55
    artist: float = 0.45
    era: float = 0.15
    language: float = 0.20
    popularity: float = 0.30
    freshness: float = 0.12

    # Penalties (subtracted).
    artist_repeat: float = 0.90
    recent_play: float = 0.70
    global_skip_rate: float = 0.35
    disliked_similarity: float = 0.60

    # How much of the taste vector comes from the live session rather than the
    # long-term profile. A dislike should bend the next few tracks without
    # rewriting who the listener is.
    session_blend: float = 0.40

    def for_character(self, character: WaveCharacter) -> ScoringWeights:
        """Shift the weighting to match the requested 'character' setting."""
        if character is WaveCharacter.FAVOURITE:
            return replace(self, taste=1.40, popularity=0.15, freshness=0.04, artist=0.70)
        if character is WaveCharacter.UNFAMILIAR:
            return replace(self, taste=0.75, popularity=0.05, freshness=0.45, artist=0.15)
        if character is WaveCharacter.POPULAR:
            return replace(self, taste=0.70, popularity=1.10, freshness=0.10)
        return self

    def for_cold_start(self) -> ScoringWeights:
        """With no history the taste vector is noise; lean on popularity."""
        return replace(self, taste=0.25, popularity=1.00, genre=0.25, artist=0.10)


DEFAULT_WEIGHTS = ScoringWeights()


@dataclass(slots=True)
class UserContext:
    """Everything about the listener that scoring needs, already in numpy form."""

    user_id: uuid.UUID
    positive_vector: np.ndarray
    negative_vector: np.ndarray
    session_vector: np.ndarray
    genre_affinity: dict[str, float] = field(default_factory=dict)
    artist_affinity: dict[str, float] = field(default_factory=dict)
    era_affinity: dict[str, float] = field(default_factory=dict)
    language_affinity: dict[str, float] = field(default_factory=dict)
    is_cold: bool = True
    has_negative: bool = False

    # Session state
    recent_artist_ids: list[str] = field(default_factory=list)
    recent_track_ids: set[str] = field(default_factory=set)
    played_track_ids: set[str] = field(default_factory=set)
    liked_track_ids: set[str] = field(default_factory=set)
    disliked_vectors: list[np.ndarray] = field(default_factory=list)

    def effective_taste(self, blend: float) -> np.ndarray:
        """Blend long-term taste with the current session's drift."""
        if not np.any(self.session_vector):
            return self.positive_vector
        if not np.any(self.positive_vector):
            return self.session_vector
        return (1.0 - blend) * self.positive_vector + blend * self.session_vector


@dataclass(slots=True)
class Candidate:
    """A track reduced to the fields scoring touches."""

    track_id: uuid.UUID
    artist_ids: list[uuid.UUID]
    album_id: uuid.UUID | None
    vector: np.ndarray
    genre_slugs: list[str]
    language: str
    release_year: int | None
    play_count: int
    like_count: int
    skip_rate: float
    popularity: float = 0.0
    source: str = "pool"


@dataclass(slots=True)
class ScoredCandidate:
    candidate: Candidate
    score: float
    components: dict[str, float]

    @property
    def track_id(self) -> uuid.UUID:
        return self.candidate.track_id


def mood_fit(candidate_vector: np.ndarray, mood: WaveMood) -> float:
    """How well a track matches a mood, in 0..1."""
    target, weight = mood_arrays(mood)
    if not np.any(weight):
        return 1.0
    return clamp(1.0 - weighted_distance(candidate_vector, target, weight))


def apply_mood_gate(
    candidates: list[Candidate],
    mood: WaveMood,
    *,
    threshold: float = 0.65,
    min_keep: int = 60,
) -> list[Candidate]:
    """Narrow the pool to tracks that actually fit the mood.

    Mood has to gate rather than merely nudge. Added as one more weighted term
    it loses every time: a well-trained taste vector scores ~0.95 by cosine
    while the mood term can only contribute a fraction of that, so asking for
    'energetic' would return the same calm favourites as before. Selecting
    'energetic' is an instruction about *which* music may play, and taste then
    decides the order within what is left.

    The floor on how many candidates survive keeps the stream alive on a small
    catalogue, where nothing may clear the threshold.
    """
    if mood is WaveMood.ANY or not candidates:
        return candidates

    scored = [(mood_fit(candidate.vector, mood), candidate) for candidate in candidates]
    kept = [candidate for fit, candidate in scored if fit >= threshold]

    if len(kept) >= min_keep:
        return kept

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [candidate for _, candidate in scored[: max(min_keep, len(kept))]]


def popularity_score(play_count: int, max_play_count: int) -> float:
    """Log-compressed popularity in 0..1, so one viral track cannot dominate."""
    if max_play_count <= 0:
        return 0.0
    return clamp(math.log1p(play_count) / math.log1p(max_play_count))


def score_candidate(
    candidate: Candidate,
    context: UserContext,
    weights: ScoringWeights,
    mood: WaveMood,
    *,
    mood_target: np.ndarray | None = None,
    mood_weight: np.ndarray | None = None,
) -> ScoredCandidate:
    """Score one candidate. Returns the total plus a breakdown for explainability."""
    components: dict[str, float] = {}

    # --- taste match --------------------------------------------------------
    taste_vector = context.effective_taste(weights.session_blend)
    if np.any(taste_vector):
        # Centre both vectors: raw 0..1 features all point the same way, so
        # plain cosine similarity would be ~0.95 for every pair and carry no
        # information. Subtracting the neutral midpoint restores the contrast.
        taste_similarity = cosine_similarity(
            candidate.vector - 0.5, taste_vector - 0.5
        )
    else:
        taste_similarity = 0.0
    components["taste"] = weights.taste * taste_similarity

    # --- mood ---------------------------------------------------------------
    if mood is not WaveMood.ANY:
        if mood_target is None or mood_weight is None:
            mood_target, mood_weight = mood_arrays(mood)
        if np.any(mood_weight):
            distance = weighted_distance(candidate.vector, mood_target, mood_weight)
            components["mood"] = weights.mood * (1.0 - 2.0 * distance)
        else:
            components["mood"] = 0.0
    else:
        components["mood"] = 0.0

    # --- affinities ---------------------------------------------------------
    if candidate.genre_slugs and context.genre_affinity:
        values = [context.genre_affinity.get(slug, 0.0) for slug in candidate.genre_slugs]
        components["genre"] = weights.genre * float(np.mean(values))
    else:
        components["genre"] = 0.0

    if candidate.artist_ids and context.artist_affinity:
        values = [context.artist_affinity.get(str(a), 0.0) for a in candidate.artist_ids]
        components["artist"] = weights.artist * float(max(values))
    else:
        components["artist"] = 0.0

    if candidate.release_year and context.era_affinity:
        decade = str((candidate.release_year // 10) * 10)
        components["era"] = weights.era * context.era_affinity.get(decade, 0.0)
    else:
        components["era"] = 0.0

    if context.language_affinity:
        components["language"] = weights.language * context.language_affinity.get(
            candidate.language, 0.0
        )
    else:
        components["language"] = 0.0

    # --- popularity and novelty --------------------------------------------
    components["popularity"] = weights.popularity * candidate.popularity
    is_new_to_user = str(candidate.track_id) not in context.played_track_ids
    components["freshness"] = weights.freshness if is_new_to_user else 0.0

    # --- penalties ----------------------------------------------------------
    penalty = 0.0

    # Same artist served very recently in this session.
    if context.recent_artist_ids:
        window = context.recent_artist_ids[-4:]
        if any(str(a) in window for a in candidate.artist_ids):
            # Hardest right after the artist played, easing off further back.
            position = max(
                (window[::-1].index(str(a)) for a in candidate.artist_ids if str(a) in window),
                default=0,
            )
            penalty += weights.artist_repeat * (1.0 - position / len(window))
    components["artist_repeat"] = -penalty

    recent_penalty = 0.0
    if str(candidate.track_id) in context.recent_track_ids:
        recent_penalty = weights.recent_play
    components["recent_play"] = -recent_penalty

    # A track the whole catalogue skips is probably mistagged or broken.
    skip_penalty = weights.global_skip_rate * clamp(candidate.skip_rate)
    components["global_skip"] = -skip_penalty

    dislike_penalty = 0.0
    if context.disliked_vectors:
        similarities = [
            cosine_similarity(candidate.vector - 0.5, vector - 0.5)
            for vector in context.disliked_vectors
        ]
        worst = max(similarities)
        if worst > 0.5:
            dislike_penalty = weights.disliked_similarity * (worst - 0.5) * 2.0
    components["disliked_similarity"] = -dislike_penalty

    total = sum(components.values())
    return ScoredCandidate(candidate=candidate, score=total, components=components)


def rank_candidates(
    candidates: Iterable[Candidate],
    context: UserContext,
    weights: ScoringWeights,
    mood: WaveMood,
) -> list[ScoredCandidate]:
    mood_target, mood_weight = mood_arrays(mood)
    scored = [
        score_candidate(
            candidate,
            context,
            weights,
            mood,
            mood_target=mood_target,
            mood_weight=mood_weight,
        )
        for candidate in candidates
    ]
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored


def select_diverse(
    ranked: list[ScoredCandidate],
    count: int,
    *,
    exploration: float = 0.3,
    artist_window: int = 4,
    album_window: int = 8,
    similarity_penalty: float = 0.45,
    rng: np.random.Generator | None = None,
    recent_artist_ids: Iterable[str] = (),
) -> list[ScoredCandidate]:
    """Greedy selection that keeps a run of tracks from feeling repetitive.

    Pure top-N would hand back five songs by the same artist, all sounding
    alike. So each pick is penalised by how similar it is to what has already
    been chosen (an MMR-style rule), artists and albums get a cooldown window,
    and a share of picks is drawn from further down the ranking so the stream
    can still surprise.
    """
    if count <= 0 or not ranked:
        return []

    rng = rng or np.random.default_rng()
    remaining = list(ranked)
    chosen: list[ScoredCandidate] = []
    chosen_vectors: list[np.ndarray] = []
    artist_history: list[set[str]] = [
        {str(a)} for a in list(recent_artist_ids)[-artist_window:]
    ]
    album_history: list[str] = []

    while remaining and len(chosen) < count:
        best_index, best_adjusted = -1, -math.inf

        for index, item in enumerate(remaining):
            adjusted = item.score
            candidate_artists = {str(a) for a in item.candidate.artist_ids}

            recent_artists: set[str] = set()
            for entry in artist_history[-artist_window:]:
                recent_artists |= entry
            if candidate_artists & recent_artists:
                adjusted -= 1.5

            if item.candidate.album_id is not None:
                if str(item.candidate.album_id) in album_history[-album_window:]:
                    adjusted -= 0.4

            if chosen_vectors:
                closest = max(
                    cosine_similarity(item.candidate.vector - 0.5, vector - 0.5)
                    for vector in chosen_vectors
                )
                adjusted -= similarity_penalty * clamp(closest)

            if adjusted > best_adjusted:
                best_adjusted, best_index = adjusted, index

        if best_index < 0:
            break

        # Exploration: sometimes take a lower-ranked candidate on purpose, so a
        # settled profile does not collapse into the same twenty songs. The
        # artist cooldown still applies — hearing the same act twice in a row
        # reads as a bug, never as a discovery.
        if exploration > 0 and len(remaining) > 8 and rng.random() < exploration:
            recent_artists = set()
            for entry in artist_history[-artist_window:]:
                recent_artists |= entry
            tail_start = max(1, int(len(remaining) * 0.15))
            tail_end = min(len(remaining), max(tail_start + 1, int(len(remaining) * 0.6)))
            for _ in range(6):
                probe = int(rng.integers(tail_start, tail_end))
                probe_artists = {str(a) for a in remaining[probe].candidate.artist_ids}
                if not (probe_artists & recent_artists):
                    best_index = probe
                    break

        pick = remaining.pop(best_index)
        chosen.append(pick)
        chosen_vectors.append(pick.candidate.vector)
        artist_history.append({str(a) for a in pick.candidate.artist_ids})
        if pick.candidate.album_id is not None:
            album_history.append(str(pick.candidate.album_id))

    return chosen


def explain(scored: ScoredCandidate, top_n: int = 3) -> dict[str, Any]:
    """Compact, client-friendly reason for why this track was chosen."""
    contributions = {
        key: round(value, 4) for key, value in scored.components.items() if abs(value) > 1e-6
    }
    ordered = sorted(contributions.items(), key=lambda kv: abs(kv[1]), reverse=True)
    return {
        "score": round(scored.score, 4),
        "source": scored.candidate.source,
        "top_factors": [{"factor": key, "value": value} for key, value in ordered[:top_n]],
        "components": contributions,
    }


def ensure_vector(raw: Iterable[float] | None) -> np.ndarray:
    vector = coerce_vector(raw)
    if vector.size != FEATURE_COUNT:  # pragma: no cover - coerce_vector guarantees size
        raise ValueError(f"expected {FEATURE_COUNT} features, got {vector.size}")
    return vector

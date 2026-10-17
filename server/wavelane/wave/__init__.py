"""The Wave engine — Wavelane's personalised endless radio."""

from .engine import WaveEngine, WavePick
from .features import (
    ANALYZER_VERSION,
    FEATURE_COUNT,
    FEATURE_NAMES,
    canonical_genre,
    coerce_vector,
    detect_language,
    genre_prior,
    normalize_tempo,
    to_vector,
    vector_to_dict,
)
from .feedback import apply_feedback, get_or_create_profile, profile_snapshot
from .scoring import (
    DEFAULT_WEIGHTS,
    Candidate,
    ScoringWeights,
    UserContext,
    rank_candidates,
    select_diverse,
)

__all__ = [
    "ANALYZER_VERSION",
    "DEFAULT_WEIGHTS",
    "FEATURE_COUNT",
    "FEATURE_NAMES",
    "Candidate",
    "ScoringWeights",
    "UserContext",
    "WaveEngine",
    "WavePick",
    "apply_feedback",
    "canonical_genre",
    "coerce_vector",
    "detect_language",
    "genre_prior",
    "get_or_create_profile",
    "normalize_tempo",
    "profile_snapshot",
    "rank_candidates",
    "select_diverse",
    "to_vector",
    "vector_to_dict",
]

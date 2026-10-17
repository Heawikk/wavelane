"""Canonical sonic feature space used by the wave engine.

Every track is reduced to a fixed-length vector of normalised 0..1 descriptors.
Having one ordered representation means scoring is plain numpy arithmetic and
never touches the ORM, and it keeps the stored ``AudioFeature.vector`` column
interchangeable with whatever the analyser produced.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..models.enums import WaveMood
from ..utils import clamp, slugify

# Order matters: it defines the on-disk layout of AudioFeature.vector.
FEATURE_NAMES: tuple[str, ...] = (
    "energy",
    "valence",
    "danceability",
    "acousticness",
    "instrumentalness",
    "brightness",
    "loudness",
    "dynamics",
    "vocalness",
    "tempo_norm",
)
FEATURE_COUNT = len(FEATURE_NAMES)
FEATURE_INDEX = {name: i for i, name in enumerate(FEATURE_NAMES)}

ANALYZER_VERSION = 1

# Tempo is normalised over a musically useful window rather than 0..inf.
TEMPO_MIN_BPM = 50.0
TEMPO_MAX_BPM = 190.0

NEUTRAL_VECTOR = np.full(FEATURE_COUNT, 0.5, dtype=np.float32)


def normalize_tempo(bpm: float) -> float:
    if bpm <= 0:
        return 0.5
    return clamp((bpm - TEMPO_MIN_BPM) / (TEMPO_MAX_BPM - TEMPO_MIN_BPM))


def denormalize_tempo(value: float) -> float:
    return TEMPO_MIN_BPM + clamp(value) * (TEMPO_MAX_BPM - TEMPO_MIN_BPM)


def to_vector(features: Mapping[str, Any] | Any) -> np.ndarray:
    """Build the ordered vector from a dict or an AudioFeature-like object."""
    if isinstance(features, Mapping):
        getter = features.get
    else:
        getter = lambda key, default=None: getattr(features, key, default)  # noqa: E731

    values = []
    for name in FEATURE_NAMES:
        if name == "tempo_norm":
            raw = getter("tempo_norm")
            if raw is None:
                raw = normalize_tempo(float(getter("tempo_bpm", 0.0) or 0.0))
        else:
            raw = getter(name, 0.5)
        values.append(clamp(float(raw if raw is not None else 0.5)))
    return np.asarray(values, dtype=np.float32)


def vector_to_dict(vector: Iterable[float]) -> dict[str, float]:
    array = np.asarray(list(vector), dtype=np.float32)
    if array.size != FEATURE_COUNT:
        array = _resize(array)
    return {name: float(array[i]) for i, name in enumerate(FEATURE_NAMES)}


def coerce_vector(raw: Iterable[float] | None) -> np.ndarray:
    """Accept whatever is stored in the DB and always return a usable vector."""
    if raw is None:
        return NEUTRAL_VECTOR.copy()
    array = np.asarray(list(raw), dtype=np.float32)
    if array.size == 0:
        return NEUTRAL_VECTOR.copy()
    if array.size != FEATURE_COUNT:
        array = _resize(array)
    return np.clip(np.nan_to_num(array, nan=0.5), 0.0, 1.0)


def _resize(array: np.ndarray) -> np.ndarray:
    """Pad or truncate a vector from an older analyser version."""
    out = NEUTRAL_VECTOR.copy()
    size = min(array.size, FEATURE_COUNT)
    out[:size] = array[:size]
    return out


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def weighted_distance(a: np.ndarray, b: np.ndarray, weights: np.ndarray) -> float:
    """Normalised weighted euclidean distance in 0..1."""
    total = float(np.sum(weights))
    if total == 0.0:
        return 0.0
    diff = (a - b) ** 2
    return float(np.sqrt(np.sum(diff * weights) / total))


# ---------------------------------------------------------------------------
# Genre priors
#
# With no DSP analysis available we still need a sane starting point, and even
# when DSP data exists the genre tag carries information the signal does not
# (a quiet black-metal demo is still metal). Each entry lists only the
# dimensions the genre actually constrains; the rest stay neutral.
# ---------------------------------------------------------------------------

GENRE_PRIORS: dict[str, dict[str, float]] = {
    "pop": {"energy": 0.65, "valence": 0.65, "danceability": 0.70, "acousticness": 0.25,
            "instrumentalness": 0.08, "vocalness": 0.90, "brightness": 0.60, "tempo_bpm": 118},
    "rock": {"energy": 0.75, "valence": 0.52, "danceability": 0.45, "acousticness": 0.20,
             "instrumentalness": 0.15, "vocalness": 0.82, "brightness": 0.60, "tempo_bpm": 126},
    "metal": {"energy": 0.92, "valence": 0.35, "danceability": 0.35, "acousticness": 0.05,
              "instrumentalness": 0.20, "vocalness": 0.78, "brightness": 0.72,
              "dynamics": 0.35, "tempo_bpm": 140},
    "punk": {"energy": 0.90, "valence": 0.50, "danceability": 0.45, "acousticness": 0.08,
             "vocalness": 0.85, "tempo_bpm": 160},
    "electronic": {"energy": 0.78, "valence": 0.55, "danceability": 0.82, "acousticness": 0.05,
                   "instrumentalness": 0.70, "vocalness": 0.30, "brightness": 0.65,
                   "tempo_bpm": 126},
    "house": {"energy": 0.78, "danceability": 0.90, "acousticness": 0.04,
              "instrumentalness": 0.60, "tempo_bpm": 124},
    "techno": {"energy": 0.82, "danceability": 0.85, "acousticness": 0.03,
               "instrumentalness": 0.85, "vocalness": 0.15, "valence": 0.45, "tempo_bpm": 132},
    "drum-and-bass": {"energy": 0.90, "danceability": 0.80, "instrumentalness": 0.65,
                      "tempo_bpm": 174},
    "ambient": {"energy": 0.15, "valence": 0.50, "danceability": 0.15, "acousticness": 0.45,
                "instrumentalness": 0.92, "vocalness": 0.08, "brightness": 0.35,
                "dynamics": 0.70, "tempo_bpm": 80},
    "hip-hop": {"energy": 0.70, "valence": 0.55, "danceability": 0.80, "acousticness": 0.15,
                "instrumentalness": 0.05, "vocalness": 0.92, "brightness": 0.50,
                "tempo_bpm": 92},
    "rap": {"energy": 0.72, "danceability": 0.80, "instrumentalness": 0.04,
            "vocalness": 0.93, "tempo_bpm": 92},
    "rnb": {"energy": 0.55, "valence": 0.55, "danceability": 0.70, "acousticness": 0.30,
            "instrumentalness": 0.06, "vocalness": 0.92, "tempo_bpm": 96},
    "soul": {"energy": 0.55, "valence": 0.60, "danceability": 0.62, "acousticness": 0.45,
             "vocalness": 0.92, "dynamics": 0.60, "tempo_bpm": 100},
    "jazz": {"energy": 0.42, "valence": 0.55, "danceability": 0.45, "acousticness": 0.72,
             "instrumentalness": 0.62, "vocalness": 0.35, "dynamics": 0.78, "tempo_bpm": 112},
    "blues": {"energy": 0.48, "valence": 0.40, "acousticness": 0.65, "instrumentalness": 0.35,
              "vocalness": 0.80, "dynamics": 0.70, "tempo_bpm": 98},
    "classical": {"energy": 0.30, "valence": 0.50, "danceability": 0.18, "acousticness": 0.95,
                  "instrumentalness": 0.95, "vocalness": 0.10, "brightness": 0.45,
                  "dynamics": 0.92, "tempo_bpm": 100},
    "folk": {"energy": 0.40, "valence": 0.52, "danceability": 0.42, "acousticness": 0.85,
             "instrumentalness": 0.20, "vocalness": 0.82, "dynamics": 0.65, "tempo_bpm": 104},
    "country": {"energy": 0.52, "valence": 0.58, "danceability": 0.52, "acousticness": 0.70,
                "vocalness": 0.85, "tempo_bpm": 110},
    "indie": {"energy": 0.58, "valence": 0.52, "danceability": 0.52, "acousticness": 0.40,
              "instrumentalness": 0.22, "vocalness": 0.78, "tempo_bpm": 118},
    "reggae": {"energy": 0.55, "valence": 0.70, "danceability": 0.75, "acousticness": 0.35,
               "vocalness": 0.85, "tempo_bpm": 90},
    "latin": {"energy": 0.75, "valence": 0.78, "danceability": 0.88, "acousticness": 0.30,
              "vocalness": 0.88, "tempo_bpm": 100},
    "soundtrack": {"energy": 0.45, "valence": 0.48, "acousticness": 0.60,
                   "instrumentalness": 0.80, "vocalness": 0.20, "dynamics": 0.85,
                   "tempo_bpm": 100},
    "chanson": {"energy": 0.45, "valence": 0.45, "acousticness": 0.60, "vocalness": 0.92,
                "tempo_bpm": 104},
    "shanson": {"energy": 0.45, "valence": 0.45, "acousticness": 0.60, "vocalness": 0.92,
                "tempo_bpm": 104},
    "disco": {"energy": 0.78, "valence": 0.80, "danceability": 0.90, "acousticness": 0.15,
              "tempo_bpm": 120},
    "lo-fi": {"energy": 0.30, "valence": 0.50, "danceability": 0.55, "acousticness": 0.45,
              "instrumentalness": 0.85, "vocalness": 0.12, "brightness": 0.35,
              "tempo_bpm": 82},
}

# Sub-genre -> parent, so "melodic-techno" inherits the techno prior.
GENRE_ALIASES: dict[str, str] = {
    "alternative": "rock",
    "alternative-rock": "rock",
    "hard-rock": "rock",
    "post-rock": "rock",
    "progressive-rock": "rock",
    "heavy-metal": "metal",
    "death-metal": "metal",
    "black-metal": "metal",
    "metalcore": "metal",
    "nu-metal": "metal",
    "hardcore": "punk",
    "pop-punk": "punk",
    "edm": "electronic",
    "dance": "electronic",
    "electro": "electronic",
    "trance": "electronic",
    "dubstep": "electronic",
    "synthwave": "electronic",
    "idm": "electronic",
    "deep-house": "house",
    "tech-house": "house",
    "progressive-house": "house",
    "melodic-techno": "techno",
    "minimal-techno": "techno",
    "dnb": "drum-and-bass",
    "jungle": "drum-and-bass",
    "liquid-funk": "drum-and-bass",
    "trip-hop": "hip-hop",
    "boom-bap": "hip-hop",
    "trap": "rap",
    "cloud-rap": "rap",
    "r-b": "rnb",
    "r-n-b": "rnb",
    "funk": "soul",
    "motown": "soul",
    "smooth-jazz": "jazz",
    "bebop": "jazz",
    "swing": "jazz",
    "opera": "classical",
    "baroque": "classical",
    "orchestral": "classical",
    "piano": "classical",
    "neoclassical": "classical",
    "singer-songwriter": "folk",
    "acoustic": "folk",
    "bard": "folk",
    "indie-rock": "indie",
    "indie-pop": "indie",
    "dream-pop": "indie",
    "shoegaze": "indie",
    "ska": "reggae",
    "dancehall": "reggae",
    "reggaeton": "latin",
    "salsa": "latin",
    "bossa-nova": "latin",
    "film-score": "soundtrack",
    "score": "soundtrack",
    "game-music": "soundtrack",
    "lofi": "lo-fi",
    "lofi-hip-hop": "lo-fi",
    "chillhop": "lo-fi",
    "drone": "ambient",
    "new-age": "ambient",
    "russian-pop": "pop",
    "k-pop": "pop",
    "j-pop": "pop",
    "europop": "pop",
    "electropop": "pop",
}


def canonical_genre(raw: str) -> str:
    """Map an arbitrary tag onto a slug we have a prior for, when possible."""
    slug = slugify(raw)
    if slug in GENRE_PRIORS:
        return slug
    if slug in GENRE_ALIASES:
        return GENRE_ALIASES[slug]
    # Substring fallback: "russian hip-hop 2010s" -> "hip-hop".
    for known in GENRE_PRIORS:
        if known in slug:
            return known
    for alias, parent in GENRE_ALIASES.items():
        if alias in slug:
            return parent
    return slug


def genre_prior(genres: Iterable[str]) -> dict[str, float]:
    """Average the priors of every recognised genre tag."""
    accumulator: dict[str, list[float]] = {}
    for raw in genres:
        prior = GENRE_PRIORS.get(canonical_genre(raw))
        if not prior:
            continue
        for key, value in prior.items():
            accumulator.setdefault(key, []).append(value)
    return {key: float(np.mean(values)) for key, values in accumulator.items()}


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

_CYRILLIC = re.compile(r"[Ѐ-ӿ]")
_CJK = re.compile(r"[぀-ヿ一-鿿가-힯]")
_INSTRUMENTAL_HINTS = (
    "instrumental", "karaoke", "backing track", "minus", "минус",
    "без слов", "no vocals", "inst.",
)


def detect_language(
    *,
    title: str = "",
    artist: str = "",
    lyrics: str | None = None,
    genres: Iterable[str] = (),
    instrumentalness: float | None = None,
) -> str:
    """Heuristic language bucket: russian | foreign | instrumental | unknown.

    Deliberately cheap: script detection on the text we already have plus a few
    strong hints. Real per-track language metadata, when a tag provides it,
    should be preferred by the caller.
    """
    haystack = f"{title} {artist}".lower()
    if any(hint in haystack for hint in _INSTRUMENTAL_HINTS):
        return "instrumental"

    genre_slugs = {canonical_genre(g) for g in genres}
    if genre_slugs & {"classical", "ambient", "soundtrack", "lo-fi", "techno"}:
        if instrumentalness is None or instrumentalness >= 0.6:
            return "instrumental"

    if instrumentalness is not None and instrumentalness >= 0.88:
        return "instrumental"

    text = f"{title} {artist} {lyrics or ''}"
    cyrillic = len(_CYRILLIC.findall(text))
    latin = len(re.findall(r"[A-Za-z]", text))
    cjk = len(_CJK.findall(text))

    if cyrillic and cyrillic >= latin:
        return "russian"
    if cjk and cjk >= max(latin, cyrillic):
        return "foreign"
    if latin:
        return "foreign"
    return "unknown"


# ---------------------------------------------------------------------------
# Mood targets
#
# A mood is a target point plus per-dimension weights: "energetic" is an
# assertion about energy and tempo and says nothing about acousticness, so the
# unrelated dimensions get zero weight instead of pulling the match around.
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class MoodTarget:
    targets: dict[str, float] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)

    def as_arrays(self) -> tuple[np.ndarray, np.ndarray]:
        target = NEUTRAL_VECTOR.copy()
        weight = np.zeros(FEATURE_COUNT, dtype=np.float32)
        for name, value in self.targets.items():
            index = FEATURE_INDEX.get(name)
            if index is None:
                continue
            target[index] = clamp(value)
            weight[index] = self.weights.get(name, 1.0)
        return target, weight


MOOD_TARGETS: dict[WaveMood, MoodTarget] = {
    WaveMood.ANY: MoodTarget(),
    WaveMood.CALM: MoodTarget(
        targets={"energy": 0.22, "tempo_norm": normalize_tempo(78), "danceability": 0.30,
                 "acousticness": 0.70},
        weights={"energy": 1.4, "tempo_norm": 0.8, "danceability": 0.5, "acousticness": 0.6},
    ),
    WaveMood.CHILL: MoodTarget(
        targets={"energy": 0.42, "valence": 0.58, "tempo_norm": normalize_tempo(96)},
        weights={"energy": 1.1, "valence": 0.6, "tempo_norm": 0.6},
    ),
    WaveMood.ENERGETIC: MoodTarget(
        targets={"energy": 0.88, "tempo_norm": normalize_tempo(136), "danceability": 0.70,
                 "loudness": 0.75},
        weights={"energy": 1.5, "tempo_norm": 1.0, "danceability": 0.6, "loudness": 0.5},
    ),
    WaveMood.FOCUS: MoodTarget(
        targets={"energy": 0.38, "instrumentalness": 0.85, "vocalness": 0.15,
                 "dynamics": 0.45},
        weights={"energy": 0.9, "instrumentalness": 1.5, "vocalness": 1.2, "dynamics": 0.4},
    ),
    WaveMood.PARTY: MoodTarget(
        targets={"energy": 0.88, "danceability": 0.92, "valence": 0.80,
                 "tempo_norm": normalize_tempo(126)},
        weights={"energy": 1.2, "danceability": 1.6, "valence": 1.0, "tempo_norm": 0.7},
    ),
    WaveMood.SAD: MoodTarget(
        targets={"valence": 0.18, "energy": 0.35, "acousticness": 0.60},
        weights={"valence": 1.8, "energy": 0.8, "acousticness": 0.4},
    ),
}


def mood_arrays(mood: WaveMood) -> tuple[np.ndarray, np.ndarray]:
    return MOOD_TARGETS.get(mood, MOOD_TARGETS[WaveMood.ANY]).as_arrays()

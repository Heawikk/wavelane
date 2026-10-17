"""Enumerations shared by models, schemas and the wave engine."""

from __future__ import annotations

from enum import StrEnum


class AlbumType(StrEnum):
    ALBUM = "album"
    SINGLE = "single"
    EP = "ep"
    COMPILATION = "compilation"
    LIVE = "live"


class TrackStatus(StrEnum):
    PENDING = "pending"      # uploaded, metadata not yet extracted
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ArtistRole(StrEnum):
    MAIN = "main"
    FEATURED = "featured"
    REMIXER = "remixer"
    COMPOSER = "composer"


class PlaybackContext(StrEnum):
    WAVE = "wave"
    ALBUM = "album"
    PLAYLIST = "playlist"
    ARTIST = "artist"
    SEARCH = "search"
    LIKED = "liked"
    UNKNOWN = "unknown"


class FeedbackKind(StrEnum):
    LIKE = "like"
    DISLIKE = "dislike"
    SKIP = "skip"
    COMPLETE = "complete"
    BAN_ARTIST = "ban_artist"
    UNLIKE = "unlike"


class WaveMood(StrEnum):
    """'Настроение' — energy target of the stream."""
    ANY = "any"
    CALM = "calm"
    CHILL = "chill"
    ENERGETIC = "energetic"
    FOCUS = "focus"
    PARTY = "party"
    SAD = "sad"


class WaveCharacter(StrEnum):
    """'Характер' — how familiar the material should be."""
    ANY = "any"
    FAVOURITE = "favourite"   # tracks the user already likes
    UNFAMILIAR = "unfamiliar" # discovery
    POPULAR = "popular"       # catalogue hits


class WaveLanguage(StrEnum):
    ANY = "any"
    RUSSIAN = "russian"
    FOREIGN = "foreign"
    INSTRUMENTAL = "instrumental"


class AnalysisSource(StrEnum):
    METADATA = "metadata"   # priors derived from genre/year/duration
    DSP = "dsp"             # real signal analysis via ffmpeg + numpy

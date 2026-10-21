"""SQLAlchemy models. Importing this package registers every table on Base."""

from .admin import AdminEvent
from .base import Base, JsonType, TimestampMixin
from .catalog import (
    Album,
    Artist,
    AudioFeature,
    Genre,
    Track,
    TrackArtist,
    TrackGenre,
)
from .enums import (
    AlbumType,
    AnalysisSource,
    ArtistRole,
    FeedbackKind,
    PlaybackContext,
    TrackStatus,
    WaveCharacter,
    WaveLanguage,
    WaveMood,
)
from .library import (
    ArtistReaction,
    PlayEvent,
    Playlist,
    PlaylistTrack,
    SavedAlbum,
    TrackReaction,
)
from .user import AuthSession, User
from .wave import TasteProfile, WaveQueueItem, WaveSession, WaveSettings

__all__ = [
    "AdminEvent",
    "Album",
    "AlbumType",
    "AnalysisSource",
    "Artist",
    "ArtistReaction",
    "ArtistRole",
    "AudioFeature",
    "AuthSession",
    "Base",
    "FeedbackKind",
    "Genre",
    "JsonType",
    "PlayEvent",
    "PlaybackContext",
    "Playlist",
    "PlaylistTrack",
    "SavedAlbum",
    "TasteProfile",
    "TimestampMixin",
    "Track",
    "TrackArtist",
    "TrackGenre",
    "TrackReaction",
    "TrackStatus",
    "User",
    "WaveCharacter",
    "WaveLanguage",
    "WaveMood",
    "WaveQueueItem",
    "WaveSession",
    "WaveSettings",
]

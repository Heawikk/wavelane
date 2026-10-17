"""Library, playlist and playback-reporting schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from ..models.enums import PlaybackContext
from .catalog import AlbumBrief, ArtistBrief, TrackOut
from .common import ORMModel


class PlaylistBrief(ORMModel):
    id: uuid.UUID
    title: str
    description: str | None = None
    cover_path: str | None = None
    is_public: bool = False
    track_count: int = 0
    duration_ms: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PlaylistOut(PlaylistBrief):
    owner_id: uuid.UUID
    owner_name: str | None = None
    tracks: list[TrackOut] = Field(default_factory=list)


class PlaylistCreate(ORMModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    is_public: bool = False
    track_ids: list[uuid.UUID] = Field(default_factory=list)


class PlaylistUpdate(ORMModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=2000)
    is_public: bool | None = None


class PlaylistTracksAdd(ORMModel):
    track_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    position: int | None = Field(
        default=None, ge=0, description="Insert at this index; appends when omitted."
    )


class PlaylistReorder(ORMModel):
    track_ids: list[uuid.UUID] = Field(
        min_length=1, description="The playlist's tracks in their new order."
    )


class ReactionRequest(ORMModel):
    # "like" | "dislike"; sending the one already set clears it.
    kind: str = Field(pattern="^(like|dislike)$")


class ReactionOut(ORMModel):
    track_id: uuid.UUID
    kind: str | None = None
    created_at: datetime | None = None


class ArtistReactionRequest(ORMModel):
    kind: str = Field(pattern="^(follow|ban)$")


class LibraryStats(ORMModel):
    liked_tracks: int = 0
    disliked_tracks: int = 0
    playlists: int = 0
    saved_albums: int = 0
    followed_artists: int = 0
    tracks_played: int = 0
    listening_ms: int = 0


class PlayReport(ORMModel):
    """What the client sends when a track finishes, is skipped or is paused."""

    track_id: uuid.UUID
    ms_played: int = Field(ge=0, le=24 * 60 * 60 * 1000)
    completed: bool = False
    skipped: bool = False
    context_type: PlaybackContext = PlaybackContext.UNKNOWN
    context_id: uuid.UUID | None = None
    started_at: datetime | None = None


class PlayReportResult(ORMModel):
    recorded: bool
    completion: float
    counted_as: str


class HistoryEntry(ORMModel):
    track: TrackOut
    started_at: datetime
    ms_played: int
    completion: float
    completed: bool
    skipped: bool
    context_type: PlaybackContext


class SearchResults(ORMModel):
    query: str
    tracks: list[TrackOut] = Field(default_factory=list)
    artists: list[ArtistBrief] = Field(default_factory=list)
    albums: list[AlbumBrief] = Field(default_factory=list)
    playlists: list[PlaylistBrief] = Field(default_factory=list)

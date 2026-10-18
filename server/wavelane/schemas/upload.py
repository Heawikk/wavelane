"""Upload, import, conflict and delete schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from .catalog import TrackOut
from .common import ORMModel


class FileInfo(ORMModel):
    """The properties of one audio file that matter when choosing between two."""

    container: str | None = None
    quality: str = ""
    bitrate_kbps: int | None = None
    lossless: bool = False
    file_size: int = 0
    duration_ms: int = 0


class ConflictOut(ORMModel):
    """A file that is the same recording as a track already in the library."""

    id: str
    filename: str
    title: str
    artist_name: str
    existing_track_id: uuid.UUID
    existing: FileInfo
    incoming: FileInfo
    #: What the server would pick: "replace" for a clearly better copy, else "keep_old".
    recommended: Literal["replace", "keep_old"]
    job_id: str | None = None


class UploadedTrack(ORMModel):
    filename: str
    #: added | duplicate | conflict | failed
    status: str = "added"
    created: bool = Field(default=False, description="True when a new track was created.")
    track: TrackOut | None = None
    conflict: ConflictOut | None = None
    error: str | None = None


class UploadResult(ORMModel):
    uploaded: int = 0
    duplicates: int = 0
    conflicts: int = 0
    failed: int = 0
    items: list[UploadedTrack] = Field(default_factory=list)


# --- folder import ---------------------------------------------------------


class ImportStart(ORMModel):
    path: str = Field(min_length=1, description="Folder on the server to import.")
    recursive: bool = True
    analyze: bool = Field(
        default=True,
        description="Analyse the audio. Tracks without it cannot be picked by the wave.",
    )


class ImportJobOut(ORMModel):
    id: str
    #: scanning | running | done | cancelled | failed
    state: str
    path: str
    total: int = 0
    processed: int = 0
    imported: int = 0
    duplicates: int = 0
    conflicts: int = 0
    failed: int = 0
    current: str = ""
    errors: list[str] = Field(default_factory=list)
    analyze: bool = True
    started_at: datetime
    finished_at: datetime | None = None

    @property
    def finished(self) -> bool:
        return self.state in ("done", "cancelled", "failed")


# --- resolving conflicts -----------------------------------------------------


class ResolveItem(ORMModel):
    conflict_id: str
    action: Literal["keep_old", "replace"]


class ResolveRequest(ORMModel):
    resolutions: list[ResolveItem] = Field(min_length=1, max_length=1000)


class ResolveResult(ORMModel):
    replaced: int = 0
    kept_old: int = 0
    created: int = 0
    not_found: int = 0
    errors: list[str] = Field(default_factory=list)


# --- deleting ----------------------------------------------------------------


class DeleteTracksRequest(ORMModel):
    track_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class DeleteResult(ORMModel):
    deleted: int = 0
    files_removed: int = 0
    albums_removed: int = 0
    artists_removed: int = 0


class CleanupResult(ORMModel):
    files_removed: int = 0
    bytes_freed: int = 0

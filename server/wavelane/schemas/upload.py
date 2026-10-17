"""Upload and ingest results."""

from __future__ import annotations

import uuid

from pydantic import Field

from .catalog import TrackOut
from .common import ORMModel


class UploadedTrack(ORMModel):
    filename: str
    created: bool = Field(description="False when the file was already in the catalogue.")
    track: TrackOut | None = None
    error: str | None = None


class UploadResult(ORMModel):
    uploaded: int = 0
    duplicates: int = 0
    failed: int = 0
    items: list[UploadedTrack] = Field(default_factory=list)


class ScanRequest(ORMModel):
    path: str = Field(min_length=1, description="Server-side folder to scan.")
    recursive: bool = True
    limit: int = Field(default=1000, ge=1, le=20000)
    analyze: bool = True


class ScanResult(ORMModel):
    scanned: int = 0
    imported: int = 0
    duplicates: int = 0
    failed: int = 0
    errors: list[str] = Field(default_factory=list)
    track_ids: list[uuid.UUID] = Field(default_factory=list)

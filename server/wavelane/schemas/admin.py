"""Schemas of the administrator's dashboard."""

from __future__ import annotations

import uuid
from datetime import datetime

from .common import ORMModel


class AdminActivity(ORMModel):
    """What administrators did to the library: tracks added and deleted, words added and synced."""

    tracks_added: int = 0
    tracks_deleted: int = 0
    lyrics_added: int = 0
    lyrics_synced: int = 0


class AdminMember(AdminActivity):
    id: uuid.UUID
    username: str
    display_name: str
    avatar_path: str | None = None
    created_at: datetime
    last_seen_at: datetime | None = None
    #: The account that is asking.
    is_you: bool = False


class AdminTeam(ORMModel):
    admins: list[AdminMember]
    #: Everyone together, including administrators whose account has since been removed.
    totals: AdminActivity


class AdminStats(ORMModel):
    tracks: int = 0
    artists: int = 0
    albums: int = 0
    storage_bytes: int = 0
    #: Tracks with any words, and how they split between synced and plain text.
    with_lyrics: int = 0
    synced_lyrics: int = 0
    plain_lyrics: int = 0
    without_lyrics: int = 0

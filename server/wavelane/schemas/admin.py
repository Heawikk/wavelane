"""Schemas of the administrator's dashboard."""

from __future__ import annotations

from .common import ORMModel


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

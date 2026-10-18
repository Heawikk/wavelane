"""Lyrics request and response bodies."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import Field

from .common import ORMModel


class LyricLineOut(ORMModel):
    #: Milliseconds from the start of the track; null in plain text.
    time_ms: int | None = None
    text: str


class LyricsOut(ORMModel):
    track_id: uuid.UUID
    #: "none" when the track has no lyrics, "plain" for text, "synced" for timed lines.
    kind: Literal["none", "plain", "synced"]
    lines: list[LyricLineOut] = Field(default_factory=list)
    #: The stored text as written (LRC when synced). Only sent to administrators,
    #: who edit it; listeners have no use for it.
    text: str | None = None


class LyricsIn(ORMModel):
    #: Plain text, or LRC: one ``[mm:ss.xx]`` tag in front of each line.
    text: str = Field(min_length=1)

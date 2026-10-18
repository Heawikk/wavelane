"""Song lyrics: plain text, or LRC text whose lines carry timestamps.

The text is stored as the administrator wrote it (``Track.lyrics``), in the LRC
format that every lyrics tool already speaks, so it can be pasted in, exported
and edited by hand. It is parsed on the way out into lines the client can follow.

A text is *synced* when it has timestamped lines. The rest is plain text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

#: Hard limits, so a pasted novel cannot become a track's lyrics.
MAX_TEXT_CHARS = 100_000
MAX_LINES = 3_000

LyricsKind = Literal["none", "plain", "synced"]

# [mm:ss], [mm:ss.x], [mm:ss.xx], [mm:ss.xxx] and [mm:ss:xx]; minutes may exceed 59.
_TIME_TAG = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]")
# [ar:Artist], [ti:Title], [offset:+250] ...
_META_TAG = re.compile(r"^\[([A-Za-z#]+):([^\]]*)\]\s*$")
# Enhanced LRC marks single words: <00:12.34>. The line-level time is enough here.
_WORD_TAG = re.compile(r"<\d{1,3}:\d{2}(?:[.:]\d{1,3})?>")


@dataclass(slots=True, frozen=True)
class LyricLine:
    #: Milliseconds from the start of the track; ``None`` in plain text.
    time_ms: int | None
    text: str


@dataclass(slots=True, frozen=True)
class ParsedLyrics:
    kind: LyricsKind
    lines: list[LyricLine]


class LyricsError(ValueError):
    """The text cannot be used as lyrics."""


def _tag_ms(minutes: str, seconds: str, fraction: str | None) -> int:
    ms = (int(minutes) * 60 + int(seconds)) * 1000
    if fraction:
        # ".5" is half a second, ".05" is fifty milliseconds, ".050" the same.
        ms += int(fraction.ljust(3, "0")[:3])
    return ms


def normalise_text(text: str) -> str:
    """Unify line endings and trim the ends; stored text never has a BOM or CRs."""
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    return text.strip("\n").rstrip()


def parse_lyrics(text: str | None) -> ParsedLyrics:
    """Turn stored text into lines.

    * Timestamped lines make the text synced; lines without a timestamp are then
      dropped (they are usually credits or headers), and the lines are put in
      time order, with a line carrying several tags repeated at each of them.
    * Otherwise the text is plain and every line is kept, blank ones included,
      so verses stay apart.
    * An ``[offset:ms]`` tag shifts every timestamp, as the LRC convention says.
    """
    if text is None or not text.strip():
        return ParsedLyrics("none", [])

    text = normalise_text(text)
    offset_ms = 0
    timed: list[LyricLine] = []
    plain: list[LyricLine] = []

    for raw in text.split("\n"):
        line = raw.strip()
        meta = _META_TAG.match(line)
        if meta:
            if meta.group(1).lower() == "offset":
                try:
                    offset_ms = int(meta.group(2).strip())
                except ValueError:
                    pass
            continue

        tags = list(_TIME_TAG.finditer(line))
        if not tags:
            plain.append(LyricLine(None, _WORD_TAG.sub("", line).strip()))
            continue

        lyric = _WORD_TAG.sub("", _TIME_TAG.sub("", line)).strip()
        for tag in tags:
            timed.append(LyricLine(_tag_ms(*tag.groups()), lyric))

    if timed:
        if not any(ln.text for ln in timed):
            return ParsedLyrics("none", [])
        # By LRC convention a positive offset makes the lyrics appear earlier.
        shifted = [LyricLine(max(0, (ln.time_ms or 0) - offset_ms), ln.text) for ln in timed]
        shifted.sort(key=lambda ln: ln.time_ms or 0)
        return ParsedLyrics("synced", shifted[:MAX_LINES])

    while plain and not plain[-1].text:
        plain.pop()
    while plain and not plain[0].text:
        plain.pop(0)
    # Never more than one blank line in a row.
    collapsed: list[LyricLine] = []
    for ln in plain:
        if not ln.text and collapsed and not collapsed[-1].text:
            continue
        collapsed.append(ln)
    if not collapsed:
        return ParsedLyrics("none", [])
    return ParsedLyrics("plain", collapsed[:MAX_LINES])


def validate_text(text: str) -> str:
    """Return the text ready for storage, or raise :class:`LyricsError`."""
    cleaned = normalise_text(text)
    if len(cleaned) > MAX_TEXT_CHARS:
        raise LyricsError(f"the text is longer than {MAX_TEXT_CHARS} characters")
    parsed = parse_lyrics(cleaned)
    if parsed.kind == "none":
        raise LyricsError("the text has no lyrics in it")
    if len(parsed.lines) >= MAX_LINES:
        raise LyricsError(f"more than {MAX_LINES} lines")
    return cleaned


def format_time_tag(time_ms: int) -> str:
    """``[mm:ss.xx]`` for a time in milliseconds."""
    time_ms = max(0, int(time_ms))
    minutes, rest = divmod(time_ms, 60_000)
    seconds, millis = divmod(rest, 1000)
    return f"[{minutes:02d}:{seconds:02d}.{millis // 10:02d}]"

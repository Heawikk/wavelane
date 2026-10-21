"""Telling one credit that names several artists into the artists it names.

Tags and file names routinely hold "A, B, C" in a single artist field. Taken whole it would
become one artist called "A, B, C" with a page of its own; it should be three artists on one
track. The comma is the separator that means "and then another one": "Tyler, The Creator" and
"Earth, Wind & Fire" are the rare acts that have one in their name, and are listed below.

"&", "and", "и", "x" are *not* split. "Above & Beyond", "Artik & Asti" and "Король и Шут" are one
act each, and nothing in the text tells them from two people who happen to share a track.
"""

from __future__ import annotations

import re

#: Acts whose name contains a comma. Matched without regard to case, as whole names.
COMMA_ACTS = (
    "Tyler, The Creator",
    "Earth, Wind & Fire",
    "Crosby, Stills, Nash & Young",
    "Crosby, Stills & Nash",
    "Emerson, Lake & Palmer",
    "The Last Artful, Dodgr",
    "Dave Dee, Dozy, Beaky, Mick & Tich",
)

# A piece that is not a name but the tail of the previous one: "Sammy Davis, Jr."
_SUFFIX = re.compile(r"^(?:jr|sr|ii|iii|inc|ltd|llc|co)\.?$", re.IGNORECASE)

_PLACEHOLDER = "\x00"


def _protect(value: str) -> str:
    """Hide the commas of the acts that have one, so the split leaves them whole."""
    for act in COMMA_ACTS:
        value = re.sub(
            re.escape(act), lambda m: m.group(0).replace(",", _PLACEHOLDER), value, flags=re.I
        )
    return value


def split_commas(value: str) -> list[str]:
    """The artists named in one credit, split on commas. A credit without one comes back whole."""
    if not value:
        return []
    pieces = [piece.strip() for piece in _protect(value).split(",")]
    names: list[str] = []
    for piece in pieces:
        piece = piece.replace(_PLACEHOLDER, ",")
        if not piece:
            continue
        if names and _SUFFIX.match(piece):
            names[-1] = f"{names[-1]}, {piece}"
        else:
            names.append(piece)
    return names


def split_artist_name(name: str) -> list[str]:
    """The artists a stored artist name stands for: [name] itself unless it lists several.

    A name that only repeats one artist ("Tinlicker, Tinlicker") stands for that one."""
    names = split_commas(name)
    unique: list[str] = []
    seen: set[str] = set()
    for part in names:
        key = part.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(part)
    return unique or [name.strip()]

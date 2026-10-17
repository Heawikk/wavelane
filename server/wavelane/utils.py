"""Small shared helpers."""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime

_WHITESPACE = re.compile(r"\s+")
_NON_SLUG = re.compile(r"[^a-z0-9]+")


def now_utc() -> datetime:
    """Timezone-aware current time. Always use this instead of datetime.now()."""
    return datetime.now(UTC)


def as_aware(value: datetime | None) -> datetime | None:
    """SQLite drops tzinfo on read; re-attach UTC so comparisons stay valid."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def normalize_name(value: str) -> str:
    """Casefold + strip accents + collapse whitespace, for dedupe keys."""
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _WHITESPACE.sub(" ", stripped.casefold()).strip()


def slugify(value: str) -> str:
    base = normalize_name(value)
    transliterated = _transliterate(base)
    slug = _NON_SLUG.sub("-", transliterated).strip("-")
    return slug or "item"


_CYRILLIC_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _transliterate(value: str) -> str:
    return "".join(_CYRILLIC_MAP.get(ch, ch) for ch in value)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))

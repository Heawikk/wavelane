"""HTTP range streaming for audio files.

Seeking in a player is a ``Range`` request, so this has to be right: a wrong
``Content-Range`` or an off-by-one end byte shows up as a track that will not
scrub or that cuts off a fraction of a second early.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import anyio

_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


class RangeNotSatisfiable(Exception):
    def __init__(self, file_size: int) -> None:
        super().__init__("requested range not satisfiable")
        self.file_size = file_size


@dataclass(frozen=True, slots=True)
class ByteRange:
    start: int
    end: int  # inclusive, as the HTTP spec defines it
    file_size: int

    @property
    def length(self) -> int:
        return self.end - self.start + 1

    @property
    def is_full(self) -> bool:
        return self.start == 0 and self.end == self.file_size - 1

    @property
    def content_range(self) -> str:
        return f"bytes {self.start}-{self.end}/{self.file_size}"


def parse_range(header: str | None, file_size: int) -> ByteRange | None:
    """Parse a single-range ``Range`` header. Returns None to send the whole file.

    Multi-range requests are answered with the full file instead; no audio
    client needs them, and building a multipart/byteranges body for one would
    be pure dead weight.
    """
    if not header or file_size <= 0:
        return None

    header = header.strip()
    if "," in header:
        return None

    match = _RANGE_RE.match(header)
    if not match:
        return None

    raw_start, raw_end = match.group(1), match.group(2)

    if not raw_start and not raw_end:
        return None

    if not raw_start:
        # "bytes=-500" means the final 500 bytes.
        suffix_length = int(raw_end)
        if suffix_length <= 0:
            raise RangeNotSatisfiable(file_size)
        start = max(file_size - suffix_length, 0)
        end = file_size - 1
    else:
        start = int(raw_start)
        if start >= file_size:
            raise RangeNotSatisfiable(file_size)
        end = int(raw_end) if raw_end else file_size - 1
        # A client may ask past the end; clamp rather than refuse.
        end = min(end, file_size - 1)

    if start > end:
        raise RangeNotSatisfiable(file_size)

    return ByteRange(start=start, end=end, file_size=file_size)


async def iter_file_range(
    path: Path,
    byte_range: ByteRange | None,
    chunk_size: int = 256 * 1024,
    file_size: int | None = None,
) -> AsyncIterator[bytes]:
    """Yield the requested bytes without blocking the event loop.

    ``file_size`` is accepted so the caller, which has already stat'ed the
    file to build the headers, does not make us stat it again.
    """
    start = byte_range.start if byte_range else 0
    if byte_range is not None:
        remaining = byte_range.length
    elif file_size is not None:
        remaining = file_size
    else:
        remaining = await anyio.to_thread.run_sync(lambda: path.stat().st_size)

    async with await anyio.open_file(path, "rb") as handle:
        if start:
            await handle.seek(start)
        while remaining > 0:
            chunk = await handle.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def streaming_headers(
    byte_range: ByteRange | None,
    file_size: int,
    *,
    content_type: str,
    filename: str | None = None,
    cache_seconds: int = 0,
) -> dict[str, str]:
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": content_type,
    }
    if byte_range is not None and not byte_range.is_full:
        headers["Content-Range"] = byte_range.content_range
        headers["Content-Length"] = str(byte_range.length)
    else:
        headers["Content-Length"] = str(file_size)

    if filename:
        headers["Content-Disposition"] = f'inline; filename="{_ascii_filename(filename)}"'
    if cache_seconds > 0:
        headers["Cache-Control"] = f"private, max-age={cache_seconds}"
    else:
        headers["Cache-Control"] = "no-store"
    return headers


def _ascii_filename(name: str) -> str:
    """Content-Disposition is header-encoded; keep it to safe ASCII."""
    cleaned = name.replace('"', "").replace("\\", "")
    return cleaned.encode("ascii", "ignore").decode("ascii") or "audio"

"""Conflicts: a new file that is the same recording as one already in the library.

When that happens the new file is staged and the decision goes to the person
importing. This module keeps the waiting files and applies the decision.

The registry is in memory on purpose. A pending conflict is a staged file plus
an unanswered question; if the server restarts, both are simply gone and the
file can be imported again. Persisting them would mean a table, a migration and
a clean-up policy for a state that is only ever minutes old.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Track
from ..schemas.upload import ConflictOut, FileInfo
from ..utils import now_utc
from .ingest import IngestService, PreparedFile

logger = logging.getLogger(__name__)

PENDING_TTL = timedelta(hours=24)
# Bitrate must beat the existing file by this much to count as better, so two
# near-identical encodes do not trade places on a rounding difference.
BITRATE_MARGIN = 1.05


@dataclass(slots=True)
class PendingConflict:
    id: str
    user_id: uuid.UUID
    filename: str
    prepared: PreparedFile
    existing_track_id: uuid.UUID
    job_id: str | None = None
    created_at: datetime = field(default_factory=now_utc)


class ConflictRegistry:
    def __init__(self) -> None:
        self._items: dict[str, PendingConflict] = {}

    def add(
        self,
        *,
        user_id: uuid.UUID,
        filename: str,
        prepared: PreparedFile,
        existing_track_id: uuid.UUID,
        job_id: str | None = None,
    ) -> PendingConflict:
        item = PendingConflict(
            id=secrets.token_urlsafe(9),
            user_id=user_id,
            filename=filename,
            prepared=prepared,
            existing_track_id=existing_track_id,
            job_id=job_id,
        )
        self._items[item.id] = item
        return item

    def get(self, conflict_id: str) -> PendingConflict | None:
        return self._items.get(conflict_id)

    def pop(self, conflict_id: str) -> PendingConflict | None:
        return self._items.pop(conflict_id, None)

    def all(self) -> list[PendingConflict]:
        return sorted(self._items.values(), key=lambda item: item.created_at)

    def expired(self) -> list[PendingConflict]:
        cutoff = now_utc() - PENDING_TTL
        return [item for item in self._items.values() if item.created_at < cutoff]

    def __len__(self) -> int:
        return len(self._items)


_registry: ConflictRegistry | None = None


def get_conflict_registry() -> ConflictRegistry:
    global _registry
    if _registry is None:
        _registry = ConflictRegistry()
    return _registry


# ---------------------------------------------------------------------------
# Comparing the two files
# ---------------------------------------------------------------------------


def quality_label(container: str | None, bitrate_kbps: int | None, lossless: bool) -> str:
    if lossless:
        return (container or "").upper()
    if bitrate_kbps:
        return f"{bitrate_kbps} kbps"
    return (container or "").upper()


def recommend(existing: Track, incoming: PreparedFile) -> str:
    """"replace" when the new file is clearly the better copy, else "keep_old"."""
    new_lossless = incoming.stored.lossless
    if new_lossless != existing.lossless:
        return "replace" if new_lossless else "keep_old"

    new_bitrate = incoming.meta.bitrate_kbps or 0
    old_bitrate = existing.bitrate_kbps or 0
    if not new_lossless and new_bitrate > old_bitrate * BITRATE_MARGIN:
        return "replace"
    return "keep_old"


def describe_conflict(pending: PendingConflict, existing: Track) -> ConflictOut:
    """The payload a client needs to show "old file or new file?"."""
    prepared = pending.prepared
    meta = prepared.meta
    return ConflictOut(
        id=pending.id,
        filename=pending.filename,
        title=existing.title,
        artist_name=existing.artist_display,
        existing_track_id=existing.id,
        existing=FileInfo(
            container=existing.container,
            quality=quality_label(existing.container, existing.bitrate_kbps, existing.lossless),
            bitrate_kbps=existing.bitrate_kbps,
            lossless=existing.lossless,
            file_size=existing.file_size,
            duration_ms=existing.duration_ms,
        ),
        incoming=FileInfo(
            container=prepared.stored.container,
            quality=quality_label(
                prepared.stored.container, meta.bitrate_kbps, prepared.stored.lossless
            ),
            bitrate_kbps=meta.bitrate_kbps,
            lossless=prepared.stored.lossless,
            file_size=prepared.stored.size,
            duration_ms=meta.duration_ms,
        ),
        recommended=recommend(existing, prepared),
        job_id=pending.job_id,
    )


# ---------------------------------------------------------------------------
# Applying a decision
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Resolution:
    action: str          # replaced | kept_old | created | not_found
    track_id: uuid.UUID | None = None


async def resolve_conflict(
    session: AsyncSession,
    service: IngestService,
    registry: ConflictRegistry,
    conflict_id: str,
    action: str,
) -> Resolution:
    """Apply "keep_old" or "replace" to one pending conflict.

    The caller commits and then calls ``service.apply_deferred_deletes()``, so
    the superseded file is only removed once the database change is durable.
    """
    pending = registry.pop(conflict_id)
    if pending is None:
        return Resolution("not_found")

    prepared = pending.prepared

    if action == "keep_old":
        await service.discard(prepared)
        return Resolution("kept_old", pending.existing_track_id)

    existing = await session.get(Track, pending.existing_track_id)
    if existing is None:
        # The track the file would have replaced was deleted while the question
        # was open. The file is still wanted, so it becomes a track of its own.
        track = await service.commit(prepared, pending.user_id)
        return Resolution("created", track.id)

    await service.replace_file(existing, prepared)
    return Resolution("replaced", existing.id)

"""Keeping count of what each administrator does to the library."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AdminEvent, Track
from .lyrics import parse_lyrics

TRACK_ADDED = "track_added"
TRACK_DELETED = "track_deleted"
LYRICS_ADDED = "lyrics_added"
LYRICS_SYNCED = "lyrics_synced"

KINDS = (TRACK_ADDED, TRACK_DELETED, LYRICS_ADDED, LYRICS_SYNCED)


def record(
    session: AsyncSession, admin_id: uuid.UUID | None, kind: str, amount: int = 1
) -> None:
    """Note that an administrator did something. Joins the caller's transaction."""
    if admin_id is not None and amount > 0:
        session.add(AdminEvent(admin_id=admin_id, kind=kind, amount=amount))


def record_lyrics_change(
    session: AsyncSession, admin_id: uuid.UUID | None, before: str | None, after: str | None
) -> None:
    """Count words that appeared, and words that became synced to the music.

    Text going from nothing to something is "added"; text that is synced now and was not
    before is "synced" (both, when synced text is the first thing a track gets). Changing
    words that were already there, or removing them, counts for neither.
    """
    old, new = parse_lyrics(before).kind, parse_lyrics(after).kind
    if old == "none" and new != "none":
        record(session, admin_id, LYRICS_ADDED)
    if new == "synced" and old != "synced":
        record(session, admin_id, LYRICS_SYNCED)


async def totals_by_admin(session: AsyncSession) -> dict[uuid.UUID, dict[str, int]]:
    rows = await session.execute(
        select(AdminEvent.admin_id, AdminEvent.kind, func.sum(AdminEvent.amount))
        .where(AdminEvent.admin_id.is_not(None))
        .group_by(AdminEvent.admin_id, AdminEvent.kind)
    )
    totals: dict[uuid.UUID, dict[str, int]] = {}
    for admin_id, kind, amount in rows:
        totals.setdefault(admin_id, {})[kind] = int(amount or 0)
    return totals


async def totals_overall(session: AsyncSession) -> dict[str, int]:
    """Every administrator together, including ones whose account is gone."""
    rows = await session.execute(
        select(AdminEvent.kind, func.sum(AdminEvent.amount)).group_by(AdminEvent.kind)
    )
    return {kind: int(amount or 0) for kind, amount in rows}


async def backfill_uploads(session: AsyncSession) -> int:
    """Turn the uploader every existing track already carries into "track added" events.

    Runs once, when the log has never been written: tracks that were uploaded before it
    existed are credited to whoever uploaded them, dated when they were uploaded. Deletions
    and words cannot be recovered and count from here on.
    """
    if await session.scalar(select(func.count()).select_from(AdminEvent)):
        return 0
    rows = await session.execute(
        select(Track.uploaded_by_id, Track.created_at).where(Track.uploaded_by_id.is_not(None))
    )
    events = [
        AdminEvent(admin_id=admin_id, kind=TRACK_ADDED, amount=1, created_at=created_at)
        for admin_id, created_at in rows
    ]
    session.add_all(events)
    await session.flush()
    return len(events)

"""Numbers for the administrator's dashboard."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select

from ...models import Album, Artist, Track, User
from ...schemas.admin import AdminActivity, AdminMember, AdminStats, AdminTeam
from ...services import admin_log
from ...services.catalog import count_query, ready_tracks
from ...services.lyrics import parse_lyrics
from ..deps import AdminUser, DbSession

router = APIRouter(tags=["admin"])


@router.get(
    "/admin/stats",
    response_model=AdminStats,
    summary="How many tracks there are, and how many have words (admin)",
)
async def admin_stats(admin: AdminUser, db: DbSession) -> AdminStats:
    tracks = await count_query(db, ready_tracks())
    storage_bytes = await db.scalar(select(func.coalesce(func.sum(Track.file_size), 0))) or 0
    artists = await db.scalar(select(func.count()).select_from(Artist)) or 0
    albums = await db.scalar(select(func.count()).select_from(Album)) or 0

    # Whether text is synced depends on how it parses, which only the parser knows.
    plain = synced = 0
    texts = await db.scalars(
        ready_tracks().with_only_columns(Track.lyrics).where(Track.lyrics.is_not(None))
    )
    for text in texts.all():
        kind = parse_lyrics(text).kind
        if kind == "synced":
            synced += 1
        elif kind == "plain":
            plain += 1

    return AdminStats(
        tracks=tracks,
        artists=artists,
        albums=albums,
        storage_bytes=int(storage_bytes),
        with_lyrics=plain + synced,
        synced_lyrics=synced,
        plain_lyrics=plain,
        without_lyrics=max(0, tracks - plain - synced),
    )


def _activity(counts: dict[str, int]) -> dict[str, int]:
    return {
        "tracks_added": counts.get(admin_log.TRACK_ADDED, 0),
        "tracks_deleted": counts.get(admin_log.TRACK_DELETED, 0),
        "lyrics_added": counts.get(admin_log.LYRICS_ADDED, 0),
        "lyrics_synced": counts.get(admin_log.LYRICS_SYNCED, 0),
    }


@router.get(
    "/admin/admins",
    response_model=AdminTeam,
    summary="The administrators, and what each has added and deleted (admin)",
)
async def admin_team(admin: AdminUser, db: DbSession) -> AdminTeam:
    people = (
        await db.scalars(
            select(User)
            .where(User.is_admin.is_(True), User.is_active.is_(True))
            .order_by(User.created_at, User.username)
        )
    ).all()
    per_admin = await admin_log.totals_by_admin(db)
    members = [
        AdminMember(
            id=person.id,
            username=person.username,
            display_name=person.display_name,
            avatar_path=person.avatar_path,
            created_at=person.created_at,
            last_seen_at=person.last_seen_at,
            is_you=person.id == admin.id,
            **_activity(per_admin.get(person.id, {})),
        )
        for person in people
    ]
    # Most active first; the account asking leads on a tie so it is easy to find.
    members.sort(
        key=lambda m: (-(m.tracks_added + m.lyrics_added + m.lyrics_synced + m.tracks_deleted),
                       not m.is_you)
    )
    return AdminTeam(
        admins=members,
        totals=AdminActivity(**_activity(await admin_log.totals_overall(db))),
    )

"""The administrator's dashboard numbers."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.anyio


async def test_stats_count_tracks_and_lyrics(client, api, account, upload_track):
    plain = (await upload_track(account, "plain.wav", freqs=(330.0,)))["track"]
    synced = (await upload_track(account, "synced.wav", freqs=(550.0,)))["track"]
    await upload_track(account, "silent.wav", freqs=(770.0,))
    await client.put(
        f"{api}/tracks/{plain['id']}/lyrics", headers=account.headers, json={"text": "la\nla la"}
    )
    await client.put(
        f"{api}/tracks/{synced['id']}/lyrics",
        headers=account.headers,
        json={"text": "[00:01.00]one\n[00:03.50]two"},
    )

    response = await client.get(f"{api}/admin/stats", headers=account.headers)

    assert response.status_code == 200, response.text
    stats = response.json()
    assert stats["tracks"] == 3
    assert stats["with_lyrics"] == 2
    assert stats["synced_lyrics"] == 1
    assert stats["plain_lyrics"] == 1
    assert stats["without_lyrics"] == 1
    assert stats["storage_bytes"] > 0


async def test_stats_are_for_administrators_only(client, api, account, register):
    listener = await register("guest")

    assert (await client.get(f"{api}/admin/stats", headers=listener.headers)).status_code == 403
    assert (await client.get(f"{api}/admin/stats")).status_code == 401


async def _promote(user_id: str) -> None:
    import uuid

    from wavelane.db import get_session_factory
    from wavelane.models import User

    async with get_session_factory()() as session:
        user = await session.get(User, uuid.UUID(user_id))
        user.is_admin = True
        await session.commit()


async def test_admins_list_counts_what_each_one_did(client, api, account, register, upload_track):
    helper = await register("helper")
    await _promote(helper.user["id"])

    first = (await upload_track(account, "a.wav", freqs=(330.0,)))["track"]
    second = (await upload_track(account, "b.wav", freqs=(550.0,)))["track"]
    third = (await upload_track(helper, "c.wav", freqs=(770.0,)))["track"]

    # words: plain first, then synced over it, then synced straight away
    put = lambda who, track, text: client.put(  # noqa: E731
        f"{api}/tracks/{track['id']}/lyrics", headers=who.headers, json={"text": text}
    )
    await put(account, first, "la la")
    await put(account, first, "[00:01.00]la\n[00:02.00]la")
    await put(account, first, "[00:01.00]la\n[00:02.50]la")  # an edit counts for nothing
    await put(helper, third, "[00:01.00]hey")
    # removing a track is counted for whoever pressed the button, not the uploader
    removed = await client.delete(f"{api}/tracks/{second['id']}", headers=helper.headers)
    assert removed.status_code == 200

    response = await client.get(f"{api}/admin/admins", headers=account.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    by_name = {a["username"]: a for a in body["admins"]}
    assert set(by_name) == {account.user["username"], "helper"}
    mine = by_name[account.user["username"]]
    assert (mine["tracks_added"], mine["tracks_deleted"]) == (2, 0)
    assert (mine["lyrics_added"], mine["lyrics_synced"]) == (1, 1)
    assert mine["is_you"] is True
    theirs = by_name["helper"]
    assert (theirs["tracks_added"], theirs["tracks_deleted"]) == (1, 1)
    assert (theirs["lyrics_added"], theirs["lyrics_synced"]) == (1, 1)
    assert theirs["is_you"] is False
    assert body["totals"] == {
        "tracks_added": 3, "tracks_deleted": 1, "lyrics_added": 2, "lyrics_synced": 2
    }


async def test_admins_list_leaves_out_listeners(client, api, account, register):
    await register("guest")

    body = (await client.get(f"{api}/admin/admins", headers=account.headers)).json()

    assert [a["username"] for a in body["admins"]] == [account.user["username"]]


async def test_admins_list_is_for_administrators_only(client, api, account, register):
    listener = await register("guest")

    assert (await client.get(f"{api}/admin/admins", headers=listener.headers)).status_code == 403


async def test_tracks_uploaded_before_the_log_are_credited_once(client, api, account, upload_track):
    from sqlalchemy import delete, func, select

    from wavelane.db import get_session_factory
    from wavelane.models import AdminEvent
    from wavelane.services.admin_log import backfill_uploads

    await upload_track(account, "old.wav", freqs=(330.0,))
    async with get_session_factory()() as session:
        await session.execute(delete(AdminEvent))  # as if the track pre-dates the log
        await session.commit()
        assert await backfill_uploads(session) == 1
        await session.commit()
        assert await backfill_uploads(session) == 0  # the log is no longer empty
        assert await session.scalar(select(func.count()).select_from(AdminEvent)) == 1

    body = (await client.get(f"{api}/admin/admins", headers=account.headers)).json()
    assert body["admins"][0]["tracks_added"] == 1

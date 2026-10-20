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

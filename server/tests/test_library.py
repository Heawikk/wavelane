"""Library reactions, playlists and history."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.anyio


async def test_like_is_a_toggle(client, api, account, upload_track):
    track = (await upload_track(account, "likeable.wav"))["track"]

    liked = await client.put(
        f"{api}/library/tracks/{track['id']}/reaction",
        headers=account.headers,
        json={"kind": "like"},
    )
    assert liked.json()["kind"] == "like"

    listing = await client.get(f"{api}/library/liked", headers=account.headers)
    assert [t["id"] for t in listing.json()["items"]] == [track["id"]]

    cleared = await client.put(
        f"{api}/library/tracks/{track['id']}/reaction",
        headers=account.headers,
        json={"kind": "like"},
    )
    assert cleared.json()["kind"] is None

    empty = await client.get(f"{api}/library/liked", headers=account.headers)
    assert empty.json()["items"] == []


async def test_like_and_dislike_are_mutually_exclusive(client, api, account, upload_track):
    track = (await upload_track(account, "switcheroo.wav"))["track"]
    url = f"{api}/library/tracks/{track['id']}/reaction"

    await client.put(url, headers=account.headers, json={"kind": "like"})
    switched = await client.put(url, headers=account.headers, json={"kind": "dislike"})
    assert switched.json()["kind"] == "dislike"

    liked = await client.get(f"{api}/library/liked", headers=account.headers)
    assert liked.json()["items"] == []

    detail = await client.get(f"{api}/tracks/{track['id']}", headers=account.headers)
    assert detail.json()["disliked"] is True
    assert detail.json()["liked"] is False


async def test_reaction_shows_up_on_track_responses(client, api, account, upload_track):
    track = (await upload_track(account, "flagged.wav"))["track"]
    await client.put(
        f"{api}/library/tracks/{track['id']}/reaction",
        headers=account.headers,
        json={"kind": "like"},
    )
    listing = await client.get(f"{api}/tracks", headers=account.headers)
    assert listing.json()["items"][0]["liked"] is True

    # The catalogue is for people with an account.
    assert (await client.get(f"{api}/tracks")).status_code == 401


async def test_playlist_lifecycle(client, api, account, upload_track):
    first = (await upload_track(account, "p1.wav", freqs=(220.0,)))["track"]
    second = (await upload_track(account, "p2.wav", freqs=(330.0,)))["track"]
    third = (await upload_track(account, "p3.wav", freqs=(440.0,)))["track"]

    created = await client.post(
        f"{api}/playlists",
        headers=account.headers,
        json={"title": "Evening", "track_ids": [first["id"], second["id"]]},
    )
    assert created.status_code == 201
    playlist = created.json()
    assert playlist["track_count"] == 2
    assert [t["id"] for t in playlist["tracks"]] == [first["id"], second["id"]]
    assert playlist["duration_ms"] > 0

    # Insert at the front.
    added = await client.post(
        f"{api}/playlists/{playlist['id']}/tracks",
        headers=account.headers,
        json={"track_ids": [third["id"]], "position": 0},
    )
    assert [t["id"] for t in added.json()["tracks"]] == [
        third["id"], first["id"], second["id"]
    ]

    reordered = await client.put(
        f"{api}/playlists/{playlist['id']}/order",
        headers=account.headers,
        json={"track_ids": [second["id"], third["id"], first["id"]]},
    )
    assert [t["id"] for t in reordered.json()["tracks"]] == [
        second["id"], third["id"], first["id"]
    ]

    removed = await client.delete(
        f"{api}/playlists/{playlist['id']}/tracks/{third['id']}",
        headers=account.headers,
    )
    assert [t["id"] for t in removed.json()["tracks"]] == [second["id"], first["id"]]
    assert removed.json()["track_count"] == 2

    emptied = await client.delete(
        f"{api}/playlists/{playlist['id']}/tracks", headers=account.headers
    )
    assert emptied.status_code == 200

    deleted = await client.delete(
        f"{api}/playlists/{playlist['id']}", headers=account.headers
    )
    assert deleted.status_code == 200
    gone = await client.get(f"{api}/playlists/{playlist['id']}", headers=account.headers)
    assert gone.status_code == 404


async def test_playlist_can_hold_the_same_track_twice(client, api, account, upload_track):
    track = (await upload_track(account, "repeat.wav"))["track"]
    created = await client.post(
        f"{api}/playlists", headers=account.headers, json={"title": "Loop"}
    )
    playlist_id = created.json()["id"]

    added = await client.post(
        f"{api}/playlists/{playlist_id}/tracks",
        headers=account.headers,
        json={"track_ids": [track["id"], track["id"]]},
    )
    assert added.json()["track_count"] == 2


async def test_private_playlist_is_hidden_from_others(client, api, account, register):
    created = await client.post(
        f"{api}/playlists",
        headers=account.headers,
        json={"title": "Secret", "is_public": False},
    )
    playlist_id = created.json()["id"]
    stranger = await register("stranger")

    hidden = await client.get(f"{api}/playlists/{playlist_id}", headers=stranger.headers)
    assert hidden.status_code == 404

    blocked = await client.patch(
        f"{api}/playlists/{playlist_id}",
        headers=stranger.headers,
        json={"title": "Taken over"},
    )
    assert blocked.status_code in (403, 404)


async def test_public_playlist_is_readable_by_others(client, api, account, register):
    created = await client.post(
        f"{api}/playlists",
        headers=account.headers,
        json={"title": "Shared", "is_public": True},
    )
    playlist_id = created.json()["id"]
    stranger = await register("friend")

    visible = await client.get(f"{api}/playlists/{playlist_id}", headers=stranger.headers)
    assert visible.status_code == 200
    assert visible.json()["title"] == "Shared"

    # Still not writable.
    blocked = await client.patch(
        f"{api}/playlists/{playlist_id}",
        headers=stranger.headers,
        json={"title": "Renamed"},
    )
    assert blocked.status_code == 403


async def test_play_reporting_counts_and_records(client, api, account, upload_track):
    track = (await upload_track(account, "played.wav", seconds=2.0))["track"]

    partial = await client.post(
        f"{api}/library/plays",
        headers=account.headers,
        json={"track_id": track["id"], "ms_played": 100, "skipped": True},
    )
    assert partial.status_code == 200
    assert partial.json()["counted_as"] == "skip"

    finished = await client.post(
        f"{api}/library/plays",
        headers=account.headers,
        json={
            "track_id": track["id"],
            "ms_played": track["duration_ms"],
            "completed": True,
            "context_type": "album",
        },
    )
    assert finished.json()["counted_as"] == "complete"
    assert finished.json()["completion"] >= 0.95

    history = await client.get(f"{api}/library/history", headers=account.headers)
    entries = history.json()["items"]
    assert len(entries) == 2
    # Newest first.
    assert entries[0]["completed"] is True
    assert entries[1]["skipped"] is True

    stats = await client.get(f"{api}/library/stats", headers=account.headers)
    assert stats.json()["tracks_played"] == 2
    assert stats.json()["listening_ms"] > 0


async def test_saved_albums_toggle(client, api, account, tagged_wav_factory):
    # An album row only exists when a file carries an album tag.
    path = tagged_wav_factory(
        filename="saveable.wav", title="Opener", artist="Shelf Band", album="Shelf Life"
    )
    with path.open("rb") as handle:
        upload = await client.post(
            f"{api}/upload",
            headers=account.headers,
            files={"files": (path.name, handle, "audio/wav")},
        )
    assert upload.status_code == 201

    albums = await client.get(f"{api}/albums", headers=account.headers)
    items = albums.json()["items"]
    assert [a["title"] for a in items] == ["Shelf Life"]

    album_id = items[0]["id"]
    saved = await client.put(f"{api}/library/albums/{album_id}", headers=account.headers)
    assert "saved" in saved.json()["detail"]

    listing = await client.get(f"{api}/library/albums", headers=account.headers)
    assert [a["id"] for a in listing.json()["items"]] == [album_id]

    unsaved = await client.put(f"{api}/library/albums/{album_id}", headers=account.headers)
    assert "removed" in unsaved.json()["detail"]


async def test_follow_and_ban_artist(client, api, account, upload_track):
    track = (await upload_track(account, "Some Band - Song.wav"))["track"]
    artist_id = track["artists"][0]["id"]

    followed = await client.put(
        f"{api}/library/artists/{artist_id}/reaction",
        headers=account.headers,
        json={"kind": "follow"},
    )
    assert "followed" in followed.json()["detail"]

    listing = await client.get(f"{api}/library/artists", headers=account.headers)
    assert [a["id"] for a in listing.json()] == [artist_id]

    banned = await client.put(
        f"{api}/library/artists/{artist_id}/reaction",
        headers=account.headers,
        json={"kind": "ban"},
    )
    assert "banned" in banned.json()["detail"]

    # A ban is not a follow, so the follow list empties.
    after = await client.get(f"{api}/library/artists", headers=account.headers)
    assert after.json() == []


async def test_library_requires_authentication(client, api):
    for path in ("/library/stats", "/library/liked", "/library/history", "/playlists"):
        response = await client.get(f"{api}{path}")
        assert response.status_code == 401, path

"""Correcting metadata by hand: tracks, artists, artist pictures, and finding things to correct."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.anyio

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


async def _upload(client, api, account, factory, **tags) -> dict:
    path = factory(**tags)
    with path.open("rb") as handle:
        response = await client.post(
            f"{api}/upload",
            headers=account.headers,
            files={"files": (path.name, handle, "audio/wav")},
        )
    assert response.status_code == 201, response.text
    item = response.json()["items"][0]
    assert item["error"] is None, item["error"]
    return item["track"]


async def test_a_track_can_be_moved_to_other_artists_and_album(
    client, api, account, tagged_wav_factory
):
    track = await _upload(
        client, api, account, tagged_wav_factory,
        filename="one.wav", title="Draft", artist="Wrong Name", album="Wrong Album",
    )

    response = await client.patch(
        f"{api}/tracks/{track['id']}",
        headers=account.headers,
        json={
            "title": "Final",
            "artists": ["Right Name", "Second Voice"],
            "featured_artists": ["Guest"],
            "album": "Right Album",
            "release_year": 2021,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Final"
    credits = [(a["name"], a["role"]) for a in body["artists"]]
    assert credits == [("Right Name", "main"), ("Second Voice", "main"), ("Guest", "featured")]
    assert body["album"]["title"] == "Right Album"
    assert body["album"]["release_year"] == 2021

    # the new names are real artists now, and the old one, left with nothing, is gone
    found = (await client.get(f"{api}/artists?q=right", headers=account.headers)).json()
    assert [a["name"] for a in found["items"]] == ["Right Name"]
    assert found["items"][0]["track_count"] == 1
    old = (await client.get(f"{api}/artists?q=wrong", headers=account.headers)).json()
    assert old["items"] == []


async def test_leaving_parts_out_keeps_them_and_an_empty_album_removes_it(
    client, api, account, tagged_wav_factory
):
    track = await _upload(
        client, api, account, tagged_wav_factory,
        filename="two.wav", title="Keep", artist="Stays", album="Gets Dropped",
    )

    renamed = await client.patch(
        f"{api}/tracks/{track['id']}", headers=account.headers, json={"title": "Kept"}
    )
    assert [a["name"] for a in renamed.json()["artists"]] == ["Stays"]
    assert renamed.json()["album"]["title"] == "Gets Dropped"

    dropped = await client.patch(
        f"{api}/tracks/{track['id']}", headers=account.headers, json={"album": ""}
    )
    assert dropped.json()["album"] is None


async def test_a_track_cannot_lose_all_its_artists(client, api, account, upload_track):
    track = (await upload_track(account, "solo.wav"))["track"]

    response = await client.patch(
        f"{api}/tracks/{track['id']}", headers=account.headers, json={"artists": ["  "]}
    )

    assert response.status_code == 422


async def test_tracks_can_be_listed_with_a_search_text(
    client, api, account, tagged_wav_factory
):
    await _upload(client, api, account, tagged_wav_factory,
                  filename="a.wav", title="Moonlight", artist="Night Owl", freqs=(300.0,))
    await _upload(client, api, account, tagged_wav_factory,
                  filename="b.wav", title="Sunrise", artist="Early Bird", freqs=(520.0,))

    by_title = (await client.get(f"{api}/tracks?q=moon", headers=account.headers)).json()
    by_artist = (await client.get(f"{api}/tracks?q=early", headers=account.headers)).json()
    nothing = (await client.get(f"{api}/tracks?q=zzzz", headers=account.headers)).json()

    assert [t["title"] for t in by_title["items"]] == ["Moonlight"] and by_title["total"] == 1
    assert [t["title"] for t in by_artist["items"]] == ["Sunrise"]
    assert nothing["items"] == [] and nothing["total"] == 0


async def test_an_artist_can_be_edited_and_given_a_picture(
    client, api, account, tagged_wav_factory
):
    track = await _upload(client, api, account, tagged_wav_factory,
                          filename="c.wav", title="Song", artist="Plain Name")
    artist_id = track["artists"][0]["id"]

    edited = await client.patch(
        f"{api}/artists/{artist_id}",
        headers=account.headers,
        json={"name": "Fancy Name", "country": "ru", "bio": "  Makes songs.  "},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["name"] == "Fancy Name"
    assert edited.json()["country"] == "RU"
    assert edited.json()["bio"] == "Makes songs."

    pictured = await client.post(
        f"{api}/artists/{artist_id}/image",
        headers=account.headers,
        files={"image": ("face.png", PNG, "image/png")},
    )
    assert pictured.status_code == 200, pictured.text
    path = pictured.json()["image_path"]
    assert path
    assert (await client.get(f"{api}/covers/{path}")).status_code == 200

    removed = await client.delete(f"{api}/artists/{artist_id}/image", headers=account.headers)
    assert removed.json()["image_path"] is None

    cleared = await client.patch(
        f"{api}/artists/{artist_id}", headers=account.headers, json={"country": ""}
    )
    assert cleared.json()["country"] is None


async def test_artist_pictures_must_be_pictures_and_small(
    client, api, account, tagged_wav_factory
):
    track = await _upload(client, api, account, tagged_wav_factory,
                          filename="d.wav", title="Song", artist="Someone")
    artist_id = track["artists"][0]["id"]

    fake = await client.post(
        f"{api}/artists/{artist_id}/image",
        headers=account.headers,
        files={"image": ("face.png", b"not an image at all", "image/png")},
    )
    huge = await client.post(
        f"{api}/artists/{artist_id}/image",
        headers=account.headers,
        files={"image": ("face.png", PNG + b"\x00" * 1_600_000, "image/png")},
    )

    assert fake.status_code == 415
    assert huge.status_code == 413


async def test_two_artists_cannot_share_a_name(client, api, account, tagged_wav_factory):
    first = await _upload(client, api, account, tagged_wav_factory,
                          filename="e.wav", title="A", artist="First", freqs=(310.0,))
    await _upload(client, api, account, tagged_wav_factory,
                  filename="f.wav", title="B", artist="Second", freqs=(540.0,))

    clash = await client.patch(
        f"{api}/artists/{first['artists'][0]['id']}",
        headers=account.headers,
        json={"name": "second"},
    )

    assert clash.status_code == 409


async def test_only_administrators_edit_artists(client, api, account, register, tagged_wav_factory):
    track = await _upload(client, api, account, tagged_wav_factory,
                          filename="g.wav", title="A", artist="Guarded")
    guest = await register("guest")

    edit = await client.patch(
        f"{api}/artists/{track['artists'][0]['id']}", headers=guest.headers, json={"name": "Hacked"}
    )
    picture = await client.post(
        f"{api}/artists/{track['artists'][0]['id']}/image",
        headers=guest.headers,
        files={"image": ("face.png", PNG, "image/png")},
    )

    assert edit.status_code == 403
    assert picture.status_code == 403

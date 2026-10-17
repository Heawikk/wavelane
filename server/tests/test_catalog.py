"""Upload, ingest, catalogue browsing and range streaming."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.anyio


async def test_upload_creates_a_track_with_features(client, api, account, upload_track):
    item = await upload_track(account, "01 - Testers - First Song.wav", bpm=120)
    assert item["created"] is True
    track = item["track"]

    # Filename "01 - Artist - Title" is parsed when the file carries no tags.
    assert track["title"]
    assert track["duration_ms"] > 0
    assert track["container"] == "wav"
    assert track["lossless"] is True

    detail = await client.get(f"{api}/tracks/{track['id']}", headers=account.headers)
    assert detail.status_code == 200
    features = detail.json()["features"]
    assert features is not None
    assert 0.0 <= features["energy"] <= 1.0
    assert features["language"] in {"russian", "foreign", "instrumental", "unknown"}


async def test_uploading_the_same_file_twice_is_deduplicated(
    client, api, account, wav_factory
):
    path = wav_factory("dupe.wav", freqs=(330.0,))

    async def send():
        with path.open("rb") as handle:
            return await client.post(
                f"{api}/upload",
                headers=account.headers,
                files={"files": (path.name, handle, "audio/wav")},
            )

    first = await send()
    second = await send()
    assert first.json()["uploaded"] == 1
    assert second.json()["duplicates"] == 1
    assert second.json()["uploaded"] == 0

    listing = await client.get(f"{api}/tracks", headers=account.headers)
    assert listing.json()["total"] == 1


async def test_unsupported_format_is_reported_not_raised(client, api, account, tmp_path):
    bogus = tmp_path / "notes.txt"
    bogus.write_text("this is not audio")
    with bogus.open("rb") as handle:
        response = await client.post(
            f"{api}/upload",
            headers=account.headers,
            files={"files": (bogus.name, handle, "text/plain")},
        )
    assert response.status_code == 201
    payload = response.json()
    assert payload["failed"] == 1
    assert "unsupported audio format" in payload["items"][0]["error"]


async def test_stream_returns_full_file_and_accepts_ranges(
    client, api, account, upload_track
):
    track = (await upload_track(account, "stream-me.wav", seconds=2.0))["track"]
    track_id = track["id"]

    full = await client.get(f"{api}/stream/{track_id}", headers=account.headers)
    assert full.status_code == 200
    assert full.headers["accept-ranges"] == "bytes"
    total = int(full.headers["content-length"])
    assert len(full.content) == total

    partial = await client.get(
        f"{api}/stream/{track_id}",
        headers={**account.headers, "Range": "bytes=0-1023"},
    )
    assert partial.status_code == 206
    assert partial.headers["content-range"] == f"bytes 0-1023/{total}"
    assert len(partial.content) == 1024
    assert partial.content == full.content[:1024]

    # An open-ended range reads to the end of the file.
    tail = await client.get(
        f"{api}/stream/{track_id}",
        headers={**account.headers, "Range": f"bytes={total - 100}-"},
    )
    assert tail.status_code == 206
    assert len(tail.content) == 100
    assert tail.content == full.content[-100:]

    # A suffix range asks for the final N bytes.
    suffix = await client.get(
        f"{api}/stream/{track_id}", headers={**account.headers, "Range": "bytes=-50"}
    )
    assert suffix.status_code == 206
    assert suffix.content == full.content[-50:]


async def test_range_beyond_end_of_file_is_rejected(client, api, account, upload_track):
    track = (await upload_track(account, "short.wav", seconds=1.0))["track"]
    full = await client.get(f"{api}/stream/{track['id']}", headers=account.headers)
    total = int(full.headers["content-length"])

    response = await client.get(
        f"{api}/stream/{track['id']}",
        headers={**account.headers, "Range": f"bytes={total + 10}-{total + 20}"},
    )
    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{total}"


async def test_stream_requires_authentication(client, api, account, upload_track):
    track = (await upload_track(account, "private.wav"))["track"]
    anonymous = await client.get(f"{api}/stream/{track['id']}")
    assert anonymous.status_code == 401


async def test_stream_token_allows_header_free_playback(
    client, api, account, upload_track
):
    track = (await upload_track(account, "tokenised.wav"))["track"]

    issued = await client.get(
        f"{api}/tracks/{track['id']}/stream-token", headers=account.headers
    )
    assert issued.status_code == 200
    token = issued.json()["token"]

    # No Authorization header at all — this is how a media player fetches it.
    played = await client.get(f"{api}/stream/{track['id']}?token={token}")
    assert played.status_code == 200
    assert len(played.content) > 0


async def test_stream_token_is_bound_to_one_track(
    client, api, account, upload_track
):
    first = (await upload_track(account, "one.wav", freqs=(220.0,)))["track"]
    second = (await upload_track(account, "two.wav", freqs=(660.0,)))["track"]

    issued = await client.get(
        f"{api}/tracks/{first['id']}/stream-token", headers=account.headers
    )
    token = issued.json()["token"]

    wrong = await client.get(f"{api}/stream/{second['id']}?token={token}")
    assert wrong.status_code == 403


async def test_search_finds_tracks_by_title(client, api, account, upload_track):
    await upload_track(account, "Nebula Drift.wav")
    await upload_track(account, "Harbour Lights.wav")

    found = await client.get(f"{api}/search?q=nebula", headers=account.headers)
    assert found.status_code == 200
    titles = [t["title"] for t in found.json()["tracks"]]
    assert any("Nebula" in title for title in titles)

    missing = await client.get(f"{api}/search?q=zzzznothing", headers=account.headers)
    assert missing.json()["tracks"] == []


async def test_track_metadata_can_be_corrected(client, api, account, upload_track):
    track = (await upload_track(account, "wrong-title.wav"))["track"]

    updated = await client.patch(
        f"{api}/tracks/{track['id']}",
        headers=account.headers,
        json={"title": "Correct Title", "explicit": True, "genres": ["Ambient", "Lo-Fi"]},
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["title"] == "Correct Title"
    assert payload["explicit"] is True
    assert set(payload["genres"]) == {"ambient", "lo-fi"}


async def test_non_owner_cannot_edit_a_track(client, api, account, register, upload_track):
    track = (await upload_track(account, "mine.wav"))["track"]
    other = await register("intruder")

    response = await client.patch(
        f"{api}/tracks/{track['id']}",
        headers=other.headers,
        json={"title": "Hijacked"},
    )
    assert response.status_code == 403


async def test_pagination_reports_totals(client, api, account, upload_track):
    for index in range(5):
        await upload_track(account, f"page-{index}.wav", freqs=(200.0 + index * 40,))

    page = await client.get(f"{api}/tracks?limit=2&offset=0", headers=account.headers)
    assert page.status_code == 200
    payload = page.json()
    assert payload["total"] == 5
    assert len(payload["items"]) == 2
    assert payload["limit"] == 2

    last = await client.get(f"{api}/tracks?limit=2&offset=4", headers=account.headers)
    assert len(last.json()["items"]) == 1

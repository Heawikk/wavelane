"""Admin-only import, conflicts, folder imports, deletion and clean-up."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from wavelane.services.conflicts import recommend

pytestmark = pytest.mark.anyio


def audio_files(settings) -> list[Path]:
    return [p for p in settings.audio_dir.rglob("*") if p.is_file()]


async def upload_path(client, api, account, path: Path) -> dict:
    with path.open("rb") as handle:
        response = await client.post(
            f"{api}/upload",
            headers=account.headers,
            files={"files": (path.name, handle, "audio/wav")},
        )
    assert response.status_code == 201, response.text
    return response.json()


async def wait_for_job(client, api, account, job_id: str, patience: float = 40.0) -> dict:
    deadline = asyncio.get_event_loop().time() + patience
    while True:
        response = await client.get(f"{api}/admin/imports/{job_id}", headers=account.headers)
        job = response.json()
        if job["state"] in ("done", "cancelled", "failed"):
            return job
        assert asyncio.get_event_loop().time() < deadline, f"import stuck: {job}"
        await asyncio.sleep(0.2)


# ---------------------------------------------------------------------------
# Who may do what
# ---------------------------------------------------------------------------


async def test_only_administrators_may_import_or_delete(
    client, api, account, register, upload_track, tmp_path
):
    track = (await upload_track(account, "owned.wav"))["track"]
    guest = await register("guest")
    assert guest.is_admin is False

    wav = tmp_path / "guest.wav"
    wav.write_bytes(b"RIFF")
    with wav.open("rb") as handle:
        upload = await client.post(
            f"{api}/upload", headers=guest.headers, files={"files": ("guest.wav", handle)}
        )
    assert upload.status_code == 403

    assert (
        await client.post(
            f"{api}/admin/imports", headers=guest.headers, json={"path": str(tmp_path)}
        )
    ).status_code == 403
    assert (await client.get(f"{api}/imports/conflicts", headers=guest.headers)).status_code == 403
    assert (
        await client.post(
            f"{api}/imports/conflicts/resolve",
            headers=guest.headers,
            json={"resolutions": [{"conflict_id": "x", "action": "keep_old"}]},
        )
    ).status_code == 403
    assert (
        await client.delete(f"{api}/tracks/{track['id']}", headers=guest.headers)
    ).status_code == 403
    assert (
        await client.post(
            f"{api}/tracks/bulk-delete", headers=guest.headers, json={"track_ids": [track["id"]]}
        )
    ).status_code == 403
    assert (await client.post(f"{api}/admin/cleanup", headers=guest.headers)).status_code == 403

    # ...and the track survived all of that.
    still_there = await client.get(f"{api}/tracks/{track['id']}", headers=account.headers)
    assert still_there.status_code == 200


# ---------------------------------------------------------------------------
# Conflicts
# ---------------------------------------------------------------------------


def same_recording(factory, name: str, *, freq: float, seconds: float = 1.0) -> Path:
    """Same tags, different audio: the same song as a different file."""
    return factory(
        filename=name,
        title="Harbour Lights",
        artist="Tidewater",
        album="Coastline",
        freqs=(freq,),
        seconds=seconds,
    )


async def test_identical_file_is_a_duplicate_not_a_conflict(
    client, api, account, tagged_wav_factory
):
    path = same_recording(tagged_wav_factory, "a.wav", freq=220.0)
    await upload_path(client, api, account, path)
    again = await upload_path(client, api, account, path)

    assert again["duplicates"] == 1
    assert again["conflicts"] == 0
    assert again["items"][0]["status"] == "duplicate"


async def test_a_different_file_of_the_same_song_is_a_conflict(
    client, api, account, tagged_wav_factory, app_env
):
    first = same_recording(tagged_wav_factory, "first.wav", freq=220.0)
    second = same_recording(tagged_wav_factory, "second.wav", freq=330.0)

    await upload_path(client, api, account, first)
    result = await upload_path(client, api, account, second)

    assert result["conflicts"] == 1
    assert result["uploaded"] == 0
    item = result["items"][0]
    assert item["status"] == "conflict"
    conflict = item["conflict"]
    assert conflict["title"] == "Harbour Lights"
    assert conflict["artist_name"] == "Tidewater"
    assert conflict["existing"]["lossless"] is True
    assert conflict["incoming"]["container"] == "wav"
    # Same format and bitrate: nothing says the new one is better.
    assert conflict["recommended"] == "keep_old"

    # Nothing was added while the question is open, but the file is held.
    tracks = await client.get(f"{api}/tracks", headers=account.headers)
    assert tracks.json()["total"] == 1
    assert len(audio_files(app_env)) == 2

    pending = await client.get(f"{api}/imports/conflicts", headers=account.headers)
    assert [c["id"] for c in pending.json()] == [conflict["id"]]


async def test_keeping_the_old_file_discards_the_new_one(
    client, api, account, tagged_wav_factory, app_env
):
    first = same_recording(tagged_wav_factory, "first.wav", freq=220.0)
    second = same_recording(tagged_wav_factory, "second.wav", freq=330.0)
    created = await upload_path(client, api, account, first)
    track_id = created["items"][0]["track"]["id"]
    conflict = (await upload_path(client, api, account, second))["items"][0]["conflict"]

    resolved = await client.post(
        f"{api}/imports/conflicts/resolve",
        headers=account.headers,
        json={"resolutions": [{"conflict_id": conflict["id"], "action": "keep_old"}]},
    )
    assert resolved.status_code == 200
    assert resolved.json()["kept_old"] == 1

    # The track still plays the original file, and the new one is gone.
    stream = await client.get(f"{api}/stream/{track_id}", headers=account.headers)
    assert stream.content == first.read_bytes()
    assert len(audio_files(app_env)) == 1
    assert (await client.get(f"{api}/imports/conflicts", headers=account.headers)).json() == []


async def test_replacing_keeps_the_track_and_everything_attached_to_it(
    client, api, account, tagged_wav_factory, app_env
):
    first = same_recording(tagged_wav_factory, "first.wav", freq=220.0)
    second = same_recording(tagged_wav_factory, "second.wav", freq=330.0)
    created = await upload_path(client, api, account, first)
    track_id = created["items"][0]["track"]["id"]

    # Things a replacement must not lose: a like and a playlist entry.
    await client.put(
        f"{api}/library/tracks/{track_id}/reaction", headers=account.headers, json={"kind": "like"}
    )
    playlist = await client.post(
        f"{api}/playlists", headers=account.headers,
        json={"title": "Keep", "track_ids": [track_id]},
    )
    playlist_id = playlist.json()["id"]

    conflict = (await upload_path(client, api, account, second))["items"][0]["conflict"]
    resolved = await client.post(
        f"{api}/imports/conflicts/resolve",
        headers=account.headers,
        json={"resolutions": [{"conflict_id": conflict["id"], "action": "replace"}]},
    )
    assert resolved.json()["replaced"] == 1

    # Same track, new audio.
    stream = await client.get(f"{api}/stream/{track_id}", headers=account.headers)
    assert stream.content == second.read_bytes()
    assert len(audio_files(app_env)) == 1, "the superseded file should have been removed"

    detail = await client.get(f"{api}/tracks/{track_id}", headers=account.headers)
    assert detail.json()["liked"] is True
    assert (await client.get(f"{api}/tracks", headers=account.headers)).json()["total"] == 1
    kept = await client.get(f"{api}/playlists/{playlist_id}", headers=account.headers)
    assert [t["id"] for t in kept.json()["tracks"]] == [track_id]


async def test_a_clearly_different_length_is_a_separate_track(
    client, api, account, tagged_wav_factory
):
    """A radio edit and an extended mix share tags but are different recordings."""
    short = same_recording(tagged_wav_factory, "short.wav", freq=220.0, seconds=1.0)
    long = same_recording(tagged_wav_factory, "long.wav", freq=330.0, seconds=14.0)
    await upload_path(client, api, account, short)
    result = await upload_path(client, api, account, long)

    assert result["conflicts"] == 0
    assert result["uploaded"] == 1
    assert (await client.get(f"{api}/tracks", headers=account.headers)).json()["total"] == 2


async def test_resolving_an_unknown_conflict_is_reported_not_raised(client, api, account):
    response = await client.post(
        f"{api}/imports/conflicts/resolve",
        headers=account.headers,
        json={"resolutions": [{"conflict_id": "does-not-exist", "action": "replace"}]},
    )
    assert response.status_code == 200
    assert response.json()["not_found"] == 1


def fake_existing(*, lossless: bool, bitrate: int):
    return SimpleNamespace(lossless=lossless, bitrate_kbps=bitrate)


def fake_incoming(*, lossless: bool, bitrate: int):
    return SimpleNamespace(
        stored=SimpleNamespace(lossless=lossless), meta=SimpleNamespace(bitrate_kbps=bitrate)
    )


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ((False, 128), (True, 900), "replace"),    # lossless beats lossy
        ((True, 900), (False, 320), "keep_old"),   # never trade lossless for lossy
        ((False, 128), (False, 320), "replace"),   # clearly higher bitrate
        ((False, 320), (False, 128), "keep_old"),
        ((False, 192), (False, 194), "keep_old"),  # within the margin: not worth churning
        ((True, 900), (True, 1100), "keep_old"),   # both lossless: nothing to gain
    ],
)
def test_recommendation(old, new, expected):
    existing = fake_existing(lossless=old[0], bitrate=old[1])
    incoming = fake_incoming(lossless=new[0], bitrate=new[1])
    assert recommend(existing, incoming) == expected


# ---------------------------------------------------------------------------
# Folder imports
# ---------------------------------------------------------------------------


def build_music_folder(root: Path, factory) -> None:
    root.mkdir()
    for index in range(3):
        path = factory(
            filename=f"track{index}.wav",
            title=f"Song {index}",
            artist="Folder Band",
            album="Folder Album",
            freqs=(200.0 + index * 90,),
        )
        shutil.copy(path, root / path.name)

    # an exact copy: a duplicate
    shutil.copy(root / "track0.wav", root / "track0-copy.wav")

    # the same song as track1 but a different file: a conflict
    clash = factory(
        filename="clash.wav", title="Song 1", artist="Folder Band", album="Folder Album",
        freqs=(777.0,),
    )
    shutil.copy(clash, root / "clash.wav")

    # not audio: ignored, not an error
    (root / "notes.txt").write_text("not music")
    # nested folders are included
    nested = root / "deep" / "er"
    nested.mkdir(parents=True)
    extra = factory(
        filename="nested.wav", title="Nested Song", artist="Folder Band", album="Folder Album",
        freqs=(1234.0,),
    )
    shutil.copy(extra, nested / "nested.wav")


async def test_folder_import_reports_what_it_did(
    client, api, account, tagged_wav_factory, tmp_path
):
    folder = tmp_path / "library"
    build_music_folder(folder, tagged_wav_factory)

    started = await client.post(
        f"{api}/admin/imports", headers=account.headers, json={"path": str(folder)}
    )
    assert started.status_code == 202
    job = await wait_for_job(client, api, account, started.json()["id"])

    assert job["state"] == "done"
    # 3 tracks + 1 copy + 1 clash + 1 nested; notes.txt is not counted
    assert job["total"] == 6
    assert job["processed"] == 6
    assert job["failed"] == 0, job["errors"]
    assert job["duplicates"] == 1
    assert job["conflicts"] == 1
    assert job["imported"] == 4

    tracks = await client.get(f"{api}/tracks?limit=50", headers=account.headers)
    assert tracks.json()["total"] == 4

    pending = await client.get(f"{api}/imports/conflicts", headers=account.headers)
    assert len(pending.json()) == 1
    assert pending.json()[0]["job_id"] == job["id"]


async def test_importing_a_folder_twice_adds_nothing_new(
    client, api, account, tagged_wav_factory, tmp_path
):
    folder = tmp_path / "library"
    build_music_folder(folder, tagged_wav_factory)

    first = await client.post(
        f"{api}/admin/imports", headers=account.headers, json={"path": str(folder)}
    )
    await wait_for_job(client, api, account, first.json()["id"])

    second = await client.post(
        f"{api}/admin/imports", headers=account.headers, json={"path": str(folder)}
    )
    job = await wait_for_job(client, api, account, second.json()["id"])

    assert job["imported"] == 0
    assert job["failed"] == 0
    # Every file is now a duplicate of something already in the library. The
    # conflicting file from the first run is still held, so it is a duplicate of
    # nothing and conflicts again.
    assert job["duplicates"] + job["conflicts"] == job["total"]


async def test_only_one_import_runs_at_a_time(client, api, account, tagged_wav_factory, tmp_path):
    folder = tmp_path / "library"
    build_music_folder(folder, tagged_wav_factory)

    first = await client.post(
        f"{api}/admin/imports", headers=account.headers, json={"path": str(folder)}
    )
    second = await client.post(
        f"{api}/admin/imports", headers=account.headers, json={"path": str(folder)}
    )
    assert first.status_code == 202
    assert second.status_code == 409

    await wait_for_job(client, api, account, first.json()["id"])


async def test_cancelling_an_import_stops_it(client, api, account, tagged_wav_factory, tmp_path):
    folder = tmp_path / "many"
    folder.mkdir()
    for index in range(40):
        path = tagged_wav_factory(
            filename=f"m{index}.wav", title=f"Bulk {index}", artist=f"Band {index}",
            freqs=(150.0 + index * 11,),
        )
        shutil.copy(path, folder / path.name)

    started = await client.post(
        f"{api}/admin/imports", headers=account.headers, json={"path": str(folder)}
    )
    cancelled = await client.post(
        f"{api}/admin/imports/{started.json()['id']}/cancel", headers=account.headers
    )
    assert cancelled.status_code == 200
    job = await wait_for_job(client, api, account, started.json()["id"])

    assert job["state"] == "cancelled"
    assert job["processed"] < job["total"]


async def test_import_rejects_a_missing_folder_or_a_file(client, api, account, tmp_path):
    missing = await client.post(
        f"{api}/admin/imports", headers=account.headers, json={"path": str(tmp_path / "nope")}
    )
    assert missing.status_code == 400

    a_file = tmp_path / "file.txt"
    a_file.write_text("x")
    not_a_dir = await client.post(
        f"{api}/admin/imports", headers=account.headers, json={"path": str(a_file)}
    )
    assert not_a_dir.status_code == 400


async def test_an_unknown_import_is_a_404(client, api, account):
    assert (
        await client.get(f"{api}/admin/imports/nope", headers=account.headers)
    ).status_code == 404


# ---------------------------------------------------------------------------
# Deleting
# ---------------------------------------------------------------------------


async def make_album(client, api, account, factory, count: int = 2) -> list[dict]:
    tracks = []
    for index in range(count):
        path = factory(
            filename=f"del{index}.wav", title=f"Delete Me {index}", artist="Short Lived",
            album="Gone Soon", freqs=(300.0 + index * 70,), track=f"{index + 1}/{count}",
        )
        result = await upload_path(client, api, account, path)
        tracks.append(result["items"][0]["track"])
    return tracks


async def test_deleting_a_track_removes_its_file_and_keeps_the_rest(
    client, api, account, tagged_wav_factory, app_env
):
    first, second = await make_album(client, api, account, tagged_wav_factory)
    assert len(audio_files(app_env)) == 2

    deleted = await client.delete(f"{api}/tracks/{first['id']}", headers=account.headers)
    assert deleted.status_code == 200
    body = deleted.json()
    assert body["deleted"] == 1
    assert body["files_removed"] == 1
    # The album and the artist still have a track, so they stay.
    assert body["albums_removed"] == 0
    assert body["artists_removed"] == 0

    gone = await client.get(f"{api}/tracks/{first['id']}", headers=account.headers)
    kept = await client.get(f"{api}/tracks/{second['id']}", headers=account.headers)
    assert gone.status_code == 404
    assert kept.status_code == 200
    assert len(audio_files(app_env)) == 1

    artists = await client.get(f"{api}/artists", headers=account.headers)
    assert artists.json()["items"][0]["track_count"] == 1


async def test_deleting_the_last_track_removes_the_empty_album_and_artist(
    client, api, account, tagged_wav_factory, app_env
):
    first, second = await make_album(client, api, account, tagged_wav_factory)
    await client.delete(f"{api}/tracks/{first['id']}", headers=account.headers)
    last = await client.delete(f"{api}/tracks/{second['id']}", headers=account.headers)

    assert last.json()["albums_removed"] == 1
    assert last.json()["artists_removed"] == 1
    assert (await client.get(f"{api}/albums", headers=account.headers)).json()["items"] == []
    assert (await client.get(f"{api}/artists", headers=account.headers)).json()["items"] == []
    assert audio_files(app_env) == []


async def test_bulk_delete_and_playlist_totals(
    client, api, account, tagged_wav_factory, app_env
):
    first, second = await make_album(client, api, account, tagged_wav_factory)
    playlist = await client.post(
        f"{api}/playlists", headers=account.headers,
        json={"title": "Mix", "track_ids": [first["id"], second["id"]]},
    )
    playlist_id = playlist.json()["id"]
    assert playlist.json()["track_count"] == 2

    # deleting one of two leaves the playlist with one, and correct totals
    await client.delete(f"{api}/tracks/{first['id']}", headers=account.headers)
    after_one = await client.get(f"{api}/playlists/{playlist_id}", headers=account.headers)
    assert after_one.json()["track_count"] == 1
    assert after_one.json()["duration_ms"] == second["duration_ms"]

    bulk = await client.post(
        f"{api}/tracks/bulk-delete",
        headers=account.headers,
        json={"track_ids": [second["id"], first["id"]]},  # one is already gone
    )
    assert bulk.status_code == 200
    assert bulk.json()["deleted"] == 1
    assert audio_files(app_env) == []
    emptied = await client.get(f"{api}/playlists/{playlist_id}", headers=account.headers)
    assert emptied.json()["track_count"] == 0


async def test_deleting_an_unknown_track_is_a_404(client, api, account):
    response = await client.delete(
        f"{api}/tracks/00000000-0000-0000-0000-000000000000", headers=account.headers
    )
    assert response.status_code == 404


async def test_deleting_a_track_drops_its_history_and_reactions(
    client, api, account, tagged_wav_factory
):
    (track, _) = await make_album(client, api, account, tagged_wav_factory)
    await client.put(
        f"{api}/library/tracks/{track['id']}/reaction", headers=account.headers,
        json={"kind": "like"},
    )
    await client.post(
        f"{api}/library/plays", headers=account.headers,
        json={"track_id": track["id"], "ms_played": 900, "completed": True},
    )

    await client.delete(f"{api}/tracks/{track['id']}", headers=account.headers)

    liked = await client.get(f"{api}/library/liked", headers=account.headers)
    history = await client.get(f"{api}/library/history", headers=account.headers)
    assert liked.json()["items"] == []
    assert history.json()["items"] == []


# ---------------------------------------------------------------------------
# Clean-up
# ---------------------------------------------------------------------------


async def test_cleanup_removes_orphans_but_not_tracked_or_held_files(
    client, api, account, tagged_wav_factory, app_env
):
    first = same_recording(tagged_wav_factory, "first.wav", freq=220.0)
    second = same_recording(tagged_wav_factory, "second.wav", freq=330.0)
    await upload_path(client, api, account, first)
    await upload_path(client, api, account, second)  # held: waiting for a decision

    orphan = app_env.audio_dir / "ab" / "cd" / "stray.wav"
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"x" * 1000)
    assert len(audio_files(app_env)) == 3

    result = await client.post(f"{api}/admin/cleanup", headers=account.headers)
    assert result.status_code == 200
    assert result.json()["files_removed"] == 1
    assert result.json()["bytes_freed"] == 1000
    # the tracked file and the one waiting on a conflict are both still there
    assert len(audio_files(app_env)) == 2
    assert (await client.get(f"{api}/imports/conflicts", headers=account.headers)).json()


async def test_cleanup_refuses_to_run_on_an_empty_catalogue(client, api, account, app_env):
    """A fresh database next to a full music folder must not wipe the folder."""
    survivor = app_env.audio_dir / "ab" / "cd" / "precious.flac"
    survivor.parent.mkdir(parents=True)
    survivor.write_bytes(b"x")

    response = await client.post(f"{api}/admin/cleanup", headers=account.headers)
    assert response.status_code == 409
    assert survivor.exists()

"""Tag reading, artist/album creation and metadata heuristics."""

from __future__ import annotations

import pytest

from wavelane.services.ingest import (
    _guess_album_type,
    _parse_date,
    _parse_pair,
    _split_artists,
    _title_from_filename,
    read_metadata,
)

pytestmark = pytest.mark.anyio


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_artist_splitting_keeps_band_names_intact():
    """Commas and ampersands belong to names more often than they separate them."""
    main, featured = _split_artists(["Earth, Wind & Fire"], "September")
    assert main == ["Earth, Wind & Fire"]
    assert featured == []

    main, featured = _split_artists(["Simon and Garfunkel"], "America")
    assert main == ["Simon and Garfunkel"]

    # Reserved separators do split.
    main, _ = _split_artists(["Artist A; Artist B"], "Song")
    assert main == ["Artist A", "Artist B"]

    main, _ = _split_artists(["Artist A/Artist B"], "Song")
    assert main == ["Artist A", "Artist B"]


def test_featured_artists_are_separated():
    main, featured = _split_artists(["Main Act feat. Guest One & Guest Two"], "Track")
    assert main == ["Main Act"]
    assert featured == ["Guest One", "Guest Two"]


def test_feature_credit_in_the_title_is_picked_up():
    main, featured = _split_artists(["Solo Act"], "Big Song (feat. Someone Else)")
    assert main == ["Solo Act"]
    assert featured == ["Someone Else"]


def test_duplicate_feature_credit_is_not_repeated():
    main, featured = _split_artists(["Band X feat. Band X"], "Song")
    assert main == ["Band X"]
    assert featured == []


@pytest.mark.parametrize(
    ("value", "expected_year"),
    [
        ("1997", 1997),
        ("2014-03-21", 2014),
        ("21.03.2014", 2014),
        ("2014-03", 2014),
        ("released in 1982 originally", 1982),
        ("garbage", None),
        ("", None),
    ],
)
def test_date_parsing(value, expected_year):
    _, year = _parse_date(value)
    assert year == expected_year


@pytest.mark.parametrize(
    ("value", "expected"),
    [("3/12", (3, 12)), ("7", (7, None)), ("", (None, None)), ("05/009", (5, 9))],
)
def test_track_pair_parsing(value, expected):
    assert _parse_pair(value) == expected


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        ("05 - Artist - The Song", "The Song"),
        ("The Song", "The Song"),
        ("12. Another_Song", "Another Song"),
        ("Artist - Song Name", "Song Name"),
    ],
)
def test_title_from_filename(tmp_path, stem, expected):
    assert _title_from_filename(tmp_path / f"{stem}.wav") == expected


def test_album_type_is_guessed_from_track_count_and_title():
    from wavelane.models import AlbumType
    from wavelane.services.ingest import TrackMetadata

    assert _guess_album_type(TrackMetadata(album="Some Single", total_tracks=1)) is (
        AlbumType.SINGLE
    )
    assert _guess_album_type(TrackMetadata(album="Short EP", total_tracks=4)) is AlbumType.EP
    assert _guess_album_type(TrackMetadata(album="Live at Wembley", total_tracks=20)) is (
        AlbumType.LIVE
    )
    assert _guess_album_type(TrackMetadata(album="Greatest Hits", total_tracks=18)) is (
        AlbumType.COMPILATION
    )
    assert _guess_album_type(TrackMetadata(album="Normal Record", total_tracks=11)) is (
        AlbumType.ALBUM
    )


# ---------------------------------------------------------------------------
# Reading real files
# ---------------------------------------------------------------------------


def test_metadata_is_read_from_tags(tagged_wav_factory):
    path = tagged_wav_factory(
        title="Night Drive",
        artist="Neon District feat. Vera",
        album="City Lights",
        album_artist="Neon District",
        genre="Synthwave",
        year="2019",
        track="4/10",
    )
    meta = read_metadata(path)

    assert meta.title == "Night Drive"
    assert meta.artists == ["Neon District"]
    assert meta.featured_artists == ["Vera"]
    assert meta.album == "City Lights"
    assert meta.album_artist == "Neon District"
    assert meta.genres == ["Synthwave"]
    assert meta.release_year == 2019
    assert meta.track_number == 4
    assert meta.total_tracks == 10
    assert meta.duration_ms > 0


def test_filename_hint_is_used_when_tags_are_missing(wav_factory, tmp_path):
    """Stored files are named by hash, so the hint carries the real name."""
    stored = wav_factory("f1d2d2f924e986ac86fdf7b36c94bcdf32beec15.wav")
    meta = read_metadata(stored, source_hint="03 - Quiet Hours - Lantern.wav")

    assert meta.title == "Lantern"
    assert meta.artists == ["Quiet Hours"]
    assert meta.track_number == 3


def test_tagless_file_falls_back_to_its_own_name(wav_factory):
    path = wav_factory("Mystery Artist - Mystery Song.wav")
    meta = read_metadata(path)
    assert meta.title == "Mystery Song"
    assert meta.artists == ["Mystery Artist"]


# ---------------------------------------------------------------------------
# Through the API
# ---------------------------------------------------------------------------


async def test_tagged_upload_creates_artist_album_and_genre(
    client, api, account, tagged_wav_factory
):
    path = tagged_wav_factory(
        filename="tagged-upload.wav",
        title="Harbour",
        artist="Tidewater",
        album="Coastline",
        genre="Ambient",
        year="2021",
        track="2/9",
    )
    with path.open("rb") as handle:
        response = await client.post(
            f"{api}/upload",
            headers=account.headers,
            files={"files": (path.name, handle, "audio/wav")},
        )
    assert response.status_code == 201, response.text
    track = response.json()["items"][0]["track"]

    assert track["title"] == "Harbour"
    assert track["artist_name"] == "Tidewater"
    assert track["album"]["title"] == "Coastline"
    assert track["album"]["release_year"] == 2021
    assert track["track_number"] == 2
    assert "ambient" in track["genres"]

    # The genre prior should make an ambient track read as calm and instrumental.
    detail = await client.get(f"{api}/tracks/{track['id']}", headers=account.headers)
    features = detail.json()["features"]
    assert features["energy"] < 0.4
    assert features["instrumentalness"] > 0.7
    assert features["source"] == "metadata"

    albums = await client.get(f"{api}/albums", headers=account.headers)
    assert [a["title"] for a in albums.json()["items"]] == ["Coastline"]

    artists = await client.get(f"{api}/artists", headers=account.headers)
    assert [a["name"] for a in artists.json()["items"]] == ["Tidewater"]


_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360f8cfc0f01f0005000201a5f645400000000049454e44ae426082"
)


async def _upload(client, api, account, path):
    with path.open("rb") as handle:
        response = await client.post(
            f"{api}/upload",
            headers=account.headers,
            files={"files": (path.name, handle, "audio/wav")},
        )
    assert response.status_code == 201, response.text
    return response.json()["items"][0]["track"]


async def test_embedded_cover_is_kept_without_an_album_tag(
    client, api, account, tagged_wav_factory
):
    """A single has no album row to hold its artwork; the track must keep it itself."""
    path = tagged_wav_factory(title="Lone Song", artist="Solo", cover=_PNG)
    track = await _upload(client, api, account, path)

    assert track["album"] is None
    assert track["cover_path"]

    image = await client.get(f"{api}/covers/{track['cover_path']}")
    assert image.status_code == 200
    assert image.content == _PNG


async def test_embedded_cover_of_an_album_track_still_belongs_to_the_album(
    client, api, account, tagged_wav_factory
):
    path = tagged_wav_factory(title="On A Record", artist="Solo", album="Record", cover=_PNG)
    track = await _upload(client, api, account, path)

    assert track["album"]["cover_path"]
    assert track["cover_path"] == track["album"]["cover_path"]


async def test_tracks_of_one_album_are_grouped(client, api, account, tagged_wav_factory):
    for index in range(3):
        path = tagged_wav_factory(
            filename=f"grouped-{index}.wav",
            freqs=(220.0 + index * 55,),
            title=f"Part {index + 1}",
            artist="One Band",
            album="One Record",
            track=f"{index + 1}/3",
        )
        with path.open("rb") as handle:
            response = await client.post(
                f"{api}/upload",
                headers=account.headers,
                files={"files": (path.name, handle, "audio/wav")},
            )
        assert response.status_code == 201

    albums = await client.get(f"{api}/albums", headers=account.headers)
    items = albums.json()["items"]
    assert len(items) == 1, "all three tracks should share one album"

    tracks = await client.get(
        f"{api}/albums/{items[0]['id']}/tracks", headers=account.headers
    )
    titles = [t["title"] for t in tracks.json()]
    assert titles == ["Part 1", "Part 2", "Part 3"]


async def test_album_artist_wins_over_track_artist(
    client, api, account, tagged_wav_factory
):
    """A compilation must not be filed under whoever performed track one."""
    path = tagged_wav_factory(
        filename="compilation.wav",
        title="Guest Spot",
        artist="Featured Performer",
        album="Various Sessions",
        album_artist="Various Artists",
    )
    with path.open("rb") as handle:
        await client.post(
            f"{api}/upload",
            headers=account.headers,
            files={"files": (path.name, handle, "audio/wav")},
        )

    albums = await client.get(f"{api}/albums", headers=account.headers)
    album = albums.json()["items"][0]
    detail = await client.get(f"{api}/albums/{album['id']}", headers=account.headers)
    assert detail.json()["artist"]["name"] == "Various Artists"

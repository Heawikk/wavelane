"""Artists named "A, B, C" are really several artists: in new uploads and in what is already stored."""

from __future__ import annotations

import pytest

from wavelane.services.credits import split_artist_name, split_commas

pytestmark = pytest.mark.anyio


def test_commas_separate_artists():
    assert split_commas("A, B,C") == ["A", "B", "C"]
    assert split_commas("Solo") == ["Solo"]
    assert split_commas("") == []


def test_acts_with_a_comma_in_the_name_stay_whole():
    assert split_commas("Tyler, The Creator") == ["Tyler, The Creator"]
    assert split_commas("Earth, Wind & Fire, Kendrick Lamar") == ["Earth, Wind & Fire", "Kendrick Lamar"]
    assert split_commas("Sammy Davis, Jr., Frank") == ["Sammy Davis, Jr.", "Frank"]


def test_ampersands_are_left_alone():
    assert split_commas("Above & Beyond") == ["Above & Beyond"]
    assert split_artist_name("Король и Шут") == ["Король и Шут"]


def test_a_name_that_repeats_one_artist_is_that_artist():
    assert split_artist_name("Tinlicker, Tinlicker") == ["Tinlicker"]
    assert split_artist_name("Tinlicker") == ["Tinlicker"]


async def test_upload_makes_one_artist_per_name(client, api, account, tagged_wav_factory):
    path = tagged_wav_factory(
        title="Ты какую группу уважаешь?", artist="M1LUM, Орущий дед, Фазер Мартин", album="Single"
    )
    with path.open("rb") as handle:
        response = await client.post(
            f"{api}/upload", headers=account.headers, files={"files": (path.name, handle, "audio/wav")}
        )
    track = response.json()["items"][0]["track"]

    assert [a["name"] for a in track["artists"]] == ["M1LUM", "Орущий дед", "Фазер Мартин"]
    artists = (await client.get(f"{api}/artists?limit=50", headers=account.headers)).json()["items"]
    assert sorted(a["name"] for a in artists) == sorted(["M1LUM", "Орущий дед", "Фазер Мартин"])


async def test_stored_lists_are_split_on_every_track_album_and_follow(client, api, account, register):
    import uuid

    from sqlalchemy import func, select

    from wavelane.db import get_session_factory
    from wavelane.models import Album, Artist, ArtistReaction, Track, TrackArtist
    from wavelane.models.enums import ArtistRole
    from wavelane.services.artist_split import split_combined_artists
    from wavelane.utils import normalize_name, now_utc

    me = account.user["id"]
    factory = get_session_factory()
    async with factory() as session:
        def artist(name: str) -> Artist:
            row = Artist(name=name, normalized_name=normalize_name(name), sort_name=name)
            session.add(row)
            return row

        combined, alone, other = artist("Ann, Bob, Cat"), artist("Ann"), artist("Dan, Eve")
        await session.flush()

        # an album under the combined artist, and one that "Ann" already has under the same title
        moved = Album(title="Moved", normalized_title="moved", artist_id=other.id)
        dup_old = Album(title="Same", normalized_title="same", artist_id=combined.id)
        dup_new = Album(title="Same", normalized_title="same", artist_id=alone.id)
        session.add_all([moved, dup_old, dup_new])
        await session.flush()

        def track(title: str, album: Album | None, *links: tuple[Artist, ArtistRole]) -> Track:
            row = Track(
                title=title, normalized_title=normalize_name(title), album_id=album.id if album else None,
                storage_path=f"x/{title}", content_hash=uuid.uuid4().hex + uuid.uuid4().hex,
            )
            session.add(row)
            return row, links

        built = [
            track("T1", dup_old, (combined, ArtistRole.MAIN), (other, ArtistRole.FEATURED)),
            track("T2", moved, (other, ArtistRole.MAIN)),
            track("T3", None, (alone, ArtistRole.MAIN), (combined, ArtistRole.FEATURED)),
        ]
        await session.flush()
        for row, links in built:
            for position, (who, role) in enumerate(links):
                session.add(TrackArtist(track_id=row.id, artist_id=who.id, role=role, position=position))
        session.add(
            ArtistReaction(user_id=uuid.UUID(me), artist_id=combined.id, kind="follow", created_at=now_utc())
        )
        await session.commit()

    async with factory() as session:
        report = await split_combined_artists(session)
        await session.commit()

    assert report.combined == 2
    async with factory() as session:
        names = set(await session.scalars(select(Artist.name)))
        assert names == {"Ann", "Bob", "Cat", "Dan", "Eve"}

        async def credits(title: str) -> list[tuple[str, str]]:
            rows = await session.execute(
                select(Artist.name, TrackArtist.role)
                .join(TrackArtist, TrackArtist.artist_id == Artist.id)
                .join(Track, Track.id == TrackArtist.track_id)
                .where(Track.title == title)
                .order_by(TrackArtist.position)
            )
            return [(name, role.value) for name, role in rows]

        assert await credits("T1") == [
            ("Ann", "main"), ("Bob", "main"), ("Cat", "main"), ("Dan", "featured"), ("Eve", "featured")
        ]
        # Ann was already the main artist of T3, so she stays first and the others join as featured
        assert await credits("T3") == [("Ann", "main"), ("Bob", "featured"), ("Cat", "featured")]
        assert await credits("T2") == [("Dan", "main"), ("Eve", "main")]

        # the album that Ann already had absorbed the other; the other one moved to its first artist
        albums = {(a.title, a.artist.name) for a in await session.scalars(select(Album))}
        assert albums == {("Same", "Ann"), ("Moved", "Dan")}
        t1 = await session.scalar(select(Track).where(Track.title == "T1"))
        assert t1.album.title == "Same" and t1.album.artist.name == "Ann"

        # whoever followed "Ann, Bob, Cat" now follows the three of them
        followed = {
            r.artist.name for r in await session.scalars(select(ArtistReaction)) if r.kind == "follow"
        }
        assert followed == {"Ann", "Bob", "Cat"}

        # counters match the credits again, and a second run finds nothing to do
        for who in await session.scalars(select(Artist)):
            links = await session.scalar(
                select(func.count()).select_from(TrackArtist).where(TrackArtist.artist_id == who.id)
            )
            assert who.track_count == links, who.name
        assert (await split_combined_artists(session)).combined == 0

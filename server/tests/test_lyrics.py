"""Lyrics: parsing of plain and LRC text, and who may read or write them."""

from __future__ import annotations

import pytest

from wavelane.services.lyrics import (
    LyricsError,
    format_time_tag,
    parse_lyrics,
    validate_text,
)

pytestmark = pytest.mark.anyio


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_no_text_is_no_lyrics():
    for text in (None, "", "   \n \n"):
        parsed = parse_lyrics(text)
        assert parsed.kind == "none"
        assert parsed.lines == []


def test_plain_text_keeps_lines_and_verse_breaks():
    parsed = parse_lyrics("first\nsecond\n\n\n\nthird\n")
    assert parsed.kind == "plain"
    assert [ln.text for ln in parsed.lines] == ["first", "second", "", "third"]
    assert all(ln.time_ms is None for ln in parsed.lines)


def test_lrc_lines_become_synced_and_are_ordered():
    parsed = parse_lyrics("[00:12.50]second\n[00:01.00]first\n[01:02.05]third")
    assert parsed.kind == "synced"
    assert [(ln.time_ms, ln.text) for ln in parsed.lines] == [
        (1000, "first"),
        (12500, "second"),
        (62050, "third"),
    ]


def test_fraction_digits_mean_what_they_say():
    parsed = parse_lyrics("[00:01.5]a\n[00:02.05]b\n[00:03.123]c\n[00:04]d\n[00:05:25]e")
    assert [ln.time_ms for ln in parsed.lines] == [1500, 2050, 3123, 4000, 5250]


def test_one_line_with_several_tags_is_repeated():
    parsed = parse_lyrics("[00:10.00][00:40.00]chorus\n[00:20.00]verse")
    assert [(ln.time_ms, ln.text) for ln in parsed.lines] == [
        (10000, "chorus"),
        (20000, "verse"),
        (40000, "chorus"),
    ]


def test_metadata_and_credits_are_not_lyrics():
    parsed = parse_lyrics("[ar:Someone]\n[ti:Song]\nWritten by somebody\n[00:05.00]hello")
    assert parsed.kind == "synced"
    assert [ln.text for ln in parsed.lines] == ["hello"]


def test_offset_tag_shifts_every_line():
    parsed = parse_lyrics("[offset:500]\n[00:05.00]hello\n[00:00.20]early")
    # A positive offset makes lyrics appear earlier, and never before zero.
    assert [ln.time_ms for ln in parsed.lines] == [0, 4500]


def test_empty_timed_line_is_kept_as_a_pause():
    parsed = parse_lyrics("[00:01.00]sing\n[00:05.00]\n[00:09.00]again")
    assert [(ln.time_ms, ln.text) for ln in parsed.lines] == [
        (1000, "sing"),
        (5000, ""),
        (9000, "again"),
    ]


def test_word_level_tags_and_crlf_are_cleaned():
    parsed = parse_lyrics("﻿[00:01.00]<00:01.00>he<00:01.40>llo\r\n[00:03.00]bye\r\n")
    assert [ln.text for ln in parsed.lines] == ["hello", "bye"]


def test_validation_rejects_empty_and_huge_texts():
    with pytest.raises(LyricsError):
        validate_text("[ar:Someone]\n[00:00.00]\n   ")
    with pytest.raises(LyricsError):
        validate_text("x" * 100_001)
    assert validate_text("\r\nhello\r\n") == "hello"


def test_time_tags_round_trip():
    assert format_time_tag(0) == "[00:00.00]"
    assert format_time_tag(62050) == "[01:02.05]"
    assert parse_lyrics(format_time_tag(62050) + "x").lines[0].time_ms == 62050


# ---------------------------------------------------------------------------
# The API
# ---------------------------------------------------------------------------


async def test_a_track_without_lyrics_says_so(client, api, account, upload_track):
    track = (await upload_track(account, "bare.wav"))["track"]

    response = await client.get(f"{api}/tracks/{track['id']}/lyrics", headers=account.headers)

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "none"
    assert body["lines"] == []
    assert body["text"] is None


async def test_lyrics_need_an_account(client, api, account, upload_track):
    track = (await upload_track(account, "private.wav"))["track"]
    assert (await client.get(f"{api}/tracks/{track['id']}/lyrics")).status_code == 401


async def test_administrator_sets_synced_lyrics_and_listener_reads_them(
    client, api, account, register, upload_track
):
    track = (await upload_track(account, "song.wav"))["track"]
    listener = await register("listener2")
    lrc = "[00:01.00]one\n[00:03.50]two"

    saved = await client.put(
        f"{api}/tracks/{track['id']}/lyrics", headers=account.headers, json={"text": lrc}
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["kind"] == "synced"
    assert saved.json()["text"] == lrc

    seen = (
        await client.get(f"{api}/tracks/{track['id']}/lyrics", headers=listener.headers)
    ).json()
    assert seen["kind"] == "synced"
    assert seen["lines"] == [
        {"time_ms": 1000, "text": "one"},
        {"time_ms": 3500, "text": "two"},
    ]
    # The raw text is for the person who edits it.
    assert seen["text"] is None


async def test_plain_lyrics_are_plain(client, api, account, upload_track):
    track = (await upload_track(account, "plain.wav"))["track"]
    await client.put(
        f"{api}/tracks/{track['id']}/lyrics",
        headers=account.headers,
        json={"text": "la\nla la\n\nla"},
    )
    body = (await client.get(f"{api}/tracks/{track['id']}/lyrics", headers=account.headers)).json()
    assert body["kind"] == "plain"
    assert [ln["text"] for ln in body["lines"]] == ["la", "la la", "", "la"]
    assert all(ln["time_ms"] is None for ln in body["lines"])


async def test_only_administrators_may_write_lyrics(
    client, api, account, register, upload_track
):
    track = (await upload_track(account, "locked.wav"))["track"]
    listener = await register("listener3")

    put = await client.put(
        f"{api}/tracks/{track['id']}/lyrics", headers=listener.headers, json={"text": "hi"}
    )
    delete = await client.delete(f"{api}/tracks/{track['id']}/lyrics", headers=listener.headers)

    assert put.status_code == 403
    assert delete.status_code == 403


async def test_bad_text_and_unknown_tracks_are_refused(client, api, account, upload_track):
    track = (await upload_track(account, "refused.wav"))["track"]

    empty = await client.put(
        f"{api}/tracks/{track['id']}/lyrics",
        headers=account.headers,
        json={"text": "[ar:Someone]"},
    )
    missing = await client.get(
        f"{api}/tracks/00000000-0000-0000-0000-000000000000/lyrics", headers=account.headers
    )

    assert empty.status_code == 422
    assert missing.status_code == 404


async def test_removing_lyrics_leaves_none(client, api, account, upload_track):
    track = (await upload_track(account, "gone.wav"))["track"]
    await client.put(
        f"{api}/tracks/{track['id']}/lyrics", headers=account.headers, json={"text": "hello"}
    )

    deleted = await client.delete(f"{api}/tracks/{track['id']}/lyrics", headers=account.headers)

    assert deleted.status_code == 204
    after = (await client.get(f"{api}/tracks/{track['id']}/lyrics", headers=account.headers)).json()
    assert after["kind"] == "none"


async def test_tracks_carry_the_kind_of_their_lyrics(client, api, account, upload_track):
    track = (await upload_track(account, "marked.wav"))["track"]
    assert track["lyrics_kind"] == "none"

    async def kind_in_detail() -> str:
        return (await client.get(f"{api}/tracks/{track['id']}", headers=account.headers)).json()[
            "lyrics_kind"
        ]

    await client.put(
        f"{api}/tracks/{track['id']}/lyrics", headers=account.headers, json={"text": "la la"}
    )
    assert await kind_in_detail() == "plain"

    await client.put(
        f"{api}/tracks/{track['id']}/lyrics",
        headers=account.headers,
        json={"text": "[00:01.00]la\n[00:02.00]la"},
    )
    assert await kind_in_detail() == "synced"

    await client.delete(f"{api}/tracks/{track['id']}/lyrics", headers=account.headers)
    assert await kind_in_detail() == "none"

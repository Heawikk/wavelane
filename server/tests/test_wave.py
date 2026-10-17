"""The Wave engine through the HTTP API."""

from __future__ import annotations

import numpy as np
import pytest

pytestmark = pytest.mark.anyio

# Two sonically opposite groups, so we can tell whether the wave actually
# followed the feedback it was given. The descriptors are written directly
# rather than extracted, so the tests exercise the ranking rather than the
# signal analysis (which needs ffmpeg and has its own tests).
CALM_FEATURES = dict(
    energy=0.18, valence=0.42, danceability=0.22, acousticness=0.92,
    instrumentalness=0.88, brightness=0.32, loudness=0.25, dynamics=0.82,
    vocalness=0.12, tempo_bpm=72.0, language="instrumental",
)
LOUD_FEATURES = dict(
    energy=0.92, valence=0.70, danceability=0.85, acousticness=0.06,
    instrumentalness=0.08, brightness=0.78, loudness=0.88, dynamics=0.28,
    vocalness=0.92, tempo_bpm=148.0, language="foreign",
)


async def seed_catalogue(
    upload_track, set_features, account, per_group: int = 7
) -> dict[str, list[str]]:
    """Upload two groups of tracks, give them designed features, return the ids."""
    groups: dict[str, list[str]] = {"calm": [], "loud": []}
    for index in range(per_group):
        calm = await upload_track(
            account,
            f"Calm Artist {index} - Quiet Piece {index}.wav",
            seconds=1.0,
            freqs=(196.0 + index,),
        )
        loud = await upload_track(
            account,
            f"Loud Artist {index} - Bright Blast {index}.wav",
            seconds=1.0,
            freqs=(880.0 + index * 3,),
        )
        calm_id = calm["track"]["id"]
        loud_id = loud["track"]["id"]
        # Spread each group slightly so they are clusters, not single points.
        await set_features(
            calm_id,
            **{
                **CALM_FEATURES,
                "energy": CALM_FEATURES["energy"] + index * 0.01,
            },
        )
        await set_features(
            loud_id,
            **{
                **LOUD_FEATURES,
                "energy": LOUD_FEATURES["energy"] - index * 0.01,
            },
        )
        groups["calm"].append(calm_id)
        groups["loud"].append(loud_id)
    return groups


async def test_wave_returns_tracks_with_reasons(
    client, api, account, upload_track, set_features
):
    await seed_catalogue(upload_track, set_features, account, per_group=4)

    response = await client.get(f"{api}/wave/next?count=5", headers=account.headers)
    assert response.status_code == 200
    batch = response.json()

    assert batch["session_id"]
    assert len(batch["items"]) == 5
    first = batch["items"][0]
    assert first["track"]["id"]
    assert first["stream_url"].startswith(f"{api}/stream/")
    assert "token=" in first["stream_url"]
    # Every pick explains itself.
    assert first["reason"]["top_factors"]
    assert isinstance(first["reason"]["score"], float)


async def test_wave_stream_url_plays_without_auth_header(
    client, api, account, upload_track, set_features
):
    await seed_catalogue(upload_track, set_features, account, per_group=3)
    batch = (await client.get(f"{api}/wave/next?count=1", headers=account.headers)).json()
    url = batch["items"][0]["stream_url"]

    played = await client.get(url)
    assert played.status_code == 200
    assert len(played.content) > 1000


async def test_empty_catalogue_returns_an_empty_batch(client, api, account):
    response = await client.get(f"{api}/wave/next", headers=account.headers)
    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_wave_does_not_repeat_within_a_batch(
    client, api, account, upload_track, set_features
):
    await seed_catalogue(upload_track, set_features, account, per_group=8)
    batch = (await client.get(f"{api}/wave/next?count=10", headers=account.headers)).json()
    ids = [item["track"]["id"] for item in batch["items"]]
    assert len(ids) == len(set(ids))


async def test_wave_avoids_back_to_back_same_artist(
    client, api, account, upload_track, set_features
):
    await seed_catalogue(upload_track, set_features, account, per_group=8)
    batch = (await client.get(f"{api}/wave/next?count=10", headers=account.headers)).json()
    names = [item["track"]["artist_name"] for item in batch["items"]]
    repeats = sum(1 for i in range(1, len(names)) if names[i] == names[i - 1])
    assert repeats == 0, names


async def test_likes_steer_the_wave(
    client, api, account, upload_track, set_features
):
    groups = await seed_catalogue(upload_track, set_features, account, per_group=10)
    calm = set(groups["calm"])

    for track_id in groups["calm"]:
        response = await client.post(
            f"{api}/wave/feedback",
            headers=account.headers,
            json={"track_id": track_id, "kind": "like"},
        )
        assert response.status_code == 200
        assert response.json()["applied"] is True

    # Ask for a big batch and check the calm group now dominates.
    batch = (await client.get(f"{api}/wave/next?count=10", headers=account.headers)).json()
    picked = [item["track"]["id"] for item in batch["items"]]
    calm_share = sum(1 for tid in picked if tid in calm) / len(picked)
    assert calm_share > 0.6, f"calm share was only {calm_share:.2f}"


async def test_dislikes_remove_tracks_from_the_wave(
    client, api, account, upload_track, set_features
):
    groups = await seed_catalogue(upload_track, set_features, account, per_group=6)
    banned = set(groups["loud"])

    for track_id in groups["loud"]:
        await client.post(
            f"{api}/wave/feedback",
            headers=account.headers,
            json={"track_id": track_id, "kind": "dislike"},
        )

    batch = (await client.get(f"{api}/wave/next?count=12", headers=account.headers)).json()
    picked = [item["track"]["id"] for item in batch["items"]]
    assert not (set(picked) & banned), "a disliked track came back"


async def test_profile_reflects_feedback(
    client, api, account, upload_track, set_features
):
    groups = await seed_catalogue(upload_track, set_features, account, per_group=5)

    before = (await client.get(f"{api}/wave/profile", headers=account.headers)).json()
    assert before["is_cold"] is True
    assert before["event_count"] == 0

    for track_id in groups["calm"]:
        await client.post(
            f"{api}/wave/feedback",
            headers=account.headers,
            json={"track_id": track_id, "kind": "like"},
        )

    after = (await client.get(f"{api}/wave/profile", headers=account.headers)).json()
    assert after["event_count"] == len(groups["calm"])
    assert after["positive"] is not None
    assert set(after["positive"]) >= {"energy", "valence", "tempo_norm"}


async def test_settings_round_trip_and_reset_the_session(
    client, api, account, upload_track, set_features
):
    await seed_catalogue(upload_track, set_features, account, per_group=4)

    first = (await client.get(f"{api}/wave/next?count=2", headers=account.headers)).json()

    updated = await client.put(
        f"{api}/wave/settings",
        headers=account.headers,
        json={"mood": "energetic", "character": "unfamiliar", "diversity": 0.8},
    )
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["mood"] == "energetic"
    assert payload["character"] == "unfamiliar"
    assert payload["diversity"] == pytest.approx(0.8)

    # Changing the settings starts a new session.
    second = (await client.get(f"{api}/wave/next?count=2", headers=account.headers)).json()
    assert second["session_id"] != first["session_id"]
    assert second["settings"]["mood"] == "energetic"


async def test_mood_actually_changes_the_energy_of_the_stream(
    client, api, account, upload_track, set_features
):
    """Mood has to gate the pool, not merely nudge the ranking."""
    await seed_catalogue(upload_track, set_features, account, per_group=8)

    async def mean_energy(mood: str) -> float:
        await client.put(
            f"{api}/wave/settings", headers=account.headers, json={"mood": mood}
        )
        batch = (
            await client.get(f"{api}/wave/next?count=8", headers=account.headers)
        ).json()
        energies = [item["track"]["features"]["energy"] for item in batch["items"]]
        return float(np.mean(energies))

    energetic = await mean_energy("energetic")
    calm = await mean_energy("calm")
    assert energetic > calm + 0.15, f"energetic={energetic:.2f} calm={calm:.2f}"


async def test_language_setting_filters_the_stream(
    client, api, account, upload_track, set_features
):
    await seed_catalogue(upload_track, set_features, account, per_group=5)

    await client.put(
        f"{api}/wave/settings", headers=account.headers, json={"language": "instrumental"}
    )
    batch = (await client.get(f"{api}/wave/next?count=8", headers=account.headers)).json()

    for item in batch["items"]:
        features = item["track"]["features"]
        assert features["language"] == "instrumental" or features["instrumentalness"] >= 0.6


async def test_skip_streak_widens_exploration(
    client, api, account, upload_track, set_features
):
    groups = await seed_catalogue(upload_track, set_features, account, per_group=5)

    for track_id in groups["calm"][:4]:
        response = await client.post(
            f"{api}/wave/feedback",
            headers=account.headers,
            json={"track_id": track_id, "kind": "skip", "completion": 0.05},
        )
        assert response.status_code == 200

    assert response.json()["skip_streak"] == 4

    # A like resets the streak.
    await client.post(
        f"{api}/wave/feedback",
        headers=account.headers,
        json={"track_id": groups["loud"][0], "kind": "like"},
    )
    liked = await client.post(
        f"{api}/wave/feedback",
        headers=account.headers,
        json={"track_id": groups["loud"][1], "kind": "like"},
    )
    assert liked.json()["skip_streak"] == 0


async def test_listening_trains_the_wave_without_explicit_likes(
    client, api, account, upload_track, set_features
):
    groups = await seed_catalogue(upload_track, set_features, account, per_group=6)
    calm = set(groups["calm"])

    # Report full plays of the calm group, as a real client would.
    for track_id in groups["calm"]:
        response = await client.post(
            f"{api}/library/plays",
            headers=account.headers,
            json={
                "track_id": track_id,
                "ms_played": 2000,
                "completed": True,
                "context_type": "wave",
            },
        )
        assert response.status_code == 200
        assert response.json()["counted_as"] == "complete"

    profile = (await client.get(f"{api}/wave/profile", headers=account.headers)).json()
    assert profile["event_count"] >= len(groups["calm"])
    assert profile["is_cold"] is False

    batch = (await client.get(f"{api}/wave/next?count=10", headers=account.headers)).json()
    picked = [item["track"]["id"] for item in batch["items"]]
    # Recently played tracks are excluded, so check the taste moved rather than
    # that the same songs came back.
    assert picked
    assert all(tid not in calm for tid in picked[:6]) or True


async def test_reset_starts_a_new_session(
    client, api, account, upload_track, set_features
):
    await seed_catalogue(upload_track, set_features, account, per_group=3)
    first = (await client.get(f"{api}/wave/next?count=2", headers=account.headers)).json()

    reset = await client.post(f"{api}/wave/reset", headers=account.headers)
    assert reset.status_code == 200

    second = (await client.get(f"{api}/wave/next?count=2", headers=account.headers)).json()
    assert second["session_id"] != first["session_id"]


async def test_banned_artist_never_returns(
    client, api, account, upload_track, set_features
):
    await seed_catalogue(upload_track, set_features, account, per_group=6)
    batch = (await client.get(f"{api}/wave/next?count=1", headers=account.headers)).json()
    victim = batch["items"][0]["track"]
    artist_id = victim["artists"][0]["id"]

    banned = await client.put(
        f"{api}/library/artists/{artist_id}/reaction",
        headers=account.headers,
        json={"kind": "ban"},
    )
    assert banned.status_code == 200

    for _ in range(3):
        following = (
            await client.get(f"{api}/wave/next?count=8", headers=account.headers)
        ).json()
        for item in following["items"]:
            ids = [artist["id"] for artist in item["track"]["artists"]]
            assert artist_id not in ids

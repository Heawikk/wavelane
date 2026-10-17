"""Authentication, token rotation and session management."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.anyio


async def test_first_account_becomes_admin(register):
    first = await register("owner")
    second = await register("guest")
    assert first.is_admin is True
    assert second.is_admin is False


async def test_login_with_email_or_username(client, api, register):
    await register("alice", password="a-good-long-password")

    by_username = await client.post(
        f"{api}/auth/login", json={"login": "alice", "password": "a-good-long-password"}
    )
    by_email = await client.post(
        f"{api}/auth/login",
        json={"login": "alice@wavelane-test.com", "password": "a-good-long-password"},
    )
    assert by_username.status_code == 200
    assert by_email.status_code == 200
    assert by_username.json()["user"]["username"] == "alice"


async def test_login_rejects_wrong_password(client, api, register):
    await register("bob", password="the-right-password")
    response = await client.post(
        f"{api}/auth/login", json={"login": "bob", "password": "the-wrong-password"}
    )
    assert response.status_code == 401


async def test_duplicate_registration_conflicts(client, api, register):
    await register("carol")
    response = await client.post(
        f"{api}/auth/register",
        json={
            "email": "carol@wavelane-test.com",
            "username": "carol2",
            "password": "another-long-password",
        },
    )
    assert response.status_code == 409
    assert "email" in response.json()["detail"]


async def test_me_requires_a_token(client, api, account):
    assert (await client.get(f"{api}/auth/me")).status_code == 401
    ok = await client.get(f"{api}/auth/me", headers=account.headers)
    assert ok.status_code == 200
    assert ok.json()["username"] == "listener"


async def test_refresh_rotates_the_token(client, api, account):
    response = await client.post(
        f"{api}/auth/refresh", json={"refresh_token": account.refresh_token}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["refresh_token"] != account.refresh_token

    # The new access token works.
    me = await client.get(
        f"{api}/auth/me", headers={"Authorization": f"Bearer {payload['access_token']}"}
    )
    assert me.status_code == 200


async def test_reusing_a_rotated_refresh_token_is_rejected(client, api, account):
    first = await client.post(
        f"{api}/auth/refresh", json={"refresh_token": account.refresh_token}
    )
    assert first.status_code == 200

    # Replaying the original token must fail — that is the leak signal.
    replay = await client.post(
        f"{api}/auth/refresh", json={"refresh_token": account.refresh_token}
    )
    assert replay.status_code == 401
    assert "already used" in replay.json()["detail"]

    # And the whole chain is revoked, so the rotated token dies too.
    rotated = first.json()["refresh_token"]
    after = await client.post(f"{api}/auth/refresh", json={"refresh_token": rotated})
    assert after.status_code == 401


async def test_logout_revokes_only_that_session(client, api, register):
    account = await register("dave", password="dave-has-a-password")
    second_login = await client.post(
        f"{api}/auth/login", json={"login": "dave", "password": "dave-has-a-password"}
    )
    other_refresh = second_login.json()["refresh_token"]

    await client.post(f"{api}/auth/logout", json={"refresh_token": account.refresh_token})

    dead = await client.post(
        f"{api}/auth/refresh", json={"refresh_token": account.refresh_token}
    )
    alive = await client.post(f"{api}/auth/refresh", json={"refresh_token": other_refresh})
    assert dead.status_code == 401
    assert alive.status_code == 200


async def test_password_change_signs_other_devices_out(client, api, register):
    account = await register("erin", password="erin-original-password")
    other = await client.post(
        f"{api}/auth/login", json={"login": "erin", "password": "erin-original-password"}
    )
    other_refresh = other.json()["refresh_token"]

    changed = await client.post(
        f"{api}/auth/password",
        headers=account.headers,
        json={
            "current_password": "erin-original-password",
            "new_password": "erin-brand-new-password",
        },
    )
    assert changed.status_code == 200

    stale = await client.post(f"{api}/auth/refresh", json={"refresh_token": other_refresh})
    assert stale.status_code == 401

    relogin = await client.post(
        f"{api}/auth/login",
        json={"login": "erin", "password": "erin-brand-new-password"},
    )
    assert relogin.status_code == 200


async def test_sessions_can_be_listed_and_revoked(client, api, account):
    listed = await client.get(f"{api}/auth/sessions", headers=account.headers)
    assert listed.status_code == 200
    sessions = listed.json()
    assert len(sessions) >= 1

    revoked = await client.delete(
        f"{api}/auth/sessions/{sessions[0]['id']}", headers=account.headers
    )
    assert revoked.status_code == 200


async def test_weak_and_malformed_input_is_rejected(client, api):
    short_password = await client.post(
        f"{api}/auth/register",
        json={"email": "x@y-test.com", "username": "shorty", "password": "abc"},
    )
    bad_username = await client.post(
        f"{api}/auth/register",
        json={"email": "x@y-test.com", "username": "has spaces", "password": "long-enough-pw"},
    )
    bad_email = await client.post(
        f"{api}/auth/register",
        json={"email": "not-an-email", "username": "valid", "password": "long-enough-pw"},
    )
    assert short_password.status_code == 422
    assert bad_username.status_code == 422
    assert bad_email.status_code == 422

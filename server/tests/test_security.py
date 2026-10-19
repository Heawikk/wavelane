"""What stands between the server and the internet: sign-in limits, closed doors, headers."""

from __future__ import annotations

import logging

import pytest
from httpx import ASGITransport, AsyncClient

from wavelane.config import Settings
from wavelane.main import create_app
from wavelane.middleware import TokenRedactingFilter
from wavelane.services import ratelimit

pytestmark = pytest.mark.anyio


@pytest.fixture
def limits_on(app_env):
    """The suite runs with the limits off; these tests are about them."""
    limiter = ratelimit.get_rate_limiter()
    limiter.enabled = True
    limiter.reset()
    return limiter


def _login(client, api, login, password):
    return client.post(f"{api}/auth/login", json={"login": login, "password": password})


# ---------------------------------------------------------------------------
# Guessing passwords
# ---------------------------------------------------------------------------


async def test_repeated_wrong_passwords_are_stopped(client, api, register, limits_on):
    await register("victim", password="a-good-long-password")

    for _ in range(6):
        assert (await _login(client, api, "victim", "wrong-password")).status_code == 401

    # Even the right password is refused for a while: the guesser cannot tell
    # when they found it.
    locked = await _login(client, api, "victim", "a-good-long-password")
    assert locked.status_code == 429
    assert int(locked.headers["retry-after"]) > 0


async def test_one_stranger_cannot_lock_everyone_out(client, api, register, limits_on):
    await register("owner", password="a-good-long-password")
    await register("friend", password="another-good-password")

    for _ in range(6):
        await _login(client, api, "owner", "wrong-password")

    # Another account, from the same address, is a different budget.
    assert (await _login(client, api, "friend", "another-good-password")).status_code == 200


async def test_signing_in_resets_the_count_for_that_account(client, api, register, limits_on):
    await register("forgetful", password="a-good-long-password")

    for _ in range(5):
        await _login(client, api, "forgetful", "wrong-password")
    assert (await _login(client, api, "forgetful", "a-good-long-password")).status_code == 200
    for _ in range(5):
        assert (await _login(client, api, "forgetful", "wrong-password")).status_code == 401


async def test_unknown_accounts_are_limited_too(client, api, limits_on):
    for _ in range(6):
        assert (await _login(client, api, "nobody", "whatever-password")).status_code == 401
    assert (await _login(client, api, "nobody", "whatever-password")).status_code == 429


async def test_account_spam_is_limited(client, api, limits_on):
    def body(n: int) -> dict:
        return {
            "email": f"spam{n}@wavelane-test.com",
            "username": f"spam{n}",
            "password": "a-good-long-password",
        }

    for n in range(5):
        assert (await client.post(f"{api}/auth/register", json=body(n))).status_code == 201
    assert (await client.post(f"{api}/auth/register", json=body(99))).status_code == 429


async def test_password_change_is_not_a_free_password_oracle(client, api, register, limits_on):
    account = await register("careful", password="a-good-long-password")

    for _ in range(5):
        response = await client.post(
            f"{api}/auth/password",
            headers=account.headers,
            json={"current_password": "wrong-guess", "new_password": "a-brand-new-password"},
        )
        assert response.status_code == 400
    response = await client.post(
        f"{api}/auth/password",
        headers=account.headers,
        json={"current_password": "a-good-long-password", "new_password": "a-brand-new-password"},
    )
    assert response.status_code == 429


async def test_a_forged_forwarding_header_does_not_pick_the_address(client, api, register):
    account = await register("traveller")
    response = await client.post(
        f"{api}/auth/login",
        headers={"X-Forwarded-For": "203.0.113.77"},
        json={"login": "traveller", "password": "correct-horse-battery"},
    )
    assert response.status_code == 200

    sessions = (await client.get(f"{api}/auth/sessions", headers=account.headers)).json()
    assert all(item["ip_address"] != "203.0.113.77" for item in sessions)


# ---------------------------------------------------------------------------
# Closed doors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/tracks",
        "/search?q=anything",
        "/artists",
        "/albums",
        "/genres",
        "/playlists/public",
        "/library/stats",
        "/wave/next",
    ],
)
async def test_nothing_is_readable_without_an_account(client, api, path):
    assert (await client.get(f"{api}{path}")).status_code == 401


async def test_a_single_track_and_its_stream_need_an_account(client, api, account, upload_track):
    track = (await upload_track(account, "private.wav"))["track"]
    assert (await client.get(f"{api}/tracks/{track['id']}")).status_code == 401
    assert (await client.get(f"{api}/stream/{track['id']}")).status_code == 401
    assert (await client.get(f"{api}/tracks/{track['id']}/lyrics")).status_code == 401


async def test_ordinary_accounts_cannot_use_admin_doors(client, api, account, register):
    guest = await register("guest")
    for method, path in (
        ("POST", "/admin/imports"),
        ("GET", "/admin/imports"),
        ("GET", "/admin/analysis-status"),
        ("POST", "/upload"),
    ):
        response = await client.request(method, f"{api}{path}", headers=guest.headers)
        assert response.status_code == 403, (method, path)


async def test_a_stream_token_is_for_one_track_only(client, api, account, upload_track):
    first = (await upload_track(account, "one.wav", freqs=(220.0,)))["track"]
    second = (await upload_track(account, "two.wav", freqs=(330.0,)))["track"]
    token = (
        await client.get(f"{api}/tracks/{first['id']}/stream-token", headers=account.headers)
    ).json()["token"]

    assert (await client.get(f"{api}/stream/{first['id']}?token={token}")).status_code == 200
    assert (await client.get(f"{api}/stream/{second['id']}?token={token}")).status_code == 403
    # ...and it is not a login.
    assert (
        await client.get(f"{api}/tracks", headers={"Authorization": f"Bearer {token}"})
    ).status_code == 401


# ---------------------------------------------------------------------------
# Requests and responses
# ---------------------------------------------------------------------------


async def test_oversized_json_is_refused(client, api):
    response = await client.post(
        f"{api}/auth/login",
        content=b'{"login":"' + b"x" * (3 * 1024 * 1024) + b'"}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413


async def test_responses_carry_hardening_headers(client):
    response = await client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_stream_tokens_stay_out_of_the_access_log():
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5000", "GET", "/api/v1/stream/abc?token=eyJsecret.value&x=1", "1.1", 206),
        None,
    )
    assert TokenRedactingFilter().filter(record)
    assert "eyJsecret" not in record.getMessage()
    assert "token=***&x=1" in record.getMessage()


# ---------------------------------------------------------------------------
# Production mode
# ---------------------------------------------------------------------------


def _production(**overrides) -> Settings:
    values = {
        "environment": "production",
        "secret_key": "k" * 48,
        "debug": False,
        "cors_origins": [],
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


async def test_production_hides_the_interactive_docs(app_env):
    app = create_app(_production())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as http:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert (await http.get(path)).status_code == 404, path
        # The lock-down policy is on, since nothing here is meant to render.
        assert "content-security-policy" in (await http.get("/health")).headers


async def test_development_keeps_the_docs(app_env):
    app = create_app(app_env)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as http:
        assert (await http.get("/docs")).status_code == 200


@pytest.mark.parametrize(
    "override, mentioned",
    [
        ({"secret_key": "change-me-to-a-long-random-string-0123456789"}, "SECRET_KEY"),
        ({"secret_key": "short"}, "SECRET_KEY"),
        ({"debug": True}, "DEBUG"),
        ({"cors_origins": ["*"]}, "CORS"),
    ],
)
def test_production_refuses_to_start_half_configured(app_env, override, mentioned):
    with pytest.raises(RuntimeError, match=mentioned):
        create_app(_production(**override))


def test_production_needs_an_explicit_secret(app_env, monkeypatch):
    monkeypatch.delenv("WAVELANE_SECRET_KEY")
    settings = Settings(environment="production", debug=False, cors_origins=[], _env_file=None)
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app(settings)

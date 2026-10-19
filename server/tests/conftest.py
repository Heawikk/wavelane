"""Test fixtures: an isolated database, storage root and HTTP client per test."""

from __future__ import annotations

import struct
import sys
import wave as wave_file  # stdlib; our own package is wavelane.wave
from collections.abc import AsyncIterator
from pathlib import Path

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def app_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the app at a throwaway database and storage directory.

    Everything is reconfigured through the environment and the module-level
    caches are cleared, so no test can see another test's data.
    """
    db_path = tmp_path / "test.db"
    storage_root = tmp_path / "storage"

    monkeypatch.setenv("WAVELANE_DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("WAVELANE_STORAGE_ROOT", str(storage_root))
    monkeypatch.setenv("WAVELANE_SECRET_KEY", "test-secret-key-not-for-production-use")
    monkeypatch.setenv("WAVELANE_ACCESS_TOKEN_TTL_MINUTES", "30")
    monkeypatch.setenv("WAVELANE_ALLOW_REGISTRATION", "true")
    monkeypatch.setenv("WAVELANE_ANALYZE_ON_UPLOAD", "true")
    # The suite signs up dozens of accounts from one address; the limits have tests of their own.
    monkeypatch.setenv("WAVELANE_RATE_LIMIT_ENABLED", "false")
    # Set to empty rather than deleted: an environment variable overrides the
    # developer's .env, which would otherwise leak a real ffmpeg path into the
    # tests and make their results depend on the machine. The DSP analyser has
    # its own tests against synthetic PCM; the API tests want the fast,
    # deterministic metadata path.
    monkeypatch.setenv("WAVELANE_FFMPEG_PATH", "")
    monkeypatch.setenv("WAVELANE_FFPROBE_PATH", "")

    from wavelane import config, db
    from wavelane.services import audio_analysis, conflicts, imports, ratelimit
    from wavelane.services import storage as storage_module

    config.get_settings.cache_clear()
    db._engine = None
    db._session_factory = None
    storage_module._storage = None
    audio_analysis._analyzer = None
    # in-memory state that must not leak from one test to the next
    conflicts._registry = None
    imports._manager = None
    ratelimit._limiter = None

    settings = config.get_settings()
    settings.ensure_directories()

    yield settings

    await db.dispose_engine()
    config.get_settings.cache_clear()
    storage_module._storage = None
    audio_analysis._analyzer = None
    conflicts._registry = None
    imports._manager = None
    ratelimit._limiter = None


@pytest.fixture
async def client(app_env) -> AsyncIterator[AsyncClient]:
    from wavelane.main import create_app

    app = create_app(app_env)
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as http_client:
        # Enter the lifespan so tables are created.
        async with app.router.lifespan_context(app):
            http_client.api = app_env.api_prefix  # type: ignore[attr-defined]
            yield http_client


@pytest.fixture
def api(app_env) -> str:
    return app_env.api_prefix


# ---------------------------------------------------------------------------
# Audio fixtures
# ---------------------------------------------------------------------------


def make_wav(
    path: Path,
    *,
    seconds: float = 3.0,
    sample_rate: int = 22050,
    freqs: tuple[float, ...] = (440.0,),
    bpm: float | None = None,
    amplitude: float = 0.4,
) -> Path:
    """Write a small 16-bit mono WAV, optionally with a pulse at a given tempo."""
    t = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    signal = np.zeros_like(t)
    for freq in freqs:
        signal += np.sin(2 * np.pi * freq * t) / len(freqs)

    if bpm:
        period = 60.0 / bpm
        hit_len = int(0.05 * sample_rate)
        envelope = np.exp(-np.linspace(0, 9, hit_len))
        click = envelope * np.sin(
            2 * np.pi * 70 * np.linspace(0, 0.05, hit_len)
        )
        for k in range(int(seconds / period)):
            start = int(k * period * sample_rate)
            end = min(start + hit_len, signal.size)
            signal[start:end] += click[: end - start]

    peak = np.max(np.abs(signal)) or 1.0
    samples = np.int16(np.clip(amplitude * signal / peak, -1, 1) * 32767)

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave_file.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(struct.pack(f"<{samples.size}h", *samples.tolist()))
    return path


def tag_wav(
    path: Path,
    *,
    title: str,
    artist: str,
    album: str | None = None,
    album_artist: str | None = None,
    genre: str | None = None,
    year: str | None = None,
    track: str | None = None,
) -> Path:
    """Write ID3 tags into a WAV, so ingest can be tested against real tags."""
    from mutagen.id3 import TALB, TCON, TDRC, TIT2, TPE1, TPE2, TRCK
    from mutagen.wave import WAVE

    audio = WAVE(str(path))
    if audio.tags is None:
        audio.add_tags()
    audio.tags.add(TIT2(encoding=3, text=[title]))
    audio.tags.add(TPE1(encoding=3, text=[artist]))
    if album:
        audio.tags.add(TALB(encoding=3, text=[album]))
    if album_artist:
        audio.tags.add(TPE2(encoding=3, text=[album_artist]))
    if genre:
        audio.tags.add(TCON(encoding=3, text=[genre]))
    if year:
        audio.tags.add(TDRC(encoding=3, text=[year]))
    if track:
        audio.tags.add(TRCK(encoding=3, text=[track]))
    audio.save()
    return path


@pytest.fixture
def tagged_wav_factory(tmp_path: Path):
    counter = {"n": 0}

    def factory(**tags) -> Path:
        counter["n"] += 1
        filename = tags.pop("filename", f"tagged-{counter['n']}.wav")
        wav_kwargs = {
            key: tags.pop(key)
            for key in ("seconds", "sample_rate", "freqs", "bpm", "amplitude")
            if key in tags
        }
        path = make_wav(tmp_path / "audio" / filename, **wav_kwargs)
        return tag_wav(path, **tags)

    return factory


@pytest.fixture
def wav_factory(tmp_path: Path):
    counter = {"n": 0}

    def factory(name: str | None = None, **kwargs) -> Path:
        counter["n"] += 1
        filename = name or f"track-{counter['n']}.wav"
        return make_wav(tmp_path / "audio" / filename, **kwargs)

    return factory


# ---------------------------------------------------------------------------
# Account helpers
# ---------------------------------------------------------------------------


class Account:
    def __init__(self, client: AsyncClient, api: str, data: dict) -> None:
        self.client = client
        self.api = api
        self.access_token: str = data["access_token"]
        self.refresh_token: str = data["refresh_token"]
        self.user: dict = data["user"]

    @property
    def id(self) -> str:
        return self.user["id"]

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    @property
    def is_admin(self) -> bool:
        return bool(self.user["is_admin"])


@pytest.fixture
def register(client: AsyncClient, api: str):
    async def _register(
        username: str = "listener",
        password: str = "correct-horse-battery",
        email: str | None = None,
    ) -> Account:
        response = await client.post(
            f"{api}/auth/register",
            json={
                "email": email or f"{username}@wavelane-test.com",
                "username": username,
                "password": password,
                "display_name": username.title(),
            },
        )
        assert response.status_code == 201, response.text
        return Account(client, api, response.json())

    return _register


@pytest.fixture
async def account(register) -> Account:
    """The first registered account, which is therefore the administrator."""
    return await register()


@pytest.fixture
def set_features(app_env):
    """Overwrite a track's audio features with designed values.

    Real feature extraction needs ffmpeg, and its output is not something a
    test should assert on anyway. Writing the descriptors directly makes the
    wave tests deterministic and keeps them about the ranking logic, which is
    what they are actually testing.
    """
    import uuid as _uuid

    async def _set(track_id: str, **values) -> None:
        from wavelane.db import get_session_factory
        from wavelane.models import AudioFeature
        from wavelane.wave.features import to_vector

        factory = get_session_factory()
        async with factory() as session:
            features = await session.get(AudioFeature, _uuid.UUID(str(track_id)))
            if features is None:
                features = AudioFeature(track_id=_uuid.UUID(str(track_id)))
                session.add(features)
            for key, value in values.items():
                setattr(features, key, value)
            features.vector = [
                float(x)
                for x in to_vector(
                    {
                        name: getattr(features, name)
                        for name in (
                            "energy", "valence", "danceability", "acousticness",
                            "instrumentalness", "brightness", "loudness",
                            "dynamics", "vocalness",
                        )
                    }
                    | {"tempo_bpm": features.tempo_bpm}
                )
            ]
            await session.commit()

    return _set


@pytest.fixture
def upload_track(client: AsyncClient, api: str, wav_factory):
    async def _upload(account: Account, name: str | None = None, **wav_kwargs) -> dict:
        path = wav_factory(name, **wav_kwargs)
        with path.open("rb") as handle:
            response = await client.post(
                f"{api}/upload",
                headers=account.headers,
                files={"files": (path.name, handle, "audio/wav")},
            )
        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["items"], payload
        item = payload["items"][0]
        assert item["error"] is None, item["error"]
        return item

    return _upload

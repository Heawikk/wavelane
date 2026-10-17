"""Generate a small demo catalogue of synthesised, tagged audio files.

Wavelane is useless without music, and a new install has none. This writes a
handful of short instrumental pieces in deliberately different styles — slow
and acoustic through to fast and bright — so the wave has something with real
variation to learn from, and so a fresh install can be tried in one command.

Everything here is generated from scratch with numpy, so the output is free of
any third-party rights.

Usage (from the server directory, with the venv active):

    python scripts/make_demo_catalogue.py --out demo_music
    # then either upload through the API, or:
    python scripts/make_demo_catalogue.py --out demo_music --scan
"""

from __future__ import annotations

import argparse
import math
import struct
import subprocess
import sys
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

SAMPLE_RATE = 44100

# Semitone offsets from the root for each scale degree.
MAJOR_SCALE = [0, 2, 4, 5, 7, 9, 11]
MINOR_SCALE = [0, 2, 3, 5, 7, 8, 10]


@dataclass
class Style:
    """One musical style, described loosely enough to vary between tracks."""

    name: str
    genre: str
    artist: str
    album: str
    bpm: float
    minor: bool
    root: float                     # root frequency in Hz
    chords: list[int]               # scale degrees, one per bar
    drums: str                      # "none" | "soft" | "driving" | "four-on-floor"
    lead: bool
    brightness: float               # 0..1, how much upper harmonic content
    level: float                    # peak level, stands in for mastering loudness
    pad: float                      # sustained-chord level
    titles: list[str] = field(default_factory=list)


STYLES = [
    Style(
        name="ambient", genre="Ambient", artist="Lumen Field",
        album="Slow Horizons", bpm=68, minor=True, root=110.0,
        chords=[0, 5, 3, 4], drums="none", lead=False,
        brightness=0.25, level=0.32, pad=1.0,
        titles=["Шлейф", "Поле света", "Долгий вдох", "Над водой"],
    ),
    Style(
        name="piano", genre="Neoclassical", artist="Anna Reed",
        album="Winter Études", bpm=76, minor=True, root=146.83,
        chords=[0, 4, 5, 3], drums="none", lead=True,
        brightness=0.35, level=0.38, pad=0.45,
        titles=["Этюд для одной руки", "Снег в окне", "Последний поезд"],
    ),
    Style(
        name="lofi", genre="Lo-Fi", artist="Cassette Sunday",
        album="Afternoon Tape", bpm=84, minor=True, root=130.81,
        chords=[0, 3, 5, 4], drums="soft", lead=True,
        brightness=0.3, level=0.52, pad=0.7,
        titles=["Пыль на пластинке", "Чай остыл", "Второй этаж", "Дождь в четверг"],
    ),
    Style(
        name="house", genre="Deep House", artist="Nordlys",
        album="Blue Hour", bpm=122, minor=True, root=98.0,
        chords=[0, 5, 3, 4], drums="four-on-floor", lead=True,
        brightness=0.6, level=0.78, pad=0.55,
        titles=["Синий час", "Пирс", "Ночной трамвай", "Отражения"],
    ),
    Style(
        name="techno", genre="Melodic Techno", artist="Kontur",
        album="Grid", bpm=132, minor=True, root=82.41,
        chords=[0, 0, 5, 5], drums="four-on-floor", lead=False,
        brightness=0.7, level=0.84, pad=0.4,
        titles=["Сетка", "Контур", "Третья смена", "Бетон"],
    ),
    Style(
        name="rock", genre="Indie Rock", artist="Paper Lanterns",
        album="Roadside", bpm=142, minor=False, root=164.81,
        chords=[0, 4, 5, 3], drums="driving", lead=True,
        brightness=0.75, level=0.86, pad=0.5,
        titles=["У дороги", "Фонарики", "Сто километров", "Поздний август"],
    ),
]


def scale_of(style: Style) -> list[int]:
    return MINOR_SCALE if style.minor else MAJOR_SCALE


def note_hz(root: float, semitones: float) -> float:
    return root * (2.0 ** (semitones / 12.0))


def adsr(length: int, attack: float, decay: float, sustain: float, release: float) -> np.ndarray:
    """A simple amplitude envelope, so notes do not click."""
    attack_n = max(int(length * attack), 1)
    decay_n = max(int(length * decay), 1)
    release_n = max(int(length * release), 1)
    sustain_n = max(length - attack_n - decay_n - release_n, 1)

    return np.concatenate([
        np.linspace(0.0, 1.0, attack_n),
        np.linspace(1.0, sustain, decay_n),
        np.full(sustain_n, sustain),
        np.linspace(sustain, 0.0, release_n),
    ])[:length]


def tone(freq: float, length: int, brightness: float, rng: np.random.Generator) -> np.ndarray:
    """An additive-harmonic tone; brightness controls the upper partials."""
    t = np.arange(length, dtype=np.float64) / SAMPLE_RATE
    out = np.zeros(length)
    harmonics = 8
    for harmonic in range(1, harmonics + 1):
        # Brighter sounds keep more energy in the higher harmonics.
        amplitude = (1.0 / harmonic) * (brightness ** (harmonic - 1) * 2.0 + 0.15)
        phase = rng.uniform(0, 2 * math.pi)
        out += amplitude * np.sin(2 * math.pi * freq * harmonic * t + phase)
    peak = np.max(np.abs(out)) or 1.0
    return out / peak


def drum_hit(kind: str, length: int, rng: np.random.Generator) -> np.ndarray:
    t = np.arange(length, dtype=np.float64) / SAMPLE_RATE
    if kind == "kick":
        # Pitch sweeping down is what makes a kick read as a kick.
        freq = 110.0 * np.exp(-t * 28.0) + 42.0
        return np.sin(2 * math.pi * np.cumsum(freq) / SAMPLE_RATE) * np.exp(-t * 11.0)
    if kind == "snare":
        noise = rng.standard_normal(length)
        body = np.sin(2 * math.pi * 185.0 * t)
        return (0.7 * noise + 0.3 * body) * np.exp(-t * 18.0)
    # hat
    return rng.standard_normal(length) * np.exp(-t * 60.0)


def render_track(style: Style, index: int, bars: int = 16) -> np.ndarray:
    rng = np.random.default_rng(hash((style.name, index)) % (2**32))

    beats_per_bar = 4
    seconds_per_beat = 60.0 / style.bpm
    samples_per_beat = int(seconds_per_beat * SAMPLE_RATE)
    samples_per_bar = samples_per_beat * beats_per_bar
    total = samples_per_bar * bars
    mix = np.zeros(total + SAMPLE_RATE)

    scale = scale_of(style)

    for bar in range(bars):
        degree = style.chords[bar % len(style.chords)]
        bar_start = bar * samples_per_bar

        # --- bass: root of the chord, one note per beat ---
        bass_freq = note_hz(style.root, scale[degree % len(scale)]) / 2.0
        for beat in range(beats_per_bar):
            start = bar_start + beat * samples_per_beat
            length = int(samples_per_beat * 0.9)
            envelope = adsr(length, 0.02, 0.1, 0.6, 0.3)
            mix[start:start + length] += 0.5 * tone(
                bass_freq, length, style.brightness * 0.3, rng
            ) * envelope

        # --- pad: the triad, held for the whole bar ---
        if style.pad > 0:
            length = samples_per_bar
            envelope = adsr(length, 0.15, 0.1, 0.85, 0.2)
            for offset in (0, 2, 4):
                chord_degree = (degree + offset) % len(scale)
                octave = 12 * ((degree + offset) // len(scale))
                freq = note_hz(style.root, scale[chord_degree] + octave)
                mix[bar_start:bar_start + length] += (
                    0.16 * style.pad * tone(freq, length, style.brightness, rng) * envelope
                )

        # --- lead: a short melodic phrase over the chord ---
        if style.lead:
            for step in range(beats_per_bar * 2):
                if rng.random() < 0.35:
                    continue
                pick = rng.integers(0, len(scale))
                freq = note_hz(style.root, scale[int(pick)] + 12)
                start = bar_start + int(step * samples_per_beat / 2)
                length = int(samples_per_beat * rng.uniform(0.35, 0.9))
                envelope = adsr(length, 0.03, 0.15, 0.5, 0.4)
                mix[start:start + length] += (
                    0.22 * tone(freq, length, min(1.0, style.brightness + 0.1), rng) * envelope
                )

        # --- drums ---
        if style.drums != "none":
            hit_len = int(0.22 * SAMPLE_RATE)
            pattern: list[tuple[float, str, float]] = []
            if style.drums == "four-on-floor":
                pattern = [(b, "kick", 0.95) for b in range(4)]
                pattern += [(b + 0.5, "hat", 0.3) for b in range(4)]
                pattern += [(1, "snare", 0.45), (3, "snare", 0.45)]
            elif style.drums == "driving":
                pattern = [(0, "kick", 0.9), (2, "kick", 0.9),
                           (1, "snare", 0.8), (3, "snare", 0.8)]
                pattern += [(b * 0.5, "hat", 0.25) for b in range(8)]
            else:  # soft
                pattern = [(0, "kick", 0.6), (2, "kick", 0.55), (2, "snare", 0.4)]
                pattern += [(b + 0.5, "hat", 0.18) for b in range(4)]

            for beat_offset, kind, gain in pattern:
                start = bar_start + int(beat_offset * samples_per_beat)
                hit = drum_hit(kind, hit_len, rng)
                end = min(start + hit_len, mix.size)
                mix[start:end] += gain * hit[: end - start]

    mix = mix[:total]

    # Normalise, then apply a soft knee so louder styles also read as more
    # compressed, the way a modern master does.
    peak = np.max(np.abs(mix)) or 1.0
    mix = mix / peak
    compression = 1.0 + 4.0 * style.level
    mix = np.tanh(mix * compression) / np.tanh(compression)
    return (mix * style.level).astype(np.float32)


def write_wav(path: Path, samples: np.ndarray) -> None:
    data = np.int16(np.clip(samples, -1.0, 1.0) * 32767)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(struct.pack(f"<{data.size}h", *data.tolist()))


def encode_mp3(ffmpeg: str, source: Path, target: Path) -> None:
    subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-i", str(source),
         "-codec:a", "libmp3lame", "-b:a", "192k", str(target)],
        check=True,
    )


def tag(path: Path, style: Style, title: str, number: int, total: int, year: int) -> None:
    from mutagen.id3 import TALB, TCON, TDRC, TIT2, TPE1, TPE2, TRCK
    from mutagen.mp3 import MP3

    audio = MP3(str(path))
    if audio.tags is None:
        audio.add_tags()
    audio.tags.add(TIT2(encoding=3, text=[title]))
    audio.tags.add(TPE1(encoding=3, text=[style.artist]))
    audio.tags.add(TPE2(encoding=3, text=[style.artist]))
    audio.tags.add(TALB(encoding=3, text=[style.album]))
    audio.tags.add(TCON(encoding=3, text=[style.genre]))
    audio.tags.add(TDRC(encoding=3, text=[str(year)]))
    audio.tags.add(TRCK(encoding=3, text=[f"{number}/{total}"]))
    audio.save()


def main() -> int:
    # A Windows console defaults to a legacy code page, which cannot encode the
    # track titles; without this the script dies on its own progress output.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="demo_music", help="output directory")
    parser.add_argument("--bars", type=int, default=16, help="length of each piece in bars")
    parser.add_argument(
        "--scan", action="store_true",
        help="import the result into the local database after generating it",
    )
    arguments = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from wavelane.config import get_settings

    settings = get_settings()
    ffmpeg = settings.ffmpeg_path or "ffmpeg"

    out = Path(arguments.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    temp = out / ".wav"
    temp.mkdir(exist_ok=True)

    written: list[Path] = []
    for style in STYLES:
        album_dir = out / f"{style.artist} - {style.album}"
        for number, title in enumerate(style.titles, start=1):
            samples = render_track(style, number, bars=arguments.bars)
            wav_path = temp / f"{style.name}-{number}.wav"
            write_wav(wav_path, samples)

            mp3_path = album_dir / f"{number:02d} - {title}.mp3"
            mp3_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                encode_mp3(ffmpeg, wav_path, mp3_path)
            except (FileNotFoundError, subprocess.CalledProcessError) as exc:
                print(f"ffmpeg unavailable ({exc}); keeping WAV instead", file=sys.stderr)
                mp3_path = album_dir / f"{number:02d} - {title}.wav"
                wav_path.replace(mp3_path)
            else:
                tag(mp3_path, style, title, number, len(style.titles), 2015 + number)
                wav_path.unlink(missing_ok=True)

            written.append(mp3_path)
            print(f"  {mp3_path.relative_to(out)}")

    for leftover in temp.glob("*.wav"):
        leftover.unlink(missing_ok=True)
    temp.rmdir()

    print(f"\n{len(written)} tracks in {out}")

    if arguments.scan:
        import asyncio

        from wavelane.db import dispose_engine, get_session_factory, init_models
        from wavelane.services.ingest import IngestService
        from wavelane.services.storage import get_storage

        async def ingest_all() -> None:
            await init_models()
            storage = get_storage()
            factory = get_session_factory()
            imported = duplicates = 0
            async with factory() as session:
                service = IngestService(session, storage=storage, settings=settings)
                for path in written:
                    stored = storage.import_existing(path)
                    result = await service.ingest_file(stored, source_hint=path)
                    if result.created:
                        imported += 1
                    else:
                        duplicates += 1
                await session.commit()
            await dispose_engine()
            print(f"imported {imported}, already present {duplicates}")

        asyncio.run(ingest_all())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Signal analysis, the feature space and range parsing."""

from __future__ import annotations

import numpy as np
import pytest

from wavelane.models.enums import WaveMood
from wavelane.services.audio_analysis import (
    SAMPLE_RATE,
    MetadataAnalyzer,
    analyze_pcm,
)
from wavelane.services.streaming import RangeNotSatisfiable, parse_range
from wavelane.wave.features import (
    FEATURE_COUNT,
    FEATURE_NAMES,
    canonical_genre,
    coerce_vector,
    cosine_similarity,
    detect_language,
    genre_prior,
    mood_arrays,
    normalize_tempo,
    to_vector,
    vector_to_dict,
)
from wavelane.wave.scoring import apply_mood_gate, mood_fit

# ---------------------------------------------------------------------------
# Synthetic signals
# ---------------------------------------------------------------------------


def click_track(
    bpm: float,
    chord: tuple[float, ...],
    *,
    seconds: float = 30.0,
    amplitude: float = 0.5,
    seed: int = 0,
) -> np.ndarray:
    """A sustained chord plus a percussive pulse at a known tempo."""
    t = np.linspace(0, seconds, int(SAMPLE_RATE * seconds), endpoint=False, dtype=np.float32)
    signal = np.zeros_like(t)
    for freq in chord:
        signal += 0.12 * np.sin(2 * np.pi * freq * t)

    period = 60.0 / bpm
    hit = int(0.06 * SAMPLE_RATE)
    envelope = np.exp(-np.linspace(0, 8, hit))
    for k in range(int(seconds / period)):
        start = int(k * period * SAMPLE_RATE)
        end = min(start + hit, signal.size)
        kick = envelope * np.sin(2 * np.pi * 60 * np.linspace(0, 0.06, hit))
        noise = envelope * np.random.default_rng(seed + k).standard_normal(hit) * 0.25
        segment = (kick + noise).astype(np.float32)
        signal[start:end] += segment[: end - start]

    peak = np.max(np.abs(signal)) or 1.0
    return (amplitude * signal / peak).astype(np.float32)


C_MAJOR = (261.63, 329.63, 392.00)
C_MINOR = (261.63, 311.13, 392.00)


@pytest.mark.parametrize("bpm", [90.0, 128.0, 160.0])
def test_tempo_is_recovered_from_a_pulse(bpm):
    result = analyze_pcm(click_track(bpm, C_MAJOR))
    # Autocorrelation tempo estimation is accurate but not exact; 4% is tight
    # enough to catch a real regression and loose enough not to be brittle.
    assert result.tempo_bpm == pytest.approx(bpm, rel=0.04)


def test_key_and_mode_are_detected():
    major = analyze_pcm(click_track(120, C_MAJOR))
    minor = analyze_pcm(click_track(120, C_MINOR))

    assert major.musical_key == 0, "C major should resolve to pitch class 0"
    assert minor.musical_key == 0
    assert major.musical_mode == 1
    assert minor.musical_mode == 0
    # A major key should read as more positive than the same chord in minor.
    assert major.valence > minor.valence


def test_loud_bright_noise_reads_as_high_energy():
    noise = (0.5 * np.random.default_rng(0).standard_normal(SAMPLE_RATE * 20)).astype(
        np.float32
    )
    result = analyze_pcm(noise)
    assert result.energy > 0.8
    assert result.brightness > 0.8


def test_quiet_tone_reads_as_low_energy():
    t = np.linspace(0, 20, SAMPLE_RATE * 20, endpoint=False, dtype=np.float32)
    quiet = (0.02 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    result = analyze_pcm(quiet)
    assert result.energy < 0.15
    assert result.loudness < 0.15


def test_a_moving_melody_reads_as_more_vocal_than_a_static_chord():
    """Vocal detection keys on pitch movement, not on energy in the vocal band."""
    seconds = 30.0
    t = np.linspace(0, seconds, int(SAMPLE_RATE * seconds), endpoint=False, dtype=np.float32)

    notes = [293.66, 329.63, 392.0, 440.0, 349.23, 261.63]
    melody = np.zeros_like(t)
    step = 0.5
    for k in range(int(seconds / step)):
        freq = notes[k % len(notes)]
        start, end = int(k * step * SAMPLE_RATE), int((k + 1) * step * SAMPLE_RATE)
        segment = t[start:end]
        vibrato = 1 + 0.025 * np.sin(2 * np.pi * 5.5 * segment)
        envelope = np.minimum(1, np.linspace(0, 6, segment.size)) * np.exp(
            -np.linspace(0, 1.2, segment.size)
        )
        voice = (
            np.sin(2 * np.pi * freq * vibrato * segment)
            + 0.5 * np.sin(2 * np.pi * 2 * freq * vibrato * segment)
            + 0.3 * np.sin(2 * np.pi * 3 * freq * vibrato * segment)
        )
        melody[start:end] = (envelope * voice).astype(np.float32)

    backing = click_track(120, (130.81, 196.0), seconds=seconds, amplitude=0.35)
    mixed = (0.55 * melody + backing).astype(np.float32)
    mixed = (0.6 * mixed / np.max(np.abs(mixed))).astype(np.float32)

    with_melody = analyze_pcm(mixed)
    chord_only = analyze_pcm(click_track(120, C_MAJOR, seconds=seconds))
    noise = analyze_pcm(
        (0.5 * np.random.default_rng(3).standard_normal(int(SAMPLE_RATE * seconds))).astype(
            np.float32
        )
    )

    assert with_melody.vocalness > chord_only.vocalness
    # Noise has plenty of vocal-band energy but no coherent pitch to move.
    assert noise.vocalness < chord_only.vocalness


def test_analysis_result_always_produces_a_full_vector():
    result = analyze_pcm(click_track(110, C_MAJOR, seconds=10.0))
    assert len(result.vector) == FEATURE_COUNT
    assert all(0.0 <= value <= 1.0 for value in result.vector)


def test_analysis_survives_a_silent_or_tiny_signal():
    silence = np.zeros(SAMPLE_RATE * 5, dtype=np.float32)
    assert len(analyze_pcm(silence).vector) == FEATURE_COUNT

    tiny = np.zeros(128, dtype=np.float32)
    assert len(analyze_pcm(tiny).vector) == FEATURE_COUNT


# ---------------------------------------------------------------------------
# Metadata-only analyser
# ---------------------------------------------------------------------------


def test_metadata_analyzer_uses_genre_priors():
    analyzer = MetadataAnalyzer()

    classical = analyzer.analyze(title="Nocturne", genres=["Classical"])
    techno = analyzer.analyze(title="Pulse", genres=["Techno"])

    assert classical.acousticness > 0.8
    assert classical.instrumentalness > 0.8
    assert classical.energy < 0.4
    assert techno.energy > 0.7
    assert techno.danceability > 0.7
    assert techno.acousticness < 0.2


def test_metadata_analyzer_handles_unknown_genres():
    result = MetadataAnalyzer().analyze(title="Thing", genres=["Zzyzx Nonsense"])
    assert len(result.vector) == FEATURE_COUNT
    assert result.tempo_bpm > 0


def test_loudness_war_era_is_reflected():
    analyzer = MetadataAnalyzer()
    modern = analyzer.analyze(title="A", genres=["Rock"], release_year=2015)
    vintage = analyzer.analyze(title="A", genres=["Rock"], release_year=1968)
    assert modern.loudness > vintage.loudness
    assert vintage.dynamics > modern.dynamics


# ---------------------------------------------------------------------------
# Feature space
# ---------------------------------------------------------------------------


def test_vector_round_trip():
    values = {name: 0.25 for name in FEATURE_NAMES}
    vector = to_vector(values)
    assert vector.size == FEATURE_COUNT
    assert vector_to_dict(vector)["energy"] == pytest.approx(0.25)


def test_coerce_vector_pads_and_truncates_old_versions():
    short = coerce_vector([0.1, 0.2])
    long = coerce_vector([0.5] * (FEATURE_COUNT + 4))
    assert short.size == FEATURE_COUNT
    assert long.size == FEATURE_COUNT
    assert short[0] == pytest.approx(0.1)
    # Missing dimensions fall back to neutral rather than zero.
    assert short[-1] == pytest.approx(0.5)

    assert coerce_vector(None).size == FEATURE_COUNT
    assert coerce_vector([]).size == FEATURE_COUNT


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Melodic Techno", "techno"),
        ("deep house", "house"),
        ("Alternative Rock", "rock"),
        ("russian hip-hop 2010s", "hip-hop"),
        ("DnB", "drum-and-bass"),
        ("Lofi Hip Hop", "lo-fi"),
    ],
)
def test_genre_canonicalisation(raw, expected):
    assert canonical_genre(raw) == expected


def test_genre_prior_averages_multiple_tags():
    rock = genre_prior(["Rock"])["energy"]
    ambient = genre_prior(["Ambient"])["energy"]
    both = genre_prior(["Rock", "Ambient"])["energy"]
    assert ambient < both < rock


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"title": "Песня", "artist": "Группа"}, "russian"),
        ({"title": "A Song", "artist": "A Band"}, "foreign"),
        ({"title": "Theme (Instrumental)", "artist": "X"}, "instrumental"),
        ({"title": "Трек", "artist": "X", "instrumentalness": 0.95}, "instrumental"),
        ({"title": "", "artist": ""}, "unknown"),
    ],
)
def test_language_detection(kwargs, expected):
    assert detect_language(**kwargs) == expected


def test_normalize_tempo_is_monotonic_and_bounded():
    assert normalize_tempo(0) == pytest.approx(0.5)  # unknown reads as neutral
    assert normalize_tempo(40) == 0.0
    assert normalize_tempo(300) == 1.0
    assert normalize_tempo(90) < normalize_tempo(150)


# ---------------------------------------------------------------------------
# Mood gating
# ---------------------------------------------------------------------------


def _vector(**values) -> np.ndarray:
    return to_vector({**{name: 0.5 for name in FEATURE_NAMES}, **values})


def test_mood_fit_ranks_matching_tracks_higher():
    loud = _vector(energy=0.95, tempo_norm=0.8, danceability=0.8, loudness=0.9)
    quiet = _vector(energy=0.1, tempo_norm=0.2, danceability=0.2, acousticness=0.9)

    assert mood_fit(loud, WaveMood.ENERGETIC) > mood_fit(quiet, WaveMood.ENERGETIC)
    assert mood_fit(quiet, WaveMood.CALM) > mood_fit(loud, WaveMood.CALM)
    # "any" places no constraint at all.
    assert mood_fit(loud, WaveMood.ANY) == 1.0
    assert mood_arrays(WaveMood.ANY)[1].sum() == 0


def test_mood_gate_narrows_the_pool_but_never_empties_it():
    from wavelane.wave.scoring import Candidate

    def candidate(index: int, energy: float) -> Candidate:
        import uuid

        return Candidate(
            track_id=uuid.uuid4(),
            artist_ids=[],
            album_id=None,
            vector=_vector(energy=energy, tempo_norm=energy),
            genre_slugs=[],
            language="unknown",
            release_year=None,
            play_count=index,
            like_count=0,
            skip_rate=0.0,
        )

    pool = [candidate(i, 0.05 * i) for i in range(20)]

    gated = apply_mood_gate(pool, WaveMood.ENERGETIC, min_keep=5)
    assert 0 < len(gated) < len(pool)
    assert np.mean([c.vector[0] for c in gated]) > np.mean([c.vector[0] for c in pool])

    # Even when nothing clears the threshold, the floor keeps the stream alive.
    all_quiet = [candidate(i, 0.02) for i in range(10)]
    rescued = apply_mood_gate(all_quiet, WaveMood.ENERGETIC, min_keep=4)
    assert len(rescued) == 4

    assert apply_mood_gate(pool, WaveMood.ANY) is pool


def test_centred_cosine_separates_opposite_tracks():
    """Raw 0..1 vectors all point the same way; centring restores contrast."""
    calm = _vector(energy=0.1, loudness=0.1, tempo_norm=0.2, acousticness=0.9)
    loud = _vector(energy=0.9, loudness=0.9, tempo_norm=0.8, acousticness=0.1)

    raw = cosine_similarity(calm, loud)
    centred = cosine_similarity(calm - 0.5, loud - 0.5)
    # All-positive vectors sit in one octant, so even opposites score well
    # above zero and the useful range is squashed into the top of the scale.
    assert raw > 0.5
    # Centring on the neutral midpoint recovers the sign.
    assert centred < 0.0, "centred similarity should show these are opposites"
    assert raw - centred > 0.5


# ---------------------------------------------------------------------------
# Range parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("header", "size", "expected"),
    [
        ("bytes=0-99", 1000, (0, 99)),
        ("bytes=100-", 1000, (100, 999)),
        ("bytes=-100", 1000, (900, 999)),
        ("bytes=0-99999", 1000, (0, 999)),  # clamped, not refused
        ("bytes=999-999", 1000, (999, 999)),
        ("bytes=-5000", 1000, (0, 999)),  # suffix longer than the file
    ],
)
def test_range_parsing(header, size, expected):
    byte_range = parse_range(header, size)
    assert byte_range is not None
    assert (byte_range.start, byte_range.end) == expected
    assert byte_range.length == expected[1] - expected[0] + 1
    assert byte_range.content_range == f"bytes {expected[0]}-{expected[1]}/{size}"


@pytest.mark.parametrize(
    "header",
    [None, "", "bytes=", "items=0-10", "bytes=abc-def", "bytes=0-10, 20-30"],
)
def test_unusable_range_headers_fall_back_to_the_whole_file(header):
    assert parse_range(header, 1000) is None


@pytest.mark.parametrize("header", ["bytes=1000-1010", "bytes=500-100", "bytes=-0"])
def test_impossible_ranges_are_rejected(header):
    with pytest.raises(RangeNotSatisfiable):
        parse_range(header, 1000)


def test_full_range_is_recognised():
    byte_range = parse_range("bytes=0-999", 1000)
    assert byte_range is not None
    assert byte_range.is_full is True


# ---------------------------------------------------------------------------
# Octave disambiguation
# ---------------------------------------------------------------------------


def test_genre_prior_resolves_a_halved_tempo():
    """Autocorrelation often lands on half the real tempo; the tag settles it."""
    from wavelane.services.audio_analysis import AnalysisResult

    result = AnalysisResult(tempo_bpm=66.3)
    result.snap_tempo_octave(132.0)  # techno prior
    assert result.tempo_bpm == pytest.approx(132.6, rel=0.01)


def test_genre_prior_resolves_a_doubled_tempo():
    from wavelane.services.audio_analysis import AnalysisResult

    result = AnalysisResult(tempo_bpm=152.0)
    result.snap_tempo_octave(100.0)  # classical prior
    assert result.tempo_bpm == pytest.approx(76.0, rel=0.01)


def test_a_tempo_close_to_the_prior_is_left_alone():
    from wavelane.services.audio_analysis import AnalysisResult

    for detected, prior in ((143.6, 118.0), (68.0, 80.0), (83.4, 82.0), (123.0, 124.0)):
        result = AnalysisResult(tempo_bpm=detected)
        result.snap_tempo_octave(prior)
        assert result.tempo_bpm == pytest.approx(detected), (
            f"{detected} against prior {prior} should not move"
        )


def test_an_unusual_tempo_survives_when_no_octave_fits_better():
    """A 200 BPM drum-and-bass track must not be halved to match a pop prior."""
    from wavelane.services.audio_analysis import AnalysisResult

    result = AnalysisResult(tempo_bpm=174.0)
    result.snap_tempo_octave(174.0)
    assert result.tempo_bpm == pytest.approx(174.0)


def test_tempo_is_not_averaged_with_the_prior():
    """Averaging 66 and 132 would give 99, which is neither."""
    from wavelane.services.audio_analysis import AnalysisResult

    result = AnalysisResult(tempo_bpm=66.0)
    result.apply({"tempo_bpm": 132.0, "energy": 0.9}, weight=0.25)
    assert result.tempo_bpm == pytest.approx(66.0)
    # Continuous descriptors are still blended.
    assert 0.5 < result.energy < 0.7


def test_missing_tempo_falls_back_to_the_prior():
    from wavelane.services.audio_analysis import AnalysisResult

    result = AnalysisResult(tempo_bpm=0.0)
    result.apply({"tempo_bpm": 118.0}, weight=0.25)
    assert result.tempo_bpm == pytest.approx(118.0)

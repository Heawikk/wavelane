"""Audio feature extraction.

Two analysers, used in order of preference:

``DspAnalyzer``
    Decodes a representative excerpt with ffmpeg and derives real signal
    features with numpy — tempo from an onset envelope, key and mode from a
    chroma correlation, energy/brightness/dynamics from the spectrogram.

``MetadataAnalyzer``
    Fallback when ffmpeg is absent. Builds priors from genre tags, release year
    and duration. Much coarser, but the wave engine still has something to work
    with, and the feature row records which source it came from.
"""

from __future__ import annotations

import logging
import math
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from shutil import which
from typing import Any

import numpy as np

from ..config import Settings, get_settings
from ..models.enums import AnalysisSource
from ..utils import clamp
from ..wave.features import (
    ANALYZER_VERSION,
    FEATURE_NAMES,
    detect_language,
    genre_prior,
    normalize_tempo,
    to_vector,
)

logger = logging.getLogger(__name__)

# --- analysis parameters ---------------------------------------------------
SAMPLE_RATE = 22050
FRAME_SIZE = 2048
HOP_SIZE = 512
EXCERPT_SECONDS = 120.0
EXCERPT_SKIP_SECONDS = 15.0

# Krumhansl-Schmuckler key profiles, used to estimate key and major/minor mode.
_MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88], dtype=np.float64
)
_MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17], dtype=np.float64
)


@dataclass(slots=True)
class AnalysisResult:
    """Everything the analysers can produce, in the shape AudioFeature expects."""

    tempo_bpm: float = 0.0
    energy: float = 0.5
    valence: float = 0.5
    danceability: float = 0.5
    acousticness: float = 0.5
    instrumentalness: float = 0.5
    brightness: float = 0.5
    loudness: float = 0.5
    dynamics: float = 0.5
    vocalness: float = 0.5
    language: str = "unknown"
    musical_key: int | None = None
    musical_mode: int | None = None
    source: AnalysisSource = AnalysisSource.METADATA
    analyzer_version: int = ANALYZER_VERSION
    vector: list[float] = field(default_factory=list)

    def finalize(self) -> AnalysisResult:
        """Clamp every descriptor and refresh the canonical vector."""
        for name in (
            "energy", "valence", "danceability", "acousticness", "instrumentalness",
            "brightness", "loudness", "dynamics", "vocalness",
        ):
            setattr(self, name, clamp(float(getattr(self, name))))
        self.tempo_bpm = max(0.0, float(self.tempo_bpm))
        self.vector = [float(x) for x in to_vector(self.as_feature_dict())]
        return self

    def as_feature_dict(self) -> dict[str, Any]:
        return {
            "tempo_bpm": self.tempo_bpm,
            "tempo_norm": normalize_tempo(self.tempo_bpm),
            "energy": self.energy,
            "valence": self.valence,
            "danceability": self.danceability,
            "acousticness": self.acousticness,
            "instrumentalness": self.instrumentalness,
            "brightness": self.brightness,
            "loudness": self.loudness,
            "dynamics": self.dynamics,
            "vocalness": self.vocalness,
        }

    def apply(self, values: dict[str, float], weight: float = 1.0) -> None:
        """Blend external values (e.g. genre priors) into the current estimate.

        Tempo is handled separately by ``snap_tempo_octave`` rather than
        averaged: halfway between 66 and 132 BPM is 99, which is not a tempo
        either of them could plausibly be. Energy and the rest are genuine
        continuous quantities where a weighted mean does mean something.
        """
        for key, value in values.items():
            if key == "tempo_bpm":
                if self.tempo_bpm <= 0:
                    self.tempo_bpm = value
                continue
            if hasattr(self, key) and key in FEATURE_NAMES:
                current = float(getattr(self, key))
                setattr(self, key, current * (1 - weight) + value * weight)

    def snap_tempo_octave(self, prior_bpm: float, tolerance: float = 0.45) -> None:
        """Use a genre's typical tempo to resolve an octave error.

        Autocorrelation locks onto the beat period *or* a simple multiple of it,
        so the estimate is frequently exactly half or double the real tempo —
        the pattern is visible in the peaks, not a rounding error. A genre tag
        cannot tell us the tempo, but it can say which octave is plausible, and
        that is enough to pick between 66 and 132.

        Nothing is changed when the estimate already agrees with the prior
        within ``tolerance`` octaves, so a genuinely unusual tempo survives.
        """
        if self.tempo_bpm <= 0 or prior_bpm <= 0:
            return

        current_distance = abs(math.log2(self.tempo_bpm / prior_bpm))
        if current_distance <= tolerance:
            return

        best = self.tempo_bpm
        best_distance = current_distance
        for factor in (0.25, 1.0 / 3.0, 0.5, 2.0, 3.0, 4.0):
            candidate = self.tempo_bpm * factor
            if not 40.0 <= candidate <= 220.0:
                continue
            distance = abs(math.log2(candidate / prior_bpm))
            if distance < best_distance:
                best, best_distance = candidate, distance

        self.tempo_bpm = best


# ---------------------------------------------------------------------------
# Metadata-only analyser
# ---------------------------------------------------------------------------


class MetadataAnalyzer:
    """Derives priors from tags alone. Always available."""

    source = AnalysisSource.METADATA

    def analyze(
        self,
        *,
        title: str = "",
        artist: str = "",
        genres: Iterable[str] = (),
        release_year: int | None = None,
        duration_ms: int = 0,
        lyrics: str | None = None,
    ) -> AnalysisResult:
        result = AnalysisResult(source=AnalysisSource.METADATA)
        genres = list(genres)

        prior = genre_prior(genres)
        if prior:
            # Genre tags are the only real information we have here.
            result.apply(prior, weight=1.0)
        else:
            result.tempo_bpm = 110.0

        # Very long tracks skew instrumental/ambient; very short ones skew interlude.
        duration_s = duration_ms / 1000.0
        if duration_s > 420:
            result.instrumentalness = clamp(result.instrumentalness + 0.12)
            result.energy = clamp(result.energy - 0.05)
        elif 0 < duration_s < 90:
            result.energy = clamp(result.energy - 0.05)

        # Loudness-war era: mid-90s onwards is mastered hotter with less dynamic range.
        if release_year:
            if release_year >= 1995:
                result.loudness = clamp(result.loudness + 0.15)
                result.dynamics = clamp(result.dynamics - 0.15)
            elif release_year < 1975:
                result.brightness = clamp(result.brightness - 0.10)
                result.dynamics = clamp(result.dynamics + 0.10)

        result.vocalness = clamp(1.0 - result.instrumentalness)
        result.language = detect_language(
            title=title,
            artist=artist,
            lyrics=lyrics,
            genres=genres,
            instrumentalness=result.instrumentalness,
        )
        return result.finalize()


# ---------------------------------------------------------------------------
# DSP analyser
# ---------------------------------------------------------------------------


class DspAnalyzer:
    """Real signal analysis. Requires ffmpeg on PATH or configured explicitly."""

    source = AnalysisSource.DSP

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._ffmpeg = self.settings.ffmpeg_path or which("ffmpeg") or ""

    @property
    def available(self) -> bool:
        return bool(self._ffmpeg)

    # --- decoding -----------------------------------------------------------

    def decode(self, path: Path, duration_ms: int = 0) -> np.ndarray:
        """Decode a mono float32 excerpt. Raises RuntimeError if ffmpeg fails."""
        if not self._ffmpeg:
            raise RuntimeError("ffmpeg not available")

        # Skip the intro and analyse the body of the track, where the groove is.
        start = EXCERPT_SKIP_SECONDS
        if duration_ms:
            total = duration_ms / 1000.0
            if total <= EXCERPT_SECONDS:
                start = 0.0
            else:
                start = min(max(total * 0.1, EXCERPT_SKIP_SECONDS), total - EXCERPT_SECONDS)

        command = [
            self._ffmpeg, "-v", "error", "-nostdin",
            "-ss", f"{start:.2f}",
            "-t", f"{EXCERPT_SECONDS:.2f}",
            "-i", str(path),
            "-f", "f32le", "-acodec", "pcm_f32le",
            "-ac", "1", "-ar", str(SAMPLE_RATE),
            "-",
        ]
        try:
            completed = subprocess.run(
                command, capture_output=True, check=True, timeout=180
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"ffmpeg timed out on {path.name}") from exc
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.decode("utf-8", "replace").strip()[:300]
            raise RuntimeError(f"ffmpeg failed on {path.name}: {detail}") from exc

        samples = np.frombuffer(completed.stdout, dtype=np.float32)
        if samples.size < SAMPLE_RATE:
            raise RuntimeError(f"decoded excerpt too short for {path.name}")
        return np.nan_to_num(samples, nan=0.0, posinf=0.0, neginf=0.0)

    def analyze(
        self,
        path: Path,
        *,
        title: str = "",
        artist: str = "",
        genres: Iterable[str] = (),
        release_year: int | None = None,
        duration_ms: int = 0,
        lyrics: str | None = None,
    ) -> AnalysisResult:
        samples = self.decode(path, duration_ms)
        result = analyze_pcm(samples, SAMPLE_RATE)

        # Genre tags still add information the signal does not carry; blend
        # them in lightly so DSP stays dominant, and let the genre's typical
        # tempo settle which octave the detected beat belongs to.
        prior = genre_prior(genres)
        if prior:
            result.apply(prior, weight=0.25)
            if "tempo_bpm" in prior:
                result.snap_tempo_octave(prior["tempo_bpm"])

        result.language = detect_language(
            title=title,
            artist=artist,
            lyrics=lyrics,
            genres=genres,
            instrumentalness=result.instrumentalness,
        )
        return result.finalize()


# ---------------------------------------------------------------------------
# Pure-numpy feature extraction (testable without ffmpeg)
# ---------------------------------------------------------------------------


def analyze_pcm(samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> AnalysisResult:
    """Extract features from mono float PCM in -1..1."""
    samples = np.asarray(samples, dtype=np.float32)
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    if samples.size < FRAME_SIZE * 2:
        return AnalysisResult(source=AnalysisSource.DSP).finalize()

    magnitudes, frame_rms = _spectrogram(samples)
    freqs = np.fft.rfftfreq(FRAME_SIZE, d=1.0 / sample_rate)

    result = AnalysisResult(source=AnalysisSource.DSP)

    # --- loudness and dynamics ---------------------------------------------
    active = frame_rms[frame_rms > 1e-5]
    if active.size == 0:
        return result.finalize()
    mean_db = 20.0 * np.log10(float(np.mean(active)))
    peak_db = 20.0 * np.log10(float(np.percentile(active, 99)))
    # -36 dBFS reads as quiet, -6 dBFS as a hot master.
    result.loudness = clamp((mean_db + 36.0) / 30.0)
    crest = peak_db - mean_db
    # 2 dB crest is a brick-walled master, 18 dB is orchestral.
    result.dynamics = clamp(crest / 18.0)

    # --- spectral shape ----------------------------------------------------
    centroid = _spectral_centroid(magnitudes, freqs)
    # 200 Hz is dark, 4 kHz is bright, on a log scale.
    result.brightness = clamp((np.log2(max(centroid, 50.0)) - np.log2(200.0)) / 4.3)

    flatness = _spectral_flatness(magnitudes)
    rolloff = _spectral_rolloff(magnitudes, freqs, 0.85)
    band_energy = _band_energies(magnitudes, freqs, sample_rate)

    # --- energy ------------------------------------------------------------
    # Perceived energy is loudness plus high-frequency content plus how much
    # of the spectrum sits above the bass region.
    hf_share = band_energy["high"] + band_energy["mid_high"]
    result.energy = clamp(0.55 * result.loudness + 0.30 * hf_share + 0.15 * result.brightness)

    # --- tempo and danceability -------------------------------------------
    onset_env = _onset_envelope(magnitudes)
    fps = sample_rate / HOP_SIZE
    tempo, beat_strength = _estimate_tempo(onset_env, fps)
    result.tempo_bpm = tempo
    # A danceable track has a strong periodic pulse and solid low-end.
    result.danceability = clamp(
        0.50 * beat_strength + 0.25 * band_energy["low"] * 2.0 + 0.25 * _tempo_sweetspot(tempo)
    )

    # --- acousticness ------------------------------------------------------
    # Acoustic recordings: wider dynamics, less sub-bass, less brick-walling,
    # and more harmonic (less flat) spectra than synthesised material.
    result.acousticness = clamp(
        0.35 * result.dynamics
        + 0.30 * (1.0 - min(band_energy["sub"] * 4.0, 1.0))
        + 0.20 * (1.0 - flatness)
        + 0.15 * (1.0 - result.loudness)
    )

    # --- instrumentalness --------------------------------------------------
    # Vocals live in 300-3400 Hz, but so do guitars and piano, so raw band
    # energy alone would call every chord a voice. The discriminating cue is
    # movement: a sung line slides in pitch and loudness far more than the
    # backing does. Comparing the vocal band's fluctuation against the whole
    # spectrum's also cancels out percussion, which drives flux everywhere.
    vocal_share = band_energy["vocal"]
    movement_score = _pitch_movement(magnitudes, freqs, sample_rate)
    vocal_likelihood = clamp(0.30 * min(vocal_share * 1.6, 1.0) + 0.70 * movement_score)
    result.instrumentalness = clamp(1.0 - vocal_likelihood)
    result.vocalness = clamp(vocal_likelihood)

    # --- key, mode, valence ------------------------------------------------
    chroma = _chroma(magnitudes, freqs)
    key, mode, mode_strength = _estimate_key(chroma)
    result.musical_key = key
    result.musical_mode = mode
    # Major mode, brighter spectrum and faster tempo all read as happier.
    major_bias = 0.5 + (0.5 if mode == 1 else -0.5) * clamp(mode_strength) * 0.6
    result.valence = clamp(
        0.45 * major_bias + 0.25 * result.brightness + 0.15 * _tempo_sweetspot(tempo)
        + 0.15 * result.energy
    )

    # Rolloff is informative for brightness at the top end; nudge it.
    if rolloff > 0:
        result.brightness = clamp(
            0.75 * result.brightness
            + 0.25 * clamp((np.log2(max(rolloff, 100.0)) - np.log2(1000.0)) / 3.5)
        )

    return result.finalize()


def _spectrogram(samples: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Magnitude spectrogram (frames x bins) plus per-frame RMS."""
    frame_count = 1 + (samples.size - FRAME_SIZE) // HOP_SIZE
    if frame_count <= 0:
        return np.zeros((1, FRAME_SIZE // 2 + 1)), np.zeros(1)

    # Strided view avoids copying the whole signal into overlapping frames.
    frames = np.lib.stride_tricks.as_strided(
        samples,
        shape=(frame_count, FRAME_SIZE),
        strides=(samples.strides[0] * HOP_SIZE, samples.strides[0]),
        writeable=False,
    )
    rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))
    window = np.hanning(FRAME_SIZE)
    spectrum = np.fft.rfft(frames * window, axis=1)
    return np.abs(spectrum), rms


def _spectral_centroid(magnitudes: np.ndarray, freqs: np.ndarray) -> float:
    total = magnitudes.sum(axis=1)
    valid = total > 1e-9
    if not np.any(valid):
        return 0.0
    centroids = (magnitudes[valid] * freqs).sum(axis=1) / total[valid]
    return float(np.median(centroids))


def _spectral_flatness(magnitudes: np.ndarray) -> float:
    """Geometric/arithmetic mean ratio: 0 = tonal, 1 = noise-like."""
    safe = magnitudes + 1e-10
    geometric = np.exp(np.mean(np.log(safe), axis=1))
    arithmetic = np.mean(safe, axis=1)
    ratio = geometric / np.maximum(arithmetic, 1e-10)
    return float(np.clip(np.median(ratio), 0.0, 1.0))


def _spectral_rolloff(magnitudes: np.ndarray, freqs: np.ndarray, fraction: float) -> float:
    total = magnitudes.sum(axis=1, keepdims=True)
    valid = (total > 1e-9).ravel()
    if not np.any(valid):
        return 0.0
    cumulative = np.cumsum(magnitudes[valid], axis=1) / total[valid]
    indices = np.argmax(cumulative >= fraction, axis=1)
    return float(np.median(freqs[indices]))


def _band_energies(
    magnitudes: np.ndarray, freqs: np.ndarray, sample_rate: int
) -> dict[str, float]:
    """Fraction of spectral energy per perceptual band."""
    power = magnitudes.mean(axis=0) ** 2
    total = float(power.sum()) or 1.0
    nyquist = sample_rate / 2.0
    bands = {
        "sub": (20.0, 80.0),
        "low": (80.0, 250.0),
        "mid": (250.0, 2000.0),
        "mid_high": (2000.0, 6000.0),
        "high": (6000.0, min(nyquist, 11000.0)),
        "vocal": (300.0, 3400.0),
    }
    out: dict[str, float] = {}
    for name, (low, high) in bands.items():
        mask = (freqs >= low) & (freqs < high)
        out[name] = float(power[mask].sum() / total) if np.any(mask) else 0.0
    return out


def _band_variability(
    magnitudes: np.ndarray, freqs: np.ndarray, low: float, high: float
) -> float:
    """How much the energy in a band fluctuates over time (vocal activity proxy)."""
    mask = (freqs >= low) & (freqs < high)
    if not np.any(mask):
        return 0.0
    envelope = magnitudes[:, mask].sum(axis=1)
    mean = float(envelope.mean())
    if mean <= 1e-9:
        return 0.0
    # Coefficient of variation, saturating at 1.
    return clamp(float(envelope.std() / mean))


def _pitch_movement(
    magnitudes: np.ndarray, freqs: np.ndarray, sample_rate: int
) -> float:
    """Singing-voice likelihood from the behaviour of the dominant low pitch.

    The cue is movement, not energy. A sung line glides between notes and
    carries 4-8 Hz vibrato; a held chord parks the dominant peak on one
    frequency; noise makes it jump by octaves at random. So we track the
    strongest partial in the fundamental range and ask how often it moves by a
    musically expressive interval, then look for vibrato in the contour.
    """
    mask = (freqs >= 150.0) & (freqs <= 1100.0)
    if np.count_nonzero(mask) < 8:
        return 0.0

    band = magnitudes[:, mask].astype(np.float64)
    band_freqs = freqs[mask]
    if band.shape[0] < 16:
        return 0.0

    peak_indices = np.argmax(band, axis=1)
    rows = np.arange(band.shape[0])
    peak_values = band[rows, peak_indices]
    band_totals = band.sum(axis=1)

    # A real pitch stands out from its own band; a flat spectrum does not.
    with np.errstate(divide="ignore", invalid="ignore"):
        prominence = np.where(band_totals > 1e-9, peak_values / band_totals, 0.0)
    voiced = prominence > 0.08
    if np.count_nonzero(voiced) < 8:
        return 0.0

    # Parabolic interpolation around the peak: one FFT bin is ~60 cents at
    # 300 Hz, far too coarse to see vibrato without refining the estimate.
    interpolated = _interpolate_peaks(band, peak_indices, band_freqs)

    cents = np.full(band.shape[0], np.nan)
    np.putmask(cents, voiced, 1200.0 * np.log2(interpolated[voiced] / 55.0))

    valid_pairs = voiced[:-1] & voiced[1:]
    if np.count_nonzero(valid_pairs) < 6:
        return 0.0
    deltas = np.abs(np.diff(cents)[valid_pairs])

    # Below 8 cents the pitch is parked (a sustained chord); above 250 it is a
    # tracking error or an octave jump rather than a sung interval.
    expressive = float(np.mean((deltas > 8.0) & (deltas < 250.0)))

    vibrato = _vibrato_strength(cents, sample_rate / HOP_SIZE)
    return clamp(0.65 * expressive + 0.35 * vibrato)


def _interpolate_peaks(
    band: np.ndarray, peak_indices: np.ndarray, band_freqs: np.ndarray
) -> np.ndarray:
    """Sub-bin peak frequency via a parabola through the log-magnitude peak."""
    last = band.shape[1] - 1
    centre = np.clip(peak_indices, 1, last - 1) if last >= 2 else peak_indices
    rows = np.arange(band.shape[0])

    left = np.log(band[rows, centre - 1] + 1e-12)
    middle = np.log(band[rows, centre] + 1e-12)
    right = np.log(band[rows, centre + 1] + 1e-12)

    denom = left - 2.0 * middle + right
    shift = np.where(np.abs(denom) > 1e-12, 0.5 * (left - right) / denom, 0.0)
    shift = np.clip(shift, -0.5, 0.5)

    spacing = float(band_freqs[1] - band_freqs[0]) if band_freqs.size > 1 else 0.0
    return np.maximum(band_freqs[centre] + shift * spacing, 1.0)


def _vibrato_strength(cents: np.ndarray, fps: float) -> float:
    """Look for 4-8 Hz periodic modulation in the pitch contour."""
    contour = cents[np.isfinite(cents)]
    if contour.size < int(fps * 1.5):
        return 0.0

    # Remove the melody itself, keeping only fast wobble around each note.
    kernel_size = max(int(fps * 0.25), 3)
    kernel = np.ones(kernel_size) / kernel_size
    smoothed = np.convolve(contour, kernel, mode="same")
    wobble = contour - smoothed
    spread = float(np.std(wobble))
    # Vibrato is roughly 20-100 cents deep; anything larger is note movement.
    if spread < 3.0 or spread > 150.0:
        return 0.0

    autocorr = np.correlate(wobble, wobble, mode="full")[wobble.size - 1 :]
    if autocorr[0] <= 0:
        return 0.0
    autocorr /= autocorr[0]

    low_lag = max(int(round(fps / 8.0)), 1)
    high_lag = min(int(round(fps / 4.0)), autocorr.size - 1)
    if high_lag <= low_lag:
        return 0.0
    return clamp(float(np.max(autocorr[low_lag : high_lag + 1])) * 2.0)


def _onset_envelope(magnitudes: np.ndarray) -> np.ndarray:
    """Spectral flux: positive frame-to-frame increases in energy."""
    log_mag = np.log1p(magnitudes)
    flux = np.diff(log_mag, axis=0)
    envelope = np.maximum(flux, 0.0).sum(axis=1)
    if envelope.size == 0:
        return envelope
    envelope -= envelope.mean()
    peak = float(np.max(np.abs(envelope)))
    return envelope / peak if peak > 0 else envelope


def _estimate_tempo(onset_env: np.ndarray, fps: float) -> tuple[float, float]:
    """Autocorrelate the onset envelope and pick the strongest plausible BPM."""
    if onset_env.size < int(fps * 4):
        return 110.0, 0.3

    autocorr = np.correlate(onset_env, onset_env, mode="full")[onset_env.size - 1 :]
    if autocorr[0] <= 0:
        return 110.0, 0.3
    autocorr = autocorr / autocorr[0]

    min_lag = max(int(round(60.0 * fps / 190.0)), 1)
    max_lag = min(int(round(60.0 * fps / 50.0)), autocorr.size - 1)
    if max_lag <= min_lag:
        return 110.0, 0.3

    window = autocorr[min_lag : max_lag + 1]
    lags = np.arange(min_lag, max_lag + 1)
    bpms = 60.0 * fps / lags

    # Autocorrelation peaks at every multiple of the true beat period, so the
    # raw maximum lands on half or a third of the real tempo as often as not.
    # Two corrections: a log-normal prior around 120 BPM, and harmonic
    # summation, which rewards a lag whose own multiples also show peaks — true
    # of a real beat period, not of an accidental doubling.
    scored = window.astype(np.float64).copy()
    for multiple, weight in ((2, 0.5), (3, 0.25), (4, 0.125)):
        harmonic_lags = lags * multiple
        valid = harmonic_lags < autocorr.size
        scored[valid] += weight * autocorr[harmonic_lags[valid]]

    prior = np.exp(-0.5 * ((np.log2(bpms / 120.0)) / 0.9) ** 2)
    scored *= prior

    best = int(np.argmax(scored))
    tempo = float(bpms[best])
    strength = clamp(float(window[best]))
    return tempo, strength


def _tempo_sweetspot(tempo: float) -> float:
    """1.0 around 100-130 BPM, falling off outside it."""
    if tempo <= 0:
        return 0.3
    return clamp(float(np.exp(-0.5 * ((np.log2(tempo / 118.0)) / 0.45) ** 2)))


def _chroma(magnitudes: np.ndarray, freqs: np.ndarray) -> np.ndarray:
    """Fold spectral energy into 12 pitch classes."""
    spectrum = magnitudes.mean(axis=0)
    chroma = np.zeros(12, dtype=np.float64)
    # Ignore bins below A0 and above C8, where pitch estimation is unreliable.
    usable = (freqs >= 27.5) & (freqs <= 4186.0)
    if not np.any(usable):
        return chroma
    midi = 69.0 + 12.0 * np.log2(freqs[usable] / 440.0)
    classes = np.rint(midi).astype(int) % 12
    np.add.at(chroma, classes, spectrum[usable])
    total = chroma.sum()
    return chroma / total if total > 0 else chroma


def _estimate_key(chroma: np.ndarray) -> tuple[int | None, int | None, float]:
    """Correlate the chroma against rotated major/minor profiles.

    Returns (key 0-11, mode 1=major/0=minor, confidence margin 0..1).
    """
    if chroma.sum() <= 0:
        return None, None, 0.0

    best_key, best_mode, best_score, runner_up = None, None, -2.0, -2.0
    for rotation in range(12):
        rotated = np.roll(chroma, -rotation)
        for mode, profile in ((1, _MAJOR_PROFILE), (0, _MINOR_PROFILE)):
            score = _pearson(rotated, profile)
            if score > best_score:
                runner_up = best_score
                best_score, best_key, best_mode = score, rotation, mode
            elif score > runner_up:
                runner_up = score

    margin = clamp((best_score - runner_up) * 2.5) if runner_up > -2.0 else 0.0
    return best_key, best_mode, margin


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    a_centered = a - a.mean()
    b_centered = b - b.mean()
    denom = float(np.linalg.norm(a_centered) * np.linalg.norm(b_centered))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a_centered, b_centered) / denom)


# ---------------------------------------------------------------------------
# Facade
# ---------------------------------------------------------------------------


class AudioAnalyzer:
    """Picks the best available analyser and never raises on analysis failure."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._dsp = DspAnalyzer(self.settings)
        self._metadata = MetadataAnalyzer()

    @property
    def dsp_available(self) -> bool:
        return self._dsp.available

    def analyze(
        self,
        path: Path | None,
        *,
        title: str = "",
        artist: str = "",
        genres: Iterable[str] = (),
        release_year: int | None = None,
        duration_ms: int = 0,
        lyrics: str | None = None,
    ) -> AnalysisResult:
        genres = list(genres)
        kwargs = {
            "title": title,
            "artist": artist,
            "genres": genres,
            "release_year": release_year,
            "duration_ms": duration_ms,
            "lyrics": lyrics,
        }

        if path is not None and self._dsp.available:
            try:
                return self._dsp.analyze(path, **kwargs)
            except Exception as exc:  # analysis must never block an upload
                logger.warning("DSP analysis failed for %s: %s", path, exc)

        return self._metadata.analyze(**kwargs)


_analyzer: AudioAnalyzer | None = None


def get_analyzer() -> AudioAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = AudioAnalyzer()
    return _analyzer

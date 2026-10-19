#include "AudioTap.h"

#include <QGuiApplication>
#include <QLoggingCategory>
#include <QMediaPlayer>

#include <algorithm>
#include <cmath>
#include <complex>

Q_LOGGING_CATEGORY(lcTap, "wavelane.tap")

namespace {

constexpr float kPi = 3.14159265358979f;
// The range the analyser reports on, in dBFS, mapped onto 0..1.
constexpr float kFloorDb = -78.0f;
constexpr float kRangeDb = 66.0f;
constexpr float kLevelFloorDb = -58.0f;
constexpr float kLevelRangeDb = 52.0f;
// Real music loses energy towards the treble; without a tilt the right half of
// the display would sit near zero. Roughly pink-noise compensation.
constexpr float kTiltDbPerOctave = 3.0f;

// Smoothing per 16 ms tick: rise quickly, fall slowly.
constexpr qreal kAttack = 0.55;
constexpr qreal kRelease = 0.13;
constexpr qint64 kMaxFramesKept = 500;

//! In-place radix-2 FFT. `data.size()` must be a power of two.
void fft(std::vector<std::complex<float>> &data)
{
    const size_t n = data.size();
    for (size_t i = 1, j = 0; i < n; ++i) {
        size_t bit = n >> 1;
        for (; j & bit; bit >>= 1)
            j ^= bit;
        j ^= bit;
        if (i < j)
            std::swap(data[i], data[j]);
    }
    for (size_t length = 2; length <= n; length <<= 1) {
        const float angle = -2.0f * kPi / static_cast<float>(length);
        const std::complex<float> step(std::cos(angle), std::sin(angle));
        for (size_t start = 0; start < n; start += length) {
            std::complex<float> twiddle(1.0f, 0.0f);
            for (size_t k = 0; k < length / 2; ++k) {
                const std::complex<float> even = data[start + k];
                const std::complex<float> odd = data[start + k + length / 2] * twiddle;
                data[start + k] = even + odd;
                data[start + k + length / 2] = even - odd;
                twiddle *= step;
            }
        }
    }
}

float toUnit(float db, float floorDb, float rangeDb)
{
    return std::clamp((db - floorDb) / rangeDb, 0.0f, 1.0f);
}

} // namespace

AudioTap::AudioTap(QMediaPlayer *player, bool attach, QObject *parent)
    : QObject(parent)
    , m_player(player)
    , m_output(this)
{
    m_bands = QList<qreal>(BandCount, 0.0);

    m_window.resize(FftSize);
    for (int i = 0; i < FftSize; ++i)
        m_window[i] = 0.5f - 0.5f * std::cos(2.0f * kPi * static_cast<float>(i) / (FftSize - 1));

    m_positionClock.start();
    m_leadLog.start();

    m_attached = attach;
    if (attach) {
        m_player->setAudioBufferOutput(&m_output);
        connect(&m_output, &QAudioBufferOutput::audioBufferReceived, this, &AudioTap::onBuffer);
    }
    connect(m_player, &QMediaPlayer::positionChanged, this, [this](qint64 position) {
        m_positionMs = position;
        m_positionClock.restart();
    });

    m_timer.setInterval(16);
    connect(&m_timer, &QTimer::timeout, this, &AudioTap::tick);
    m_timer.start();

    // Nothing is drawn while the app is not on screen (the window is minimized, or the phone's
    // screen is off), so listening to the audio for the picture would only waste battery.
    connect(qApp, &QGuiApplication::applicationStateChanged, this, [this](Qt::ApplicationState state) {
        setActive(state >= Qt::ApplicationInactive);
    });
}

void AudioTap::setActive(bool active)
{
    if (m_active == active)
        return;
    m_active = active;
    if (!m_attached)
        return;
    if (active) {
        m_player->setAudioBufferOutput(&m_output);
        m_timer.start();
    } else {
        m_player->setAudioBufferOutput(nullptr);
        m_timer.stop();
        reset();
    }
}

void AudioTap::reset()
{
    m_samples.clear();
    m_frames.clear();
}

void AudioTap::prepareBands(int sampleRate)
{
    m_sampleRate = sampleRate;
    m_bandBins.clear();
    m_bandTilt.clear();

    const float binHz = static_cast<float>(sampleRate) / FftSize;
    const float low = 40.0f;
    const float high = std::min(16000.0f, static_cast<float>(sampleRate) / 2.0f - binHz);
    const float ratio = std::pow(high / low, 1.0f / BandCount);

    for (int band = 0; band < BandCount; ++band) {
        const float f0 = low * std::pow(ratio, static_cast<float>(band));
        const float f1 = f0 * ratio;
        int first = std::max(1, static_cast<int>(std::floor(f0 / binHz)));
        int last = std::max(first + 1, static_cast<int>(std::ceil(f1 / binHz)));
        last = std::min(last, FftSize / 2 - 1);
        first = std::min(first, last - 1);
        m_bandBins.emplace_back(first, last);
        // How far this band is from 200 Hz, in octaves, times the tilt.
        const float centre = std::sqrt(f0 * f1);
        m_bandTilt.push_back(std::max(0.0f, kTiltDbPerOctave * std::log2(centre / 200.0f)));
    }
}

void AudioTap::onBuffer(const QAudioBuffer &buffer)
{
    if (!buffer.isValid() || buffer.frameCount() <= 0)
        return;

    const QAudioFormat format = buffer.format();
    const int channels = std::max(1, format.channelCount());
    const int rate = format.sampleRate();
    if (rate <= 0)
        return;
    if (rate != m_sampleRate)
        prepareBands(rate);

    // Where this chunk begins on the track's own clock. If it is not where the
    // previous one ended, playback jumped (a seek, or a new track) and what is
    // buffered no longer belongs to the same timeline.
    const qint64 expectedUs = m_samplesStartUs
                              + static_cast<qint64>(m_samples.size()) * 1000000 / rate;
    const qint64 startUs = buffer.startTime() >= 0 ? buffer.startTime() : expectedUs;
    if (m_samples.empty()) {
        m_samplesStartUs = startUs;
    } else if (std::llabs(startUs - expectedUs) > 80000) {
        m_samples.clear();
        m_frames.clear();
        m_samplesStartUs = startUs;
    }

    const int frames = buffer.frameCount();
    m_samples.reserve(m_samples.size() + static_cast<size_t>(frames));

    auto appendMono = [&](auto readSample) {
        for (int frame = 0; frame < frames; ++frame) {
            float sum = 0.0f;
            for (int channel = 0; channel < channels; ++channel)
                sum += readSample(static_cast<size_t>(frame) * channels + channel);
            m_samples.push_back(sum / static_cast<float>(channels));
        }
    };

    switch (format.sampleFormat()) {
    case QAudioFormat::UInt8: {
        const auto *data = buffer.constData<quint8>();
        appendMono([data](size_t i) { return (static_cast<float>(data[i]) - 128.0f) / 128.0f; });
        break;
    }
    case QAudioFormat::Int16: {
        const auto *data = buffer.constData<qint16>();
        appendMono([data](size_t i) { return static_cast<float>(data[i]) / 32768.0f; });
        break;
    }
    case QAudioFormat::Int32: {
        const auto *data = buffer.constData<qint32>();
        appendMono([data](size_t i) { return static_cast<float>(data[i]) / 2147483648.0f; });
        break;
    }
    case QAudioFormat::Float: {
        const auto *data = buffer.constData<float>();
        appendMono([data](size_t i) { return data[i]; });
        break;
    }
    default:
        return;
    }

    // One analysis window per hop, so the picture refreshes ~86 times a second.
    while (m_samples.size() >= static_cast<size_t>(FftSize)) {
        analyseWindow(m_samplesStartUs);
        m_samples.erase(m_samples.begin(), m_samples.begin() + Hop);
        m_samplesStartUs += static_cast<qint64>(Hop) * 1000000 / m_sampleRate;
    }
}

void AudioTap::analyseWindow(qint64 startUs)
{
    std::vector<std::complex<float>> spectrum(FftSize);
    double energy = 0.0;
    for (int i = 0; i < FftSize; ++i) {
        const float sample = m_samples[static_cast<size_t>(i)];
        energy += static_cast<double>(sample) * sample;
        spectrum[static_cast<size_t>(i)] = {sample * m_window[static_cast<size_t>(i)], 0.0f};
    }
    fft(spectrum);

    Frame frame;
    // Time of the middle of the window: that is the moment it describes.
    frame.timeUs = startUs + static_cast<qint64>(FftSize / 2) * 1000000 / m_sampleRate;

    const float rms = static_cast<float>(std::sqrt(energy / FftSize));
    frame.level = toUnit(20.0f * std::log10(rms + 1e-6f), kLevelFloorDb, kLevelRangeDb);

    for (int band = 0; band < BandCount; ++band) {
        const auto [first, last] = m_bandBins[static_cast<size_t>(band)];
        float sum = 0.0f;
        for (int bin = first; bin <= last; ++bin)
            sum += std::norm(spectrum[static_cast<size_t>(bin)]);
        const float magnitude = std::sqrt(sum / static_cast<float>(last - first + 1));
        // 4/N turns a full-scale sine's peak into 1.0 despite the Hann window.
        const float amplitude = 4.0f * magnitude / static_cast<float>(FftSize);
        const float db = 20.0f * std::log10(amplitude + 1e-5f) + m_bandTilt[static_cast<size_t>(band)];
        frame.bands[static_cast<size_t>(band)] = toUnit(db, kFloorDb, kRangeDb);
    }

    m_frames.push_back(frame);
    while (m_frames.size() > static_cast<size_t>(kMaxFramesKept))
        m_frames.pop_front();
}

qint64 AudioTap::estimatedPositionUs() const
{
    // The player reports position in coarse steps; between them, assume it is
    // advancing in real time.
    qint64 positionMs = m_positionMs;
    if (m_player->playbackState() == QMediaPlayer::PlayingState)
        positionMs += m_positionClock.elapsed();
    return positionMs * 1000;
}

void AudioTap::tick()
{
    const bool playing = m_player->playbackState() == QMediaPlayer::PlayingState;

    std::array<float, BandCount> target{};
    float targetLevel = 0.0f;

    if (playing && !m_frames.empty()) {
        const qint64 now = estimatedPositionUs();

        // Frames the playback position has already passed are of no use.
        while (m_frames.size() > 1 && m_frames[1].timeUs <= now)
            m_frames.pop_front();

        const Frame &current = m_frames.front();
        if (m_leadLog.elapsed() > 4000) {
            m_leadLog.restart();
            qCDebug(lcTap) << "lead (ms): front frame is" << (current.timeUs - now) / 1000
                           << "ahead of playback; queued" << m_frames.size();
        }

        // A frame further in the future than one hop means the picture would
        // run ahead of the sound, so hold the previous state until it is due.
        if (current.timeUs <= now + 60000) {
            target = current.bands;
            targetLevel = current.level;
        } else {
            return;
        }
    }

    bool moved = false;
    auto follow = [&moved](qreal &value, qreal goal) {
        const qreal next = value + (goal - value) * (goal > value ? kAttack : kRelease);
        if (std::abs(next - value) > 0.0005)
            moved = true;
        value = next;
    };

    follow(m_level, targetLevel);
    for (int band = 0; band < BandCount; ++band)
        follow(m_bands[band], static_cast<qreal>(target[static_cast<size_t>(band)]));

    auto mean = [this](int from, int to) {
        qreal sum = 0.0;
        for (int i = from; i < to; ++i)
            sum += m_bands[i];
        return sum / (to - from);
    };
    m_bass = mean(0, 6);
    m_mid = mean(6, 20);
    m_treble = mean(20, BandCount);

    if (moved)
        emit changed();
}

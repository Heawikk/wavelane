#pragma once

#include <QAudioBuffer>
#include <QAudioBufferOutput>
#include <QElapsedTimer>
#include <QList>
#include <QObject>
#include <QTimer>
#include <qqmlintegration.h>

#include <array>
#include <deque>
#include <vector>

class QMediaPlayer;

/*!
 * Listens to what the player is playing and reports how loud it is and how
 * that loudness is spread across the spectrum, for the animation on the wave
 * page.
 *
 * Qt hands over decoded audio in chunks that can run well ahead of what is
 * actually coming out of the speakers, so analysing "the latest chunk" would
 * make the picture move before the sound does. Each chunk is therefore turned
 * into timestamped frames, and a timer picks the frame that belongs to the
 * current playback position. The output is smoothed with a quick attack and a
 * slow release, which is what makes a beat look like a beat rather than flicker.
 */
class AudioTap : public QObject
{
    Q_OBJECT
    QML_ANONYMOUS

    //! Overall loudness, 0..1.
    Q_PROPERTY(qreal level READ level NOTIFY changed)
    //! Energy in the low, middle and high thirds of the spectrum, 0..1.
    Q_PROPERTY(qreal bass READ bass NOTIFY changed)
    Q_PROPERTY(qreal mid READ mid NOTIFY changed)
    Q_PROPERTY(qreal treble READ treble NOTIFY changed)
    //! Log-spaced bands from low to high frequency, each 0..1.
    Q_PROPERTY(QList<qreal> bands READ bands NOTIFY changed)

public:
    static constexpr int BandCount = 32;
    static constexpr int FftSize = 1024;
    static constexpr int Hop = 512;

    //! `attach` false builds an inert tap, which is how the analysis is switched off
    //! when hunting for a playback bug that it might be blamed for.
    explicit AudioTap(QMediaPlayer *player, bool attach = true, QObject *parent = nullptr);

    qreal level() const { return m_level; }
    qreal bass() const { return m_bass; }
    qreal mid() const { return m_mid; }
    qreal treble() const { return m_treble; }
    QList<qreal> bands() const { return m_bands; }

    //! Forget everything buffered, e.g. when playback is stopped.
    void reset();

signals:
    void changed();

private:
    struct Frame
    {
        qint64 timeUs = 0;
        float level = 0.0f;
        std::array<float, BandCount> bands{};
    };

    //! The analysis is only for the picture: when nothing can be seen it is switched off.
    void setActive(bool active);
    void onBuffer(const QAudioBuffer &buffer);
    void analyseWindow(qint64 startUs);
    void prepareBands(int sampleRate);
    qint64 estimatedPositionUs() const;
    void tick();

    QMediaPlayer *m_player = nullptr;
    QAudioBufferOutput m_output;
    QTimer m_timer;
    bool m_attached = false;
    bool m_active = true;

    // --- decoded audio waiting to be analysed ---
    std::vector<float> m_samples;
    qint64 m_samplesStartUs = 0;
    int m_sampleRate = 0;
    std::deque<Frame> m_frames;

    // --- FFT scratch, built once ---
    std::vector<float> m_window;
    std::vector<std::pair<int, int>> m_bandBins;
    std::vector<float> m_bandTilt;

    // --- where playback is, between the player's coarse updates ---
    qint64 m_positionMs = 0;
    QElapsedTimer m_positionClock;

    // --- smoothed output ---
    qreal m_level = 0.0;
    qreal m_bass = 0.0;
    qreal m_mid = 0.0;
    qreal m_treble = 0.0;
    QList<qreal> m_bands;
    QElapsedTimer m_leadLog;
};

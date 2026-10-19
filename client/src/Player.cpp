#include "Player.h"

#include "ApiClient.h"
#include "Settings.h"

#include <QAudioDevice>
#include <QJsonObject>
#include <QLoggingCategory>

Q_LOGGING_CATEGORY(lcPlayer, "wavelane.player")

namespace {
//! Fraction of the track after which stopping counts as "finished".
constexpr double kCompletionThreshold = 0.95;
//! How early to ask for more tracks, so playback never stalls at the end.
constexpr qint64 kNearEndMs = 20000;
} // namespace

Player::Player(ApiClient *api, Settings *settings, QObject *parent)
    : QObject(parent)
    , m_api(api)
    , m_settings(settings)
{
    m_media.setAudioOutput(&m_audio);
    m_tap = new AudioTap(&m_media, !qEnvironmentVariableIsSet("WAVELANE_NO_TAP"), this);

    if (m_settings) {
        m_audio.setVolume(static_cast<float>(m_settings->volume()) / 100.0f);
        m_audio.setMuted(m_settings->muted());
    }

    connect(&m_media, &QMediaPlayer::mediaStatusChanged, this, &Player::handleMediaStatus);
    connect(&m_media, &QMediaPlayer::positionChanged, this, &Player::handlePositionChanged);
    connect(&m_media, &QMediaPlayer::errorOccurred, this, &Player::handleError);
    connect(&m_media, &QMediaPlayer::playbackStateChanged, this, [this]() {
        qCInfo(lcPlayer) << "state" << m_media.playbackState() << "pos" << m_media.position()
                         << "track" << m_current.title;
        emit playingChanged();
    });
    connect(&m_media, &QMediaPlayer::durationChanged, this, [this]() {
        emit durationChanged();
    });

    // Set only to reproduce the stall for diagnosis; normally it is repaired.
    // Headphones plugged in or out, or the default output changed in Windows.
    // The stream moves at the first sign of it, so the gap in the sound is as
    // short as the backend allows; the device list tends to change in bursts, so
    // it is looked at once more when the burst is over.
    m_outputSettle.setSingleShot(true);
    m_outputSettle.setInterval(150);
    connect(&m_outputSettle, &QTimer::timeout, this, &Player::followDefaultOutput);
    m_outputGrace.setSingleShot(true);
    m_outputGrace.setInterval(4000);
    m_outputCheck.setSingleShot(true);
    m_outputCheck.setInterval(500);
    connect(&m_outputCheck, &QTimer::timeout, this, &Player::recoverAfterOutputChange);
    connect(&m_devices, &QMediaDevices::audioOutputsChanged, this, [this]() {
        qCInfo(lcPlayer) << "audio outputs changed; default is"
                         << QMediaDevices::defaultAudioOutput().description();
        // Errors raised by the old device going away are not the track's fault.
        m_outputGrace.start();
        followDefaultOutput();
        m_outputSettle.start();
    });
    m_recoverStalls = !qEnvironmentVariableIsSet("WAVELANE_NO_RECOVER");
    m_watchdog.setInterval(1000);
    connect(&m_watchdog, &QTimer::timeout, this, &Player::checkStall);
    m_watchdog.start();
}

bool Player::playing() const
{
    return m_media.playbackState() == QMediaPlayer::PlayingState;
}

qint64 Player::duration() const
{
    // Before the stream header is parsed QMediaPlayer reports 0; the catalogue
    // duration keeps the seek bar sane until then.
    const qint64 reported = m_media.duration();
    return reported > 0 ? reported : m_current.durationMs;
}

int Player::volume() const
{
    return static_cast<int>(qRound(m_audio.volume() * 100.0f));
}

void Player::setVolume(int value)
{
    const int bounded = qBound(0, value, 100);
    if (bounded == volume())
        return;
    m_audio.setVolume(static_cast<float>(bounded) / 100.0f);
    if (m_settings)
        m_settings->setVolume(bounded);
    emit volumeChanged();
}

bool Player::muted() const
{
    return m_audio.isMuted();
}

void Player::setMuted(bool value)
{
    if (value == m_audio.isMuted())
        return;
    m_audio.setMuted(value);
    if (m_settings)
        m_settings->setMuted(value);
    emit mutedChanged();
}

void Player::play(const Track &track, const QString &context)
{
    if (!track.isValid())
        return;

    // Whatever was playing is being replaced: log it as a skip first.
    if (m_current.isValid() && m_current.id != track.id)
        reportAndClear(true);

    m_current = track;
    m_context = context;
    m_position = 0;
    m_maxPosition = 0;
    m_reported = false;
    m_nearEndEmitted = false;
    setErrorString({});
    emit currentTrackChanged();
    emit positionChanged();
    emit durationChanged();

    if (!track.streamUrl.isEmpty()) {
        // The wave hands out a tokenised URL with every pick.
        startUrl(m_api->resolve(track.streamUrl));
    } else {
        // Anything else needs a token of its own: QMediaPlayer fetches the URL
        // itself and will not attach an Authorization header.
        requestStreamToken(track);
    }
}

void Player::requestStreamToken(const Track &track)
{
    setBuffering(true);
    const QString trackId = track.id;

    m_api->get(QStringLiteral("/tracks/%1/stream-token").arg(trackId),
               [this, trackId](const ApiClient::Response &response) {
                   // The user may have moved on while this was in flight.
                   if (m_current.id != trackId)
                       return;

                   if (!response.ok()) {
                       setBuffering(false);
                       setErrorString(response.error.isEmpty()
                                          ? tr("Could not start playback")
                                          : response.error);
                       emit playbackFailed(m_errorString);
                       return;
                   }

                   const QString url = response.object.value(QStringLiteral("url")).toString();
                   if (url.isEmpty()) {
                       setBuffering(false);
                       setErrorString(tr("The server did not return a stream URL"));
                       emit playbackFailed(m_errorString);
                       return;
                   }
                   startUrl(m_api->resolve(url));
               });
}

void Player::startUrl(const QUrl &url)
{
    m_currentUrl = url;
    m_wantPlaying = true;
    m_stalledTicks = 0;
    m_recoveryStage = 0;
    m_watchPosition = -1;
    setBuffering(true);
    m_media.setSource(url);
    m_media.play();
}

void Player::togglePlayPause()
{
    if (!m_current.isValid())
        return;
    if (playing()) {
        m_wantPlaying = false;
        m_media.pause();
    } else {
        m_wantPlaying = true;
        m_media.play();
    }
}

void Player::pause()
{
    m_wantPlaying = false;
    m_media.pause();
}

void Player::resume()
{
    if (m_current.isValid()) {
        m_wantPlaying = true;
        m_media.play();
    }
}

void Player::stop()
{
    m_wantPlaying = false;
    reportAndClear(true);
    m_media.stop();
    m_media.setSource(QUrl());
    m_tap->reset();
}

void Player::seek(qint64 milliseconds)
{
    if (!m_current.isValid())
        return;
    const qint64 target = qBound<qint64>(0, milliseconds, duration());
    m_media.setPosition(target);
    emit seeked(target);
}

void Player::seekFraction(double fraction)
{
    seek(static_cast<qint64>(qBound(0.0, fraction, 1.0) * static_cast<double>(duration())));
}

void Player::handlePositionChanged(qint64 position)
{
    m_position = position;
    m_maxPosition = qMax(m_maxPosition, position);
    emit positionChanged();

    const qint64 total = duration();
    if (!m_nearEndEmitted && total > 0 && total - position <= kNearEndMs) {
        m_nearEndEmitted = true;
        emit nearEnd(m_current.id);
    }
}

void Player::handleMediaStatus(QMediaPlayer::MediaStatus status)
{
    qCInfo(lcPlayer) << "status" << status << "state" << m_media.playbackState() << "pos"
                     << m_media.position() << "track" << m_current.title;
    switch (status) {
    case QMediaPlayer::LoadingMedia:
    case QMediaPlayer::StalledMedia:
        setBuffering(true);
        break;
    case QMediaPlayer::BufferedMedia:
    case QMediaPlayer::LoadedMedia:
        setBuffering(false);
        break;
    case QMediaPlayer::EndOfMedia: {
        setBuffering(false);
        const QString finishedId = m_current.id;
        if (m_current.isValid()) {
            reportPlay(m_current, duration() > 0 ? duration() : m_maxPosition, true, false);
            m_reported = true;
        }
        emit trackCompleted(finishedId);
        break;
    }
    case QMediaPlayer::InvalidMedia:
        setBuffering(false);
        setErrorString(tr("This track could not be played"));
        emit playbackFailed(m_errorString);
        break;
    default:
        break;
    }
}

void Player::handleError(QMediaPlayer::Error error, const QString &message)
{
    if (error == QMediaPlayer::NoError)
        return;

    if (m_outputGrace.isActive() && m_current.isValid()) {
        // The device the stream was going to just changed or vanished. Carry on
        // from the same place instead of reporting the track as broken.
        qCWarning(lcPlayer) << "error while the output changed, recovering:" << error << message;
        QTimer::singleShot(0, this, &Player::recoverAfterOutputChange);
        return;
    }
    setBuffering(false);
    setErrorString(message.isEmpty() ? tr("Playback error") : message);
    qCWarning(lcPlayer) << "playback error" << error << message;
    emit playbackFailed(m_errorString);
}

void Player::dropIfDeleted(const QStringList &trackIds)
{
    if (!m_current.isValid() || !trackIds.contains(m_current.id))
        return;
    // No play report: the server no longer has the track to report against.
    m_reported = true;
    m_media.stop();
    m_media.setSource(QUrl());
    m_current = Track();
    m_position = 0;
    m_maxPosition = 0;
    emit currentTrackChanged();
    emit positionChanged();
    emit durationChanged();
}

void Player::applyReaction(const QString &trackId, bool liked, bool disliked)
{
    if (!m_current.isValid() || m_current.id != trackId)
        return;
    m_current.liked = liked;
    m_current.disliked = disliked;
    emit currentTrackChanged();
}

void Player::applyLyricsKind(const QString &trackId, const QString &kind)
{
    if (!m_current.isValid() || m_current.id != trackId || m_current.lyricsKind == kind)
        return;
    m_current.lyricsKind = kind;
    emit currentTrackChanged();
}

void Player::reportAndClear(bool skipped)
{
    if (!m_current.isValid() || m_reported) {
        m_reported = true;
        return;
    }

    const qint64 played = m_maxPosition;
    const qint64 total = duration();
    const bool completed =
        total > 0 && static_cast<double>(played) / static_cast<double>(total)
                         >= kCompletionThreshold;

    reportPlay(m_current, played, completed, skipped && !completed);
    m_reported = true;
}

void Player::reportPlay(const Track &track, qint64 msPlayed, bool completed, bool skipped)
{
    if (!track.isValid() || msPlayed <= 0) {
        // Nothing was heard, so there is nothing to learn from.
        return;
    }

    QJsonObject body{
        {QStringLiteral("track_id"), track.id},
        {QStringLiteral("ms_played"), static_cast<double>(msPlayed)},
        {QStringLiteral("completed"), completed},
        {QStringLiteral("skipped"), skipped},
        {QStringLiteral("context_type"), m_context.isEmpty() ? QStringLiteral("unknown")
                                                             : m_context},
    };

    // Fire and forget: a failed report must never interrupt listening.
    m_api->post(QStringLiteral("/library/plays"), body,
                [](const ApiClient::Response &response) {
                    if (!response.ok())
                        qCWarning(lcPlayer) << "play report failed:" << response.error;
                });
}

void Player::checkStall()
{
    if (!playing() || !m_current.isValid()) {
        m_stalledTicks = 0;
        m_watchPosition = -1;
        return;
    }

    const qint64 position = m_media.position();
    qCInfo(lcPlayer) << "tick" << m_current.title << "pos" << position << "status"
                     << m_media.mediaStatus() << "buffer" << m_media.bufferProgress();

    if (position != m_watchPosition) {
        m_watchPosition = position;
        m_stalledTicks = 0;
        m_recoveryStage = 0;
        return;
    }

    if (++m_stalledTicks < 3)
        return;
    m_stalledTicks = 0;

    qCWarning(lcPlayer) << "STALL: position stuck at" << position << "status"
                        << m_media.mediaStatus() << "stage" << m_recoveryStage
                        << "track" << m_current.title;
    if (!m_recoverStalls)
        return;

    switch (m_recoveryStage++) {
    case 0:
        // Seeking is what frees it by hand, so try exactly that first.
        m_media.setPosition(position + 1);
        break;
    case 1:
        // Still stuck: start the stream over from where it was.
        m_media.setSource(m_currentUrl);
        m_media.setPosition(position);
        m_media.play();
        break;
    default:
        // Give up on this track rather than sit in silence.
        setErrorString(tr("Трек перестал воспроизводиться"));
        emit playbackFailed(m_errorString);
        break;
    }
}

void Player::followDefaultOutput()
{
    const QAudioDevice target = QMediaDevices::defaultAudioOutput();
    if (target.isNull()) {
        // Nothing to play to for now; the next change of the device list retries.
        qCWarning(lcPlayer) << "no audio output available";
        return;
    }

    if (target.id() != m_audio.device().id()) {
        qCInfo(lcPlayer) << "switching output to" << target.description() << "at"
                         << m_media.position();
        m_audio.setDevice(target);
    }

    // Give the backend a moment to move the stream, then make sure it is alive.
    m_outputCheck.start();
}

void Player::recoverAfterOutputChange()
{
    if (!m_wantPlaying || !m_current.isValid() || m_currentUrl.isEmpty())
        return;
    // A track that has simply ended is not something to bring back.
    if (m_media.mediaStatus() == QMediaPlayer::EndOfMedia)
        return;

    const bool alive = playing() && m_media.error() == QMediaPlayer::NoError
                       && m_media.mediaStatus() != QMediaPlayer::InvalidMedia;
    if (alive)
        return;

    qCWarning(lcPlayer) << "playback did not survive the output change; resuming at"
                        << m_position;
    const qint64 position = m_position;
    m_media.setSource(m_currentUrl);
    m_media.setPosition(position);
    m_media.play();
}

void Player::setBuffering(bool buffering)
{
    if (m_buffering == buffering)
        return;
    m_buffering = buffering;
    emit bufferingChanged();
}

void Player::setErrorString(const QString &message)
{
    if (m_errorString == message)
        return;
    m_errorString = message;
    emit errorStringChanged();
}

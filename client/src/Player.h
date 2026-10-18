#pragma once

#include "Track.h"

#include <QAudioOutput>
#include <QMediaPlayer>
#include <QObject>
#include <QVariantMap>
#include <qqmlintegration.h>

class ApiClient;
class Settings;

/*!
 * Playback, plus the listening report that trains the wave.
 *
 * The report matters as much as the audio: the server learns from how long a
 * track was actually played and whether it finished, so every track that stops
 * — finished, skipped, or replaced by another — has to produce exactly one
 * report with an accurate played time.
 */
class Player : public QObject
{
    Q_OBJECT
    QML_ANONYMOUS

    Q_PROPERTY(QVariantMap currentTrack READ currentTrack NOTIFY currentTrackChanged)
    Q_PROPERTY(bool hasTrack READ hasTrack NOTIFY currentTrackChanged)
    Q_PROPERTY(bool playing READ playing NOTIFY playingChanged)
    Q_PROPERTY(bool buffering READ buffering NOTIFY bufferingChanged)
    Q_PROPERTY(qint64 position READ position NOTIFY positionChanged)
    Q_PROPERTY(qint64 duration READ duration NOTIFY durationChanged)
    Q_PROPERTY(QString positionText READ positionText NOTIFY positionChanged)
    Q_PROPERTY(QString durationText READ durationText NOTIFY durationChanged)
    Q_PROPERTY(int volume READ volume WRITE setVolume NOTIFY volumeChanged)
    Q_PROPERTY(bool muted READ muted WRITE setMuted NOTIFY mutedChanged)
    Q_PROPERTY(QString errorString READ errorString NOTIFY errorStringChanged)
    //! Who started the current track ("wave", "liked", "search", ...).
    Q_PROPERTY(QString context READ context NOTIFY currentTrackChanged)

public:
    Player(ApiClient *api, Settings *settings, QObject *parent = nullptr);

    QVariantMap currentTrack() const { return m_current.toVariantMap(); }
    bool hasTrack() const { return m_current.isValid(); }
    QString currentTrackId() const { return m_current.id; }
    //! Who started the current track ("wave", "liked", "search", ...). Lets each
    //! controller advance only the playback it owns.
    QString context() const { return m_context; }
    bool playing() const;
    bool buffering() const { return m_buffering; }
    qint64 position() const { return m_position; }
    qint64 duration() const;
    QString positionText() const { return Track::formatMilliseconds(m_position); }
    QString durationText() const { return Track::formatMilliseconds(duration()); }
    int volume() const;
    bool muted() const;
    QString errorString() const { return m_errorString; }

    //! Start a track. `context` is reported to the server ("wave", "album", ...).
    void play(const Track &track, const QString &context);

    Q_INVOKABLE void togglePlayPause();
    Q_INVOKABLE void pause();
    Q_INVOKABLE void resume();
    Q_INVOKABLE void stop();
    Q_INVOKABLE void seek(qint64 milliseconds);
    Q_INVOKABLE void seekFraction(double fraction);
    void setVolume(int value);
    void setMuted(bool value);

    /*! Report the current track as abandoned and clear it.
     *
     *  Called before starting something else, so the listening log has one
     *  entry per track rather than losing the skip.
     */
    void reportAndClear(bool skipped);

    //! Keep the like/dislike flags of the playing track in step with the library.
    void applyReaction(const QString &trackId, bool liked, bool disliked);

signals:
    void currentTrackChanged();
    void playingChanged();
    void bufferingChanged();
    void positionChanged();
    void durationChanged();
    void volumeChanged();
    void mutedChanged();
    void errorStringChanged();

    //! The track played to its end; the queue should advance.
    void trackCompleted(const QString &trackId);
    //! Emitted once per track when about to run out, so the next batch can load.
    void nearEnd(const QString &trackId);
    void playbackFailed(const QString &message);

private:
    void handleMediaStatus(QMediaPlayer::MediaStatus status);
    void handlePositionChanged(qint64 position);
    void handleError(QMediaPlayer::Error error, const QString &message);
    void startUrl(const QUrl &url);
    void requestStreamToken(const Track &track);
    void reportPlay(const Track &track, qint64 msPlayed, bool completed, bool skipped);
    void setBuffering(bool buffering);
    void setErrorString(const QString &message);

    ApiClient *m_api = nullptr;
    Settings *m_settings = nullptr;
    QMediaPlayer m_media;
    QAudioOutput m_audio;

    Track m_current;
    QString m_context;
    qint64 m_position = 0;
    //! Highest position seen for the current track, so a seek back does not
    //! shrink the reported listening time.
    qint64 m_maxPosition = 0;
    bool m_buffering = false;
    bool m_reported = false;
    bool m_nearEndEmitted = false;
    bool m_autoPlayPending = false;
    QString m_errorString;
};

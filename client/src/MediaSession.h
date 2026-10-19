#pragma once

#include <QByteArray>
#include <QObject>
#include <QString>
#include <qqmlintegration.h>

#include <memory>

class ApiClient;
class Player;
class QTimer;
class QWindow;

/*!
 * Tells the operating system what is playing.
 *
 * On Windows this is the System Media Transport Controls: the panel that pops
 * up with the volume keys, the lock screen, and the media section of the
 * taskbar and quick settings. It shows the cover, title and artist, a progress
 * bar, and the play/pause/next buttons; the keyboard's media keys reach the
 * app through it as well. Without this, Windows only knows the app is making
 * sound.
 *
 * Other platforms have their own equivalent (MPRIS on Linux, the media session
 * on Android); this class is where those plug in. For now they get a no-op.
 */
class MediaSession : public QObject
{
    Q_OBJECT
    QML_ANONYMOUS

    //! Whether the system controls were set up successfully.
    Q_PROPERTY(bool active READ active NOTIFY activeChanged)

public:
    MediaSession(Player *player, ApiClient *api, QObject *parent = nullptr);
    ~MediaSession() override;

    //! Hook into the window's media controls. Call once the window exists.
    void attach(QWindow *window);
    bool active() const { return m_active; }

    //! On a phone: send the app to the background, keeping the music going. Elsewhere: nothing.
    Q_INVOKABLE void moveToBackground();

signals:
    void activeChanged();

    // Requests that came from outside the app: the panel, a media key, a headset.
    void playRequested();
    void pauseRequested();
    void nextRequested();
    void previousRequested();
    void seekRequested(qint64 positionMs);

private:
    void syncTrack();
    void syncState();
    void syncTimeline();
    void pushMetadata(bool withCover);
#ifdef Q_OS_ANDROID
    //! Hand the whole current state to the Android playback service.
    void pushAndroid();
#endif

    struct Impl;
    std::unique_ptr<Impl> m_impl;

    Player *m_player = nullptr;
    ApiClient *m_api = nullptr;
    QTimer *m_timelineTimer = nullptr;

    bool m_active = false;
    QString m_trackId;
    QString m_coverPath;
    QByteArray m_cover;
};

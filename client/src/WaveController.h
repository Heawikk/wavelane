#pragma once

#include "Track.h"
// Included rather than forward-declared: moc needs the complete type to
// build the metatype for the TrackListModel* properties below.
#include "TrackListModel.h"

#include <QObject>
#include <QString>
#include <qqmlintegration.h>

class ApiClient;
class Player;

/*!
 * Drives "Моя волна": an endless personalised stream.
 *
 * The queue is kept deliberately short and refilled as it drains, rather than
 * fetched far ahead. The server picks tracks from the taste profile as it
 * stands at that moment, so a long prefetched queue would keep playing choices
 * made before the listener's last like or dislike.
 */
class WaveController : public QObject
{
    Q_OBJECT
    QML_ANONYMOUS

    Q_PROPERTY(TrackListModel *queue READ queue CONSTANT)
    Q_PROPERTY(TrackListModel *history READ history CONSTANT)
    Q_PROPERTY(bool loading READ loading NOTIFY loadingChanged)
    Q_PROPERTY(bool started READ started NOTIFY startedChanged)
    Q_PROPERTY(QString statusMessage READ statusMessage NOTIFY statusMessageChanged)
    Q_PROPERTY(QString currentReason READ currentReason NOTIFY currentReasonChanged)

    Q_PROPERTY(QString mood READ mood NOTIFY settingsChanged)
    Q_PROPERTY(QString character READ character NOTIFY settingsChanged)
    Q_PROPERTY(QString language READ language NOTIFY settingsChanged)
    Q_PROPERTY(double diversity READ diversity NOTIFY settingsChanged)
    //! The taste profile as aligned text lines, for the console-style panel.
    Q_PROPERTY(QStringList profileLines READ profileLines NOTIFY profileChanged)

public:
    WaveController(ApiClient *api, Player *player, QObject *parent = nullptr);

    TrackListModel *queue() const { return m_queue; }
    TrackListModel *history() const { return m_history; }
    bool loading() const { return m_loading; }
    bool started() const { return m_started; }
    QString statusMessage() const { return m_statusMessage; }
    QString currentReason() const { return m_currentReason; }

    QString mood() const { return m_mood; }
    QString character() const { return m_character; }
    QString language() const { return m_language; }
    double diversity() const { return m_diversity; }
    QStringList profileLines() const { return m_profileLines; }

    //! Load the saved settings. Call once after signing in.
    Q_INVOKABLE void loadSettings();
    Q_INVOKABLE void refreshProfile();

    //! Mirror a like/dislike made elsewhere into the queue and history.
    void applyReaction(const QString &trackId, bool liked, bool disliked);

    //! Start (or restart) listening and begin playback.
    Q_INVOKABLE void start();
    Q_INVOKABLE void playNext();
    Q_INVOKABLE void like();
    Q_INVOKABLE void dislike();
    Q_INVOKABLE void banCurrentArtist();
    Q_INVOKABLE void reset();

    Q_INVOKABLE void setMood(const QString &mood);
    Q_INVOKABLE void setCharacter(const QString &character);
    Q_INVOKABLE void setLanguage(const QString &language);
    Q_INVOKABLE void setDiversity(double diversity);

    //! Called when the user signs out, so nothing leaks into the next session.
    void clear();

signals:
    void loadingChanged();
    void startedChanged();
    void statusMessageChanged();
    void currentReasonChanged();
    void settingsChanged();
    void profileChanged();
    void notify(const QString &message);

private:
    void fetchBatch(int count, bool autoplay, bool restart = false);
    void applySettings(const QJsonObject &object);
    void pushSettings(const QJsonObject &changes);
    void sendFeedback(const QString &kind, double completion = -1.0);
    void setLoading(bool loading);
    void setStatusMessage(const QString &message);
    void setCurrentReason(const QString &reason);
    void advance(bool autoplay);
    void ensureQueueDepth();
    static QString describeReason(const QJsonObject &reason);
    //! True when the player is currently playing a wave pick.
    bool ownsPlayback() const;

    ApiClient *m_api = nullptr;
    Player *m_player = nullptr;
    TrackListModel *m_queue = nullptr;
    TrackListModel *m_history = nullptr;

    bool m_loading = false;
    bool m_started = false;
    bool m_fetchInFlight = false;
    QString m_statusMessage;
    QString m_currentReason;

    QString m_mood = QStringLiteral("any");
    QString m_character = QStringLiteral("any");
    QString m_language = QStringLiteral("any");
    double m_diversity = 0.3;
    QStringList m_profileLines;
};

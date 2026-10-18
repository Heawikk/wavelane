#pragma once

#include <QByteArray>
#include <QElapsedTimer>
#include <QJsonObject>
#include <QLocalSocket>
#include <QObject>
#include <QString>
#include <QTimer>
#include <qqmlintegration.h>

class ApiClient;
class Player;
class Settings;

/*!
 * Shows what is playing in the user's Discord profile ("Listening to Wavelane").
 *
 * Discord's desktop app listens on a local pipe, and Rich Presence is a small
 * binary protocol over it: a handshake carrying the application id, then
 * "set activity" frames. No SDK is needed and nothing leaves the machine except
 * through Discord itself.
 *
 * The application id belongs to the user's own application on Discord's
 * developer portal, since the name Discord shows ("Wavelane") is that
 * application's name.
 */
class DiscordPresence : public QObject
{
    Q_OBJECT
    QML_ANONYMOUS

    //! A short, human-readable account of what is going on, for the settings page.
    Q_PROPERTY(QString status READ status NOTIFY statusChanged)
    Q_PROPERTY(bool connected READ connected NOTIFY statusChanged)

public:
    DiscordPresence(Player *player, ApiClient *api, Settings *settings, QObject *parent = nullptr);

    QString status() const { return m_status; }
    bool connected() const { return m_state == State::Ready; }

    //! Apply the current settings: connect, reconnect or disconnect as needed.
    Q_INVOKABLE void refresh();

signals:
    void statusChanged();

private:
    enum class State { Disabled, NoClientId, Searching, Connecting, Ready, Failed };

    void setState(State state, const QString &detail = {});
    void connectToDiscord();
    void tryPipe(int index);
    void scheduleRetry(int milliseconds);
    void closeConnection();

    void sendFrame(int opcode, const QJsonObject &payload);
    void onReadyRead();
    void handleFrame(int opcode, const QJsonObject &payload);

    void scheduleActivity();
    void sendActivity();
    QJsonObject buildActivity() const;
    QString coverUrl(const QString &coverPath) const;

    Player *m_player = nullptr;
    ApiClient *m_api = nullptr;
    Settings *m_settings = nullptr;

    QLocalSocket m_socket;
    QByteArray m_buffer;
    QTimer m_retryTimer;
    QTimer m_updateTimer;
    QElapsedTimer m_lastSent;

    State m_state = State::Disabled;
    QString m_status;
    int m_pipeIndex = 0;
    int m_firstPipe = 0;
    bool m_hadActivity = false;
    //! Set while this class is closing the socket itself, so that is not mistaken
    //! for Discord dropping the connection.
    bool m_closing = false;
};

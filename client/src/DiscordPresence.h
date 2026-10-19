#pragma once

#include <QByteArray>
#include <QElapsedTimer>
#include <QJsonObject>
#include <QLocalServer>
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
 * This class decides what the activity says. The conversation with Discord
 * itself is held by a helper process (see DiscordRelay), so that the presence
 * is taken down whenever the client goes away, however it goes.
 *
 * The application on Discord's side is Wavelane's own, so its id is a constant
 * and the only choice left to the user is whether to show anything at all.
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
    ~DiscordPresence() override;

    QString status() const { return m_status; }
    bool connected() const { return m_state == State::Ready; }

    //! Apply the current settings: start or stop showing the presence.
    Q_INVOKABLE void refresh();

signals:
    void statusChanged();

private:
    enum class State { Disabled, Starting, Searching, Connecting, Ready, Failed };

    void setState(State state, const QString &detail = {});
    void startRelay();
    void stopRelay();
    void onRelayConnected();
    void onRelayData();
    void scheduleRespawn(int milliseconds);

    void send(const QJsonObject &message);
    void scheduleActivity();
    void sendActivity();
    QJsonObject buildActivity() const;
    QString coverBase() const;
    QString coverUrl(const QString &coverPath) const;

    Player *m_player = nullptr;
    ApiClient *m_api = nullptr;
    Settings *m_settings = nullptr;

    QLocalServer m_server;
    QLocalSocket *m_relay = nullptr;
    QByteArray m_inbox;
    QTimer m_respawnTimer;
    //! Waiting for a helper that was launched to connect.
    QTimer m_launchTimer;
    QTimer m_updateTimer;
    QElapsedTimer m_lastSent;

    State m_state = State::Disabled;
    QString m_status;
    bool m_hadActivity = false;
};

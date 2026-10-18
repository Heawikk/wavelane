#pragma once

#include <QObject>
#include <QSettings>
#include <QString>

/*!
 * Persistent client settings: which server to talk to, the saved session and
 * playback preferences.
 *
 * The refresh token is kept in QSettings, which on Windows means the registry
 * under the current user. That is the usual place for a desktop app to keep a
 * session, but it is not encrypted, so a local attacker who already has the
 * user's account can read it. Treat it as "remember me", not as a secret.
 */
class Settings : public QObject
{
    Q_OBJECT

    Q_PROPERTY(QString serverUrl READ serverUrl WRITE setServerUrl NOTIFY serverUrlChanged)
    Q_PROPERTY(int volume READ volume WRITE setVolume NOTIFY volumeChanged)
    Q_PROPERTY(bool muted READ muted WRITE setMuted NOTIFY mutedChanged)
    // Discord Rich Presence. The application id comes from the user's own
    // Discord developer application, so it is a setting, not a constant.
    Q_PROPERTY(bool discordEnabled READ discordEnabled WRITE setDiscordEnabled NOTIFY discordChanged)
    Q_PROPERTY(QString discordClientId READ discordClientId WRITE setDiscordClientId NOTIFY discordChanged)
    Q_PROPERTY(QString discordCoverBase READ discordCoverBase WRITE setDiscordCoverBase NOTIFY discordChanged)

public:
    explicit Settings(QObject *parent = nullptr);

    QString serverUrl() const;
    void setServerUrl(const QString &url);

    int volume() const;
    void setVolume(int value);

    bool muted() const;
    void setMuted(bool value);

    bool discordEnabled() const;
    void setDiscordEnabled(bool value);
    QString discordClientId() const;
    void setDiscordClientId(const QString &id);
    //! Public address of the server, so Discord can fetch covers. Empty if there is none.
    QString discordCoverBase() const;
    void setDiscordCoverBase(const QString &url);

    QString refreshToken() const;
    void setRefreshToken(const QString &token);

    QString lastLogin() const;
    void setLastLogin(const QString &login);

    QString deviceName() const;

    Q_INVOKABLE void clearSession();

signals:
    void serverUrlChanged();
    void volumeChanged();
    void mutedChanged();
    void discordChanged();

private:
    QSettings m_store;
};

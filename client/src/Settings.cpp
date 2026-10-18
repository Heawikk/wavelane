#include "Settings.h"

#include <QHostInfo>

namespace {
constexpr auto kServerUrl = "server/url";
constexpr auto kRefreshToken = "session/refreshToken";
constexpr auto kLastLogin = "session/lastLogin";
constexpr auto kVolume = "playback/volume";
constexpr auto kMuted = "playback/muted";
constexpr auto kDiscordEnabled = "discord/enabled";
constexpr auto kDiscordClientId = "discord/clientId";
constexpr auto kDiscordCoverBase = "discord/coverBase";
constexpr auto kDefaultServer = "http://127.0.0.1:8000";
} // namespace

Settings::Settings(QObject *parent)
    : QObject(parent)
    , m_store(QStringLiteral("Wavelane"), QStringLiteral("Client"))
{
}

QString Settings::serverUrl() const
{
    return m_store.value(kServerUrl, QString::fromLatin1(kDefaultServer)).toString();
}

void Settings::setServerUrl(const QString &url)
{
    QString trimmed = url.trimmed();
    while (trimmed.endsWith(QLatin1Char('/')))
        trimmed.chop(1);
    if (trimmed.isEmpty() || trimmed == serverUrl())
        return;
    m_store.setValue(kServerUrl, trimmed);
    emit serverUrlChanged();
}

int Settings::volume() const
{
    return qBound(0, m_store.value(kVolume, 80).toInt(), 100);
}

void Settings::setVolume(int value)
{
    const int bounded = qBound(0, value, 100);
    if (bounded == volume())
        return;
    m_store.setValue(kVolume, bounded);
    emit volumeChanged();
}

bool Settings::muted() const
{
    return m_store.value(kMuted, false).toBool();
}

void Settings::setMuted(bool value)
{
    if (value == muted())
        return;
    m_store.setValue(kMuted, value);
    emit mutedChanged();
}

bool Settings::discordEnabled() const
{
    return m_store.value(kDiscordEnabled, true).toBool();
}

void Settings::setDiscordEnabled(bool value)
{
    if (value == discordEnabled())
        return;
    m_store.setValue(kDiscordEnabled, value);
    emit discordChanged();
}

QString Settings::discordClientId() const
{
    return m_store.value(kDiscordClientId).toString();
}

void Settings::setDiscordClientId(const QString &id)
{
    const QString trimmed = id.trimmed();
    if (trimmed == discordClientId())
        return;
    m_store.setValue(kDiscordClientId, trimmed);
    emit discordChanged();
}

QString Settings::discordCoverBase() const
{
    return m_store.value(kDiscordCoverBase).toString();
}

void Settings::setDiscordCoverBase(const QString &url)
{
    QString trimmed = url.trimmed();
    while (trimmed.endsWith(QLatin1Char('/')))
        trimmed.chop(1);
    if (trimmed == discordCoverBase())
        return;
    m_store.setValue(kDiscordCoverBase, trimmed);
    emit discordChanged();
}

QString Settings::refreshToken() const
{
    return m_store.value(kRefreshToken).toString();
}

void Settings::setRefreshToken(const QString &token)
{
    if (token.isEmpty())
        m_store.remove(kRefreshToken);
    else
        m_store.setValue(kRefreshToken, token);

    // Flushed immediately, unlike every other setting here. The server rotates
    // refresh tokens and treats a reused one as a leak, revoking the whole
    // chain. QSettings writes lazily, so a crash or a killed process would
    // leave the previous, already-spent token on disk — and the next start
    // would present it, get the session revoked, and look like a random
    // sign-out. Losing a remembered volume level to a crash is nothing; losing
    // the session is worth the sync.
    m_store.sync();
}

QString Settings::lastLogin() const
{
    return m_store.value(kLastLogin).toString();
}

void Settings::setLastLogin(const QString &login)
{
    m_store.setValue(kLastLogin, login);
}

QString Settings::deviceName() const
{
    const QString host = QHostInfo::localHostName();
    return host.isEmpty() ? QStringLiteral("Wavelane Desktop")
                          : QStringLiteral("Wavelane on %1").arg(host);
}

void Settings::clearSession()
{
    m_store.remove(kRefreshToken);
}

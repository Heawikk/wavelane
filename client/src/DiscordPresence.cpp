#include "DiscordPresence.h"

#include "ApiClient.h"
#include "DiscordRelay.h"
#include "Player.h"
#include "Settings.h"

#include <QCoreApplication>
#include <QDateTime>
#include <QDir>
#include <QHostAddress>
#include <QJsonDocument>
#include <QLoggingCategory>
#include <QProcess>
#include <QUrl>

#ifdef Q_OS_WIN
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

#include <vector>
#endif

Q_LOGGING_CATEGORY(lcDiscord, "wavelane.discord")

namespace {

//! Wavelane's application on Discord's developer portal. The name Discord shows
//! ("Listening to Wavelane") and the logo come from it.
constexpr auto kClientId = "1561320123837448242";

// Discord drops presence updates beyond about five per twenty seconds, so
// consecutive ones are kept at least this far apart.
constexpr qint64 kMinUpdateGapMs = 4000;
constexpr int kSettleMs = 1200;
// The shortest string Discord accepts for the text lines.
constexpr int kMinText = 2;
constexpr int kMaxText = 128;

//! The asset key of the logo, uploaded to the Discord application.
constexpr auto kFallbackImage = "wavelane";

QString clipped(QString text)
{
    text = text.trimmed();
    if (text.size() > kMaxText)
        text = text.left(kMaxText - 1) + QStringLiteral("…");
    // Discord rejects one-character lines outright, so pad rather than lose the update.
    while (text.size() < kMinText)
        text += QLatin1Char(' ');
    return text;
}

#ifdef Q_OS_WIN
/*!
    Start `program` so that it is not a child of this process.

    The helper has to survive the client being ended from the task manager, and
    "End task" takes a program's child processes with it. Giving the new process
    the shell as its parent keeps it out of that tree.
*/
bool launchApart(const QString &program, const QStringList &arguments)
{
    QString commandLine = QLatin1Char('"') + QDir::toNativeSeparators(program) + QLatin1Char('"');
    for (const QString &argument : arguments)
        commandLine += QLatin1Char(' ') + argument;
    std::wstring line = commandLine.toStdWString();

    DWORD shellPid = 0;
    if (const HWND shell = GetShellWindow())
        GetWindowThreadProcessId(shell, &shellPid);
    HANDLE parent = shellPid ? OpenProcess(PROCESS_CREATE_PROCESS, FALSE, shellPid) : nullptr;

    bool started = false;
    if (parent) {
        SIZE_T size = 0;
        InitializeProcThreadAttributeList(nullptr, 1, 0, &size);
        std::vector<char> storage(size);
        auto *attributes = reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(storage.data());
        if (InitializeProcThreadAttributeList(attributes, 1, 0, &size)) {
            if (UpdateProcThreadAttribute(attributes, 0, PROC_THREAD_ATTRIBUTE_PARENT_PROCESS,
                                          &parent, sizeof(parent), nullptr, nullptr)) {
                STARTUPINFOEXW startup{};
                startup.StartupInfo.cb = sizeof(startup);
                startup.lpAttributeList = attributes;
                PROCESS_INFORMATION process{};
                started = CreateProcessW(nullptr, line.data(), nullptr, nullptr, FALSE,
                                         EXTENDED_STARTUPINFO_PRESENT | DETACHED_PROCESS
                                             | CREATE_NEW_PROCESS_GROUP,
                                         nullptr, nullptr, &startup.StartupInfo, &process);
                if (started) {
                    CloseHandle(process.hThread);
                    CloseHandle(process.hProcess);
                }
            }
            DeleteProcThreadAttributeList(attributes);
        }
        CloseHandle(parent);
    }
    if (started)
        return true;
    return QProcess::startDetached(program, arguments);
}
#else
bool launchApart(const QString &program, const QStringList &arguments)
{
    return QProcess::startDetached(program, arguments);
}
#endif

} // namespace

DiscordPresence::DiscordPresence(Player *player, ApiClient *api, Settings *settings,
                                 QObject *parent)
    : QObject(parent)
    , m_player(player)
    , m_api(api)
    , m_settings(settings)
{
    m_server.setSocketOptions(QLocalServer::UserAccessOption);
    connect(&m_server, &QLocalServer::newConnection, this, &DiscordPresence::onRelayConnected);

    m_respawnTimer.setSingleShot(true);
    connect(&m_respawnTimer, &QTimer::timeout, this, &DiscordPresence::startRelay);

    // A helper that never shows up (it could not start, or Windows refused) is replaced.
    m_launchTimer.setSingleShot(true);
    m_launchTimer.setInterval(10000);
    connect(&m_launchTimer, &QTimer::timeout, this, [this]() {
        qCWarning(lcDiscord) << "the Discord helper did not connect";
        setState(State::Failed, tr("Не удалось запустить помощника"));
        scheduleRespawn(30000);
    });

    m_updateTimer.setSingleShot(true);
    connect(&m_updateTimer, &QTimer::timeout, this, &DiscordPresence::sendActivity);

    // What is playing changes the presence; each of these only schedules an
    // update, and the timer folds a burst of them into one.
    connect(m_player, &Player::currentTrackChanged, this, &DiscordPresence::scheduleActivity);
    connect(m_player, &Player::playingChanged, this, &DiscordPresence::scheduleActivity);
    connect(m_player, &Player::seeked, this, &DiscordPresence::scheduleActivity);
    connect(m_player, &Player::durationChanged, this, &DiscordPresence::scheduleActivity);

    connect(m_settings, &Settings::discordChanged, this, &DiscordPresence::refresh);
    connect(m_settings, &Settings::serverUrlChanged, this, &DiscordPresence::scheduleActivity);

    // The helper notices the socket closing on its own; saying so first only makes it quicker.
    connect(qApp, &QCoreApplication::aboutToQuit, this, &DiscordPresence::stopRelay);

    m_lastSent.start();
    refresh();
}

DiscordPresence::~DiscordPresence()
{
    stopRelay();
}

void DiscordPresence::setState(State state, const QString &detail)
{
    m_state = state;
    switch (state) {
    case State::Disabled:
        m_status = tr("Выключено");
        break;
    case State::Starting:
        m_status = tr("Запускаем…");
        break;
    case State::Searching:
        m_status = tr("Discord не найден — запустите его, я подключусь сам");
        break;
    case State::Connecting:
        m_status = tr("Подключаемся…");
        break;
    case State::Ready:
        m_status = tr("Подключено");
        break;
    case State::Failed:
        m_status = detail.isEmpty() ? tr("Ошибка") : detail;
        break;
    }
    emit statusChanged();
}

void DiscordPresence::refresh()
{
    if (!m_settings->discordEnabled()) {
        stopRelay();
        setState(State::Disabled);
        return;
    }
    if (!m_relay && !m_launchTimer.isActive())
        startRelay();
}

void DiscordPresence::startRelay()
{
    if (!m_settings->discordEnabled() || m_relay || m_launchTimer.isActive())
        return;

    const QString name = DiscordRelay::controlName(QCoreApplication::applicationPid());
    if (!m_server.isListening()) {
        QLocalServer::removeServer(name);
        if (!m_server.listen(name)) {
            qCWarning(lcDiscord) << "cannot listen for the Discord helper:" << m_server.errorString();
            setState(State::Failed, m_server.errorString());
            scheduleRespawn(30000);
            return;
        }
    }

    const QStringList arguments{QString::fromLatin1(DiscordRelay::kSwitch), name,
                                QString::fromLatin1(kClientId),
                                QString::number(QCoreApplication::applicationPid())};
    setState(State::Starting);
    if (!launchApart(QCoreApplication::applicationFilePath(), arguments)) {
        qCWarning(lcDiscord) << "cannot start the Discord helper";
        setState(State::Failed, tr("Не удалось запустить помощника"));
        scheduleRespawn(30000);
        return;
    }
    m_launchTimer.start();
}

void DiscordPresence::stopRelay()
{
    m_respawnTimer.stop();
    m_launchTimer.stop();
    m_updateTimer.stop();
    m_hadActivity = false;

    if (m_relay) {
        // Not a failure of the helper: take the handlers off before it hangs up.
        QLocalSocket *relay = m_relay;
        m_relay = nullptr;
        relay->disconnect(this);
        relay->write("{\"quit\":true}\n");
        relay->waitForBytesWritten(200);
        relay->disconnectFromServer();
        relay->deleteLater();
    }
    m_server.close();
}

void DiscordPresence::scheduleRespawn(int milliseconds)
{
    if (m_settings->discordEnabled())
        m_respawnTimer.start(milliseconds);
}

void DiscordPresence::onRelayConnected()
{
    QLocalSocket *socket = m_server.nextPendingConnection();
    if (!socket)
        return;
    if (m_relay) {
        // One helper at a time.
        socket->deleteLater();
        return;
    }

    m_launchTimer.stop();
    m_relay = socket;
    m_inbox.clear();
    m_hadActivity = false;
    connect(socket, &QLocalSocket::readyRead, this, &DiscordPresence::onRelayData);
    connect(socket, &QLocalSocket::disconnected, this, [this, socket]() {
        if (socket != m_relay)
            return;
        qCInfo(lcDiscord) << "the Discord helper went away";
        m_relay = nullptr;
        socket->deleteLater();
        if (m_settings->discordEnabled()) {
            setState(State::Starting);
            scheduleRespawn(3000);
        }
    });

    setState(State::Searching);
    // Whatever is playing right now goes out as soon as Discord is ready.
    sendActivity();
}

void DiscordPresence::onRelayData()
{
    if (!m_relay)
        return;
    m_inbox.append(m_relay->readAll());

    qsizetype end;
    while ((end = m_inbox.indexOf('\n')) >= 0) {
        const QJsonObject message = QJsonDocument::fromJson(m_inbox.left(end)).object();
        m_inbox.remove(0, end + 1);

        const QString state = message.value(QStringLiteral("state")).toString();
        if (state == QLatin1String("ready")) {
            setState(State::Ready);
            const QString user = message.value(QStringLiteral("user")).toString();
            if (!user.isEmpty()) {
                m_status = tr("Подключено · %1").arg(user);
                emit statusChanged();
            }
            // A new connection to Discord starts blank.
            m_hadActivity = false;
            sendActivity();
        } else if (state == QLatin1String("connecting")) {
            setState(State::Connecting);
        } else if (state == QLatin1String("failed")) {
            setState(State::Failed, message.value(QStringLiteral("detail")).toString());
        } else if (state == QLatin1String("searching")) {
            setState(State::Searching);
        }
    }
}

void DiscordPresence::send(const QJsonObject &message)
{
    if (!m_relay || m_relay->state() != QLocalSocket::ConnectedState)
        return;
    m_relay->write(QJsonDocument(message).toJson(QJsonDocument::Compact) + '\n');
}

QString DiscordPresence::coverBase() const
{
    // Discord fetches the picture itself, from its own servers, so the server has
    // to be reachable from the internet. One on this computer or in the home
    // network is not, and then the logo is shown instead.
    const QUrl url(m_settings->serverUrl());
    const QString host = url.host();
    if (host.isEmpty())
        return {};

    QHostAddress address;
    if (address.setAddress(host)) {
        const bool local =
            address.isLoopback() || address.isLinkLocal() || address.isUniqueLocalUnicast()
            || address.isInSubnet(QHostAddress(QStringLiteral("10.0.0.0")), 8)
            || address.isInSubnet(QHostAddress(QStringLiteral("172.16.0.0")), 12)
            || address.isInSubnet(QHostAddress(QStringLiteral("192.168.0.0")), 16)
            || address.isInSubnet(QHostAddress(QStringLiteral("100.64.0.0")), 10);
        if (local)
            return {};
    } else {
        static const QStringList privateSuffixes{QStringLiteral(".local"), QStringLiteral(".lan"),
                                                 QStringLiteral(".home"), QStringLiteral(".internal"),
                                                 QStringLiteral(".home.arpa")};
        if (!host.contains(QLatin1Char('.')))
            return {};
        for (const QString &suffix : privateSuffixes) {
            if (host.endsWith(suffix, Qt::CaseInsensitive))
                return {};
        }
    }

    QString base = url.scheme() + QStringLiteral("://") + host;
    if (url.port() > 0)
        base += QLatin1Char(':') + QString::number(url.port());
    return base;
}

QString DiscordPresence::coverUrl(const QString &coverPath) const
{
    const QString base = coverBase();
    if (coverPath.isEmpty() || base.isEmpty())
        return {};
    return base + QStringLiteral("/api/v1/covers/") + coverPath;
}

QJsonObject DiscordPresence::buildActivity() const
{
    const QVariantMap track = m_player->currentTrack();
    const QString title = track.value(QStringLiteral("title")).toString();
    const QString artist = track.value(QStringLiteral("artistName")).toString();
    const QString album = track.value(QStringLiteral("albumTitle")).toString();
    const bool playing = m_player->playing();

    QJsonObject activity;
    // 2 is "Listening", which is what turns the heading into "Listening to
    // Wavelane" and makes Discord draw a progress bar from the timestamps.
    activity.insert(QStringLiteral("type"), 2);
    activity.insert(QStringLiteral("details"), clipped(title));
    activity.insert(QStringLiteral("state"),
                    clipped(playing ? artist : (artist + tr(" · пауза"))));

    const qint64 duration = m_player->duration();
    if (playing && duration > 0) {
        const qint64 nowSeconds = QDateTime::currentSecsSinceEpoch();
        const qint64 start = nowSeconds - m_player->position() / 1000;
        activity.insert(QStringLiteral("timestamps"),
                        QJsonObject{{QStringLiteral("start"), start},
                                    {QStringLiteral("end"), start + duration / 1000}});
    }

    const QString cover = coverUrl(track.value(QStringLiteral("coverPath")).toString());
    QJsonObject assets;
    assets.insert(QStringLiteral("large_image"),
                  cover.isEmpty() ? QString::fromLatin1(kFallbackImage) : cover);
    assets.insert(QStringLiteral("large_text"),
                  clipped(album.isEmpty() ? QStringLiteral("Wavelane") : album));
    activity.insert(QStringLiteral("assets"), assets);
    return activity;
}

void DiscordPresence::scheduleActivity()
{
    if (!m_relay)
        return;
    // A burst of changes (a new track also changes duration, playing state and
    // so on) becomes one update, and updates never come faster than Discord allows.
    const qint64 sinceLast = m_lastSent.elapsed();
    const int wait = static_cast<int>(
        qMax<qint64>(kSettleMs, kMinUpdateGapMs - sinceLast));
    m_updateTimer.start(wait);
}

void DiscordPresence::sendActivity()
{
    if (!m_relay)
        return;

    if (m_player->hasTrack()) {
        send(QJsonObject{{QStringLiteral("activity"), buildActivity()}});
        m_hadActivity = true;
    } else if (m_hadActivity) {
        // Nothing is playing any more: take the presence down.
        send(QJsonObject{{QStringLiteral("clear"), true}});
        m_hadActivity = false;
    } else {
        return;
    }
    m_lastSent.restart();
}

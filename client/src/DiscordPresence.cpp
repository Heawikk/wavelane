#include "DiscordPresence.h"

#include "ApiClient.h"
#include "Player.h"
#include "Settings.h"

#include <QCoreApplication>
#include <QDateTime>
#include <QDir>
#include <QJsonDocument>
#include <QLoggingCategory>
#include <QStandardPaths>
#include <QUuid>

Q_LOGGING_CATEGORY(lcDiscord, "wavelane.discord")

namespace {

enum Opcode { Handshake = 0, Frame = 1, Close = 2, Ping = 3, Pong = 4 };

constexpr int kPipeCount = 10;
// Discord drops presence updates beyond about five per twenty seconds, so
// consecutive ones are kept at least this far apart.
constexpr qint64 kMinUpdateGapMs = 4000;
constexpr int kSettleMs = 1200;
// The shortest string Discord accepts for the text lines.
constexpr int kMinText = 2;
constexpr int kMaxText = 128;

//! The asset key of the logo, which the user uploads to their Discord application.
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

QString pipeName(int index)
{
    const QString name = QStringLiteral("discord-ipc-%1").arg(index);
#ifdef Q_OS_WIN
    return name;
#else
    // On Linux and macOS the pipe is a socket in the runtime directory.
    QString base = QStandardPaths::writableLocation(QStandardPaths::RuntimeLocation);
    if (base.isEmpty())
        base = QDir::tempPath();
    return QDir(base).filePath(name);
#endif
}

} // namespace

DiscordPresence::DiscordPresence(Player *player, ApiClient *api, Settings *settings,
                                 QObject *parent)
    : QObject(parent)
    , m_player(player)
    , m_api(api)
    , m_settings(settings)
{
    // Only for testing against a stand-in Discord on another pipe.
    bool ok = false;
    const int first = qEnvironmentVariableIntValue("WAVELANE_DISCORD_PIPE_START", &ok);
    m_firstPipe = ok ? qBound(0, first, kPipeCount - 1) : 0;

    m_retryTimer.setSingleShot(true);
    connect(&m_retryTimer, &QTimer::timeout, this, &DiscordPresence::connectToDiscord);

    m_updateTimer.setSingleShot(true);
    connect(&m_updateTimer, &QTimer::timeout, this, &DiscordPresence::sendActivity);

    connect(&m_socket, &QLocalSocket::readyRead, this, &DiscordPresence::onReadyRead);
    connect(&m_socket, &QLocalSocket::connected, this, [this]() {
        qCInfo(lcDiscord) << "connected to pipe" << m_pipeIndex;
        setState(State::Connecting);
        sendFrame(Handshake,
                  QJsonObject{{QStringLiteral("v"), 1},
                              {QStringLiteral("client_id"), m_settings->discordClientId()}});
    });
    connect(&m_socket, &QLocalSocket::errorOccurred, this,
            [this](QLocalSocket::LocalSocketError error) {
                if (m_closing)
                    return;
                if (m_state == State::Searching) {
                    // This pipe does not exist or is not Discord's: try the next one.
                    tryPipe(m_pipeIndex + 1);
                } else if (m_state == State::Connecting || m_state == State::Ready) {
                    qCInfo(lcDiscord) << "connection lost:" << error;
                    closeConnection();
                    setState(State::Searching);
                    scheduleRetry(8000);
                }
            });
    connect(&m_socket, &QLocalSocket::disconnected, this, [this]() {
        if (m_closing)
            return;
        if (m_state == State::Ready || m_state == State::Connecting) {
            qCInfo(lcDiscord) << "Discord closed the connection";
            setState(State::Searching);
            scheduleRetry(8000);
        }
    });

    // What is playing changes the presence; each of these only schedules an
    // update, and the timer folds a burst of them into one.
    connect(m_player, &Player::currentTrackChanged, this, &DiscordPresence::scheduleActivity);
    connect(m_player, &Player::playingChanged, this, &DiscordPresence::scheduleActivity);
    connect(m_player, &Player::seeked, this, &DiscordPresence::scheduleActivity);
    connect(m_player, &Player::durationChanged, this, &DiscordPresence::scheduleActivity);

    connect(m_settings, &Settings::discordChanged, this, &DiscordPresence::refresh);
    connect(m_settings, &Settings::serverUrlChanged, this, &DiscordPresence::scheduleActivity);

    m_lastSent.start();
    refresh();
}

void DiscordPresence::setState(State state, const QString &detail)
{
    m_state = state;
    switch (state) {
    case State::Disabled:
        m_status = tr("Выключено");
        break;
    case State::NoClientId:
        m_status = tr("Укажите Application ID");
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
    closeConnection();
    m_retryTimer.stop();

    if (!m_settings->discordEnabled()) {
        setState(State::Disabled);
        return;
    }
    if (m_settings->discordClientId().isEmpty()) {
        setState(State::NoClientId);
        return;
    }
    connectToDiscord();
}

void DiscordPresence::connectToDiscord()
{
    if (!m_settings->discordEnabled() || m_settings->discordClientId().isEmpty())
        return;
    setState(State::Searching);
    tryPipe(m_firstPipe);
}

void DiscordPresence::tryPipe(int index)
{
    if (index >= kPipeCount) {
        // Nothing answered. Discord may simply not be running yet.
        scheduleRetry(15000);
        return;
    }
    m_pipeIndex = index;
    m_buffer.clear();
    m_socket.abort();
    m_socket.connectToServer(pipeName(index));
}

void DiscordPresence::scheduleRetry(int milliseconds)
{
    if (m_settings->discordEnabled() && !m_settings->discordClientId().isEmpty())
        m_retryTimer.start(milliseconds);
}

void DiscordPresence::closeConnection()
{
    m_hadActivity = false;
    m_buffer.clear();
    if (m_socket.state() != QLocalSocket::UnconnectedState) {
        m_closing = true;
        m_socket.abort();
        m_closing = false;
    }
}

void DiscordPresence::sendFrame(int opcode, const QJsonObject &payload)
{
    if (m_socket.state() != QLocalSocket::ConnectedState)
        return;

    const QByteArray json = QJsonDocument(payload).toJson(QJsonDocument::Compact);
    QByteArray frame;
    frame.reserve(8 + json.size());
    // Both header fields are 32-bit little-endian, whatever the machine is.
    auto appendLe = [&frame](quint32 value) {
        for (int shift = 0; shift < 32; shift += 8)
            frame.append(static_cast<char>((value >> shift) & 0xFF));
    };
    appendLe(static_cast<quint32>(opcode));
    appendLe(static_cast<quint32>(json.size()));
    frame.append(json);
    m_socket.write(frame);
}

void DiscordPresence::onReadyRead()
{
    m_buffer.append(m_socket.readAll());

    while (m_buffer.size() >= 8) {
        auto readLe = [this](int offset) {
            quint32 value = 0;
            for (int i = 3; i >= 0; --i)
                value = (value << 8) | static_cast<quint8>(m_buffer.at(offset + i));
            return value;
        };
        const quint32 opcode = readLe(0);
        const quint32 length = readLe(4);
        if (length > 1024 * 1024) {
            // Not a frame we understand; drop the connection rather than guess.
            setState(State::Failed, tr("Неожиданный ответ Discord"));
            closeConnection();
            return;
        }
        if (m_buffer.size() < static_cast<qsizetype>(8 + length))
            return;

        const QByteArray body = m_buffer.mid(8, static_cast<qsizetype>(length));
        m_buffer.remove(0, static_cast<qsizetype>(8 + length));
        handleFrame(static_cast<int>(opcode), QJsonDocument::fromJson(body).object());
    }
}

void DiscordPresence::handleFrame(int opcode, const QJsonObject &payload)
{
    if (opcode == Ping) {
        sendFrame(Pong, payload);
        return;
    }

    if (opcode == Close) {
        const int code = payload.value(QStringLiteral("code")).toInt();
        const QString message = payload.value(QStringLiteral("message")).toString();
        qCWarning(lcDiscord) << "Discord closed the session:" << code << message;
        if (code == 4000) {
            // A wrong application id will not fix itself, so do not keep retrying.
            setState(State::Failed, tr("Неверный Application ID"));
            closeConnection();
        } else {
            setState(State::Failed, message.isEmpty() ? tr("Discord закрыл соединение") : message);
            closeConnection();
            scheduleRetry(30000);
        }
        return;
    }

    const QString event = payload.value(QStringLiteral("evt")).toString();
    if (event == QLatin1String("READY")) {
        const QString user = payload.value(QStringLiteral("data"))
                                 .toObject()
                                 .value(QStringLiteral("user"))
                                 .toObject()
                                 .value(QStringLiteral("username"))
                                 .toString();
        qCInfo(lcDiscord) << "ready, signed in as" << user;
        setState(State::Ready);
        if (!user.isEmpty()) {
            m_status = tr("Подключено · %1").arg(user);
            emit statusChanged();
        }
        m_hadActivity = false;
        scheduleActivity();
    } else if (event == QLatin1String("ERROR")) {
        const QJsonObject data = payload.value(QStringLiteral("data")).toObject();
        qCWarning(lcDiscord) << "Discord reported an error:" << data;
        const QString message = data.value(QStringLiteral("message")).toString();
        if (m_state != State::Ready)
            setState(State::Failed, message);
    }
}

QString DiscordPresence::coverUrl(const QString &coverPath) const
{
    // Discord fetches the picture itself, from its own servers, so it has to
    // be reachable from the internet. A server on 127.0.0.1 is not; in that
    // case the logo uploaded to the application is used instead.
    const QString base = m_settings->discordCoverBase();
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
    if (m_state != State::Ready)
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
    if (m_state != State::Ready)
        return;

    QJsonObject args{{QStringLiteral("pid"), static_cast<qint64>(QCoreApplication::applicationPid())}};

    if (m_player->hasTrack()) {
        args.insert(QStringLiteral("activity"), buildActivity());
        m_hadActivity = true;
    } else if (!m_hadActivity) {
        // Nothing playing and nothing shown: there is nothing to clear.
        return;
    } else {
        // Without an "activity" key the presence is cleared.
        m_hadActivity = false;
    }

    m_lastSent.restart();
    sendFrame(Frame,
              QJsonObject{{QStringLiteral("cmd"), QStringLiteral("SET_ACTIVITY")},
                          {QStringLiteral("args"), args},
                          {QStringLiteral("nonce"), QUuid::createUuid().toString(QUuid::WithoutBraces)}});
}

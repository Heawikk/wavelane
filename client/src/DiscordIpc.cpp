#include "DiscordIpc.h"

#include <QDir>
#include <QJsonDocument>
#include <QLoggingCategory>
#include <QStandardPaths>
#include <QUuid>

Q_LOGGING_CATEGORY(lcDiscordIpc, "wavelane.discord")

namespace {

enum Opcode { Handshake = 0, Frame = 1, Close = 2, Ping = 3, Pong = 4 };

constexpr int kPipeCount = 10;

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

DiscordIpc::DiscordIpc(const QString &clientId, qint64 pid, QObject *parent)
    : QObject(parent)
    , m_clientId(clientId)
    , m_pid(pid)
{
    // Only for testing against a stand-in Discord on another pipe.
    bool ok = false;
    const int first = qEnvironmentVariableIntValue("WAVELANE_DISCORD_PIPE_START", &ok);
    m_firstPipe = ok ? qBound(0, first, kPipeCount - 1) : 0;

    m_retryTimer.setSingleShot(true);
    connect(&m_retryTimer, &QTimer::timeout, this, &DiscordIpc::start);

    connect(&m_socket, &QLocalSocket::readyRead, this, &DiscordIpc::onReadyRead);
    connect(&m_socket, &QLocalSocket::connected, this, [this]() {
        qCInfo(lcDiscordIpc) << "connected to pipe" << m_pipeIndex;
        setState(State::Connecting);
        sendFrame(Handshake, QJsonObject{{QStringLiteral("v"), 1},
                                         {QStringLiteral("client_id"), m_clientId}});
    });
    connect(&m_socket, &QLocalSocket::errorOccurred, this,
            [this](QLocalSocket::LocalSocketError error) {
                if (m_closing || m_stopping)
                    return;
                if (m_state == State::Searching) {
                    // This pipe does not exist or is not Discord's: try the next one.
                    tryPipe(m_pipeIndex + 1);
                } else if (m_state == State::Connecting || m_state == State::Ready) {
                    qCInfo(lcDiscordIpc) << "connection lost:" << error;
                    closeConnection();
                    setState(State::Searching);
                    scheduleRetry(8000);
                }
            });
    connect(&m_socket, &QLocalSocket::disconnected, this, [this]() {
        if (m_closing || m_stopping)
            return;
        if (m_state == State::Ready || m_state == State::Connecting) {
            qCInfo(lcDiscordIpc) << "Discord closed the connection";
            m_shown = false;
            setState(State::Searching);
            scheduleRetry(8000);
        }
    });
}

void DiscordIpc::setState(State state, const QString &detail)
{
    if (m_state == state && m_detail == detail)
        return;
    m_state = state;
    m_detail = detail;
    emit stateChanged();
}

void DiscordIpc::start()
{
    if (m_stopping)
        return;
    setState(State::Searching);
    tryPipe(m_firstPipe);
}

void DiscordIpc::tryPipe(int index)
{
    if (index >= kPipeCount) {
        // Nothing answered. Discord may simply not be running yet.
        scheduleRetry(15000);
        return;
    }
    m_pipeIndex = index;
    m_buffer.clear();
    m_closing = true;
    m_socket.abort();
    m_closing = false;
    m_socket.connectToServer(pipeName(index));
}

void DiscordIpc::scheduleRetry(int milliseconds)
{
    if (!m_stopping)
        m_retryTimer.start(milliseconds);
}

void DiscordIpc::closeConnection()
{
    m_shown = false;
    m_buffer.clear();
    if (m_socket.state() != QLocalSocket::UnconnectedState) {
        m_closing = true;
        m_socket.abort();
        m_closing = false;
    }
}

void DiscordIpc::sendFrame(int opcode, const QJsonObject &payload)
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

void DiscordIpc::onReadyRead()
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
            closeConnection();
            setState(State::Failed, tr("Неожиданный ответ Discord"));
            scheduleRetry(30000);
            return;
        }
        if (m_buffer.size() < static_cast<qsizetype>(8 + length))
            return;

        const QByteArray body = m_buffer.mid(8, static_cast<qsizetype>(length));
        m_buffer.remove(0, static_cast<qsizetype>(8 + length));
        handleFrame(static_cast<int>(opcode), QJsonDocument::fromJson(body).object());
    }
}

void DiscordIpc::handleFrame(int opcode, const QJsonObject &payload)
{
    if (opcode == Ping) {
        sendFrame(Pong, payload);
        return;
    }

    if (opcode == Close) {
        const QString message = payload.value(QStringLiteral("message")).toString();
        qCWarning(lcDiscordIpc) << "Discord closed the session:"
                                << payload.value(QStringLiteral("code")).toInt() << message;
        closeConnection();
        setState(State::Failed, message.isEmpty() ? tr("Discord закрыл соединение") : message);
        scheduleRetry(30000);
        return;
    }

    const QString event = payload.value(QStringLiteral("evt")).toString();
    if (event == QLatin1String("READY")) {
        m_user = payload.value(QStringLiteral("data"))
                     .toObject()
                     .value(QStringLiteral("user"))
                     .toObject()
                     .value(QStringLiteral("username"))
                     .toString();
        qCInfo(lcDiscordIpc) << "ready, signed in as" << m_user;
        m_shown = false;
        setState(State::Ready);
        sendActivity();
    } else if (event == QLatin1String("ERROR")) {
        const QJsonObject data = payload.value(QStringLiteral("data")).toObject();
        qCWarning(lcDiscordIpc) << "Discord reported an error:" << data;
    }
}

void DiscordIpc::setActivity(const QJsonObject &activity)
{
    m_wanted = activity;
    sendActivity();
}

void DiscordIpc::sendActivity()
{
    if (m_state != State::Ready)
        return;

    QJsonObject args{{QStringLiteral("pid"), m_pid}};
    if (!m_wanted.isEmpty()) {
        args.insert(QStringLiteral("activity"), m_wanted);
        m_shown = true;
    } else if (!m_shown) {
        // Nothing shown and nothing wanted: there is nothing to clear.
        return;
    } else {
        // Without an "activity" key the presence is cleared.
        m_shown = false;
    }

    sendFrame(Frame, QJsonObject{{QStringLiteral("cmd"), QStringLiteral("SET_ACTIVITY")},
                                 {QStringLiteral("args"), args},
                                 {QStringLiteral("nonce"),
                                  QUuid::createUuid().toString(QUuid::WithoutBraces)}});
}

void DiscordIpc::shutdown()
{
    if (m_stopping)
        return;
    m_wanted = {};
    sendActivity();
    m_stopping = true;
    m_retryTimer.stop();

    if (m_socket.state() == QLocalSocket::ConnectedState) {
        // Let the clearing frame leave before the line is dropped.
        m_socket.waitForBytesWritten(500);
        m_socket.disconnectFromServer();
    } else {
        m_socket.abort();
    }
    emit finished();
}

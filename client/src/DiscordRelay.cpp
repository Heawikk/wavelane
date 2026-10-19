#include "DiscordRelay.h"

#include "DiscordIpc.h"

#include <QCoreApplication>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLocalSocket>
#include <QLoggingCategory>
#include <QTimer>

#ifdef Q_OS_WIN
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

Q_LOGGING_CATEGORY(lcRelay, "wavelane.discord.relay")

namespace DiscordRelay {

QString controlName(qint64 clientPid)
{
    return QStringLiteral("wavelane-discord-%1").arg(clientPid);
}

bool requested(int argc, char *argv[])
{
    return argc >= 5 && qstrcmp(argv[1], kSwitch) == 0;
}

namespace {

QString stateName(DiscordIpc::State state)
{
    switch (state) {
    case DiscordIpc::State::Searching:
        return QStringLiteral("searching");
    case DiscordIpc::State::Connecting:
        return QStringLiteral("connecting");
    case DiscordIpc::State::Ready:
        return QStringLiteral("ready");
    case DiscordIpc::State::Failed:
        return QStringLiteral("failed");
    }
    return QStringLiteral("searching");
}

} // namespace

int run(int argc, char *argv[])
{
    QCoreApplication app(argc, argv);

    // wavelane --discord-relay <control socket> <application id> <client pid>
    const QStringList args = app.arguments();
    const QString controlSocket = args.value(2);
    const QString clientId = args.value(3);
    const qint64 clientPid = args.value(4).toLongLong();

    DiscordIpc ipc(clientId, clientPid);
    QLocalSocket control;
    bool finishing = false;

    // Clear the presence, hang up and leave. Whatever the reason, this is the one way out.
    auto finish = [&]() {
        if (finishing)
            return;
        finishing = true;
        qCInfo(lcRelay) << "clearing the presence and leaving";
        ipc.shutdown();
        QTimer::singleShot(0, &app, &QCoreApplication::quit);
    };

    // Never outlive the client, even if its end of the socket somehow stays open.
#ifdef Q_OS_WIN
    HANDLE client = OpenProcess(SYNCHRONIZE, FALSE, static_cast<DWORD>(clientPid));
    if (!client) {
        qCWarning(lcRelay) << "the client is already gone";
        return 0;
    }
    QTimer watch;
    watch.setInterval(2000);
    QObject::connect(&watch, &QTimer::timeout, &app, [&]() {
        if (WaitForSingleObject(client, 0) != WAIT_TIMEOUT)
            finish();
    });
    watch.start();
#endif

    QObject::connect(&control, &QLocalSocket::disconnected, &app, finish);
    QObject::connect(&control, &QLocalSocket::errorOccurred, &app, [&]() {
        if (control.state() != QLocalSocket::ConnectedState)
            finish();
    });

    auto report = [&]() {
        if (control.state() != QLocalSocket::ConnectedState)
            return;
        const QJsonObject message{{QStringLiteral("state"), stateName(ipc.state())},
                                  {QStringLiteral("user"), ipc.user()},
                                  {QStringLiteral("detail"), ipc.detail()}};
        control.write(QJsonDocument(message).toJson(QJsonDocument::Compact) + '\n');
    };
    QObject::connect(&ipc, &DiscordIpc::stateChanged, &app, report);

    QByteArray inbox;
    QObject::connect(&control, &QLocalSocket::readyRead, &app, [&]() {
        inbox.append(control.readAll());
        qsizetype end;
        while ((end = inbox.indexOf('\n')) >= 0) {
            const QJsonObject message = QJsonDocument::fromJson(inbox.left(end)).object();
            inbox.remove(0, end + 1);
            if (message.contains(QStringLiteral("activity")))
                ipc.setActivity(message.value(QStringLiteral("activity")).toObject());
            else if (message.value(QStringLiteral("clear")).toBool())
                ipc.setActivity({});
            else if (message.value(QStringLiteral("quit")).toBool())
                finish();
        }
    });

    QObject::connect(&control, &QLocalSocket::connected, &app, [&]() {
        ipc.start();
        report();
    });
    control.connectToServer(controlSocket);

    // A client that does not answer is not coming.
    QTimer::singleShot(8000, &app, [&]() {
        if (control.state() != QLocalSocket::ConnectedState)
            finish();
    });

    const int code = app.exec();
#ifdef Q_OS_WIN
    CloseHandle(client);
#endif
    return code;
}

} // namespace DiscordRelay

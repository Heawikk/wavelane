#include "ApiClient.h"
#include "AuthController.h"
#include "DiscordPresence.h"
#include "LibraryController.h"
#include "LyricsController.h"
#include "MediaSession.h"
#include "Player.h"
#include "Settings.h"
#include "WaveController.h"

#include <QCommandLineParser>
#include <QDateTime>
#include <QFile>
#include <QGuiApplication>
#include <QIcon>
#include <QLoggingCategory>
#include <QMutex>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickStyle>
#include <QWindow>
#include <QTextStream>

Q_LOGGING_CATEGORY(lcApp, "wavelane.app")

namespace {

/*!
    Mirror Qt's messages into a file when WAVELANE_LOG_FILE is set.

    A Windows GUI build has no console, so without this there is nowhere for a
    warning to go and a misbehaving install is undiagnosable.
*/
QFile g_logFile;
QMutex g_logMutex;
QtMessageHandler g_defaultHandler = nullptr;

void fileMessageHandler(QtMsgType type, const QMessageLogContext &context, const QString &message)
{
    if (g_defaultHandler)
        g_defaultHandler(type, context, message);

    QMutexLocker locker(&g_logMutex);
    if (!g_logFile.isOpen())
        return;

    static const char *levels[] = {"debug", "warning", "critical", "fatal", "info"};
    const int index = static_cast<int>(type);
    const char *level = index >= 0 && index < 5 ? levels[index] : "log";

    QTextStream stream(&g_logFile);
    stream << QDateTime::currentDateTime().toString(Qt::ISODate) << ' '
           << level << ' ' << context.category << ": " << message << Qt::endl;
}

void installFileLogging()
{
    const QString path = qEnvironmentVariable("WAVELANE_LOG_FILE");
    if (path.isEmpty())
        return;
    g_logFile.setFileName(path);
    if (g_logFile.open(QIODevice::WriteOnly | QIODevice::Append | QIODevice::Text))
        g_defaultHandler = qInstallMessageHandler(fileMessageHandler);
}

} // namespace

int main(int argc, char *argv[])
{
    installFileLogging();

    QGuiApplication app(argc, argv);

    QGuiApplication::setApplicationName(QStringLiteral("Wavelane"));
    QGuiApplication::setOrganizationName(QStringLiteral("Wavelane"));
    QGuiApplication::setApplicationVersion(QStringLiteral("0.1.0"));

    // The same mark as the logo in the app, at every size the shell may ask for.
    QIcon icon;
    for (const int size : {16, 24, 32, 48, 64, 128, 256})
        icon.addFile(QStringLiteral(":/icons/wavelane-%1.png").arg(size), QSize(size, size));
    QGuiApplication::setWindowIcon(icon);

    QCommandLineParser parser;
    parser.setApplicationDescription(
        QStringLiteral("Wavelane - personal music streaming client"));
    parser.addHelpOption();
    parser.addVersionOption();
    QCommandLineOption playWaveOption(
        {QStringLiteral("w"), QStringLiteral("wave")},
        QStringLiteral("Start playing the wave as soon as the session is restored."));
    parser.addOption(playWaveOption);
    QCommandLineOption serverOption(
        QStringLiteral("server"),
        QStringLiteral("Server URL to use instead of the stored one."),
        QStringLiteral("url"));
    parser.addOption(serverOption);
    parser.process(app);

    // Basic gives full control over appearance; the native styles override
    // colours and would fight the dark theme.
    QQuickStyle::setStyle(QStringLiteral("Basic"));

    Settings settings;
    if (parser.isSet(serverOption))
        settings.setServerUrl(parser.value(serverOption));

    ApiClient api(&settings);
    Player player(&api, &settings);
    AuthController auth(&api, &settings);
    WaveController wave(&api, &player);
    LibraryController library(&api, &player);
    LyricsController lyrics(&api, &player);
    MediaSession media(&player, &api);
    DiscordPresence discord(&player, &api, &settings);

    // A like made in any list must show up everywhere the track appears.
    QObject::connect(&library, &LibraryController::reactionChanged, &wave,
                     &WaveController::applyReaction);
    QObject::connect(&library, &LibraryController::reactionChanged, &player,
                     &Player::applyReaction);

    // Deleted tracks must vanish from the queue, the history and the player.
    QObject::connect(&library, &LibraryController::tracksDeleted, &wave,
                     &WaveController::removeTracks);
    QObject::connect(&library, &LibraryController::tracksDeleted, &player,
                     &Player::dropIfDeleted);

    // Signing out must not leave one account's queue visible to the next.
    QObject::connect(&auth, &AuthController::signedInChanged, [&]() {
        if (!auth.signedIn()) {
            player.stop();
            wave.clear();
            library.clear();
        }
    });

    QQmlApplicationEngine engine;
    QQmlContext *context = engine.rootContext();
    context->setContextProperty(QStringLiteral("app"), &settings);
    context->setContextProperty(QStringLiteral("api"), &api);
    context->setContextProperty(QStringLiteral("auth"), &auth);
    context->setContextProperty(QStringLiteral("player"), &player);
    context->setContextProperty(QStringLiteral("wave"), &wave);
    context->setContextProperty(QStringLiteral("library"), &library);
    context->setContextProperty(QStringLiteral("lyrics"), &lyrics);
    context->setContextProperty(QStringLiteral("media"), &media);
    context->setContextProperty(QStringLiteral("discord"), &discord);

    QObject::connect(&engine, &QQmlApplicationEngine::objectCreationFailed, &app,
                     []() { QCoreApplication::exit(-1); },
                     Qt::QueuedConnection);

    engine.loadFromModule("Wavelane", "Main");
    if (engine.rootObjects().isEmpty()) {
        qCCritical(lcApp) << "the QML scene failed to load";
        return -1;
    }

    qCInfo(lcApp) << "server" << api.baseUrl() << "stored session:" << api.hasSession();

    // Let the operating system show what is playing, and take its buttons.
    if (auto *window = qobject_cast<QWindow *>(engine.rootObjects().constFirst()))
        media.attach(window);
    QObject::connect(&media, &MediaSession::playRequested, &player, &Player::resume);
    QObject::connect(&media, &MediaSession::pauseRequested, &player, &Player::pause);
    QObject::connect(&media, &MediaSession::seekRequested, &player, &Player::seek);
    QObject::connect(&media, &MediaSession::nextRequested, &app, [&]() {
        // Same rule as the Next button: the wave owns its own queue.
        if (player.context() == QLatin1String("wave"))
            wave.playNext();
        else
            library.playNext();
    });

    if (parser.isSet(playWaveOption)) {
        // --wave: go straight into listening once the session is known good.
        QObject::connect(&auth, &AuthController::restoreFinished, &wave,
                         [&wave](bool success) {
                             if (success)
                                 wave.start();
                         });
    }

    // Try to resume a stored session before showing the login page.
    auth.restoreSession();

    return app.exec();
}

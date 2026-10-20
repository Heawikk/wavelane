#include "UpdateController.h"

#include <QCoreApplication>
#include <QCryptographicHash>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QGuiApplication>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLoggingCategory>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QProcess>
#include <QStandardPaths>
#include <QVersionNumber>

#ifdef Q_OS_ANDROID
#include <QJniObject>
#endif

Q_LOGGING_CATEGORY(lcUpdate, "wavelane.update")

#ifndef WAVELANE_UPDATE_REPO
#define WAVELANE_UPDATE_REPO "Heawikk/wavelane"
#endif

namespace {

constexpr int kTransferTimeoutMs = 30000;

//! The release file this platform installs; one per release.
bool matchesPlatform(const QString &name)
{
#if defined(Q_OS_ANDROID)
    return name.endsWith(QLatin1String(".apk"), Qt::CaseInsensitive);
#elif defined(Q_OS_WIN)
    return name.endsWith(QLatin1String("portable.zip"), Qt::CaseInsensitive);
#else
    Q_UNUSED(name)
    return false;
#endif
}

QString downloadDirectory()
{
#ifdef Q_OS_ANDROID
    // In the app's files, which the file provider handing it to the installer can reach.
    return QStandardPaths::writableLocation(QStandardPaths::AppDataLocation)
           + QStringLiteral("/updates");
#else
    return QStandardPaths::writableLocation(QStandardPaths::TempLocation)
           + QStringLiteral("/wavelane-update");
#endif
}

#ifdef Q_OS_WIN
// Runs after the app has closed: unpacks the new files over the old ones and starts it again.
// Kept to plain ASCII so the encoding of the file never matters.
constexpr auto kWindowsUpdateScript = R"(param($ProcessId, $Zip, $Target, $Exe)
$log = Join-Path $env:TEMP 'wavelane-update.log'
try {
    try { Wait-Process -Id $ProcessId -Timeout 60 } catch {}
    $stage = Join-Path $env:TEMP 'wavelane-update-stage'
    if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
    New-Item -ItemType Directory -Path $stage | Out-Null
    & tar.exe -xf $Zip -C $stage
    if ($LASTEXITCODE -ne 0) { throw 'could not unpack the update' }
    $root = Join-Path $stage 'Wavelane'
    if (-not (Test-Path (Join-Path $root $Exe))) { $root = $stage }
    $done = $false
    for ($attempt = 0; $attempt -lt 8 -and -not $done; $attempt++) {
        try {
            Copy-Item -Path (Join-Path $root '*') -Destination $Target -Recurse -Force -ErrorAction Stop
            $done = $true
        } catch {
            Start-Sleep -Seconds 1
            if ($attempt -eq 7) { throw }
        }
    }
    Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item $Zip -Force -ErrorAction SilentlyContinue
} catch {
    $_ | Out-String | Add-Content -Path $log
}
Start-Process -FilePath (Join-Path $Target $Exe)
)";
#endif

} // namespace

UpdateController::UpdateController(QObject *parent)
    : QObject(parent)
{
    m_network.setTransferTimeout(kTransferTimeoutMs);
}

bool UpdateController::isNewer(const QString &candidate, const QString &current)
{
    auto parse = [](QString text) {
        if (text.startsWith(QLatin1Char('v'), Qt::CaseInsensitive))
            text.remove(0, 1);
        qsizetype end = 0;
        return QVersionNumber::fromString(text, &end);
    };
    const QVersionNumber a = parse(candidate);
    const QVersionNumber b = parse(current);
    return !a.isNull() && QVersionNumber::compare(a, b) > 0;
}

void UpdateController::setState(const QString &state, const QString &message)
{
    m_state = state;
    m_message = message;
    emit stateChanged();
}

void UpdateController::check()
{
    if (m_state == QLatin1String("checking") || m_state == QLatin1String("downloading")
        || m_state == QLatin1String("installing"))
        return;

    setState(QStringLiteral("checking"));

    QNetworkRequest request(QUrl(QStringLiteral("https://api.github.com/repos/%1/releases/latest")
                                     .arg(QLatin1String(WAVELANE_UPDATE_REPO))));
    request.setRawHeader("Accept", "application/vnd.github+json");
    request.setRawHeader("User-Agent", "Wavelane/" + QGuiApplication::applicationVersion().toUtf8());
    QNetworkReply *reply = m_network.get(request);
    connect(reply, &QNetworkReply::finished, this, [this, reply]() { handleRelease(reply); });
}

void UpdateController::handleRelease(QNetworkReply *reply)
{
    reply->deleteLater();

    const int status = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
    if (status == 404) {
        // no release published yet: nothing newer than what is running
        setState(QStringLiteral("current"));
        return;
    }
    if (status == 0) {
        qCWarning(lcUpdate) << "could not reach GitHub:" << reply->error() << reply->errorString();
        setState(QStringLiteral("error"), tr("Нет соединения с GitHub"));
        return;
    }
    if (status != 200) {
        setState(QStringLiteral("error"), tr("GitHub ответил с ошибкой %1").arg(status));
        return;
    }

    const QJsonObject release = QJsonDocument::fromJson(reply->readAll()).object();
    QString tag = release.value(QStringLiteral("tag_name")).toString();
    if (tag.startsWith(QLatin1Char('v'), Qt::CaseInsensitive))
        tag.remove(0, 1);

    if (!isNewer(tag, QGuiApplication::applicationVersion())) {
        setState(QStringLiteral("current"));
        return;
    }

    m_assetUrl.clear();
    m_assetName.clear();
    m_assetDigest.clear();
    for (const QJsonValue &value : release.value(QStringLiteral("assets")).toArray()) {
        const QJsonObject asset = value.toObject();
        const QString name = asset.value(QStringLiteral("name")).toString();
        if (!matchesPlatform(name))
            continue;
        m_assetName = name;
        m_assetUrl = QUrl(asset.value(QStringLiteral("browser_download_url")).toString());
        m_assetDigest = asset.value(QStringLiteral("digest")).toString();
        break;
    }

    m_latest = tag;
    if (!m_assetUrl.isValid() || m_assetUrl.scheme() != QLatin1String("https")) {
        setState(QStringLiteral("error"),
                 tr("В версии %1 нет файла для этого устройства").arg(tag));
        return;
    }
    qCInfo(lcUpdate) << "update available:" << tag << m_assetName;
    setState(QStringLiteral("available"));
}

void UpdateController::install()
{
    if (m_state != QLatin1String("available") || !m_assetUrl.isValid())
        return;

    QDir().mkpath(downloadDirectory());
    const QString path = downloadDirectory() + QLatin1Char('/') + m_assetName;
    m_file = new QFile(path, this);
    if (!m_file->open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        delete m_file;
        m_file = nullptr;
        setState(QStringLiteral("error"), tr("Не удалось сохранить файл обновления"));
        return;
    }

    m_progress = 0.0;
    emit progressChanged();
    setState(QStringLiteral("downloading"));

    QNetworkRequest request(m_assetUrl);
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute,
                         QNetworkRequest::NoLessSafeRedirectPolicy);
    request.setRawHeader("User-Agent", "Wavelane/" + QGuiApplication::applicationVersion().toUtf8());
    m_reply = m_network.get(request);

    connect(m_reply, &QNetworkReply::readyRead, this, [this]() {
        if (m_file)
            m_file->write(m_reply->readAll());
    });
    connect(m_reply, &QNetworkReply::downloadProgress, this, [this](qint64 received, qint64 total) {
        const double value = total > 0 ? double(received) / double(total) : 0.0;
        if (qFuzzyCompare(value + 1.0, m_progress + 1.0))
            return;
        m_progress = value;
        emit progressChanged();
    });
    connect(m_reply, &QNetworkReply::finished, this, &UpdateController::handleDownloaded);
}

void UpdateController::failDownload(const QString &message)
{
    if (m_file) {
        const QString path = m_file->fileName();
        m_file->close();
        m_file->deleteLater();
        m_file = nullptr;
        QFile::remove(path);
    }
    setState(QStringLiteral("available"), message);
}

void UpdateController::handleDownloaded()
{
    QNetworkReply *reply = m_reply;
    m_reply = nullptr;
    reply->deleteLater();

    if (reply->error() != QNetworkReply::NoError) {
        failDownload(tr("Не удалось скачать обновление"));
        return;
    }
    m_file->write(reply->readAll());
    const QString path = m_file->fileName();
    m_file->close();
    m_file->deleteLater();
    m_file = nullptr;

    if (m_assetDigest.startsWith(QLatin1String("sha256:"))) {
        QFile file(path);
        QCryptographicHash hash(QCryptographicHash::Sha256);
        if (!file.open(QIODevice::ReadOnly) || !hash.addData(&file)
            || hash.result().toHex() != m_assetDigest.mid(7).toLatin1()) {
            QFile::remove(path);
            setState(QStringLiteral("available"), tr("Скачанный файл повреждён, попробуйте ещё раз"));
            return;
        }
    }
    applyDownloaded(path);
}

void UpdateController::applyDownloaded(const QString &path)
{
#if defined(Q_OS_ANDROID)
    // The system installer takes it from here, and ends this process when it replaces the app.
    const QJniObject context = QNativeInterface::QAndroidApplication::context();
    const jboolean opened = QJniObject::callStaticMethod<jboolean>(
        "ru/nrzx/wavelane/Updater", "install", "(Landroid/content/Context;Ljava/lang/String;)Z",
        context.object(), QJniObject::fromString(path).object<jstring>());
    if (!opened) {
        setState(QStringLiteral("available"),
                 tr("Разрешите Wavelane устанавливать приложения и нажмите «Обновить» ещё раз"));
        return;
    }
    setState(QStringLiteral("available"));
#elif defined(Q_OS_WIN)
    const QString scriptPath = downloadDirectory() + QStringLiteral("/apply-update.ps1");
    QFile script(scriptPath);
    if (!script.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        setState(QStringLiteral("available"), tr("Не удалось подготовить установку"));
        return;
    }
    script.write(kWindowsUpdateScript);
    script.close();

    setState(QStringLiteral("installing"));
    const QStringList arguments{
        QStringLiteral("-NoProfile"),
        QStringLiteral("-ExecutionPolicy"), QStringLiteral("Bypass"),
        QStringLiteral("-WindowStyle"), QStringLiteral("Hidden"),
        QStringLiteral("-File"), QDir::toNativeSeparators(scriptPath),
        QStringLiteral("-ProcessId"), QString::number(QCoreApplication::applicationPid()),
        QStringLiteral("-Zip"), QDir::toNativeSeparators(path),
        QStringLiteral("-Target"), QDir::toNativeSeparators(QCoreApplication::applicationDirPath()),
        QStringLiteral("-Exe"), QFileInfo(QCoreApplication::applicationFilePath()).fileName(),
    };
    if (!QProcess::startDetached(QStringLiteral("powershell.exe"), arguments)) {
        setState(QStringLiteral("available"), tr("Не удалось запустить установку"));
        return;
    }
    QCoreApplication::quit();
#else
    Q_UNUSED(path)
    setState(QStringLiteral("error"), tr("Обновление на этой системе не поддерживается"));
#endif
}

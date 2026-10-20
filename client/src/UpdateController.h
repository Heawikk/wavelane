#pragma once

#include <QNetworkAccessManager>
#include <QObject>
#include <QString>
#include <QUrl>
#include <qqmlintegration.h>

class QFile;
class QNetworkReply;

/*!
 * Looks for a newer release on GitHub and installs it.
 *
 * The release is the latest one of the repository named at build time (WAVELANE_UPDATE_REPO). On
 * Windows the portable zip is downloaded and a small script swaps the files once the app has
 * closed, then starts it again; on Android the .apk is handed to the system installer.
 */
class UpdateController : public QObject
{
    Q_OBJECT
    QML_ANONYMOUS

    //! idle, checking, current, available, downloading, installing, error
    Q_PROPERTY(QString state READ state NOTIFY stateChanged)
    Q_PROPERTY(QString latestVersion READ latestVersion NOTIFY stateChanged)
    //! A line to show next to the button: the reason of a failure, or what to do next.
    Q_PROPERTY(QString message READ message NOTIFY stateChanged)
    //! Download progress, 0..1.
    Q_PROPERTY(double progress READ progress NOTIFY progressChanged)

public:
    explicit UpdateController(QObject *parent = nullptr);

    QString state() const { return m_state; }
    QString latestVersion() const { return m_latest; }
    QString message() const { return m_message; }
    double progress() const { return m_progress; }

    Q_INVOKABLE void check();
    Q_INVOKABLE void install();

    //! True when `candidate` is a later release than `current` ("1.10.0" > "1.9.2").
    static bool isNewer(const QString &candidate, const QString &current);

signals:
    void stateChanged();
    void progressChanged();

private:
    void setState(const QString &state, const QString &message = {});
    void handleRelease(QNetworkReply *reply);
    void handleDownloaded();
    void failDownload(const QString &message);
    void applyDownloaded(const QString &path);

    QNetworkAccessManager m_network;
    QNetworkReply *m_reply = nullptr;
    QFile *m_file = nullptr;

    QString m_state = QStringLiteral("idle");
    QString m_latest;
    QString m_message;
    double m_progress = 0.0;

    QUrl m_assetUrl;
    QString m_assetName;
    QString m_assetDigest;   //!< "sha256:<hex>" as GitHub reports it; empty when it does not.
};

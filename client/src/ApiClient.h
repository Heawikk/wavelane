#pragma once

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QList>
#include <QNetworkAccessManager>
#include <QObject>
#include <QString>
#include <QTimer>
#include <QUrl>
#include <QUrlQuery>

#include <functional>

class Settings;

/*!
 * Everything that talks to the Wavelane server goes through here.
 *
 * Two things make this more than a thin wrapper around QNetworkAccessManager:
 *
 *  - **Transparent token refresh.** A request that comes back 401 is parked,
 *    the access token is renewed, and the request is replayed once. Callers
 *    never see the 401.
 *  - **Serialised refresh.** The server rotates refresh tokens and treats a
 *    reused one as a leak, revoking the entire chain. Two refreshes racing
 *    would therefore log the user out, so only one is ever in flight and
 *    everything else waits for it.
 */
class ApiClient : public QObject
{
    Q_OBJECT

    Q_PROPERTY(QString baseUrl READ baseUrl NOTIFY baseUrlChanged)
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    Q_PROPERTY(bool offline READ offline NOTIFY offlineChanged)

public:
    struct Response
    {
        int status = 0;
        QJsonObject object;
        QJsonArray array;
        QString error;      //!< Human-readable; empty on success.
        QByteArray raw;

        bool ok() const { return error.isEmpty() && status >= 200 && status < 300; }
    };

    using Callback = std::function<void(const Response &)>;

    explicit ApiClient(Settings *settings, QObject *parent = nullptr);

    QString baseUrl() const;
    bool busy() const { return m_inFlight > 0; }
    //! The last call got no answer at all (no connection, a timeout); the server is not reachable.
    bool offline() const { return m_offline; }

    void setAccessToken(const QString &token);
    void setRefreshToken(const QString &token);
    bool hasSession() const { return !m_refreshToken.isEmpty(); }

    /*! True when the server itself refused the credentials (401/403).
     *
     *  Anything else — no connection, a timeout, a 5xx while the server
     *  restarts — says nothing about whether the session is still good, so it
     *  must never be treated as a reason to throw the stored token away.
     */
    static bool isRejection(int status) { return status == 401 || status == 403; }
    void clearTokens();

    //! Absolute URL for an API path such as "/wave/next".
    QUrl resolve(const QString &path, const QUrlQuery &query = {}) const;

    //! Absolute URL for an image path returned by the API (no auth needed).
    Q_INVOKABLE QUrl coverUrl(const QString &relativePath) const;

    void get(const QString &path, const QUrlQuery &query, Callback callback);
    void get(const QString &path, Callback callback);
    void post(const QString &path, const QJsonObject &body, Callback callback);
    void put(const QString &path, const QJsonObject &body, Callback callback);
    void patch(const QString &path, const QJsonObject &body, Callback callback);
    void del(const QString &path, Callback callback);

    //! Download a public file (a cover) without credentials. Empty on failure.
    void fetchBytes(const QUrl &url, std::function<void(const QByteArray &)> callback);

    //! Multipart upload of local files to /upload.
    void uploadFiles(const QStringList &localPaths, Callback callback);

signals:
    void baseUrlChanged();
    void busyChanged();
    void offlineChanged();
    //! The server answered again after it had been out of reach.
    void reconnected();
    //! The session could not be renewed; the UI must return to the login page.
    void sessionExpired();
    void tokensRenewed(const QString &accessToken, const QString &refreshToken);

private:
    struct Request
    {
        QByteArray verb;
        QString path;
        QUrlQuery query;
        QJsonDocument body;
        Callback callback;
        bool replayed = false;
    };

    void send(Request request);
    void finish(QNetworkReply *reply, Request request);
    void beginRefresh();
    void failWaiting(const QString &reason, int status);
    void setOffline(bool offline);
    void probe();

    static Response parse(QNetworkReply *reply);
    static QString extractError(const Response &response, QNetworkReply *reply);

    Settings *m_settings = nullptr;
    QNetworkAccessManager m_network;
    QString m_accessToken;
    QString m_refreshToken;

    bool m_refreshing = false;
    QList<Request> m_waiting;   //!< Requests parked while the token is renewed.
    int m_inFlight = 0;

    bool m_offline = false;
    QTimer m_probeTimer;        //!< While offline, asks the server whether it is back.
    bool m_probing = false;
};

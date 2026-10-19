#include "ApiClient.h"
#include "Settings.h"

#include <QFile>
#include <QFileInfo>
#include <QHttpMultiPart>
#include <QJsonArray>
#include <QJsonParseError>
#include <QLoggingCategory>
#include <QMimeDatabase>
#include <QNetworkReply>

Q_LOGGING_CATEGORY(lcApi, "wavelane.api")

namespace {
constexpr auto kApiPrefix = "/api/v1";
constexpr int kTimeoutMs = 30000;
constexpr int kUploadTimeoutMs = 5 * 60 * 1000;
} // namespace

ApiClient::ApiClient(Settings *settings, QObject *parent)
    : QObject(parent)
    , m_settings(settings)
{
    m_network.setTransferTimeout(kTimeoutMs);
    if (m_settings) {
        m_refreshToken = m_settings->refreshToken();
        connect(m_settings, &Settings::serverUrlChanged, this, &ApiClient::baseUrlChanged);
    }
}

QString ApiClient::baseUrl() const
{
    return m_settings ? m_settings->serverUrl() : QString();
}

void ApiClient::setAccessToken(const QString &token)
{
    m_accessToken = token;
}

void ApiClient::setRefreshToken(const QString &token)
{
    m_refreshToken = token;
    if (m_settings)
        m_settings->setRefreshToken(token);
}

void ApiClient::clearTokens()
{
    m_accessToken.clear();
    m_refreshToken.clear();
    if (m_settings)
        m_settings->clearSession();
}

QUrl ApiClient::resolve(const QString &path, const QUrlQuery &query) const
{
    QString full = baseUrl();
    if (!path.startsWith(QLatin1String("/api/")) && !path.startsWith(QLatin1String("http")))
        full += QString::fromLatin1(kApiPrefix);
    full += path.startsWith(QLatin1Char('/')) ? path : QLatin1Char('/') + path;

    QUrl url(full);
    if (!query.isEmpty())
        url.setQuery(query);
    return url;
}

QUrl ApiClient::coverUrl(const QString &relativePath) const
{
    if (relativePath.isEmpty())
        return {};
    // Covers are content-addressed and served without authentication, so QML
    // can point an Image straight at the URL.
    return resolve(QStringLiteral("/covers/") + relativePath);
}

void ApiClient::get(const QString &path, const QUrlQuery &query, Callback callback)
{
    send({QByteArrayLiteral("GET"), path, query, {}, std::move(callback), false});
}

void ApiClient::get(const QString &path, Callback callback)
{
    get(path, QUrlQuery{}, std::move(callback));
}

void ApiClient::post(const QString &path, const QJsonObject &body, Callback callback)
{
    send({QByteArrayLiteral("POST"), path, {}, QJsonDocument(body), std::move(callback), false});
}

void ApiClient::put(const QString &path, const QJsonObject &body, Callback callback)
{
    send({QByteArrayLiteral("PUT"), path, {}, QJsonDocument(body), std::move(callback), false});
}

void ApiClient::patch(const QString &path, const QJsonObject &body, Callback callback)
{
    send({QByteArrayLiteral("PATCH"), path, {}, QJsonDocument(body), std::move(callback), false});
}

void ApiClient::del(const QString &path, Callback callback)
{
    send({QByteArrayLiteral("DELETE"), path, {}, {}, std::move(callback), false});
}

void ApiClient::send(Request request)
{
    // A refresh is in progress: park everything so the replay happens with the
    // new token, and so no second refresh is started.
    if (m_refreshing && request.path != QLatin1String("/auth/refresh")) {
        m_waiting.append(std::move(request));
        return;
    }

    QNetworkRequest networkRequest(resolve(request.path, request.query));
    networkRequest.setHeader(QNetworkRequest::ContentTypeHeader,
                             QStringLiteral("application/json"));
    networkRequest.setAttribute(QNetworkRequest::RedirectPolicyAttribute,
                                QNetworkRequest::NoLessSafeRedirectPolicy);
    if (!m_accessToken.isEmpty())
        networkRequest.setRawHeader(QByteArrayLiteral("Authorization"),
                                    QByteArrayLiteral("Bearer ") + m_accessToken.toUtf8());

    const QByteArray payload =
        request.body.isNull() ? QByteArray() : request.body.toJson(QJsonDocument::Compact);

    QNetworkReply *reply = nullptr;
    if (request.verb == "GET")
        reply = m_network.get(networkRequest);
    else if (request.verb == "DELETE")
        reply = m_network.deleteResource(networkRequest);
    else
        reply = m_network.sendCustomRequest(networkRequest, request.verb, payload);

    ++m_inFlight;
    emit busyChanged();

    connect(reply, &QNetworkReply::finished, this, [this, reply, request]() mutable {
        finish(reply, std::move(request));
    });
}

void ApiClient::finish(QNetworkReply *reply, Request request)
{
    reply->deleteLater();
    --m_inFlight;
    emit busyChanged();

    Response response = parse(reply);

    const bool isRefreshCall = request.path == QLatin1String("/auth/refresh");

    if (response.status == 401 && !request.replayed && !isRefreshCall
        && !m_refreshToken.isEmpty()) {
        // Park the request and renew the token; it will be replayed once.
        request.replayed = true;
        m_waiting.append(std::move(request));
        beginRefresh();
        return;
    }

    response.error = extractError(response, reply);

    if (response.status == 401 && !isRefreshCall && m_refreshToken.isEmpty())
        emit sessionExpired();

    if (request.callback)
        request.callback(response);
}

void ApiClient::beginRefresh()
{
    if (m_refreshing)
        return;
    m_refreshing = true;

    QJsonObject body{{QStringLiteral("refresh_token"), m_refreshToken}};

    // Sent directly rather than through send(), which would park it.
    Request refresh{QByteArrayLiteral("POST"), QStringLiteral("/auth/refresh"), {},
                    QJsonDocument(body), nullptr, true};

    refresh.callback = [this](const Response &response) {
        m_refreshing = false;

        if (!response.ok()) {
            qCWarning(lcApi) << "token refresh failed:" << response.status << response.error;

            if (isRejection(response.status)) {
                // The server looked at the token and refused it: it is spent,
                // revoked or expired, and keeping it would only fail again.
                clearTokens();
                failWaiting(QStringLiteral("session expired, please sign in again"),
                            response.status);
                emit sessionExpired();
            } else {
                // The server could not be reached, or was having a bad moment.
                // The token may be perfectly good, so keep it and let the
                // caller retry later. Wiping it here is what used to sign
                // people out whenever they started the app before the server.
                failWaiting(response.error.isEmpty() ? QStringLiteral("server unavailable")
                                                     : response.error,
                            response.status);
            }
            return;
        }

        const QString access = response.object.value(QStringLiteral("access_token")).toString();
        const QString rotated =
            response.object.value(QStringLiteral("refresh_token")).toString();
        setAccessToken(access);
        if (!rotated.isEmpty())
            setRefreshToken(rotated);
        emit tokensRenewed(access, rotated);

        // Replay everything that was waiting, now with a valid token.
        const QList<Request> pending = std::move(m_waiting);
        m_waiting.clear();
        for (const Request &item : pending)
            send(item);
    };

    send(std::move(refresh));
}

void ApiClient::failWaiting(const QString &reason, int status)
{
    const QList<Request> pending = std::move(m_waiting);
    m_waiting.clear();
    for (const Request &item : pending) {
        if (item.callback) {
            Response failure;
            // The real status, not a made-up 401: callers use it to decide
            // whether the session is dead or the server is merely away.
            failure.status = status;
            failure.error = reason;
            item.callback(failure);
        }
    }
}

void ApiClient::fetchBytes(const QUrl &url, std::function<void(const QByteArray &)> callback)
{
    QNetworkRequest request(url);
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute,
                         QNetworkRequest::NoLessSafeRedirectPolicy);
    QNetworkReply *reply = m_network.get(request);
    connect(reply, &QNetworkReply::finished, this, [reply, callback]() {
        reply->deleteLater();
        if (callback)
            callback(reply->error() == QNetworkReply::NoError ? reply->readAll() : QByteArray());
    });
}

void ApiClient::uploadFiles(const QStringList &localPaths, Callback callback)
{
    auto *multiPart = new QHttpMultiPart(QHttpMultiPart::FormDataType);
    QMimeDatabase mimeDatabase;
    int attached = 0;

    for (const QString &localPath : localPaths) {
        auto *file = new QFile(localPath);
        if (!file->open(QIODevice::ReadOnly)) {
            qCWarning(lcApi) << "cannot open for upload:" << localPath;
            delete file;
            continue;
        }

        const QFileInfo info(localPath);
        QHttpPart part;
        part.setHeader(QNetworkRequest::ContentDispositionHeader,
                       QVariant(QStringLiteral("form-data; name=\"files\"; filename=\"%1\"")
                                    .arg(info.fileName())));
        part.setHeader(QNetworkRequest::ContentTypeHeader,
                       QVariant(mimeDatabase.mimeTypeForFile(info).name()));
        part.setBodyDevice(file);
        // The multipart owns the file and closes it when the request is done.
        file->setParent(multiPart);
        multiPart->append(part);
        ++attached;
    }

    if (attached == 0) {
        delete multiPart;
        if (callback) {
            Response failure;
            failure.error = tr("none of the selected files could be read");
            callback(failure);
        }
        return;
    }

    QNetworkRequest request(resolve(QStringLiteral("/upload")));
    if (!m_accessToken.isEmpty())
        request.setRawHeader(QByteArrayLiteral("Authorization"),
                             QByteArrayLiteral("Bearer ") + m_accessToken.toUtf8());
    // Uploads can be large and the uplink slow. The timeout counts time without any bytes moving,
    // and a request-level 0 does not switch it off (the manager's 30 s then applies), so give it
    // a long explicit one.
    request.setTransferTimeout(kUploadTimeoutMs);

    QNetworkReply *reply = m_network.post(request, multiPart);
    multiPart->setParent(reply);

    ++m_inFlight;
    emit busyChanged();

    connect(reply, &QNetworkReply::finished, this, [this, reply, callback]() {
        reply->deleteLater();
        --m_inFlight;
        emit busyChanged();

        Response response = parse(reply);
        response.error = extractError(response, reply);
        if (callback)
            callback(response);
    });
}

ApiClient::Response ApiClient::parse(QNetworkReply *reply)
{
    Response response;
    response.status =
        reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
    response.raw = reply->readAll();

    if (response.raw.isEmpty())
        return response;

    QJsonParseError parseError{};
    const QJsonDocument document = QJsonDocument::fromJson(response.raw, &parseError);
    if (parseError.error != QJsonParseError::NoError)
        return response;

    if (document.isObject())
        response.object = document.object();
    else if (document.isArray())
        response.array = document.array();
    return response;
}

QString ApiClient::extractError(const Response &response, QNetworkReply *reply)
{
    if (response.status >= 200 && response.status < 300)
        return {};

    // FastAPI puts the message in "detail", which may itself be a list for
    // validation errors.
    const QJsonValue detail = response.object.value(QStringLiteral("detail"));
    if (detail.isString())
        return detail.toString();
    if (detail.isArray() && !detail.toArray().isEmpty()) {
        const QJsonValue first = detail.toArray().first();
        if (first.isObject()) {
            const QString message = first.toObject().value(QStringLiteral("msg")).toString();
            if (!message.isEmpty())
                return message;
        }
    }

    if (reply->error() != QNetworkReply::NoError)
        return reply->errorString();
    if (response.status != 0)
        return QObject::tr("server returned status %1").arg(response.status);
    return QObject::tr("unknown network error");
}

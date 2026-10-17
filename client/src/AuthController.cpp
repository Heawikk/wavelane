#include "AuthController.h"

#include "ApiClient.h"
#include "Settings.h"

#include <QJsonObject>

AuthController::AuthController(ApiClient *api, Settings *settings, QObject *parent)
    : QObject(parent)
    , m_api(api)
    , m_settings(settings)
{
    connect(m_api, &ApiClient::sessionExpired, this, &AuthController::handleSessionExpired);
}

QString AuthController::lastLogin() const
{
    return m_settings ? m_settings->lastLogin() : QString();
}

void AuthController::setBusy(bool busy)
{
    if (m_busy == busy)
        return;
    m_busy = busy;
    emit busyChanged();
}

void AuthController::setError(const QString &message)
{
    if (m_errorMessage == message)
        return;
    m_errorMessage = message;
    emit errorMessageChanged();
}

void AuthController::clearError()
{
    setError({});
}

void AuthController::applyTokens(const QString &accessToken, const QString &refreshToken)
{
    m_api->setAccessToken(accessToken);
    if (!refreshToken.isEmpty())
        m_api->setRefreshToken(refreshToken);
}

void AuthController::applyUser(const QJsonObject &user)
{
    m_displayName = user.value(QStringLiteral("display_name")).toString();
    m_username = user.value(QStringLiteral("username")).toString();
    m_isAdmin = user.value(QStringLiteral("is_admin")).toBool();
    if (m_settings && !m_username.isEmpty())
        m_settings->setLastLogin(m_username);
    emit userChanged();

    if (!m_signedIn) {
        m_signedIn = true;
        emit signedInChanged();
    }
}

void AuthController::signIn(const QString &login, const QString &password)
{
    if (login.trimmed().isEmpty() || password.isEmpty()) {
        setError(tr("Enter your login and password"));
        return;
    }

    setBusy(true);
    clearError();

    QJsonObject body{
        {QStringLiteral("login"), login.trimmed()},
        {QStringLiteral("password"), password},
        {QStringLiteral("device_name"), m_settings ? m_settings->deviceName() : QString()},
    };

    m_api->post(QStringLiteral("/auth/login"), body, [this](const ApiClient::Response &response) {
        setBusy(false);
        if (!response.ok()) {
            setError(response.error.isEmpty() ? tr("Could not sign in") : response.error);
            return;
        }
        applyTokens(response.object.value(QStringLiteral("access_token")).toString(),
                    response.object.value(QStringLiteral("refresh_token")).toString());
        applyUser(response.object.value(QStringLiteral("user")).toObject());
    });
}

void AuthController::signUp(const QString &email,
                            const QString &username,
                            const QString &password,
                            const QString &displayName)
{
    if (email.trimmed().isEmpty() || username.trimmed().isEmpty() || password.isEmpty()) {
        setError(tr("Fill in email, username and password"));
        return;
    }
    if (password.size() < 8) {
        setError(tr("The password must be at least 8 characters"));
        return;
    }

    setBusy(true);
    clearError();

    QJsonObject body{
        {QStringLiteral("email"), email.trimmed()},
        {QStringLiteral("username"), username.trimmed()},
        {QStringLiteral("password"), password},
    };
    if (!displayName.trimmed().isEmpty())
        body.insert(QStringLiteral("display_name"), displayName.trimmed());

    m_api->post(QStringLiteral("/auth/register"), body,
                [this](const ApiClient::Response &response) {
                    setBusy(false);
                    if (!response.ok()) {
                        setError(response.error.isEmpty() ? tr("Could not create the account")
                                                          : response.error);
                        return;
                    }
                    applyTokens(
                        response.object.value(QStringLiteral("access_token")).toString(),
                        response.object.value(QStringLiteral("refresh_token")).toString());
                    applyUser(response.object.value(QStringLiteral("user")).toObject());
                });
}

void AuthController::restoreSession()
{
    if (!m_api->hasSession()) {
        emit restoreFinished(false);
        return;
    }

    setBusy(true);

    // There is no stored access token, only a refresh token. Asking for the
    // profile with no credentials returns 401, which makes ApiClient renew the
    // session and replay the request — so this one call both refreshes and
    // tells us who we are.
    m_api->get(QStringLiteral("/auth/me"), [this](const ApiClient::Response &response) {
        setBusy(false);
        if (!response.ok()) {
            m_api->clearTokens();
            emit restoreFinished(false);
            return;
        }
        applyUser(response.object);
        emit restoreFinished(true);
    });
}

void AuthController::signOut()
{
    const QString refreshToken = m_settings ? m_settings->refreshToken() : QString();

    auto finish = [this]() {
        m_api->clearTokens();
        m_displayName.clear();
        m_username.clear();
        m_isAdmin = false;
        emit userChanged();
        if (m_signedIn) {
            m_signedIn = false;
            emit signedInChanged();
        }
    };

    if (refreshToken.isEmpty()) {
        finish();
        return;
    }

    QJsonObject body{{QStringLiteral("refresh_token"), refreshToken}};
    // Revoke server-side, then drop the local session either way: the user
    // asked to sign out, so a failed call must not leave them signed in.
    m_api->post(QStringLiteral("/auth/logout"), body,
                [finish](const ApiClient::Response &) { finish(); });
}

void AuthController::setServerUrl(const QString &url)
{
    if (!m_settings)
        return;
    m_settings->setServerUrl(url);
    clearError();
}

void AuthController::handleSessionExpired()
{
    if (!m_signedIn)
        return;
    m_signedIn = false;
    emit signedInChanged();
    setError(tr("The session expired, please sign in again"));
}

#pragma once

#include <QObject>
#include <QString>
#include <qqmlintegration.h>

class ApiClient;
class Settings;

/*! Sign-in, registration and the "am I signed in" state the UI switches on. */
class AuthController : public QObject
{
    Q_OBJECT
    QML_ANONYMOUS

    Q_PROPERTY(bool signedIn READ signedIn NOTIFY signedInChanged)
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    Q_PROPERTY(QString errorMessage READ errorMessage NOTIFY errorMessageChanged)
    Q_PROPERTY(QString displayName READ displayName NOTIFY userChanged)
    Q_PROPERTY(QString username READ username NOTIFY userChanged)
    Q_PROPERTY(bool isAdmin READ isAdmin NOTIFY userChanged)
    Q_PROPERTY(QString lastLogin READ lastLogin NOTIFY userChanged)

public:
    AuthController(ApiClient *api, Settings *settings, QObject *parent = nullptr);

    bool signedIn() const { return m_signedIn; }
    bool busy() const { return m_busy; }
    QString errorMessage() const { return m_errorMessage; }
    QString displayName() const { return m_displayName; }
    QString username() const { return m_username; }
    bool isAdmin() const { return m_isAdmin; }
    QString lastLogin() const;

    Q_INVOKABLE void signIn(const QString &login, const QString &password);
    Q_INVOKABLE void signUp(const QString &email,
                            const QString &username,
                            const QString &password,
                            const QString &displayName);
    Q_INVOKABLE void signOut();

    //! Try to resume a stored session on startup. Emits restoreFinished().
    Q_INVOKABLE void restoreSession();

    Q_INVOKABLE void setServerUrl(const QString &url);
    Q_INVOKABLE void clearError();

signals:
    void signedInChanged();
    void busyChanged();
    void errorMessageChanged();
    void userChanged();
    //! Startup check finished; `success` says whether a session was resumed.
    void restoreFinished(bool success);

private:
    void setBusy(bool busy);
    void setError(const QString &message);
    void applyTokens(const QString &accessToken, const QString &refreshToken);
    void applyUser(const QJsonObject &user);
    void handleSessionExpired();

    ApiClient *m_api = nullptr;
    Settings *m_settings = nullptr;

    bool m_signedIn = false;
    bool m_busy = false;
    QString m_errorMessage;
    QString m_displayName;
    QString m_username;
    bool m_isAdmin = false;
};

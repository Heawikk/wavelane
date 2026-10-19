#pragma once

#include <QObject>
#include <QString>
#include <QTimer>
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
    Q_PROPERTY(bool restoring READ restoring NOTIFY restoringChanged)
    Q_PROPERTY(QString errorMessage READ errorMessage NOTIFY errorMessageChanged)
    Q_PROPERTY(QString displayName READ displayName NOTIFY userChanged)
    Q_PROPERTY(QString username READ username NOTIFY userChanged)
    Q_PROPERTY(bool isAdmin READ isAdmin NOTIFY userChanged)
    Q_PROPERTY(QString lastLogin READ lastLogin NOTIFY userChanged)

public:
    AuthController(ApiClient *api, Settings *settings, QObject *parent = nullptr);

    bool signedIn() const { return m_signedIn; }
    bool busy() const { return m_busy; }
    //! The stored session is being checked at startup; the UI shows a splash meanwhile.
    bool restoring() const { return m_restoring; }
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
    void restoringChanged();
    void errorMessageChanged();
    void userChanged();
    //! The app was opened with the server out of reach and has now confirmed the stored
    //! session; whatever could not be loaded at the start has to be asked for again.
    void sessionResumed();
    //! Startup check finished; `success` says whether a session was resumed.
    void restoreFinished(bool success);

private:
    void setBusy(bool busy);
    void setRestoring(bool restoring);
    void setError(const QString &message);
    void applyTokens(const QString &accessToken, const QString &refreshToken);
    void applyUser(const QJsonObject &user);
    void handleSessionExpired();
    void checkStoredSession();

    ApiClient *m_api = nullptr;
    Settings *m_settings = nullptr;

    bool m_signedIn = false;
    bool m_busy = false;
    bool m_restoring = false;
    //! The app was let in on the strength of the stored session while the server was away.
    bool m_unconfirmed = false;
    bool m_checking = false;
    int m_epoch = 0;            //!< Bumped on sign-out so a late answer of an older check is ignored.
    QTimer m_retryTimer;
    QString m_errorMessage;
    QString m_displayName;
    QString m_username;
    bool m_isAdmin = false;
};

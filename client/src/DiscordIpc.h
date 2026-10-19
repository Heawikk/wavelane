#pragma once

#include <QByteArray>
#include <QJsonObject>
#include <QLocalSocket>
#include <QObject>
#include <QString>
#include <QTimer>

/*!
 * The conversation with Discord's desktop app, over the local pipe it listens on.
 *
 * Rich Presence is a small binary protocol: a handshake that names the
 * application, then "set activity" frames. No SDK is needed and nothing leaves
 * the machine except through Discord itself.
 *
 * It lives in its own class because it runs in a separate small process (see
 * DiscordRelay): Discord only forgets a presence when the connection that set
 * it says so, and a program that is killed cannot say anything.
 */
class DiscordIpc : public QObject
{
    Q_OBJECT

public:
    enum class State { Searching, Connecting, Ready, Failed };
    Q_ENUM(State)

    DiscordIpc(const QString &clientId, qint64 pid, QObject *parent = nullptr);

    State state() const { return m_state; }
    //! The Discord user the presence belongs to, once connected.
    QString user() const { return m_user; }
    //! Why it failed, in words.
    QString detail() const { return m_detail; }

    //! Begin looking for Discord, and keep looking until it is found.
    void start();

    //! Show this activity; an empty object clears it. Sent as soon as Discord is ready.
    void setActivity(const QJsonObject &activity);

    //! Clear what is shown and hang up. `finished` follows once it has gone out.
    void shutdown();

signals:
    void stateChanged();
    void finished();

private:
    void setState(State state, const QString &detail = {});
    void tryPipe(int index);
    void scheduleRetry(int milliseconds);
    void closeConnection();
    void sendFrame(int opcode, const QJsonObject &payload);
    void onReadyRead();
    void handleFrame(int opcode, const QJsonObject &payload);
    void sendActivity();

    QString m_clientId;
    qint64 m_pid = 0;

    QLocalSocket m_socket;
    QByteArray m_buffer;
    QTimer m_retryTimer;

    State m_state = State::Searching;
    QString m_user;
    QString m_detail;
    int m_pipeIndex = 0;
    int m_firstPipe = 0;

    //! What should be showing; empty means nothing.
    QJsonObject m_wanted;
    //! Whether Discord currently has something of ours on show.
    bool m_shown = false;
    bool m_stopping = false;
    //! Set while this class is closing the socket itself, so that is not mistaken
    //! for Discord dropping the connection.
    bool m_closing = false;
};

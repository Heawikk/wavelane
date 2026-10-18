#pragma once

#include <QHash>
#include <QJsonObject>
#include <QList>
#include <QObject>
#include <QString>
#include <QVariantList>
#include <qqmlintegration.h>

class ApiClient;
class Player;

/*!
 * The lyrics of the track that is playing, and the line that is being sung.
 *
 * Lyrics are fetched only while the lyrics view is open, so listeners who never
 * open it cost the server nothing. For synced lyrics `activeIndex` follows the
 * player's position; plain text and "no lyrics" are just states for the view.
 */
class LyricsController : public QObject
{
    Q_OBJECT
    QML_ANONYMOUS

    //! The lyrics view is open, so the current track's lyrics are wanted.
    Q_PROPERTY(bool active READ active WRITE setActive NOTIFY activeChanged)
    //! "idle", "loading", "none", "plain", "synced" or "error".
    Q_PROPERTY(QString state READ state NOTIFY stateChanged)
    //! [{ time: ms (-1 in plain text), text }, ...]
    Q_PROPERTY(QVariantList lines READ lines NOTIFY linesChanged)
    //! The line being sung, -1 before the first one; always -1 unless synced.
    Q_PROPERTY(int activeIndex READ activeIndex NOTIFY activeIndexChanged)
    //! The stored text, for administrators to edit; empty for everyone else.
    Q_PROPERTY(QString rawText READ rawText NOTIFY linesChanged)
    //! The track the lyrics above belong to.
    Q_PROPERTY(QString trackId READ trackId NOTIFY linesChanged)
    Q_PROPERTY(bool saving READ saving NOTIFY savingChanged)

public:
    LyricsController(ApiClient *api, Player *player, QObject *parent = nullptr);

    bool active() const { return m_active; }
    void setActive(bool active);
    QString state() const { return m_state; }
    QVariantList lines() const { return m_lines; }
    int activeIndex() const { return m_activeIndex; }
    QString rawText() const { return m_rawText; }
    QString trackId() const { return m_trackId; }
    bool saving() const { return m_saving; }

    Q_INVOKABLE void reload();
    //! Administrators: store `text` (plain, or LRC with [mm:ss.xx] tags) for a track.
    Q_INVOKABLE void save(const QString &trackId, const QString &text);
    Q_INVOKABLE void remove(const QString &trackId);

signals:
    void activeChanged();
    void stateChanged();
    void linesChanged();
    void activeIndexChanged();
    void savingChanged();
    void saved(const QString &trackId);
    void notify(const QString &message);

private:
    void load(const QString &trackId);
    void apply(const QString &trackId, const QJsonObject &body);
    void clearLines();
    void setState(const QString &state);
    void updateActive();
    void remember(const QString &trackId, const QJsonObject &body);
    void setSaving(bool saving);

    ApiClient *m_api = nullptr;
    Player *m_player = nullptr;

    bool m_active = false;
    bool m_saving = false;
    QString m_state = QStringLiteral("idle");
    QString m_trackId;
    QString m_rawText;
    QVariantList m_lines;
    //! The time of each line, for finding the current one by bisection.
    QList<qint64> m_times;
    int m_activeIndex = -1;
    //! Answers already fetched, so skipping back and forth costs no requests.
    QHash<QString, QJsonObject> m_cache;
};

#include "LyricsController.h"

#include "ApiClient.h"
#include "Player.h"

#include <QJsonArray>
#include <QLoggingCategory>
#include <QVariantMap>

#include <algorithm>

Q_LOGGING_CATEGORY(lcLyrics, "wavelane.lyrics")

namespace {
constexpr int kCacheLimit = 12;
}

LyricsController::LyricsController(ApiClient *api, Player *player, QObject *parent)
    : QObject(parent)
    , m_api(api)
    , m_player(player)
{
    connect(m_player, &Player::currentTrackChanged, this, [this]() {
        if (m_active)
            load(m_player->currentTrackId());
    });
    connect(m_player, &Player::positionChanged, this, &LyricsController::updateActive);
    connect(m_player, &Player::seeked, this, &LyricsController::updateActive);
}

void LyricsController::setActive(bool active)
{
    if (m_active == active)
        return;
    m_active = active;
    emit activeChanged();
    if (m_active && m_player->hasTrack()) {
        // Opening the view is when someone wants today's text: an administrator may
        // have changed it since it was last fetched.
        m_cache.remove(m_player->currentTrackId());
        load(m_player->currentTrackId());
    }
}

void LyricsController::reload()
{
    if (!m_player->hasTrack())
        return;
    m_cache.remove(m_player->currentTrackId());
    load(m_player->currentTrackId());
}

void LyricsController::clearLines()
{
    m_lines.clear();
    m_times.clear();
    m_rawText.clear();
}

void LyricsController::load(const QString &trackId)
{
    if (trackId.isEmpty()) {
        m_trackId.clear();
        clearLines();
        emit linesChanged();
        setState(QStringLiteral("idle"));
        updateActive();
        return;
    }

    const auto cached = m_cache.constFind(trackId);
    if (cached != m_cache.constEnd()) {
        apply(trackId, cached.value());
        return;
    }

    // Show "loading" rather than the previous song's words while the answer is on its way.
    m_trackId = trackId;
    clearLines();
    emit linesChanged();
    setState(QStringLiteral("loading"));
    updateActive();

    m_api->get(QStringLiteral("/tracks/%1/lyrics").arg(trackId),
               [this, trackId](const ApiClient::Response &response) {
                   // The listener may have moved on to another track meanwhile.
                   if (trackId != m_player->currentTrackId())
                       return;
                   if (!response.ok()) {
                       qCWarning(lcLyrics) << "could not load lyrics:" << response.error;
                       setState(QStringLiteral("error"));
                       return;
                   }
                   remember(trackId, response.object);
                   apply(trackId, response.object);
               });
}

void LyricsController::remember(const QString &trackId, const QJsonObject &body)
{
    if (m_cache.size() >= kCacheLimit && !m_cache.contains(trackId))
        m_cache.erase(m_cache.begin());
    m_cache.insert(trackId, body);
}

void LyricsController::apply(const QString &trackId, const QJsonObject &body)
{
    m_trackId = trackId;
    clearLines();
    m_rawText = body.value(QStringLiteral("text")).toString();

    const QJsonArray lines = body.value(QStringLiteral("lines")).toArray();
    m_lines.reserve(lines.size());
    for (const QJsonValue &value : lines) {
        const QJsonObject line = value.toObject();
        const QJsonValue time = line.value(QStringLiteral("time_ms"));
        const qint64 ms = time.isNull() || time.isUndefined() ? -1 : static_cast<qint64>(time.toDouble());
        m_lines.append(QVariantMap{{QStringLiteral("time"), ms},
                                   {QStringLiteral("text"), line.value(QStringLiteral("text")).toString()}});
        m_times.append(ms);
    }
    emit linesChanged();
    setState(body.value(QStringLiteral("kind")).toString(QStringLiteral("none")));
    updateActive();
}

void LyricsController::setState(const QString &state)
{
    if (m_state == state)
        return;
    m_state = state;
    emit stateChanged();
}

void LyricsController::updateActive()
{
    int index = -1;
    if (m_state == QLatin1String("synced") && m_trackId == m_player->currentTrackId()
        && !m_times.isEmpty()) {
        // The last line that has started. Bisection, since this runs on every position tick.
        const auto next = std::upper_bound(m_times.cbegin(), m_times.cend(), m_player->position());
        index = static_cast<int>(next - m_times.cbegin()) - 1;
    }
    if (index == m_activeIndex)
        return;
    m_activeIndex = index;
    emit activeIndexChanged();
}

void LyricsController::setSaving(bool saving)
{
    if (m_saving == saving)
        return;
    m_saving = saving;
    emit savingChanged();
}

void LyricsController::save(const QString &trackId, const QString &text)
{
    if (trackId.isEmpty() || m_saving)
        return;
    setSaving(true);
    m_api->put(QStringLiteral("/tracks/%1/lyrics").arg(trackId),
               QJsonObject{{QStringLiteral("text"), text}},
               [this, trackId](const ApiClient::Response &response) {
                   setSaving(false);
                   if (!response.ok()) {
                       emit notify(response.error.isEmpty() ? tr("Не удалось сохранить текст")
                                                            : response.error);
                       return;
                   }
                   remember(trackId, response.object);
                   if (m_active && trackId == m_player->currentTrackId())
                       apply(trackId, response.object);
                   emit notify(tr("Текст сохранён"));
                   emit saved(trackId);
               });
}

void LyricsController::remove(const QString &trackId)
{
    if (trackId.isEmpty() || m_saving)
        return;
    setSaving(true);
    m_api->del(QStringLiteral("/tracks/%1/lyrics").arg(trackId),
               [this, trackId](const ApiClient::Response &response) {
                   setSaving(false);
                   if (!response.ok()) {
                       emit notify(response.error.isEmpty() ? tr("Не удалось удалить текст")
                                                            : response.error);
                       return;
                   }
                   m_cache.remove(trackId);
                   if (m_active && trackId == m_player->currentTrackId())
                       load(trackId);
                   emit notify(tr("Текст удалён"));
                   emit saved(trackId);
               });
}

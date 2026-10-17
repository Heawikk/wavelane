#include "WaveController.h"

#include "ApiClient.h"
#include "Player.h"
#include "TrackListModel.h"

#include <QJsonArray>
#include <QJsonObject>
#include <QUrlQuery>

namespace {
//! Keep at least this many tracks ahead of the one playing.
constexpr int kMinQueueDepth = 2;
constexpr int kBatchSize = 5;
constexpr int kHistoryLimit = 100;
} // namespace

WaveController::WaveController(ApiClient *api, Player *player, QObject *parent)
    : QObject(parent)
    , m_api(api)
    , m_player(player)
    , m_queue(new TrackListModel(this))
    , m_history(new TrackListModel(this))
{
    // A finished track advances the stream by itself: that is what makes it
    // endless rather than a playlist.
    // Each controller advances only the playback it started, so listening to a
    // playlist does not get hijacked by the wave.
    connect(m_player, &Player::trackCompleted, this, [this](const QString &) {
        if (ownsPlayback())
            advance(true);
    });
    connect(m_player, &Player::nearEnd, this, [this](const QString &) {
        if (ownsPlayback())
            ensureQueueDepth();
    });
    connect(m_player, &Player::playbackFailed, this, [this](const QString &message) {
        if (!ownsPlayback())
            return;
        emit notify(tr("Не удалось воспроизвести трек: %1").arg(message));
        // Do not get stuck on a broken file.
        advance(true);
    });
}

void WaveController::setLoading(bool loading)
{
    if (m_loading == loading)
        return;
    m_loading = loading;
    emit loadingChanged();
}

void WaveController::setStatusMessage(const QString &message)
{
    if (m_statusMessage == message)
        return;
    m_statusMessage = message;
    emit statusMessageChanged();
}

void WaveController::setCurrentReason(const QString &reason)
{
    if (m_currentReason == reason)
        return;
    m_currentReason = reason;
    emit currentReasonChanged();
}

void WaveController::loadSettings()
{
    m_api->get(QStringLiteral("/wave/settings"), [this](const ApiClient::Response &response) {
        if (response.ok())
            applySettings(response.object);
    });
}

void WaveController::applySettings(const QJsonObject &object)
{
    m_mood = object.value(QStringLiteral("mood")).toString(QStringLiteral("any"));
    m_character = object.value(QStringLiteral("character")).toString(QStringLiteral("any"));
    m_language = object.value(QStringLiteral("language")).toString(QStringLiteral("any"));
    m_diversity = object.value(QStringLiteral("diversity")).toDouble(0.3);
    emit settingsChanged();
}

void WaveController::start()
{
    m_queue->clear();
    setStatusMessage({});
    m_started = true;
    emit startedChanged();
    fetchBatch(kBatchSize, true, true);
}

void WaveController::reset()
{
    m_api->post(QStringLiteral("/wave/reset"), {}, [this](const ApiClient::Response &response) {
        if (!response.ok()) {
            emit notify(response.error);
            return;
        }
        emit notify(tr("Волна перезапущена"));
        start();
    });
}

void WaveController::fetchBatch(int count, bool autoplay, bool restart)
{
    if (m_fetchInFlight)
        return;
    m_fetchInFlight = true;
    setLoading(true);

    QUrlQuery query;
    query.addQueryItem(QStringLiteral("count"), QString::number(count));
    if (restart)
        query.addQueryItem(QStringLiteral("reset"), QStringLiteral("true"));

    m_api->get(QStringLiteral("/wave/next"), query,
               [this, autoplay](const ApiClient::Response &response) {
                   m_fetchInFlight = false;
                   setLoading(false);

                   if (!response.ok()) {
                       setStatusMessage(response.error);
                       emit notify(response.error);
                       return;
                   }

                   applySettings(response.object.value(QStringLiteral("settings")).toObject());

                   const QJsonArray items = response.object.value(QStringLiteral("items"))
                                                .toArray();
                   if (items.isEmpty()) {
                       setStatusMessage(
                           tr("Волне не из чего выбирать — загрузите музыку в каталог "
                              "или ослабьте настройки."));
                       return;
                   }

                   setStatusMessage({});
                   QList<Track> picks;
                   picks.reserve(items.size());
                   for (const QJsonValue &value : items) {
                       const QJsonObject item = value.toObject();
                       Track track =
                           Track::fromJson(item.value(QStringLiteral("track")).toObject());
                       track.streamUrl = item.value(QStringLiteral("stream_url")).toString();
                       track.score = item.value(QStringLiteral("score")).toDouble();
                       track.reasonSummary =
                           describeReason(item.value(QStringLiteral("reason")).toObject());
                       if (track.isValid())
                           picks.append(track);
                   }

                   m_queue->append(picks);

                   if (autoplay && !m_player->hasTrack())
                       advance(true);
               });
}

void WaveController::ensureQueueDepth()
{
    if (m_queue->count() < kMinQueueDepth)
        fetchBatch(kBatchSize, false);
}

void WaveController::advance(bool autoplay)
{
    if (m_queue->isEmpty()) {
        // Nothing buffered: pull a batch and start playing when it lands.
        fetchBatch(kBatchSize, autoplay);
        return;
    }

    const Track next = m_queue->at(0);
    m_queue->removeId(next.id);

    if (m_history->count() >= kHistoryLimit)
        m_history->removeId(m_history->at(0).id);
    m_history->appendTrack(next);

    setCurrentReason(next.reasonSummary);

    if (autoplay)
        m_player->play(next, QStringLiteral("wave"));

    ensureQueueDepth();
}

void WaveController::playNext()
{
    if (!m_started) {
        start();
        return;
    }
    // Leaving a track early is a signal in its own right.
    const qint64 duration = m_player->duration();
    const double completion =
        duration > 0 ? static_cast<double>(m_player->position()) / static_cast<double>(duration)
                     : 0.0;
    if (m_player->hasTrack())
        sendFeedback(QStringLiteral("skip"), completion);

    m_player->reportAndClear(true);
    advance(true);
}

void WaveController::like()
{
    if (!m_player->hasTrack())
        return;
    sendFeedback(QStringLiteral("like"));
    emit notify(tr("Трек добавлен в избранное"));
}

void WaveController::dislike()
{
    if (!m_player->hasTrack())
        return;
    sendFeedback(QStringLiteral("dislike"));
    emit notify(tr("Больше не покажем этот трек"));
    // A dislike should be audible immediately, so move on and drop whatever was
    // queued under the old profile.
    m_player->reportAndClear(true);
    m_queue->clear();
    advance(true);
}

void WaveController::banCurrentArtist()
{
    if (!m_player->hasTrack())
        return;
    sendFeedback(QStringLiteral("ban_artist"));
    emit notify(tr("Исполнитель больше не будет появляться в волне"));
    m_player->reportAndClear(true);
    m_queue->clear();
    advance(true);
}

void WaveController::sendFeedback(const QString &kind, double completion)
{
    const QString trackId = m_player->currentTrackId();
    if (trackId.isEmpty())
        return;

    QJsonObject body{
        {QStringLiteral("track_id"), trackId},
        {QStringLiteral("kind"), kind},
    };
    if (completion >= 0.0)
        body.insert(QStringLiteral("completion"), qBound(0.0, completion, 1.0));

    m_api->post(QStringLiteral("/wave/feedback"), body,
                [this](const ApiClient::Response &response) {
                    if (!response.ok())
                        emit notify(tr("Не удалось отправить отзыв: %1").arg(response.error));
                });
}

void WaveController::setMood(const QString &mood)
{
    if (mood == m_mood)
        return;
    pushSettings({{QStringLiteral("mood"), mood}});
}

void WaveController::setCharacter(const QString &character)
{
    if (character == m_character)
        return;
    pushSettings({{QStringLiteral("character"), character}});
}

void WaveController::setLanguage(const QString &language)
{
    if (language == m_language)
        return;
    pushSettings({{QStringLiteral("language"), language}});
}

void WaveController::setDiversity(double diversity)
{
    const double bounded = qBound(0.0, diversity, 1.0);
    if (qFuzzyCompare(bounded + 1.0, m_diversity + 1.0))
        return;
    pushSettings({{QStringLiteral("diversity"), bounded}});
}

void WaveController::pushSettings(const QJsonObject &changes)
{
    setLoading(true);
    m_api->put(QStringLiteral("/wave/settings"), changes,
               [this](const ApiClient::Response &response) {
                   setLoading(false);
                   if (!response.ok()) {
                       emit notify(response.error);
                       return;
                   }
                   applySettings(response.object);

                   // The server starts a new session when the settings change,
                   // so anything already queued belongs to the old one.
                   m_queue->clear();
                   if (m_started)
                       fetchBatch(kBatchSize, !m_player->hasTrack());
               });
}

void WaveController::clear()
{
    m_queue->clear();
    m_history->clear();
    m_started = false;
    emit startedChanged();
    setCurrentReason({});
    setStatusMessage({});
}

bool WaveController::ownsPlayback() const
{
    return !m_player->hasTrack() || m_player->context() == QLatin1String("wave");
}

QString WaveController::describeReason(const QJsonObject &reason)
{
    const QJsonArray factors = reason.value(QStringLiteral("top_factors")).toArray();
    if (factors.isEmpty())
        return {};

    // Only the strongest factor is shown; a list of weights is not an
    // explanation anyone wants to read mid-song.
    const QJsonObject first = factors.first().toObject();
    const QString name = first.value(QStringLiteral("factor")).toString();
    const double value = first.value(QStringLiteral("value")).toDouble();

    if (name == QLatin1String("taste"))
        return value >= 0 ? tr("Похоже на то, что вы слушаете")
                          : tr("Чтобы расширить вкус");
    if (name == QLatin1String("genre"))
        return tr("Ваш жанр");
    if (name == QLatin1String("artist"))
        return tr("Знакомый исполнитель");
    if (name == QLatin1String("mood"))
        return tr("Под настроение");
    if (name == QLatin1String("popularity"))
        return tr("Популярное");
    if (name == QLatin1String("freshness"))
        return tr("Новое для вас");
    if (name == QLatin1String("era"))
        return tr("Любимые годы");
    if (name == QLatin1String("language"))
        return tr("На вашем языке");
    return {};
}

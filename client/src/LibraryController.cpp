#include "LibraryController.h"

#include "ApiClient.h"
#include "Player.h"
#include "TrackListModel.h"

#include <QJsonArray>
#include <QJsonObject>
#include <QUrlQuery>

LibraryController::LibraryController(ApiClient *api, Player *player, QObject *parent)
    : QObject(parent)
    , m_api(api)
    , m_player(player)
    , m_searchResults(new TrackListModel(this))
    , m_liked(new TrackListModel(this))
    , m_catalogue(new TrackListModel(this))
{
    connect(m_player, &Player::trackCompleted, this, [this](const QString &) {
        if (ownsPlayback())
            advanceWithinList();
    });
}

bool LibraryController::ownsPlayback() const
{
    return m_activeList != nullptr && m_player->context() == m_activeContext;
}

void LibraryController::setSearching(bool searching)
{
    if (m_searching == searching)
        return;
    m_searching = searching;
    emit searchingChanged();
}

void LibraryController::setUploading(bool uploading)
{
    if (m_uploading == uploading)
        return;
    m_uploading = uploading;
    emit uploadingChanged();
}

void LibraryController::setUploadStatus(const QString &status)
{
    if (m_uploadStatus == status)
        return;
    m_uploadStatus = status;
    emit uploadStatusChanged();
}

QList<Track> LibraryController::parseTracks(const QJsonArray &array)
{
    QList<Track> tracks;
    tracks.reserve(array.size());
    for (const QJsonValue &value : array) {
        Track track = Track::fromJson(value.toObject());
        if (track.isValid())
            tracks.append(track);
    }
    return tracks;
}

void LibraryController::search(const QString &text)
{
    const QString trimmed = text.trimmed();
    if (trimmed != m_query) {
        m_query = trimmed;
        emit queryChanged();
    }
    if (trimmed.isEmpty()) {
        m_searchResults->clear();
        return;
    }

    setSearching(true);
    QUrlQuery query;
    query.addQueryItem(QStringLiteral("q"), trimmed);
    query.addQueryItem(QStringLiteral("limit"), QStringLiteral("40"));

    m_api->get(QStringLiteral("/search"), query,
               [this, trimmed](const ApiClient::Response &response) {
                   // A slower earlier search must not overwrite a newer one.
                   if (trimmed != m_query)
                       return;
                   setSearching(false);
                   if (!response.ok()) {
                       emit notify(response.error);
                       return;
                   }
                   m_searchResults->setTracks(
                       parseTracks(response.object.value(QStringLiteral("tracks")).toArray()));
               });
}

void LibraryController::clearSearch()
{
    m_query.clear();
    emit queryChanged();
    m_searchResults->clear();
}

void LibraryController::loadLiked()
{
    QUrlQuery query;
    query.addQueryItem(QStringLiteral("limit"), QStringLiteral("200"));

    m_api->get(QStringLiteral("/library/liked"), query,
               [this](const ApiClient::Response &response) {
                   if (!response.ok()) {
                       emit notify(response.error);
                       return;
                   }
                   m_liked->setTracks(
                       parseTracks(response.object.value(QStringLiteral("items")).toArray()));
               });
}

void LibraryController::loadCatalogue()
{
    QUrlQuery query;
    query.addQueryItem(QStringLiteral("limit"), QStringLiteral("200"));
    query.addQueryItem(QStringLiteral("sort"), QStringLiteral("recent"));

    m_api->get(QStringLiteral("/tracks"), query,
               [this](const ApiClient::Response &response) {
                   if (!response.ok()) {
                       emit notify(response.error);
                       return;
                   }
                   m_catalogue->setTracks(
                       parseTracks(response.object.value(QStringLiteral("items")).toArray()));
                   m_trackCount = response.object.value(QStringLiteral("total")).toInt();
                   emit statsChanged();
               });
}

void LibraryController::loadStats()
{
    m_api->get(QStringLiteral("/library/stats"), [this](const ApiClient::Response &response) {
        if (!response.ok())
            return;
        m_likedCount = response.object.value(QStringLiteral("liked_tracks")).toInt();
        emit statsChanged();
    });
}

void LibraryController::toggleLike(const QString &trackId)
{
    setReaction(trackId, QStringLiteral("like"));
}

void LibraryController::toggleDislike(const QString &trackId)
{
    setReaction(trackId, QStringLiteral("dislike"));
}

void LibraryController::setReaction(const QString &trackId, const QString &kind)
{
    if (trackId.isEmpty())
        return;

    QJsonObject body{{QStringLiteral("kind"), kind}};
    m_api->put(QStringLiteral("/library/tracks/%1/reaction").arg(trackId), body,
               [this, trackId](const ApiClient::Response &response) {
                   if (!response.ok()) {
                       emit notify(response.error);
                       return;
                   }

                   // The endpoint is a toggle, so the response says what the
                   // state actually became rather than what we asked for.
                   const QString resulting =
                       response.object.value(QStringLiteral("kind")).toString();
                   const bool liked = resulting == QLatin1String("like");
                   const bool disliked = resulting == QLatin1String("dislike");

                   for (TrackListModel *model : {m_searchResults, m_liked, m_catalogue})
                       model->setReaction(trackId, liked, disliked);

                   if (!liked)
                       m_liked->removeId(trackId);
                   loadStats();
               });
}

void LibraryController::playFrom(TrackListModel *model, int row, const QString &context)
{
    if (!model || row < 0 || row >= model->count())
        return;

    m_activeList = model;
    m_activeContext = context.isEmpty() ? QStringLiteral("search") : context;
    m_activeRow = row;
    m_player->play(model->at(row), m_activeContext);
}

void LibraryController::advanceWithinList()
{
    if (!m_activeList)
        return;
    const int nextRow = m_activeRow + 1;
    if (nextRow >= m_activeList->count()) {
        // End of the list: stop rather than looping, which would be surprising.
        m_activeList = nullptr;
        m_activeRow = -1;
        return;
    }
    m_activeRow = nextRow;
    m_player->play(m_activeList->at(nextRow), m_activeContext);
}

void LibraryController::uploadFiles(const QList<QUrl> &fileUrls)
{
    QStringList localPaths;
    for (const QUrl &url : fileUrls) {
        const QString local = url.isLocalFile() ? url.toLocalFile() : url.toString();
        if (!local.isEmpty())
            localPaths.append(local);
    }
    if (localPaths.isEmpty())
        return;

    setUploading(true);
    setUploadStatus(tr("Загрузка %n файла(ов)…", "", localPaths.size()));

    m_api->uploadFiles(localPaths, [this](const ApiClient::Response &response) {
        setUploading(false);
        if (!response.ok()) {
            setUploadStatus(response.error);
            emit notify(response.error);
            return;
        }

        const int uploaded = response.object.value(QStringLiteral("uploaded")).toInt();
        const int duplicates = response.object.value(QStringLiteral("duplicates")).toInt();
        const int failed = response.object.value(QStringLiteral("failed")).toInt();

        QStringList parts;
        if (uploaded > 0)
            parts << tr("добавлено: %1").arg(uploaded);
        if (duplicates > 0)
            parts << tr("уже было: %1").arg(duplicates);
        if (failed > 0)
            parts << tr("с ошибкой: %1").arg(failed);

        const QString summary =
            parts.isEmpty() ? tr("Ничего не добавлено") : parts.join(QStringLiteral(", "));
        setUploadStatus(summary);
        emit notify(summary);

        // Surface the first error, which is usually an unsupported format.
        if (failed > 0) {
            const QJsonArray items = response.object.value(QStringLiteral("items")).toArray();
            for (const QJsonValue &value : items) {
                const QString error =
                    value.toObject().value(QStringLiteral("error")).toString();
                if (!error.isEmpty()) {
                    emit notify(error);
                    break;
                }
            }
        }

        loadCatalogue();
        loadStats();
    });
}

void LibraryController::clear()
{
    m_searchResults->clear();
    m_liked->clear();
    m_catalogue->clear();
    m_activeList = nullptr;
    m_activeRow = -1;
    m_query.clear();
    m_trackCount = 0;
    m_likedCount = 0;
    emit queryChanged();
    emit statsChanged();
    setUploadStatus({});
}

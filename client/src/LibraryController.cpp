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

    m_importTimer.setInterval(1000);
    connect(&m_importTimer, &QTimer::timeout, this, &LibraryController::pollImport);
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
                   emit reactionChanged(trackId, liked, disliked);
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

void LibraryController::loadDetail(const QString &trackId)
{
    if (trackId.isEmpty() || trackId == m_detailId)
        return;
    m_detailId = trackId;

    m_api->get(QStringLiteral("/tracks/%1").arg(trackId),
               [this, trackId](const ApiClient::Response &response) {
                   // The selection may have moved on while this was in flight.
                   if (trackId != m_detailId || !response.ok())
                       return;
                   m_detail = Track::fromJson(response.object).toVariantMap();
                   emit detailChanged();
               });
}

void LibraryController::playNext()
{
    if (!m_activeList)
        return;
    m_player->reportAndClear(true);
    advanceWithinList();
}

bool LibraryController::importActive() const
{
    const QString state = m_importJob.value(QStringLiteral("state")).toString();
    return !state.isEmpty() && state != QLatin1String("done")
           && state != QLatin1String("cancelled") && state != QLatin1String("failed");
}

double LibraryController::importFraction() const
{
    const int total = m_importJob.value(QStringLiteral("total")).toInt();
    if (total <= 0)
        return 0.0;
    return qBound(0.0, static_cast<double>(m_importJob.value(QStringLiteral("processed")).toInt())
                           / static_cast<double>(total), 1.0);
}

void LibraryController::importFolder(const QUrl &folder)
{
    const QString path = folder.isLocalFile() ? folder.toLocalFile() : folder.toString();
    if (path.isEmpty())
        return;

    QJsonObject body{
        {QStringLiteral("path"), path},
        {QStringLiteral("recursive"), true},
        {QStringLiteral("analyze"), true},
    };
    m_api->post(QStringLiteral("/admin/imports"), body, [this](const ApiClient::Response &response) {
        if (!response.ok()) {
            emit notify(response.error);
            return;
        }
        m_importReported = false;
        m_importId = response.object.value(QStringLiteral("id")).toString();
        applyImportJob(response.object.toVariantMap());
        m_importTimer.start();
        emit notify(tr("Импорт начался. Его можно оставить работать в фоне."));
    });
}

void LibraryController::cancelImport()
{
    if (m_importId.isEmpty())
        return;
    m_api->post(QStringLiteral("/admin/imports/%1/cancel").arg(m_importId), {},
                [this](const ApiClient::Response &response) {
                    if (response.ok())
                        applyImportJob(response.object.toVariantMap());
                });
}

void LibraryController::dismissImport()
{
    if (importActive())
        return;
    m_importTimer.stop();
    m_importJob.clear();
    m_importId.clear();
    emit importChanged();
}

void LibraryController::restoreImport()
{
    m_api->get(QStringLiteral("/admin/imports"), [this](const ApiClient::Response &response) {
        if (!response.ok() || response.array.isEmpty())
            return;
        const QJsonObject newest = response.array.first().toObject();
        const QString state = newest.value(QStringLiteral("state")).toString();
        // Only adopt one that is still going; an old finished import is history.
        if (state != QLatin1String("scanning") && state != QLatin1String("running"))
            return;
        m_importReported = false;
        m_importId = newest.value(QStringLiteral("id")).toString();
        applyImportJob(newest.toVariantMap());
        m_importTimer.start();
    });
}

void LibraryController::pollImport()
{
    if (m_importId.isEmpty())
        return;
    const QString id = m_importId;
    m_api->get(QStringLiteral("/admin/imports/%1").arg(id),
               [this, id](const ApiClient::Response &response) {
                   // A transient failure just means we ask again a second later.
                   if (!response.ok() || id != m_importId)
                       return;
                   applyImportJob(response.object.toVariantMap());
               });
}

void LibraryController::applyImportJob(const QVariantMap &job)
{
    m_importJob = job;
    emit importChanged();
    if (!importActive())
        finishImport();
}

void LibraryController::finishImport()
{
    m_importTimer.stop();
    if (m_importReported)
        return;
    m_importReported = true;

    const int imported = m_importJob.value(QStringLiteral("imported")).toInt();
    const int duplicates = m_importJob.value(QStringLiteral("duplicates")).toInt();
    const int conflicts = m_importJob.value(QStringLiteral("conflicts")).toInt();
    const int failed = m_importJob.value(QStringLiteral("failed")).toInt();
    const bool cancelled = m_importJob.value(QStringLiteral("state")).toString()
                           == QLatin1String("cancelled");

    QStringList parts{tr("добавлено: %1").arg(imported)};
    if (duplicates > 0)
        parts << tr("уже было: %1").arg(duplicates);
    if (conflicts > 0)
        parts << tr("конфликтов: %1").arg(conflicts);
    if (failed > 0)
        parts << tr("с ошибкой: %1").arg(failed);
    emit notify((cancelled ? tr("Импорт остановлен: ") : tr("Импорт завершён: "))
                + parts.join(QStringLiteral(", ")));

    loadCatalogue();
    loadStats();
    if (conflicts > 0)
        loadConflicts();
}

void LibraryController::loadConflicts()
{
    m_api->get(QStringLiteral("/imports/conflicts"), [this](const ApiClient::Response &response) {
        if (!response.ok())
            return;
        const bool hadAny = !m_conflicts.isEmpty();
        m_conflicts = response.array.toVariantList();
        emit conflictsChanged();
        if (!m_conflicts.isEmpty() && !hadAny)
            emit conflictsFound();
    });
}

void LibraryController::resolveConflicts(const QVariantList &resolutions)
{
    QJsonArray items;
    for (const QVariant &entry : resolutions) {
        const QVariantMap map = entry.toMap();
        items.append(QJsonObject{
            {QStringLiteral("conflict_id"), map.value(QStringLiteral("id")).toString()},
            {QStringLiteral("action"), map.value(QStringLiteral("action")).toString()},
        });
    }
    if (items.isEmpty())
        return;

    m_api->post(QStringLiteral("/imports/conflicts/resolve"),
                QJsonObject{{QStringLiteral("resolutions"), items}},
                [this](const ApiClient::Response &response) {
                    if (!response.ok()) {
                        emit notify(response.error);
                        return;
                    }
                    const int replaced = response.object.value(QStringLiteral("replaced")).toInt();
                    const int kept = response.object.value(QStringLiteral("kept_old")).toInt();
                    QStringList parts;
                    if (replaced > 0)
                        parts << tr("заменено: %1").arg(replaced);
                    if (kept > 0)
                        parts << tr("оставлено старых: %1").arg(kept);
                    if (!parts.isEmpty())
                        emit notify(parts.join(QStringLiteral(", ")));

                    // A replaced file changes a track's length and quality.
                    m_detailId.clear();
                    loadConflicts();
                    loadCatalogue();
                    loadStats();
                });
}

void LibraryController::deleteTracks(const QStringList &trackIds)
{
    if (trackIds.isEmpty())
        return;

    QJsonArray ids;
    for (const QString &id : trackIds)
        ids.append(id);

    m_api->post(QStringLiteral("/tracks/bulk-delete"),
                QJsonObject{{QStringLiteral("track_ids"), ids}},
                [this, trackIds](const ApiClient::Response &response) {
                    if (!response.ok()) {
                        emit notify(response.error);
                        return;
                    }
                    for (const QString &id : trackIds) {
                        m_searchResults->removeId(id);
                        m_liked->removeId(id);
                        m_catalogue->removeId(id);
                    }
                    if (trackIds.contains(m_detailId)) {
                        m_detailId.clear();
                        m_detail.clear();
                        emit detailChanged();
                    }
                    emit tracksDeleted(trackIds);
                    emit notify(tr("Удалено треков: %1")
                                    .arg(response.object.value(QStringLiteral("deleted")).toInt()));
                    loadStats();
                    loadCatalogue();
                });
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
        const int conflicts = response.object.value(QStringLiteral("conflicts")).toInt();

        QStringList parts;
        if (uploaded > 0)
            parts << tr("добавлено: %1").arg(uploaded);
        if (duplicates > 0)
            parts << tr("уже было: %1").arg(duplicates);
        if (conflicts > 0)
            parts << tr("конфликтов: %1").arg(conflicts);
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
        if (conflicts > 0)
            loadConflicts();
    });
}

void LibraryController::applyLyricsKind(const QString &trackId, const QString &kind)
{
    for (TrackListModel *model : {m_searchResults, m_liked, m_catalogue})
        model->setLyricsKind(trackId, kind);
}

void LibraryController::clear()
{
    m_searchResults->clear();
    m_liked->clear();
    m_catalogue->clear();
    m_activeList = nullptr;
    m_activeRow = -1;
    m_importTimer.stop();
    m_importJob.clear();
    m_importId.clear();
    m_conflicts.clear();
    emit importChanged();
    emit conflictsChanged();
    m_query.clear();
    m_trackCount = 0;
    m_likedCount = 0;
    emit queryChanged();
    emit statsChanged();
    setUploadStatus({});
}

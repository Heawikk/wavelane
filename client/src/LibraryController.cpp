#include "LibraryController.h"

#include "ApiClient.h"
#include "Player.h"
#include "TrackListModel.h"

#include <QBuffer>
#include <QDirIterator>
#include <QFile>
#include <QFileInfo>
#include <QImage>
#include <QJsonArray>
#include <QJsonObject>
#include <QUrlQuery>

#include <algorithm>
#include <memory>

LibraryController::LibraryController(ApiClient *api, Player *player, QObject *parent)
    : QObject(parent)
    , m_api(api)
    , m_player(player)
    , m_searchResults(new TrackListModel(this))
    , m_liked(new TrackListModel(this))
    , m_catalogue(new TrackListModel(this))
    , m_browse(new TrackListModel(this))
    , m_adminArtists(new ArtistListModel(this))
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
        setSearchGroups({}, {});
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

                   QVariantList artists;
                   for (const QJsonValue &value :
                        response.object.value(QStringLiteral("artists")).toArray()) {
                       const QJsonObject artist = value.toObject();
                       artists.append(QVariantMap{
                           {QStringLiteral("id"), artist.value(QStringLiteral("id")).toString()},
                           {QStringLiteral("name"), artist.value(QStringLiteral("name")).toString()},
                           {QStringLiteral("imagePath"),
                            artist.value(QStringLiteral("image_path")).toString()},
                       });
                   }
                   QVariantList albums;
                   for (const QJsonValue &value :
                        response.object.value(QStringLiteral("albums")).toArray()) {
                       const QJsonObject album = value.toObject();
                       const int year = album.value(QStringLiteral("release_year")).toInt();
                       albums.append(QVariantMap{
                           {QStringLiteral("id"), album.value(QStringLiteral("id")).toString()},
                           {QStringLiteral("title"), album.value(QStringLiteral("title")).toString()},
                           {QStringLiteral("coverPath"),
                            album.value(QStringLiteral("cover_path")).toString()},
                           {QStringLiteral("year"), year > 0 ? QString::number(year) : QString()},
                       });
                   }
                   setSearchGroups(artists, albums);
               });
}

void LibraryController::setSearchGroups(const QVariantList &artists, const QVariantList &albums)
{
    if (m_searchArtists.isEmpty() && m_searchAlbums.isEmpty() && artists.isEmpty()
        && albums.isEmpty())
        return;
    m_searchArtists = artists;
    m_searchAlbums = albums;
    emit searchGroupsChanged();
}

void LibraryController::clearSearch()
{
    m_query.clear();
    emit queryChanged();
    m_searchResults->clear();
    setSearchGroups({}, {});
}

void LibraryController::openArtist(const QString &artistId, const QString &name)
{
    openBrowse(QStringLiteral("artist"), artistId, name,
               QStringLiteral("/artists/%1/tracks").arg(artistId));
}

void LibraryController::openAlbum(const QString &albumId, const QString &title)
{
    openBrowse(QStringLiteral("album"), albumId, title,
               QStringLiteral("/albums/%1/tracks").arg(albumId));
}

void LibraryController::openBrowse(const QString &kind, const QString &id, const QString &title,
                                   const QString &path)
{
    if (id.isEmpty())
        return;
    m_browseKind = kind;
    m_browseId = id;
    m_browseTitle = title;
    m_browseLoading = true;
    m_browse->clear();
    emit browseChanged();

    QUrlQuery query;
    query.addQueryItem(QStringLiteral("limit"), QStringLiteral("200"));
    m_api->get(path, query, [this, id](const ApiClient::Response &response) {
        // Closed, or another one opened, while this was on its way.
        if (id != m_browseId)
            return;
        m_browseLoading = false;
        emit browseChanged();
        if (!response.ok()) {
            emit notify(response.error);
            return;
        }
        // An album's tracks come as a plain list, an artist's as a page.
        const QJsonArray items = response.array.isEmpty()
                                     ? response.object.value(QStringLiteral("items")).toArray()
                                     : response.array;
        m_browse->setTracks(parseTracks(items));
    });
}

void LibraryController::closeBrowse()
{
    if (m_browseKind.isEmpty())
        return;
    m_browseKind.clear();
    m_browseId.clear();
    m_browseTitle.clear();
    m_browseLoading = false;
    m_browse->clear();
    emit browseChanged();
}

void LibraryController::loadAdminStats()
{
    m_api->get(QStringLiteral("/admin/stats"), [this](const ApiClient::Response &response) {
        if (!response.ok()) {
            m_adminStats.clear();
            emit adminStatsChanged();
            emit notify(response.error);
            return;
        }
        m_adminStats = response.object.toVariantMap();
        emit adminStatsChanged();
    });
}

void LibraryController::loadAdminTeam()
{
    m_api->get(QStringLiteral("/admin/admins"), [this](const ApiClient::Response &response) {
        if (!response.ok()) {
            m_adminTeam.clear();
            emit adminTeamChanged();
            emit notify(response.error);
            return;
        }
        m_adminTeam = response.object.toVariantMap();
        emit adminTeamChanged();
    });
}

void LibraryController::showArtist(const QString &artistId, const QString &name)
{
    if (artistId.isEmpty())
        return;
    openArtist(artistId, name);
    emit artistShown();
}

void LibraryController::loadPlayerArtists(const QVariantList &credits)
{
    // One request per artist, put back in the order of the credits when all have answered; an
    // answer for a track that is no longer playing is dropped.
    const int run = ++m_playerArtistsRun;
    m_playerArtists.clear();
    emit playerArtistsChanged();
    if (credits.isEmpty())
        return;

    auto results = std::make_shared<QVariantList>();
    for (const QVariant &credit : credits) {
        const QVariantMap entry = credit.toMap();
        // what is known now; the answer adds the picture and the rest
        results->append(QVariantMap{{QStringLiteral("id"), entry.value(QStringLiteral("id"))},
                                    {QStringLiteral("name"), entry.value(QStringLiteral("name"))},
                                    {QStringLiteral("role"), entry.value(QStringLiteral("role"))}});
    }
    m_playerArtists = *results;
    emit playerArtistsChanged();

    for (int i = 0; i < credits.size(); ++i) {
        const QString id = credits.at(i).toMap().value(QStringLiteral("id")).toString();
        m_api->get(QStringLiteral("/artists/%1").arg(id), [this, run, i, results](const ApiClient::Response &response) {
            if (run != m_playerArtistsRun || !response.ok())
                return;
            QVariantMap entry = results->at(i).toMap();
            entry.insert(QStringLiteral("imagePath"), response.object.value(QStringLiteral("image_path")).toString());
            entry.insert(QStringLiteral("bio"), response.object.value(QStringLiteral("bio")).toString());
            entry.insert(QStringLiteral("country"), response.object.value(QStringLiteral("country")).toString());
            entry.insert(QStringLiteral("trackCount"), response.object.value(QStringLiteral("track_count")).toInt());
            (*results)[i] = entry;
            m_playerArtists = *results;
            emit playerArtistsChanged();
        });
    }
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

namespace {
constexpr int kCataloguePage = 200; // the most the server gives per page
}

void LibraryController::searchCatalogue(const QString &text)
{
    const QString trimmed = text.trimmed();
    if (trimmed == m_catalogueQuery)
        return;
    m_catalogueQuery = trimmed;
    loadCatalogue();
}

void LibraryController::loadMoreCatalogue()
{
    if (m_loadingMore || !catalogueHasMore())
        return;
    m_loadingMore = true;

    const int offset = m_catalogue->count();
    const QString text = m_catalogueQuery;
    QUrlQuery query;
    query.addQueryItem(QStringLiteral("limit"), QString::number(kCataloguePage));
    query.addQueryItem(QStringLiteral("offset"), QString::number(offset));
    query.addQueryItem(QStringLiteral("sort"), QStringLiteral("recent"));
    if (!text.isEmpty())
        query.addQueryItem(QStringLiteral("q"), text);

    m_api->get(QStringLiteral("/tracks"), query,
               [this, offset, text](const ApiClient::Response &response) {
                   // The list was reloaded (or searched) while this was on its way.
                   if (text != m_catalogueQuery || offset != m_catalogue->count()) {
                       m_loadingMore = false;
                       return;
                   }
                   m_loadingMore = false;
                   if (!response.ok()) {
                       emit notify(response.error);
                       return;
                   }
                   m_catalogue->append(
                       parseTracks(response.object.value(QStringLiteral("items")).toArray()));
                   m_trackCount = response.object.value(QStringLiteral("total")).toInt();
                   emit statsChanged();
               });
}

void LibraryController::loadCatalogue()
{
    QUrlQuery query;
    query.addQueryItem(QStringLiteral("limit"), QString::number(kCataloguePage));
    query.addQueryItem(QStringLiteral("sort"), QStringLiteral("recent"));
    const QString text = m_catalogueQuery;
    if (!text.isEmpty())
        query.addQueryItem(QStringLiteral("q"), text);

    m_api->get(QStringLiteral("/tracks"), query,
               [this, text](const ApiClient::Response &response) {
                   if (text != m_catalogueQuery)
                       return;
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

                   for (TrackListModel *model : {m_searchResults, m_liked, m_catalogue, m_browse})
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
                        m_browse->removeId(id);
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

    if (m_uploading)
        return;

    m_run = UploadRun();
    m_run.pending = localPaths;
    m_run.total = localPaths.size();

    setUploading(true);
    uploadNext();
}

void LibraryController::setSaving(bool saving)
{
    if (m_saving == saving)
        return;
    m_saving = saving;
    emit savingChanged();
}

void LibraryController::beginTrackEdit(const QString &trackId)
{
    if (trackId.isEmpty())
        return;
    m_api->get(QStringLiteral("/tracks/%1").arg(trackId),
               [this, trackId](const ApiClient::Response &response) {
                   if (!response.ok()) {
                       emit notify(response.error);
                       return;
                   }
                   const QJsonObject track = response.object;
                   QStringList main;
                   QStringList featured;
                   for (const QJsonValue &value : track.value(QStringLiteral("artists")).toArray()) {
                       const QJsonObject credit = value.toObject();
                       const QString name = credit.value(QStringLiteral("name")).toString();
                       const QString role = credit.value(QStringLiteral("role")).toString();
                       if (role == QLatin1String("featured"))
                           featured.append(name);
                       else if (role == QLatin1String("main"))
                           main.append(name);
                   }
                   QStringList genres;
                   for (const QJsonValue &genre : track.value(QStringLiteral("genres")).toArray())
                       genres.append(genre.toString());
                   const QJsonObject album = track.value(QStringLiteral("album")).toObject();

                   m_trackEdit = {
                       {QStringLiteral("id"), trackId},
                       {QStringLiteral("title"), track.value(QStringLiteral("title")).toString()},
                       {QStringLiteral("artists"), main.join(QStringLiteral(", "))},
                       {QStringLiteral("featured"), featured.join(QStringLiteral(", "))},
                       {QStringLiteral("album"), album.value(QStringLiteral("title")).toString()},
                       {QStringLiteral("year"), album.value(QStringLiteral("release_year")).toInt()},
                       {QStringLiteral("trackNumber"),
                        track.value(QStringLiteral("track_number")).toInt()},
                       {QStringLiteral("genres"), genres.join(QStringLiteral(", "))},
                       {QStringLiteral("explicit"), track.value(QStringLiteral("explicit")).toBool()},
                   };
                   emit trackEditChanged();
                   emit trackEditReady();
               });
}

void LibraryController::saveTrack(const QString &trackId, const QVariantMap &fields)
{
    if (trackId.isEmpty() || m_saving)
        return;

    // The form gives names separated by commas; the server takes lists.
    auto names = [](const QVariant &value) {
        QJsonArray out;
        for (const QString &part : value.toString().split(QLatin1Char(','), Qt::SkipEmptyParts)) {
            const QString name = part.simplified();
            if (!name.isEmpty())
                out.append(name);
        }
        return out;
    };

    QJsonObject body;
    body.insert(QStringLiteral("title"), fields.value(QStringLiteral("title")).toString().trimmed());
    body.insert(QStringLiteral("artists"), names(fields.value(QStringLiteral("artists"))));
    body.insert(QStringLiteral("featured_artists"), names(fields.value(QStringLiteral("featured"))));
    body.insert(QStringLiteral("album"), fields.value(QStringLiteral("album")).toString().trimmed());
    body.insert(QStringLiteral("genres"), names(fields.value(QStringLiteral("genres"))));
    body.insert(QStringLiteral("explicit"), fields.value(QStringLiteral("explicit")).toBool());
    const int year = fields.value(QStringLiteral("year")).toInt();
    if (year > 0)
        body.insert(QStringLiteral("release_year"), year);
    const int number = fields.value(QStringLiteral("trackNumber")).toInt();
    if (number >= 0)
        body.insert(QStringLiteral("track_number"), number);

    setSaving(true);
    m_api->patch(QStringLiteral("/tracks/%1").arg(trackId), body,
                 [this, trackId](const ApiClient::Response &response) {
                     setSaving(false);
                     if (!response.ok()) {
                         emit notify(response.error);
                         return;
                     }
                     const Track track = Track::fromJson(response.object);
                     for (TrackListModel *model :
                          {m_searchResults, m_liked, m_catalogue, m_browse})
                         model->replaceTrack(track);
                     if (trackId == m_detailId) {
                         m_detail = track.toVariantMap();
                         emit detailChanged();
                     }
                     emit notify(tr("Сохранено"));
                     emit trackSaved(trackId);
                 });
}

void LibraryController::loadAdminArtists(const QString &text)
{
    m_adminArtistsQuery = text.trimmed();
    QUrlQuery query;
    query.addQueryItem(QStringLiteral("limit"), QString::number(kCataloguePage));
    query.addQueryItem(QStringLiteral("sort"), QStringLiteral("name"));
    if (!m_adminArtistsQuery.isEmpty())
        query.addQueryItem(QStringLiteral("q"), m_adminArtistsQuery);

    const QString asked = m_adminArtistsQuery;
    m_api->get(QStringLiteral("/artists"), query,
               [this, asked](const ApiClient::Response &response) {
                   if (asked != m_adminArtistsQuery)
                       return;
                   if (!response.ok()) {
                       emit notify(response.error);
                       return;
                   }
                   QList<QJsonObject> items;
                   for (const QJsonValue &value : response.object.value(QStringLiteral("items")).toArray())
                       items.append(value.toObject());
                   m_adminArtists->setArtists(items);
                   m_adminArtistsTotal = response.object.value(QStringLiteral("total")).toInt();
                   emit adminArtistsChanged();
               });
}

void LibraryController::loadMoreAdminArtists()
{
    if (m_loadingMoreArtists || !adminArtistsHasMore())
        return;
    m_loadingMoreArtists = true;

    const int offset = m_adminArtists->count();
    const QString asked = m_adminArtistsQuery;
    QUrlQuery query;
    query.addQueryItem(QStringLiteral("limit"), QString::number(kCataloguePage));
    query.addQueryItem(QStringLiteral("offset"), QString::number(offset));
    query.addQueryItem(QStringLiteral("sort"), QStringLiteral("name"));
    if (!asked.isEmpty())
        query.addQueryItem(QStringLiteral("q"), asked);

    m_api->get(QStringLiteral("/artists"), query,
               [this, offset, asked](const ApiClient::Response &response) {
                   m_loadingMoreArtists = false;
                   if (asked != m_adminArtistsQuery || offset != m_adminArtists->count())
                       return;
                   if (!response.ok()) {
                       emit notify(response.error);
                       return;
                   }
                   QList<QJsonObject> items;
                   for (const QJsonValue &value : response.object.value(QStringLiteral("items")).toArray())
                       items.append(value.toObject());
                   m_adminArtists->append(items);
                   m_adminArtistsTotal = response.object.value(QStringLiteral("total")).toInt();
                   emit adminArtistsChanged();
               });
}

void LibraryController::applyArtistAnswer(bool ok, const QString &error, const QJsonObject &artist,
                                          const QString &message)
{
    setSaving(false);
    if (!ok) {
        emit notify(error);
        return;
    }
    m_adminArtists->update(artist);
    // Search results that show this artist (with the old picture or name) follow.
    const QString id = artist.value(QStringLiteral("id")).toString();
    QVariantList artists = m_searchArtists;
    bool changed = false;
    for (QVariant &entry : artists) {
        QVariantMap found = entry.toMap();
        if (found.value(QStringLiteral("id")).toString() != id)
            continue;
        found.insert(QStringLiteral("name"), artist.value(QStringLiteral("name")).toString());
        found.insert(QStringLiteral("imagePath"), artist.value(QStringLiteral("image_path")).toString());
        entry = found;
        changed = true;
    }
    if (changed) {
        m_searchArtists = artists;
        emit searchGroupsChanged();
    }
    emit notify(message);
    emit artistSaved(id);
}

void LibraryController::saveArtist(const QString &artistId, const QVariantMap &fields)
{
    if (artistId.isEmpty() || m_saving)
        return;
    QJsonObject body;
    body.insert(QStringLiteral("name"), fields.value(QStringLiteral("name")).toString().trimmed());
    body.insert(QStringLiteral("country"), fields.value(QStringLiteral("country")).toString().trimmed());
    body.insert(QStringLiteral("bio"), fields.value(QStringLiteral("bio")).toString());

    setSaving(true);
    m_api->patch(QStringLiteral("/artists/%1").arg(artistId), body,
                 [this](const ApiClient::Response &response) {
                     applyArtistAnswer(response.ok(), response.error, response.object, tr("Сохранено"));
                 });
}

void LibraryController::setArtistImage(const QString &artistId, const QUrl &file)
{
    if (artistId.isEmpty() || m_saving)
        return;

    // Read through QFile so that a picture handed over by the system (a content:// address on
    // Android) opens like any other.
    const QString path = file.isLocalFile() ? file.toLocalFile() : file.toString();
    QFile source(path);
    if (!source.open(QIODevice::ReadOnly)) {
        emit notify(tr("Не удалось открыть картинку"));
        return;
    }
    QImage image = QImage::fromData(source.readAll());
    if (image.isNull()) {
        emit notify(tr("Это не картинка, или формат не поддерживается"));
        return;
    }

    // A photo straight from a camera is many megabytes; a profile picture needs a fraction.
    constexpr int kLongestSide = 800;
    if (qMax(image.width(), image.height()) > kLongestSide)
        image = image.scaled(kLongestSide, kLongestSide, Qt::KeepAspectRatio, Qt::SmoothTransformation);

    QByteArray bytes;
    QBuffer buffer(&bytes);
    buffer.open(QIODevice::WriteOnly);
    const bool transparent = image.hasAlphaChannel();
    image.save(&buffer, transparent ? "PNG" : "JPG", transparent ? -1 : 88);

    setSaving(true);
    m_api->uploadBytes(QStringLiteral("/artists/%1/image").arg(artistId), QStringLiteral("image"),
                       transparent ? QStringLiteral("artist.png") : QStringLiteral("artist.jpg"), bytes,
                       transparent ? QStringLiteral("image/png") : QStringLiteral("image/jpeg"),
                       [this](const ApiClient::Response &response) {
                           applyArtistAnswer(response.ok(), response.error, response.object,
                                              tr("Картинка сохранена"));
                       });
}

void LibraryController::removeArtistImage(const QString &artistId)
{
    if (artistId.isEmpty() || m_saving)
        return;
    setSaving(true);
    m_api->del(QStringLiteral("/artists/%1/image").arg(artistId),
               [this](const ApiClient::Response &response) {
                   applyArtistAnswer(response.ok(), response.error, response.object, tr("Картинка убрана"));
               });
}

void LibraryController::uploadFolder(const QUrl &folder)
{
    const QString root = folder.isLocalFile() ? folder.toLocalFile() : folder.toString();
    if (root.isEmpty() || m_uploading)
        return;

    // The folder is on this computer, not on the server, so its files go up one by one like any
    // others. (Asking the server to read the path only works when it runs on this very machine.)
    static const QStringList filters{
        QStringLiteral("*.mp3"),  QStringLiteral("*.flac"), QStringLiteral("*.m4a"),
        QStringLiteral("*.ogg"),  QStringLiteral("*.opus"), QStringLiteral("*.wav"),
        QStringLiteral("*.aac"),  QStringLiteral("*.wma"),  QStringLiteral("*.aiff"),
        QStringLiteral("*.aif"),
    };
    QStringList paths;
    QDirIterator it(root, filters, QDir::Files | QDir::Readable, QDirIterator::Subdirectories);
    while (it.hasNext())
        paths.append(it.next());

    if (paths.isEmpty()) {
        emit notify(tr("В этой папке нет аудиофайлов"));
        return;
    }
    std::sort(paths.begin(), paths.end());

    QList<QUrl> files;
    files.reserve(paths.size());
    for (const QString &path : std::as_const(paths))
        files.append(QUrl::fromLocalFile(path));
    uploadFiles(files);
}

void LibraryController::uploadNext()
{
    if (m_run.pending.isEmpty()) {
        finishUpload();
        return;
    }

    const int number = m_run.total - m_run.pending.size() + 1;
    const QString path = m_run.pending.takeFirst();
    setUploadStatus(m_run.total > 1 ? tr("Загрузка %1 из %2…").arg(number).arg(m_run.total)
                                    : tr("Загрузка…"));

    m_api->uploadFiles({path}, [this](const ApiClient::Response &response) {
        if (!response.ok()) {
            // The connection itself failed (or the server refused the request): this file is lost.
            ++m_run.failed;
            if (m_run.firstError.isEmpty())
                m_run.firstError = response.error;
            // A dead connection would fail every remaining file one timeout at a time.
            if (++m_run.dropped >= 3) {
                m_run.failed += m_run.pending.size();
                m_run.pending.clear();
            }
        } else {
            m_run.dropped = 0;
            m_run.uploaded += response.object.value(QStringLiteral("uploaded")).toInt();
            m_run.duplicates += response.object.value(QStringLiteral("duplicates")).toInt();
            m_run.conflicts += response.object.value(QStringLiteral("conflicts")).toInt();
            const int failed = response.object.value(QStringLiteral("failed")).toInt();
            m_run.failed += failed;
            if (failed > 0 && m_run.firstError.isEmpty()) {
                const QJsonArray items = response.object.value(QStringLiteral("items")).toArray();
                for (const QJsonValue &value : items) {
                    const QString error =
                        value.toObject().value(QStringLiteral("error")).toString();
                    if (!error.isEmpty()) {
                        m_run.firstError = error;
                        break;
                    }
                }
            }
        }
        uploadNext();
    });
}

void LibraryController::finishUpload()
{
    setUploading(false);

    QStringList parts;
    if (m_run.uploaded > 0)
        parts << tr("добавлено: %1").arg(m_run.uploaded);
    if (m_run.duplicates > 0)
        parts << tr("уже было: %1").arg(m_run.duplicates);
    if (m_run.conflicts > 0)
        parts << tr("конфликтов: %1").arg(m_run.conflicts);
    if (m_run.failed > 0)
        parts << tr("с ошибкой: %1").arg(m_run.failed);

    const QString summary =
        parts.isEmpty() ? tr("Ничего не добавлено") : parts.join(QStringLiteral(", "));
    setUploadStatus(summary);
    emit notify(summary);

    // Surface the first error, which is usually an unsupported format or a lost connection.
    if (m_run.failed > 0 && !m_run.firstError.isEmpty())
        emit notify(m_run.firstError);

    const int conflicts = m_run.conflicts;
    m_run = UploadRun();

    loadCatalogue();
    loadStats();
    if (conflicts > 0)
        loadConflicts();
}

void LibraryController::applyLyricsKind(const QString &trackId, const QString &kind)
{
    for (TrackListModel *model : {m_searchResults, m_liked, m_catalogue, m_browse})
        model->setLyricsKind(trackId, kind);
}

void LibraryController::clear()
{
    m_searchResults->clear();
    m_liked->clear();
    m_catalogue->clear();
    m_browse->clear();
    m_adminArtists->clear();
    m_adminArtistsTotal = 0;
    m_adminArtistsQuery.clear();
    m_catalogueQuery.clear();
    m_trackEdit.clear();
    emit adminArtistsChanged();
    m_browseKind.clear();
    m_browseId.clear();
    m_browseTitle.clear();
    m_browseLoading = false;
    m_searchArtists.clear();
    m_searchAlbums.clear();
    m_adminStats.clear();
    m_adminTeam.clear();
    m_playerArtists.clear();
    ++m_playerArtistsRun;
    emit searchGroupsChanged();
    emit browseChanged();
    emit adminStatsChanged();
    emit adminTeamChanged();
    emit playerArtistsChanged();
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

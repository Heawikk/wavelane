#pragma once

#include "Track.h"
// Included rather than forward-declared: moc needs the complete type to
// build the metatype for the TrackListModel* properties below.
#include "ArtistListModel.h"
#include "TrackListModel.h"

#include <QJsonObject>
#include <QObject>
#include <QString>
#include <QTimer>
#include <QUrl>
#include <QVariantList>
#include <qqmlintegration.h>

class ApiClient;
class Player;

/*! Search, the liked list, uploads, and sequential playback within a list. */
class LibraryController : public QObject
{
    Q_OBJECT
    QML_ANONYMOUS

    Q_PROPERTY(TrackListModel *searchResults READ searchResults CONSTANT)
    Q_PROPERTY(TrackListModel *liked READ liked CONSTANT)
    Q_PROPERTY(TrackListModel *catalogue READ catalogue CONSTANT)
    //! The tracks of the artist or album opened from the search results.
    Q_PROPERTY(TrackListModel *browse READ browse CONSTANT)
    //! Artists and albums matching the search ([{ id, name, imagePath }] / [{ id, title, coverPath, year }]).
    Q_PROPERTY(QVariantList searchArtists READ searchArtists NOTIFY searchGroupsChanged)
    Q_PROPERTY(QVariantList searchAlbums READ searchAlbums NOTIFY searchGroupsChanged)
    //! What is open in the browse list: "artist", "album", or empty when none is.
    Q_PROPERTY(QString browseKind READ browseKind NOTIFY browseChanged)
    Q_PROPERTY(QString browseTitle READ browseTitle NOTIFY browseChanged)
    Q_PROPERTY(bool browseLoading READ browseLoading NOTIFY browseChanged)
    //! Totals for the administrator's dashboard; empty until loaded.
    Q_PROPERTY(QVariantMap adminStats READ adminStats NOTIFY adminStatsChanged)
    Q_PROPERTY(QVariantMap adminTeam READ adminTeam NOTIFY adminTeamChanged)
    //! More of the catalogue exists on the server than is loaded.
    Q_PROPERTY(bool catalogueHasMore READ catalogueHasMore NOTIFY statsChanged)
    //! The administrator's list of artists, and how many the server has (for the search typed).
    Q_PROPERTY(ArtistListModel *adminArtists READ adminArtists CONSTANT)
    Q_PROPERTY(int adminArtistsTotal READ adminArtistsTotal NOTIFY adminArtistsChanged)
    Q_PROPERTY(bool adminArtistsHasMore READ adminArtistsHasMore NOTIFY adminArtistsChanged)
    //! The full record of the track being edited, as the edit form wants it.
    Q_PROPERTY(QVariantMap trackEdit READ trackEdit NOTIFY trackEditChanged)
    //! A save of a track or an artist is on its way.
    Q_PROPERTY(bool saving READ saving NOTIFY savingChanged)
    Q_PROPERTY(bool searching READ searching NOTIFY searchingChanged)
    Q_PROPERTY(bool uploading READ uploading NOTIFY uploadingChanged)
    Q_PROPERTY(QString uploadStatus READ uploadStatus NOTIFY uploadStatusChanged)
    Q_PROPERTY(QString query READ query NOTIFY queryChanged)
    Q_PROPERTY(int trackCount READ trackCount NOTIFY statsChanged)
    Q_PROPERTY(int likedCount READ likedCount NOTIFY statsChanged)
    //! Full details (including audio features) of the last track asked about.
    Q_PROPERTY(QVariantMap detail READ detail NOTIFY detailChanged)
    //! The running or just-finished folder import; empty when there is none.
    Q_PROPERTY(QVariantMap importJob READ importJob NOTIFY importChanged)
    Q_PROPERTY(bool importActive READ importActive NOTIFY importChanged)
    Q_PROPERTY(double importFraction READ importFraction NOTIFY importChanged)
    //! Files waiting for an "old or new?" answer.
    Q_PROPERTY(QVariantList conflicts READ conflicts NOTIFY conflictsChanged)

public:
    LibraryController(ApiClient *api, Player *player, QObject *parent = nullptr);

    TrackListModel *searchResults() const { return m_searchResults; }
    TrackListModel *liked() const { return m_liked; }
    TrackListModel *catalogue() const { return m_catalogue; }
    TrackListModel *browse() const { return m_browse; }
    QVariantList searchArtists() const { return m_searchArtists; }
    QVariantList searchAlbums() const { return m_searchAlbums; }
    QString browseKind() const { return m_browseKind; }
    QString browseTitle() const { return m_browseTitle; }
    bool browseLoading() const { return m_browseLoading; }
    QVariantMap adminStats() const { return m_adminStats; }
    QVariantMap adminTeam() const { return m_adminTeam; }
    bool catalogueHasMore() const { return m_catalogue->count() < m_trackCount; }
    ArtistListModel *adminArtists() const { return m_adminArtists; }
    int adminArtistsTotal() const { return m_adminArtistsTotal; }
    bool adminArtistsHasMore() const { return m_adminArtists->count() < m_adminArtistsTotal; }
    QVariantMap trackEdit() const { return m_trackEdit; }
    bool saving() const { return m_saving; }
    bool searching() const { return m_searching; }
    bool uploading() const { return m_uploading; }
    QString uploadStatus() const { return m_uploadStatus; }
    QString query() const { return m_query; }
    int trackCount() const { return m_trackCount; }
    int likedCount() const { return m_likedCount; }
    QVariantMap detail() const { return m_detail; }
    QVariantMap importJob() const { return m_importJob; }
    bool importActive() const;
    double importFraction() const;
    QVariantList conflicts() const { return m_conflicts; }

    Q_INVOKABLE void search(const QString &text);
    Q_INVOKABLE void clearSearch();
    Q_INVOKABLE void loadLiked();
    Q_INVOKABLE void loadCatalogue();
    //! The next page of the catalogue, appended (the administrator's list of every track).
    Q_INVOKABLE void loadMoreCatalogue();
    //! Narrow the catalogue (the administrator's list of every track) to what matches the text.
    Q_INVOKABLE void searchCatalogue(const QString &text);

    //! Fetch the full record of a track for the edit form; `trackEditReady` follows.
    Q_INVOKABLE void beginTrackEdit(const QString &trackId);
    //! { title, artists[], featured[], album, year, trackNumber, genres[], explicit } of the form.
    Q_INVOKABLE void saveTrack(const QString &trackId, const QVariantMap &fields);

    //! The first page of the artists matching the text (everyone when it is empty).
    Q_INVOKABLE void loadAdminArtists(const QString &text);
    Q_INVOKABLE void loadMoreAdminArtists();
    //! { name, country, bio }
    Q_INVOKABLE void saveArtist(const QString &artistId, const QVariantMap &fields);
    //! The picture is shrunk before it goes up.
    Q_INVOKABLE void setArtistImage(const QString &artistId, const QUrl &file);
    Q_INVOKABLE void removeArtistImage(const QString &artistId);
    Q_INVOKABLE void openArtist(const QString &artistId, const QString &name);
    Q_INVOKABLE void openAlbum(const QString &albumId, const QString &title);
    Q_INVOKABLE void closeBrowse();
    Q_INVOKABLE void loadAdminStats();
    Q_INVOKABLE void loadAdminTeam();
    Q_INVOKABLE void loadStats();

    //! Toggle like / dislike on any track, from any list.
    Q_INVOKABLE void toggleLike(const QString &trackId);
    Q_INVOKABLE void toggleDislike(const QString &trackId);

    //! Play a row, and keep playing down that list afterwards.
    Q_INVOKABLE void playFrom(TrackListModel *model, int row, const QString &context);

    Q_INVOKABLE void uploadFiles(const QList<QUrl> &fileUrls);
    //! Upload every audio file under a folder of this computer, subfolders included.
    Q_INVOKABLE void uploadFolder(const QUrl &folder);

    //! List endpoints leave the audio features out; this fetches them for one track.
    Q_INVOKABLE void loadDetail(const QString &trackId);

    //! Import every audio file under a folder on the server, in the background.
    Q_INVOKABLE void importFolder(const QUrl &folder);
    Q_INVOKABLE void cancelImport();
    Q_INVOKABLE void dismissImport();
    //! Pick up an import that was already running when the app started.
    Q_INVOKABLE void restoreImport();

    Q_INVOKABLE void loadConflicts();
    //! [{ id, action }] where action is "keep_old" or "replace".
    Q_INVOKABLE void resolveConflicts(const QVariantList &resolutions);

    Q_INVOKABLE void deleteTracks(const QStringList &trackIds);

    //! Skip to the next track of the list playback is walking through.
    Q_INVOKABLE void playNext();

    void clear();

    //! Mirror a change of a track's lyrics into every list that shows it.
    void applyLyricsKind(const QString &trackId, const QString &kind);

signals:
    void searchingChanged();
    void uploadingChanged();
    void uploadStatusChanged();
    void queryChanged();
    void statsChanged();
    void notify(const QString &message);
    void detailChanged();
    void importChanged();
    void conflictsChanged();
    void searchGroupsChanged();
    void browseChanged();
    void adminStatsChanged();
    void adminTeamChanged();
    void adminArtistsChanged();
    void trackEditChanged();
    void savingChanged();
    //! The record asked for with beginTrackEdit has arrived.
    void trackEditReady();
    void trackSaved(const QString &trackId);
    void artistSaved(const QString &artistId);
    //! New conflicts appeared; the UI should ask about them.
    void conflictsFound();
    //! Tracks were deleted; other views must forget them.
    void tracksDeleted(const QStringList &trackIds);
    //! A like/dislike changed anywhere; other models mirror it.
    void reactionChanged(const QString &trackId, bool liked, bool disliked);

private:
    void setSearching(bool searching);
    void setSaving(bool saving);
    void applyArtistAnswer(bool ok, const QString &error, const QJsonObject &artist,
                           const QString &message);
    void setSearchGroups(const QVariantList &artists, const QVariantList &albums);
    void openBrowse(const QString &kind, const QString &id, const QString &title,
                    const QString &path);
    void setUploading(bool uploading);
    void setUploadStatus(const QString &status);
    //! Sends the next file of the running upload, or reports the result once none is left.
    void uploadNext();
    void finishUpload();
    void setReaction(const QString &trackId, const QString &kind);
    void advanceWithinList();
    bool ownsPlayback() const;
    void pollImport();
    void applyImportJob(const QVariantMap &job);
    void finishImport();
    static QList<Track> parseTracks(const QJsonArray &array);

    ApiClient *m_api = nullptr;
    Player *m_player = nullptr;
    TrackListModel *m_searchResults = nullptr;
    TrackListModel *m_liked = nullptr;
    TrackListModel *m_catalogue = nullptr;
    TrackListModel *m_browse = nullptr;
    QVariantList m_searchArtists;
    QVariantList m_searchAlbums;
    QString m_browseKind;
    QString m_browseTitle;
    QString m_browseId;
    bool m_browseLoading = false;
    QVariantMap m_adminStats;
    QVariantMap m_adminTeam;
    bool m_loadingMore = false;
    QString m_catalogueQuery;
    ArtistListModel *m_adminArtists = nullptr;
    int m_adminArtistsTotal = 0;
    QString m_adminArtistsQuery;
    bool m_loadingMoreArtists = false;
    QVariantMap m_trackEdit;
    bool m_saving = false;

    bool m_searching = false;
    bool m_uploading = false;
    QString m_uploadStatus;
    //! Files are sent one request each: a stall costs one file, not the whole batch.
    struct UploadRun
    {
        QStringList pending;
        int total = 0;
        int uploaded = 0;
        int duplicates = 0;
        int failed = 0;
        int conflicts = 0;
        int dropped = 0; //!< consecutive transport failures; the run gives up after a few
        QString firstError;
    };
    UploadRun m_run;
    QString m_query;
    int m_trackCount = 0;
    int m_likedCount = 0;

    QVariantMap m_detail;
    QString m_detailId;

    QVariantMap m_importJob;
    QString m_importId;
    QTimer m_importTimer;
    bool m_importReported = false;
    QVariantList m_conflicts;

    //! The list playback is walking through, and where it is.
    TrackListModel *m_activeList = nullptr;
    QString m_activeContext;
    int m_activeRow = -1;
};

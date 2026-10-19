#pragma once

#include "Track.h"
// Included rather than forward-declared: moc needs the complete type to
// build the metatype for the TrackListModel* properties below.
#include "TrackListModel.h"

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
    Q_INVOKABLE void loadStats();

    //! Toggle like / dislike on any track, from any list.
    Q_INVOKABLE void toggleLike(const QString &trackId);
    Q_INVOKABLE void toggleDislike(const QString &trackId);

    //! Play a row, and keep playing down that list afterwards.
    Q_INVOKABLE void playFrom(TrackListModel *model, int row, const QString &context);

    Q_INVOKABLE void uploadFiles(const QList<QUrl> &fileUrls);

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
    //! New conflicts appeared; the UI should ask about them.
    void conflictsFound();
    //! Tracks were deleted; other views must forget them.
    void tracksDeleted(const QStringList &trackIds);
    //! A like/dislike changed anywhere; other models mirror it.
    void reactionChanged(const QString &trackId, bool liked, bool disliked);

private:
    void setSearching(bool searching);
    void setUploading(bool uploading);
    void setUploadStatus(const QString &status);
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

    bool m_searching = false;
    bool m_uploading = false;
    QString m_uploadStatus;
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

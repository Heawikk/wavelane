#pragma once

#include "Track.h"
// Included rather than forward-declared: moc needs the complete type to
// build the metatype for the TrackListModel* properties below.
#include "TrackListModel.h"

#include <QObject>
#include <QString>
#include <QUrl>
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

    void clear();

signals:
    void searchingChanged();
    void uploadingChanged();
    void uploadStatusChanged();
    void queryChanged();
    void statsChanged();
    void notify(const QString &message);

private:
    void setSearching(bool searching);
    void setUploading(bool uploading);
    void setUploadStatus(const QString &status);
    void setReaction(const QString &trackId, const QString &kind);
    void advanceWithinList();
    bool ownsPlayback() const;
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

    //! The list playback is walking through, and where it is.
    TrackListModel *m_activeList = nullptr;
    QString m_activeContext;
    int m_activeRow = -1;
};

#pragma once

#include "Track.h"

#include <QAbstractListModel>
#include <QList>
#include <qqmlintegration.h>

/*! A list of tracks for a QML view. */
class TrackListModel : public QAbstractListModel
{
    Q_OBJECT
    QML_ANONYMOUS

    Q_PROPERTY(int count READ count NOTIFY countChanged)
    Q_PROPERTY(bool empty READ isEmpty NOTIFY countChanged)
    //! Bumped on every change, so a QML binding can depend on "anything in
    //! this model changed" without watching each row.
    Q_PROPERTY(int revision READ revision NOTIFY revisionChanged)

public:
    enum Roles {
        IdRole = Qt::UserRole + 1,
        TitleRole,
        ArtistRole,
        AlbumRole,
        AlbumIdRole,
        CoverPathRole,
        DurationRole,
        DurationMsRole,
        LikedRole,
        DislikedRole,
        ExplicitRole,
        LosslessRole,
        QualityRole,
        PlayCountRole,
        GenresRole,
        ScoreRole,
        ReasonRole,
        FeaturesRole,
        LyricsKindRole,
        TrackRole,          //!< The whole track as a QVariantMap.
    };
    Q_ENUM(Roles)

    explicit TrackListModel(QObject *parent = nullptr);

    int rowCount(const QModelIndex &parent = {}) const override;
    QVariant data(const QModelIndex &index, int role) const override;
    QHash<int, QByteArray> roleNames() const override;

    int count() const { return static_cast<int>(m_tracks.size()); }
    int revision() const { return m_revision; }
    bool isEmpty() const { return m_tracks.isEmpty(); }
    const QList<Track> &tracks() const { return m_tracks; }

    void setTracks(QList<Track> tracks);
    void append(const QList<Track> &tracks);
    void appendTrack(const Track &track);
    void clear();

    Track at(int row) const;
    Q_INVOKABLE int indexOfId(const QString &id) const;

    //! Update the like/dislike flags of one row in place.
    void setReaction(const QString &trackId, bool liked, bool disliked);
    //! Update which kind of lyrics one row has, after an administrator edited them.
    void setLyricsKind(const QString &trackId, const QString &kind);
    void removeId(const QString &trackId);
    //! Take in the new state of a track (after it was edited); rows that show it follow.
    void replaceTrack(const Track &track);

    Q_INVOKABLE QVariantMap get(int row) const;

signals:
    void countChanged();
    void revisionChanged();

private:
    QList<Track> m_tracks;
    int m_revision = 0;
};

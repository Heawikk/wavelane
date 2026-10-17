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
        TrackRole,          //!< The whole track as a QVariantMap.
    };
    Q_ENUM(Roles)

    explicit TrackListModel(QObject *parent = nullptr);

    int rowCount(const QModelIndex &parent = {}) const override;
    QVariant data(const QModelIndex &index, int role) const override;
    QHash<int, QByteArray> roleNames() const override;

    int count() const { return static_cast<int>(m_tracks.size()); }
    bool isEmpty() const { return m_tracks.isEmpty(); }
    const QList<Track> &tracks() const { return m_tracks; }

    void setTracks(QList<Track> tracks);
    void append(const QList<Track> &tracks);
    void appendTrack(const Track &track);
    void clear();

    Track at(int row) const;
    int indexOfId(const QString &id) const;

    //! Update the like/dislike flags of one row in place.
    void setReaction(const QString &trackId, bool liked, bool disliked);
    void removeId(const QString &trackId);

    Q_INVOKABLE QVariantMap get(int row) const;

signals:
    void countChanged();

private:
    QList<Track> m_tracks;
};

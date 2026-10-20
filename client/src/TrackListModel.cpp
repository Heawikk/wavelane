#include "TrackListModel.h"

TrackListModel::TrackListModel(QObject *parent)
    : QAbstractListModel(parent)
{
    auto bump = [this]() {
        ++m_revision;
        emit revisionChanged();
    };
    connect(this, &QAbstractItemModel::dataChanged, this, bump);
    connect(this, &QAbstractItemModel::modelReset, this, bump);
    connect(this, &QAbstractItemModel::rowsInserted, this, bump);
    connect(this, &QAbstractItemModel::rowsRemoved, this, bump);
}

int TrackListModel::rowCount(const QModelIndex &parent) const
{
    return parent.isValid() ? 0 : static_cast<int>(m_tracks.size());
}

QVariant TrackListModel::data(const QModelIndex &index, int role) const
{
    if (!index.isValid() || index.row() < 0 || index.row() >= m_tracks.size())
        return {};

    const Track &track = m_tracks.at(index.row());
    switch (role) {
    case IdRole:         return track.id;
    case TitleRole:      return track.title;
    case ArtistRole:     return track.artistName;
    case AlbumRole:      return track.albumTitle;
    case AlbumIdRole:    return track.albumId;
    case CoverPathRole:  return track.coverPath;
    case DurationRole:   return track.formattedDuration();
    case DurationMsRole: return track.durationMs;
    case LikedRole:      return track.liked;
    case DislikedRole:   return track.disliked;
    case ExplicitRole:   return track.explicitContent;
    case LosslessRole:   return track.lossless;
    case QualityRole:    return track.qualityLabel();
    case PlayCountRole:  return track.playCount;
    case GenresRole:     return track.genres;
    case ScoreRole:      return track.score;
    case ReasonRole:     return track.reasonSummary;
    case FeaturesRole:   return track.features;
    case LyricsKindRole: return track.lyricsKind;
    case TrackRole:      return track.toVariantMap();
    default:             return {};
    }
}

QHash<int, QByteArray> TrackListModel::roleNames() const
{
    return {
        {IdRole,         QByteArrayLiteral("trackId")},
        {TitleRole,      QByteArrayLiteral("title")},
        {ArtistRole,     QByteArrayLiteral("artistName")},
        {AlbumRole,      QByteArrayLiteral("albumTitle")},
        {AlbumIdRole,    QByteArrayLiteral("albumId")},
        {CoverPathRole,  QByteArrayLiteral("coverPath")},
        {DurationRole,   QByteArrayLiteral("duration")},
        {DurationMsRole, QByteArrayLiteral("durationMs")},
        {LikedRole,      QByteArrayLiteral("liked")},
        {DislikedRole,   QByteArrayLiteral("disliked")},
        {ExplicitRole,   QByteArrayLiteral("isExplicit")},
        {LosslessRole,   QByteArrayLiteral("lossless")},
        {QualityRole,    QByteArrayLiteral("quality")},
        {PlayCountRole,  QByteArrayLiteral("playCount")},
        {GenresRole,     QByteArrayLiteral("genres")},
        {ScoreRole,      QByteArrayLiteral("score")},
        {ReasonRole,     QByteArrayLiteral("reason")},
        {FeaturesRole,   QByteArrayLiteral("features")},
        {LyricsKindRole, QByteArrayLiteral("lyricsKind")},
        {TrackRole,      QByteArrayLiteral("track")},
    };
}

void TrackListModel::setTracks(QList<Track> tracks)
{
    beginResetModel();
    m_tracks = std::move(tracks);
    endResetModel();
    emit countChanged();
}

void TrackListModel::append(const QList<Track> &tracks)
{
    if (tracks.isEmpty())
        return;
    const int first = static_cast<int>(m_tracks.size());
    beginInsertRows({}, first, first + static_cast<int>(tracks.size()) - 1);
    m_tracks.append(tracks);
    endInsertRows();
    emit countChanged();
}

void TrackListModel::appendTrack(const Track &track)
{
    append({track});
}

void TrackListModel::clear()
{
    if (m_tracks.isEmpty())
        return;
    beginResetModel();
    m_tracks.clear();
    endResetModel();
    emit countChanged();
}

Track TrackListModel::at(int row) const
{
    if (row < 0 || row >= m_tracks.size())
        return {};
    return m_tracks.at(row);
}

int TrackListModel::indexOfId(const QString &id) const
{
    for (int row = 0; row < m_tracks.size(); ++row) {
        if (m_tracks.at(row).id == id)
            return row;
    }
    return -1;
}

void TrackListModel::replaceTrack(const Track &track)
{
    const int row = indexOfId(track.id);
    if (row < 0)
        return;
    // What a PATCH answer cannot tell (the wave's reason and stream link) stays as it was.
    Track merged = track;
    merged.streamUrl = m_tracks.at(row).streamUrl;
    merged.score = m_tracks.at(row).score;
    merged.reasonSummary = m_tracks.at(row).reasonSummary;
    m_tracks[row] = merged;
    const QModelIndex changed = index(row);
    emit dataChanged(changed, changed);
}

void TrackListModel::setReaction(const QString &trackId, bool liked, bool disliked)
{
    const int row = indexOfId(trackId);
    if (row < 0)
        return;
    m_tracks[row].liked = liked;
    m_tracks[row].disliked = disliked;
    const QModelIndex changed = index(row);
    emit dataChanged(changed, changed, {LikedRole, DislikedRole, TrackRole});
}

void TrackListModel::setLyricsKind(const QString &trackId, const QString &kind)
{
    const int row = indexOfId(trackId);
    if (row < 0 || m_tracks[row].lyricsKind == kind)
        return;
    m_tracks[row].lyricsKind = kind;
    const QModelIndex changed = index(row);
    emit dataChanged(changed, changed, {LyricsKindRole, TrackRole});
}

void TrackListModel::removeId(const QString &trackId)
{
    const int row = indexOfId(trackId);
    if (row < 0)
        return;
    beginRemoveRows({}, row, row);
    m_tracks.removeAt(row);
    endRemoveRows();
    emit countChanged();
}

QVariantMap TrackListModel::get(int row) const
{
    if (row < 0 || row >= m_tracks.size())
        return {};
    return m_tracks.at(row).toVariantMap();
}

#include "ArtistListModel.h"

ArtistListModel::ArtistListModel(QObject *parent)
    : QAbstractListModel(parent)
{
}

ArtistListModel::Artist ArtistListModel::fromJson(const QJsonObject &object)
{
    Artist artist;
    artist.id = object.value(QStringLiteral("id")).toString();
    artist.name = object.value(QStringLiteral("name")).toString();
    artist.imagePath = object.value(QStringLiteral("image_path")).toString();
    artist.country = object.value(QStringLiteral("country")).toString();
    artist.bio = object.value(QStringLiteral("bio")).toString();
    artist.trackCount = object.value(QStringLiteral("track_count")).toInt();
    return artist;
}

int ArtistListModel::rowCount(const QModelIndex &parent) const
{
    return parent.isValid() ? 0 : static_cast<int>(m_artists.size());
}

QVariant ArtistListModel::data(const QModelIndex &index, int role) const
{
    if (!index.isValid() || index.row() < 0 || index.row() >= m_artists.size())
        return {};

    const Artist &artist = m_artists.at(index.row());
    switch (role) {
    case IdRole:         return artist.id;
    case NameRole:       return artist.name;
    case ImagePathRole:  return artist.imagePath;
    case CountryRole:    return artist.country;
    case BioRole:        return artist.bio;
    case TrackCountRole: return artist.trackCount;
    default:             return {};
    }
}

QHash<int, QByteArray> ArtistListModel::roleNames() const
{
    return {
        {IdRole,         QByteArrayLiteral("artistId")},
        {NameRole,       QByteArrayLiteral("name")},
        {ImagePathRole,  QByteArrayLiteral("imagePath")},
        {CountryRole,    QByteArrayLiteral("country")},
        {BioRole,        QByteArrayLiteral("bio")},
        {TrackCountRole, QByteArrayLiteral("trackCount")},
    };
}

void ArtistListModel::setArtists(const QList<QJsonObject> &artists)
{
    beginResetModel();
    m_artists.clear();
    m_artists.reserve(artists.size());
    for (const QJsonObject &object : artists)
        m_artists.append(fromJson(object));
    endResetModel();
    emit countChanged();
}

void ArtistListModel::append(const QList<QJsonObject> &artists)
{
    if (artists.isEmpty())
        return;
    const int first = static_cast<int>(m_artists.size());
    beginInsertRows({}, first, first + static_cast<int>(artists.size()) - 1);
    for (const QJsonObject &object : artists)
        m_artists.append(fromJson(object));
    endInsertRows();
    emit countChanged();
}

void ArtistListModel::update(const QJsonObject &artist)
{
    const Artist fresh = fromJson(artist);
    const int row = indexOfId(fresh.id);
    if (row < 0)
        return;
    m_artists[row] = fresh;
    const QModelIndex changed = index(row);
    emit dataChanged(changed, changed);
}

void ArtistListModel::clear()
{
    if (m_artists.isEmpty())
        return;
    beginResetModel();
    m_artists.clear();
    endResetModel();
    emit countChanged();
}

int ArtistListModel::indexOfId(const QString &id) const
{
    for (int row = 0; row < m_artists.size(); ++row) {
        if (m_artists.at(row).id == id)
            return row;
    }
    return -1;
}

QVariantMap ArtistListModel::get(int row) const
{
    if (row < 0 || row >= m_artists.size())
        return {};
    const Artist &artist = m_artists.at(row);
    return {
        {QStringLiteral("id"), artist.id},
        {QStringLiteral("name"), artist.name},
        {QStringLiteral("imagePath"), artist.imagePath},
        {QStringLiteral("country"), artist.country},
        {QStringLiteral("bio"), artist.bio},
        {QStringLiteral("trackCount"), artist.trackCount},
    };
}

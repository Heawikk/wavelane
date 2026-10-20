#pragma once

#include <QAbstractListModel>
#include <QJsonObject>
#include <QList>
#include <QString>
#include <qqmlintegration.h>

/*! A list of artists for the administrator's artist page. */
class ArtistListModel : public QAbstractListModel
{
    Q_OBJECT
    QML_ANONYMOUS

    Q_PROPERTY(int count READ count NOTIFY countChanged)

public:
    enum Roles {
        IdRole = Qt::UserRole + 1,
        NameRole,
        ImagePathRole,
        CountryRole,
        BioRole,
        TrackCountRole,
    };
    Q_ENUM(Roles)

    explicit ArtistListModel(QObject *parent = nullptr);

    int rowCount(const QModelIndex &parent = {}) const override;
    QVariant data(const QModelIndex &index, int role) const override;
    QHash<int, QByteArray> roleNames() const override;

    int count() const { return static_cast<int>(m_artists.size()); }

    //! Replace the list with these artists (the "items" of an /artists page).
    void setArtists(const QList<QJsonObject> &artists);
    void append(const QList<QJsonObject> &artists);
    //! Take in the new state of one artist, as the server describes it.
    void update(const QJsonObject &artist);
    void clear();

    Q_INVOKABLE QVariantMap get(int row) const;
    Q_INVOKABLE int indexOfId(const QString &id) const;

signals:
    void countChanged();

private:
    struct Artist
    {
        QString id;
        QString name;
        QString imagePath;
        QString country;
        QString bio;
        int trackCount = 0;
    };
    static Artist fromJson(const QJsonObject &object);

    QList<Artist> m_artists;
};

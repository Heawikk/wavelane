#pragma once

#include <QJsonObject>
#include <QString>
#include <QStringList>
#include <QVariantMap>

/*!
 * A track as the API describes it.
 *
 * Deliberately a plain struct rather than a QML value type: the UI reaches
 * tracks either through TrackListModel's roles or as a QVariantMap, so there
 * is no need to register a gadget and no chance of a value-type surprise.
 */
struct Track
{
    QString id;
    QString title;
    QString artistName;
    QString albumTitle;
    QString albumId;
    QString coverPath;
    int durationMs = 0;
    int trackNumber = 0;
    bool explicitContent = false;
    bool lossless = false;
    QString container;
    int bitrateKbps = 0;
    qint64 playCount = 0;
    bool liked = false;
    bool disliked = false;
    QStringList genres;

    // Only populated for wave picks.
    QString streamUrl;
    double score = 0.0;
    QString reasonSummary;
    QVariantMap features;

    bool isValid() const { return !id.isEmpty(); }

    static Track fromJson(const QJsonObject &object);
    QVariantMap toVariantMap() const;

    //! "3:42"
    QString formattedDuration() const;
    static QString formatMilliseconds(qint64 milliseconds);
};

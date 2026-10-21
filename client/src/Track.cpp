#include "Track.h"

#include <QJsonArray>

Track Track::fromJson(const QJsonObject &object)
{
    Track track;
    track.id = object.value(QStringLiteral("id")).toString();
    track.title = object.value(QStringLiteral("title")).toString();
    track.artistName = object.value(QStringLiteral("artist_name")).toString();
    track.durationMs = object.value(QStringLiteral("duration_ms")).toInt();
    track.trackNumber = object.value(QStringLiteral("track_number")).toInt();
    track.explicitContent = object.value(QStringLiteral("explicit")).toBool();
    track.lossless = object.value(QStringLiteral("lossless")).toBool();
    track.container = object.value(QStringLiteral("container")).toString();
    track.bitrateKbps = object.value(QStringLiteral("bitrate_kbps")).toInt();
    track.playCount = static_cast<qint64>(object.value(QStringLiteral("play_count")).toDouble());
    track.coverPath = object.value(QStringLiteral("cover_path")).toString();
    track.lyricsKind = object.value(QStringLiteral("lyrics_kind")).toString(QStringLiteral("none"));

    // liked/disliked are null for anonymous requests, which toBool() maps to false.
    track.liked = object.value(QStringLiteral("liked")).toBool();
    track.disliked = object.value(QStringLiteral("disliked")).toBool();

    const QJsonObject album = object.value(QStringLiteral("album")).toObject();
    if (!album.isEmpty()) {
        track.albumId = album.value(QStringLiteral("id")).toString();
        track.albumTitle = album.value(QStringLiteral("title")).toString();
        if (track.coverPath.isEmpty())
            track.coverPath = album.value(QStringLiteral("cover_path")).toString();
    }

    const QJsonArray credits = object.value(QStringLiteral("artists")).toArray();
    for (const QJsonValue &credit : credits) {
        const QJsonObject artist = credit.toObject();
        const QString role = artist.value(QStringLiteral("role")).toString();
        if (role != QLatin1String("main") && role != QLatin1String("featured"))
            continue;
        track.artists.append(QVariantMap{
            {QStringLiteral("id"), artist.value(QStringLiteral("id")).toString()},
            {QStringLiteral("name"), artist.value(QStringLiteral("name")).toString()},
            {QStringLiteral("role"), role},
        });
    }

    const QJsonArray genres = object.value(QStringLiteral("genres")).toArray();
    for (const QJsonValue &genre : genres)
        track.genres.append(genre.toString());

    const QJsonObject features = object.value(QStringLiteral("features")).toObject();
    for (auto it = features.constBegin(); it != features.constEnd(); ++it)
        track.features.insert(it.key(), it.value().toVariant());

    if (track.artistName.isEmpty())
        track.artistName = QObject::tr("Unknown artist");

    return track;
}

QVariantMap Track::toVariantMap() const
{
    return {
        {QStringLiteral("id"), id},
        {QStringLiteral("title"), title},
        {QStringLiteral("artistName"), artistName},
        {QStringLiteral("albumTitle"), albumTitle},
        {QStringLiteral("albumId"), albumId},
        {QStringLiteral("coverPath"), coverPath},
        {QStringLiteral("durationMs"), durationMs},
        {QStringLiteral("duration"), formattedDuration()},
        {QStringLiteral("explicit"), explicitContent},
        {QStringLiteral("lossless"), lossless},
        {QStringLiteral("container"), container},
        {QStringLiteral("quality"), qualityLabel()},
        {QStringLiteral("bitrateKbps"), bitrateKbps},
        {QStringLiteral("playCount"), playCount},
        {QStringLiteral("liked"), liked},
        {QStringLiteral("disliked"), disliked},
        {QStringLiteral("genres"), genres},
        {QStringLiteral("artists"), artists},
        {QStringLiteral("lyricsKind"), lyricsKind},
        {QStringLiteral("streamUrl"), streamUrl},
        {QStringLiteral("score"), score},
        {QStringLiteral("reason"), reasonSummary},
        {QStringLiteral("features"), features},
    };
}

QString Track::qualityLabel() const
{
    if (lossless)
        return container.toUpper();
    if (bitrateKbps > 0)
        return QStringLiteral("%1 kbps").arg(bitrateKbps);
    return container.toUpper();
}

QString Track::formattedDuration() const
{
    return formatMilliseconds(durationMs);
}

QString Track::formatMilliseconds(qint64 milliseconds)
{
    if (milliseconds <= 0)
        return QStringLiteral("0:00");

    const qint64 totalSeconds = milliseconds / 1000;
    const qint64 hours = totalSeconds / 3600;
    const qint64 minutes = (totalSeconds % 3600) / 60;
    const qint64 seconds = totalSeconds % 60;

    if (hours > 0) {
        return QStringLiteral("%1:%2:%3")
            .arg(hours)
            .arg(minutes, 2, 10, QLatin1Char('0'))
            .arg(seconds, 2, 10, QLatin1Char('0'));
    }
    return QStringLiteral("%1:%2").arg(minutes).arg(seconds, 2, 10, QLatin1Char('0'));
}

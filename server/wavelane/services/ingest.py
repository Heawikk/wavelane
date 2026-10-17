"""Turning an uploaded audio file into catalogue rows.

Tag extraction is deliberately format-agnostic: mutagen gives us ID3,
VorbisComment and MP4 atoms under different key names, so every field is
looked up through a list of aliases rather than one hard-coded key.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import anyio
import mutagen
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..models import (
    Album,
    AlbumType,
    Artist,
    ArtistRole,
    AudioFeature,
    Genre,
    Track,
    TrackArtist,
    TrackGenre,
    TrackStatus,
)
from ..utils import normalize_name, now_utc, slugify
from ..wave.features import canonical_genre, normalize_tempo
from .audio_analysis import AudioAnalyzer, get_analyzer
from .storage import Storage, StoredFile, get_storage

logger = logging.getLogger(__name__)

# Main credits are split only on the separators tags actually reserve for the
# purpose. Commas, "&" and "and" are left alone on purpose: "Earth, Wind & Fire"
# and "Simon and Garfunkel" are one act each, and genuinely multi-valued tags
# already reach us as separate values from mutagen.
_MAIN_SPLIT = re.compile(r"\s*[;/|]\s*")
# After a "feat." marker the convention is looser, so split more eagerly there.
_FEAT_SPLIT = re.compile(r"\s*(?:[;/|,]|&|\band\b|\bwith\b)\s*", re.IGNORECASE)
# The optional dot sits outside the word boundary deliberately: in
# r"\bfeat\.?\b" the trailing \b cannot match between "." and a space, so
# "feat. Guest" would split on "feat" alone and leave the dot stuck to the
# guest's name. Trailing whitespace is consumed for the same reason.
_FEATURE_MARKER = re.compile(r"\b(?:feat|ft|featuring)\b\.?\s*", re.IGNORECASE)
_YEAR_RE = re.compile(r"(\d{4})")
_TRACK_NUM_RE = re.compile(r"^\s*(\d+)")


@dataclass(slots=True)
class TrackMetadata:
    """Everything we could read out of the file's tags and headers."""

    title: str = ""
    artists: list[str] = field(default_factory=list)
    featured_artists: list[str] = field(default_factory=list)
    album: str = ""
    album_artist: str = ""
    genres: list[str] = field(default_factory=list)
    track_number: int | None = None
    disc_number: int = 1
    total_tracks: int | None = None
    release_date: date | None = None
    release_year: int | None = None
    label: str | None = None
    isrc: str | None = None
    lyrics: str | None = None
    comment: str | None = None
    explicit: bool = False

    duration_ms: int = 0
    bitrate_kbps: int | None = None
    sample_rate: int | None = None
    channels: int | None = None
    codec: str | None = None

    cover_data: bytes | None = None
    cover_mime: str | None = None

    @property
    def primary_artist(self) -> str:
        if self.artists:
            return self.artists[0]
        if self.album_artist:
            return self.album_artist
        return "Unknown Artist"

    @property
    def artist_display(self) -> str:
        return ", ".join(self.artists) or self.primary_artist


# ---------------------------------------------------------------------------
# Tag reading
# ---------------------------------------------------------------------------

# Field -> candidate tag keys, in priority order, across ID3/Vorbis/MP4.
_TAG_ALIASES: dict[str, tuple[str, ...]] = {
    "title": ("title", "TIT2", "\xa9nam"),
    "artist": ("artist", "TPE1", "\xa9ART"),
    "album_artist": ("albumartist", "album artist", "TPE2", "aART"),
    "album": ("album", "TALB", "\xa9alb"),
    "genre": ("genre", "TCON", "\xa9gen"),
    "date": ("date", "year", "originaldate", "TDRC", "TYER", "TDRL", "\xa9day"),
    "track": ("tracknumber", "TRCK", "trkn"),
    "disc": ("discnumber", "TPOS", "disk"),
    "label": ("label", "organization", "publisher", "TPUB"),
    "isrc": ("isrc", "TSRC"),
    "lyrics": ("lyrics", "unsyncedlyrics", "USLT", "\xa9lyr", "\xa9lyrics"),
    "comment": ("comment", "COMM", "\xa9cmt"),
    "compilation": ("compilation", "TCMP", "cpil"),
}


def read_metadata(path: Path, source_hint: Path | str | None = None) -> TrackMetadata:
    """Read tags and stream info. Never raises for a readable audio file.

    ``path`` is where the file now lives, which for stored audio is a
    content-addressed name like ``ab/cd/<sha256>.mp3``. Plenty of files carry no
    tags at all, and for those the filename is the only metadata there is — so
    ``source_hint`` carries the name the file arrived under, and every
    filename-derived guess uses that instead of the hash.
    """
    hint = Path(source_hint) if source_hint else path

    meta = TrackMetadata()
    try:
        audio = mutagen.File(path)
    except Exception as exc:
        logger.warning("mutagen could not open %s: %s", path, exc)
        audio = None

    if audio is None:
        meta.title = _title_from_filename(hint)
        meta.artists = [_artist_from_filename(hint) or "Unknown Artist"]
        return meta

    _read_stream_info(audio, meta)
    tags = _flatten_tags(audio)
    _apply_tags(tags, meta)
    _read_cover(audio, hint if hint.parent.is_dir() else path, meta)

    if not meta.title:
        meta.title = _title_from_filename(hint)
    if not meta.artists:
        guessed = _artist_from_filename(hint)
        meta.artists = [guessed] if guessed else ["Unknown Artist"]
    if meta.track_number is None:
        match = _TRACK_NUM_RE.match(hint.stem)
        if match:
            number = int(match.group(1))
            if 0 < number < 200:
                meta.track_number = number
    return meta


def _read_stream_info(audio: Any, meta: TrackMetadata) -> None:
    info = getattr(audio, "info", None)
    if info is None:
        return
    length = getattr(info, "length", 0.0) or 0.0
    meta.duration_ms = int(round(length * 1000))
    bitrate = getattr(info, "bitrate", None)
    if bitrate:
        meta.bitrate_kbps = int(bitrate // 1000)
    meta.sample_rate = getattr(info, "sample_rate", None)
    meta.channels = getattr(info, "channels", None)
    meta.codec = _codec_name(audio, info)


def _codec_name(audio: Any, info: Any) -> str:
    for attribute in ("codec", "codec_description"):
        value = getattr(info, attribute, None)
        if value:
            return str(value).lower()
    mime = getattr(audio, "mime", None)
    if mime:
        return str(mime[0]).split("/")[-1].lower()
    return type(info).__name__.lower()


def _flatten_tags(audio: Any) -> dict[str, list[str]]:
    """Normalise every tag container into lowercase key -> list of strings."""
    out: dict[str, list[str]] = {}
    tags = getattr(audio, "tags", None)
    if tags is None:
        return out

    if isinstance(tags, ID3):
        for frame in tags.values():
            key = getattr(frame, "FrameID", type(frame).__name__)
            values = _frame_values(frame)
            if values:
                out.setdefault(key.lower(), []).extend(values)
                # TXXX frames carry their real name in .desc.
                desc = getattr(frame, "desc", None)
                if desc:
                    out.setdefault(str(desc).lower(), []).extend(values)
        return out

    try:
        items = tags.items()
    except Exception:
        return out

    for key, value in items:
        values = _frame_values(value)
        if values:
            out.setdefault(str(key).lower(), []).extend(values)
    return out


def _frame_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, bytes):
        return [value.decode("utf-8", "replace")]
    if isinstance(value, str):
        return [value]
    if isinstance(value, bool):
        return ["1" if value else "0"]
    if isinstance(value, int | float):
        return [str(value)]
    if isinstance(value, tuple):
        # MP4 trkn/disk arrive as ((track, total),).
        return ["/".join(str(part) for part in value if part is not None)]
    if isinstance(value, Iterable):
        collected: list[str] = []
        for item in value:
            collected.extend(_frame_values(item))
        return collected
    text = getattr(value, "text", None)
    if text is not None:
        return _frame_values(text)
    return [str(value)]


def _lookup(tags: dict[str, list[str]], field_name: str) -> list[str]:
    for alias in _TAG_ALIASES.get(field_name, ()):
        values = tags.get(alias.lower())
        if values:
            return [v for v in (s.strip() for s in values) if v]
    return []


def _apply_tags(tags: dict[str, list[str]], meta: TrackMetadata) -> None:
    titles = _lookup(tags, "title")
    if titles:
        meta.title = titles[0]

    raw_artists = _lookup(tags, "artist")
    album_artists = _lookup(tags, "album_artist")
    meta.album_artist = album_artists[0] if album_artists else ""

    main, featured = _split_artists(raw_artists, meta.title)
    meta.artists = main
    meta.featured_artists = featured
    if not meta.artists and meta.album_artist:
        meta.artists = [meta.album_artist]

    albums = _lookup(tags, "album")
    if albums:
        meta.album = albums[0]

    genres: list[str] = []
    for value in _lookup(tags, "genre"):
        genres.extend(_split_genres(value))
    meta.genres = _dedupe(genres)

    dates = _lookup(tags, "date")
    if dates:
        meta.release_date, meta.release_year = _parse_date(dates[0])

    tracks = _lookup(tags, "track")
    if tracks:
        meta.track_number, meta.total_tracks = _parse_pair(tracks[0])

    discs = _lookup(tags, "disc")
    if discs:
        disc, _ = _parse_pair(discs[0])
        meta.disc_number = disc or 1

    labels = _lookup(tags, "label")
    if labels:
        meta.label = labels[0][:300]

    isrcs = _lookup(tags, "isrc")
    if isrcs:
        meta.isrc = isrcs[0][:20]

    lyrics = _lookup(tags, "lyrics")
    if lyrics:
        meta.lyrics = lyrics[0]

    comments = _lookup(tags, "comment")
    if comments:
        meta.comment = comments[0][:2000]

    advisory = tags.get("itunesadvisory") or tags.get("rtng")
    if advisory and advisory[0] not in {"0", ""}:
        meta.explicit = True
    haystack = f"{meta.title} {meta.comment or ''}".lower()
    if "explicit" in haystack:
        meta.explicit = True


def _split_artists(raw_artists: list[str], title: str) -> tuple[list[str], list[str]]:
    """Separate main credits from featured ones, including a 'feat.' in the title."""
    main: list[str] = []
    featured: list[str] = []

    for entry in raw_artists:
        if _FEATURE_MARKER.search(entry):
            parts = _FEATURE_MARKER.split(entry)
            main.extend(_split_credit(parts[0], _MAIN_SPLIT))
            featured.extend(_split_credit(" ".join(parts[1:]), _FEAT_SPLIT))
        else:
            main.extend(_split_credit(entry, _MAIN_SPLIT))

    # "Song Title (feat. Someone)" is extremely common and belongs in credits.
    if _FEATURE_MARKER.search(title):
        tail = _FEATURE_MARKER.split(title)[-1].strip(" )(]['\"")
        featured.extend(_split_credit(tail, _FEAT_SPLIT))

    main = _dedupe(main)
    featured = [a for a in _dedupe(featured) if normalize_name(a) not in
                {normalize_name(m) for m in main}]
    return main, featured


def _split_credit(value: str, pattern: re.Pattern[str]) -> list[str]:
    if not value:
        return []
    parts = [part.strip(" )(-–—") for part in pattern.split(value)]
    return [part for part in parts if len(part) > 1]


def _split_genres(value: str) -> list[str]:
    parts = re.split(r"[;,/|]", value)
    return [part.strip() for part in parts if part.strip()]


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = normalize_name(value)
        if key and key not in seen:
            seen.add(key)
            out.append(value)
    return out


def _parse_date(value: str) -> tuple[date | None, int | None]:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y", "%Y-%m"):
        try:
            from datetime import datetime

            parsed = datetime.strptime(value, fmt).date()
            return parsed, parsed.year
        except ValueError:
            continue
    match = _YEAR_RE.search(value)
    if match:
        year = int(match.group(1))
        if 1860 <= year <= 2200:
            return None, year
    return None, None


def _parse_pair(value: str) -> tuple[int | None, int | None]:
    """Parse "3/12" or "3" into (3, 12) / (3, None)."""
    value = value.strip()
    if not value:
        return None, None
    head, _, tail = value.partition("/")
    try:
        number = int(re.sub(r"\D", "", head) or 0) or None
    except ValueError:
        number = None
    try:
        total = int(re.sub(r"\D", "", tail) or 0) or None
    except ValueError:
        total = None
    return number, total


def _read_cover(audio: Any, path: Path, meta: TrackMetadata) -> None:
    """Pull embedded artwork; fall back to cover.jpg next to the file."""
    try:
        if isinstance(audio, FLAC) and audio.pictures:
            picture: Picture = audio.pictures[0]
            meta.cover_data, meta.cover_mime = bytes(picture.data), picture.mime
        elif isinstance(audio, MP4):
            covers = audio.tags.get("covr") if audio.tags else None
            if covers:
                cover = covers[0]
                image_format = getattr(cover, "imageformat", None)
                mime = "image/png" if image_format == MP4.MP4Cover.FORMAT_PNG else "image/jpeg"
                meta.cover_data, meta.cover_mime = bytes(cover), mime
        elif isinstance(audio, OggVorbis):
            encoded = (audio.tags or {}).get("metadata_block_picture")
            if encoded:
                import base64

                picture = Picture(base64.b64decode(encoded[0]))
                meta.cover_data, meta.cover_mime = bytes(picture.data), picture.mime
        else:
            tags = getattr(audio, "tags", None)
            if isinstance(tags, ID3):
                pictures = tags.getall("APIC")
                if pictures:
                    meta.cover_data = bytes(pictures[0].data)
                    meta.cover_mime = pictures[0].mime
    except Exception as exc:
        logger.debug("cover extraction failed for %s: %s", path, exc)

    if meta.cover_data:
        return

    for name in ("cover.jpg", "cover.png", "folder.jpg", "front.jpg", "cover.jpeg"):
        candidate = path.parent / name
        if candidate.is_file() and candidate.stat().st_size < 12 * 1024 * 1024:
            meta.cover_data = candidate.read_bytes()
            meta.cover_mime = "image/png" if candidate.suffix == ".png" else "image/jpeg"
            return


def _title_from_filename(path: Path) -> str:
    stem = re.sub(r"^\s*\d+\s*[-._)]\s*", "", path.stem)
    if " - " in stem:
        stem = stem.split(" - ", 1)[1]
    return stem.replace("_", " ").strip() or path.stem


def _artist_from_filename(path: Path) -> str | None:
    stem = re.sub(r"^\s*\d+\s*[-._)]\s*", "", path.stem)
    if " - " in stem:
        return stem.split(" - ", 1)[0].replace("_", " ").strip() or None
    return None


# ---------------------------------------------------------------------------
# Ingest service
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class IngestResult:
    track: Track
    created: bool
    metadata: TrackMetadata


class IngestService:
    """Creates or reuses artist/album/genre rows and attaches audio features."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        storage: Storage | None = None,
        analyzer: AudioAnalyzer | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.storage = storage or get_storage()
        self.analyzer = analyzer or get_analyzer()

    async def ingest_file(
        self,
        stored: StoredFile,
        *,
        uploaded_by_id: Any = None,
        source_hint: Path | str | None = None,
        metadata_override: dict[str, Any] | None = None,
        analyze: bool | None = None,
    ) -> IngestResult:
        existing = await self.session.scalar(
            select(Track).where(Track.content_hash == stored.content_hash)
        )
        if existing is not None:
            logger.info("track already in catalogue: %s", stored.content_hash[:12])
            return IngestResult(track=existing, created=False, metadata=TrackMetadata())

        meta = await anyio.to_thread.run_sync(
            read_metadata, stored.absolute_path, source_hint
        )
        if metadata_override:
            _apply_override(meta, metadata_override)

        artists = await self._upsert_artists(meta)
        album = await self._upsert_album(meta, artists)
        genres = await self._upsert_genres(meta.genres)

        # Build every relationship up front and hand them to the constructor.
        # Passing a collection (even an empty one) marks it loaded, so nothing
        # later tries to lazy-load it from synchronous serialisation code and
        # fails with MissingGreenlet.
        artist_links: list[TrackArtist] = []
        position = 0
        for role, group in (
            (ArtistRole.MAIN, artists["main"]),
            (ArtistRole.FEATURED, artists["featured"]),
        ):
            for artist in group:
                # Assign the object, not just the foreign key, so the link's
                # own `artist` relationship is populated too.
                artist_links.append(
                    TrackArtist(artist=artist, role=role, position=position)
                )
                position += 1

        genre_links = [TrackGenre(genre=genre) for genre in genres]

        should_analyze = self.settings.analyze_on_upload if analyze is None else analyze
        features = (
            await self._build_features(stored.absolute_path, meta)
            if should_analyze
            else None
        )

        track = Track(
            title=meta.title,
            normalized_title=normalize_name(meta.title),
            # Assign the object so `track.album` is loaded; setting only the
            # foreign key would leave it to a lazy load during serialisation.
            album=album,
            track_number=meta.track_number,
            disc_number=meta.disc_number or 1,
            duration_ms=meta.duration_ms,
            storage_path=stored.relative_path,
            content_hash=stored.content_hash,
            file_size=stored.size,
            container=stored.container,
            codec=meta.codec,
            bitrate_kbps=meta.bitrate_kbps,
            sample_rate=meta.sample_rate,
            channels=meta.channels,
            lossless=stored.lossless,
            explicit=meta.explicit,
            lyrics=meta.lyrics,
            isrc=meta.isrc,
            status=TrackStatus.READY,
            uploaded_by_id=uploaded_by_id,
            artist_links=artist_links,
            genre_links=genre_links,
            features=features,
        )
        self.session.add(track)
        await self.session.flush()

        # Keep denormalised counters in step.
        for artist in artists["main"]:
            artist.track_count += 1
        if album:
            album.total_tracks = max(album.total_tracks, meta.total_tracks or 0)

        await self.session.flush()
        return IngestResult(track=track, created=True, metadata=meta)

    async def _build_features(self, path: Path, meta: TrackMetadata) -> AudioFeature:
        # DSP analysis decodes audio and runs FFTs: seconds of CPU per track.
        # Running it inline would stall every other request on the event loop.
        result = await anyio.to_thread.run_sync(
            lambda: self.analyzer.analyze(
                path,
                title=meta.title,
                artist=meta.artist_display,
                genres=meta.genres,
                release_year=meta.release_year,
                duration_ms=meta.duration_ms,
                lyrics=meta.lyrics,
            )
        )
        return AudioFeature(
            tempo_bpm=result.tempo_bpm,
            energy=result.energy,
            valence=result.valence,
            danceability=result.danceability,
            acousticness=result.acousticness,
            instrumentalness=result.instrumentalness,
            brightness=result.brightness,
            loudness=result.loudness,
            dynamics=result.dynamics,
            vocalness=result.vocalness,
            language=result.language,
            musical_key=result.musical_key,
            musical_mode=result.musical_mode,
            vector=result.vector,
            source=result.source,
            analyzer_version=result.analyzer_version,
            analyzed_at=now_utc(),
        )

    async def _upsert_artists(self, meta: TrackMetadata) -> dict[str, list[Artist]]:
        main = [await self._get_or_create_artist(name) for name in meta.artists]
        featured = [await self._get_or_create_artist(name) for name in meta.featured_artists]
        if not main:
            main = [await self._get_or_create_artist("Unknown Artist")]
        return {"main": main, "featured": featured}

    async def _get_or_create_artist(self, name: str) -> Artist:
        normalized = normalize_name(name)
        artist = await self.session.scalar(
            select(Artist).where(Artist.normalized_name == normalized)
        )
        if artist is not None:
            return artist
        artist = Artist(name=name.strip(), normalized_name=normalized, sort_name=name.strip())
        self.session.add(artist)
        await self.session.flush()
        return artist

    async def _upsert_album(
        self, meta: TrackMetadata, artists: dict[str, list[Artist]]
    ) -> Album | None:
        if not meta.album:
            return None

        # Album artist wins: a compilation should not be filed under track 1's artist.
        if meta.album_artist:
            owner = await self._get_or_create_artist(meta.album_artist)
        else:
            owner = artists["main"][0]

        normalized = normalize_name(meta.album)
        album = await self.session.scalar(
            select(Album).where(
                Album.artist_id == owner.id, Album.normalized_title == normalized
            )
        )
        if album is None:
            album = Album(
                title=meta.album.strip(),
                normalized_title=normalized,
                artist_id=owner.id,
                album_type=_guess_album_type(meta),
                release_date=meta.release_date,
                release_year=meta.release_year,
                label=meta.label,
                total_tracks=meta.total_tracks or 0,
            )
            self.session.add(album)
            await self.session.flush()

        if meta.cover_data and not album.cover_path:
            try:
                album.cover_path = self.storage.save_cover(meta.cover_data, meta.cover_mime)
            except Exception as exc:
                logger.warning("could not store cover for %s: %s", meta.album, exc)
        if album.release_year is None and meta.release_year:
            album.release_year = meta.release_year
            album.release_date = album.release_date or meta.release_date
        return album

    async def _upsert_genres(self, names: Iterable[str]) -> list[Genre]:
        out: list[Genre] = []
        for name in names:
            slug = slugify(name)
            if not slug:
                continue
            genre = await self.session.scalar(select(Genre).where(Genre.slug == slug))
            if genre is None:
                parent = canonical_genre(name)
                genre = Genre(
                    name=name.strip(),
                    slug=slug,
                    parent_slug=parent if parent != slug else None,
                )
                self.session.add(genre)
                await self.session.flush()
            out.append(genre)
        return out


def _guess_album_type(meta: TrackMetadata) -> AlbumType:
    total = meta.total_tracks or 0
    lowered = meta.album.lower()
    if "single" in lowered or total == 1:
        return AlbumType.SINGLE
    if " ep" in lowered or lowered.endswith("ep") or 2 <= total <= 6:
        return AlbumType.EP
    if "live" in lowered:
        return AlbumType.LIVE
    if any(word in lowered for word in ("compilation", "greatest hits", "best of", "сборник")):
        return AlbumType.COMPILATION
    return AlbumType.ALBUM


def _apply_override(meta: TrackMetadata, override: dict[str, Any]) -> None:
    """Let an uploader correct bad tags without re-encoding the file."""
    simple = (
        "title", "album", "album_artist", "label", "isrc", "lyrics",
        "track_number", "disc_number", "total_tracks", "release_year", "explicit",
    )
    for key in simple:
        value = override.get(key)
        if value not in (None, ""):
            setattr(meta, key, value)

    if override.get("artists"):
        meta.artists = _dedupe(list(override["artists"]))
    if override.get("featured_artists"):
        meta.featured_artists = _dedupe(list(override["featured_artists"]))
    if override.get("genres"):
        meta.genres = _dedupe(list(override["genres"]))
    if override.get("release_date"):
        value = override["release_date"]
        meta.release_date = value
        meta.release_year = getattr(value, "year", meta.release_year)


__all__ = [
    "IngestResult",
    "IngestService",
    "TrackMetadata",
    "normalize_tempo",
    "read_metadata",
]

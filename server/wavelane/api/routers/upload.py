"""Uploading audio, scanning server folders, re-running analysis."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

import anyio
from fastapi import APIRouter, File, HTTPException, UploadFile, status

from ...models import AudioFeature, Track, TrackStatus
from ...schemas.catalog import TrackOut
from ...schemas.common import Message
from ...schemas.upload import ScanRequest, ScanResult, UploadedTrack, UploadResult
from ...services.audio_analysis import get_analyzer
from ...services.catalog import serialize_tracks
from ...services.ingest import IngestService, read_metadata
from ...services.storage import (
    AUDIO_EXTENSIONS,
    StorageError,
    UnsupportedFormatError,
)
from ...utils import now_utc
from ...wave.features import normalize_tempo
from ..deps import AdminUser, AppSettings, CurrentUser, DbSession, FileStorage

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingest"])

MAX_FILES_PER_REQUEST = 50


@router.post(
    "/upload",
    response_model=UploadResult,
    status_code=status.HTTP_201_CREATED,
    summary="Upload one or more audio files",
)
async def upload_tracks(
    db: DbSession,
    user: CurrentUser,
    storage: FileStorage,
    settings: AppSettings,
    files: list[UploadFile] = File(..., description="Audio files (mp3, flac, m4a, ogg, ...)"),
) -> UploadResult:
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"at most {MAX_FILES_PER_REQUEST} files per request",
        )

    service = IngestService(db, storage=storage, settings=settings)
    result = UploadResult()

    for upload in files:
        filename = upload.filename or "unnamed"
        try:
            # Staging and analysis are blocking file/CPU work; keep them off the
            # event loop so other requests are still served during an upload.
            temp_path = await anyio.to_thread.run_sync(
                storage.stage_upload, upload.file, filename, settings.max_upload_bytes
            )
        except UnsupportedFormatError as exc:
            result.failed += 1
            result.items.append(
                UploadedTrack(filename=filename, created=False, error=str(exc))
            )
            continue
        except StorageError as exc:
            result.failed += 1
            result.items.append(
                UploadedTrack(filename=filename, created=False, error=str(exc))
            )
            continue
        finally:
            await upload.close()

        try:
            stored = await anyio.to_thread.run_sync(storage.commit_audio, temp_path)
            ingested = await service.ingest_file(
                stored, uploaded_by_id=user.id, source_hint=filename
            )
        except Exception as exc:
            logger.exception("ingest failed for %s", filename)
            Path(temp_path).unlink(missing_ok=True)
            result.failed += 1
            result.items.append(
                UploadedTrack(filename=filename, created=False, error=str(exc))
            )
            continue

        serialized = (await serialize_tracks(db, [ingested.track], user.id))[0]
        if ingested.created:
            result.uploaded += 1
        else:
            result.duplicates += 1
        result.items.append(
            UploadedTrack(
                filename=filename, created=ingested.created, track=serialized
            )
        )

    await db.flush()
    return result


@router.post(
    "/admin/scan",
    response_model=ScanResult,
    summary="Import every audio file under a server-side folder (admin)",
)
async def scan_folder(
    payload: ScanRequest,
    db: DbSession,
    admin: AdminUser,
    storage: FileStorage,
    settings: AppSettings,
) -> ScanResult:
    root = Path(payload.path).expanduser()
    if not root.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"path does not exist: {root}"
        )
    if not root.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"not a directory: {root}"
        )

    pattern = "**/*" if payload.recursive else "*"
    candidates = [
        path
        for path in sorted(root.glob(pattern))
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
    ][: payload.limit]

    service = IngestService(db, storage=storage, settings=settings)
    result = ScanResult(scanned=len(candidates))

    for path in candidates:
        try:
            stored = await anyio.to_thread.run_sync(storage.import_existing, path)
            ingested = await service.ingest_file(
                stored,
                uploaded_by_id=admin.id,
                source_hint=path,
                analyze=payload.analyze,
            )
        except Exception as exc:
            result.failed += 1
            if len(result.errors) < 50:
                result.errors.append(f"{path.name}: {exc}")
            logger.warning("scan failed for %s: %s", path, exc)
            continue

        if ingested.created:
            result.imported += 1
            result.track_ids.append(ingested.track.id)
        else:
            result.duplicates += 1

    await db.flush()
    return result


@router.post(
    "/tracks/{track_id}/reanalyze",
    response_model=TrackOut,
    summary="Re-run audio analysis for one track",
)
async def reanalyze_track(
    track_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    storage: FileStorage,
) -> TrackOut:
    track = await db.get(Track, track_id)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="track not found")
    if not user.is_admin and track.uploaded_by_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only the uploader or an administrator can re-analyse this track",
        )

    path = storage.audio_path(track.storage_path)
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail="audio file is missing from storage"
        )

    metadata = await anyio.to_thread.run_sync(read_metadata, path)
    analyzer = get_analyzer()
    genres = [link.genre.slug for link in track.genre_links if link.genre]
    album_year = track.album.release_year if track.album else metadata.release_year

    analysis = await anyio.to_thread.run_sync(
        lambda: analyzer.analyze(
            path,
            title=track.title,
            artist=track.artist_display,
            genres=genres,
            release_year=album_year,
            duration_ms=track.duration_ms,
            lyrics=track.lyrics,
        )
    )

    features = track.features or AudioFeature(track_id=track.id)
    features.tempo_bpm = analysis.tempo_bpm
    features.energy = analysis.energy
    features.valence = analysis.valence
    features.danceability = analysis.danceability
    features.acousticness = analysis.acousticness
    features.instrumentalness = analysis.instrumentalness
    features.brightness = analysis.brightness
    features.loudness = analysis.loudness
    features.dynamics = analysis.dynamics
    features.vocalness = analysis.vocalness
    features.language = analysis.language
    features.musical_key = analysis.musical_key
    features.musical_mode = analysis.musical_mode
    features.vector = analysis.vector
    features.source = analysis.source
    features.analyzer_version = analysis.analyzer_version
    features.analyzed_at = now_utc()
    db.add(features)

    track.status = TrackStatus.READY
    await db.flush()
    await db.refresh(track, ["features"])
    return (await serialize_tracks(db, [track], user.id, include_features=True))[0]


@router.get(
    "/admin/analysis-status",
    response_model=Message,
    summary="Whether DSP analysis is available (admin)",
)
async def analysis_status(admin: AdminUser) -> Message:
    analyzer = get_analyzer()
    if analyzer.dsp_available:
        return Message(detail="ffmpeg found: full DSP analysis is active")
    return Message(
        detail=(
            "ffmpeg not found: falling back to metadata-only feature estimates. "
            "Install ffmpeg or set WAVELANE_FFMPEG_PATH for tempo, key and "
            "energy analysis."
        )
    )


__all__ = ["normalize_tempo", "router"]

"""Folder imports, unresolved conflicts, and library clean-up. Administrators only."""

from __future__ import annotations

import logging
from pathlib import Path

import anyio
from fastapi import APIRouter, HTTPException, status

from ...models import Track
from ...schemas.upload import (
    CleanupResult,
    ConflictOut,
    ImportJobOut,
    ImportStart,
    ResolveRequest,
    ResolveResult,
)
from ...services.conflicts import (
    describe_conflict,
    get_conflict_registry,
    resolve_conflict,
)
from ...services.imports import ImportJob, get_import_manager
from ...services.ingest import IngestService
from ...services.removal import cleanup_orphans
from ..deps import AdminUser, AppSettings, DbSession, FileStorage

logger = logging.getLogger(__name__)

router = APIRouter(tags=["imports"])


def _job_out(job: ImportJob) -> ImportJobOut:
    return ImportJobOut(
        id=job.id,
        state=job.state,
        path=job.path,
        total=job.total,
        processed=job.processed,
        imported=job.imported,
        duplicates=job.duplicates,
        conflicts=job.conflicts,
        failed=job.failed,
        current=job.current,
        errors=list(job.errors),
        analyze=job.analyze,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


# ---------------------------------------------------------------------------
# Folder imports
# ---------------------------------------------------------------------------


@router.post(
    "/admin/imports",
    response_model=ImportJobOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start importing a server-side folder in the background",
)
async def start_import(payload: ImportStart, admin: AdminUser) -> ImportJobOut:
    # anyio.Path so that probing a slow or network drive does not stall the loop.
    probe = await anyio.Path(payload.path).expanduser()
    if not await probe.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"path does not exist: {probe}"
        )
    if not await probe.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"not a directory: {probe}"
        )
    root = Path(probe)

    manager = get_import_manager()
    running = manager.active()
    if running is not None:
        # Two imports would contend for the same database lock and the same
        # CPUs; one at a time is faster as well as simpler.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"an import is already running ({running.path})",
        )

    job = manager.start(
        user_id=admin.id, path=root, analyze=payload.analyze, recursive=payload.recursive
    )
    return _job_out(job)


@router.get("/admin/imports", response_model=list[ImportJobOut], summary="Recent imports")
async def list_imports(admin: AdminUser) -> list[ImportJobOut]:
    return [_job_out(job) for job in get_import_manager().recent()]


@router.get(
    "/admin/imports/{job_id}", response_model=ImportJobOut, summary="Progress of one import"
)
async def get_import(job_id: str, admin: AdminUser) -> ImportJobOut:
    job = get_import_manager().get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="import not found")
    return _job_out(job)


@router.post(
    "/admin/imports/{job_id}/cancel",
    response_model=ImportJobOut,
    summary="Stop an import after the files already in progress",
)
async def cancel_import(job_id: str, admin: AdminUser) -> ImportJobOut:
    job = get_import_manager().cancel(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="import not found")
    return _job_out(job)


# ---------------------------------------------------------------------------
# Conflicts
# ---------------------------------------------------------------------------


@router.get(
    "/imports/conflicts",
    response_model=list[ConflictOut],
    summary="Files waiting for an old-or-new decision",
)
async def list_conflicts(db: DbSession, admin: AdminUser) -> list[ConflictOut]:
    registry = get_conflict_registry()
    out: list[ConflictOut] = []
    for pending in registry.all():
        existing = await db.get(Track, pending.existing_track_id)
        if existing is None:
            # The track it would have replaced was deleted while the question
            # was open, so there is nothing left to compare against. The
            # conflict can still be resolved by id; resolving it imports the
            # file as a track of its own.
            continue
        out.append(describe_conflict(pending, existing))
    return out


@router.post(
    "/imports/conflicts/resolve",
    response_model=ResolveResult,
    summary="Keep the old file or replace it with the new one",
)
async def resolve_conflicts(
    payload: ResolveRequest,
    db: DbSession,
    admin: AdminUser,
    storage: FileStorage,
    settings: AppSettings,
) -> ResolveResult:
    registry = get_conflict_registry()
    service = IngestService(db, storage=storage, settings=settings)
    result = ResolveResult()

    for item in payload.resolutions:
        try:
            resolution = await resolve_conflict(
                db, service, registry, item.conflict_id, item.action
            )
        except Exception as exc:
            logger.exception("could not resolve conflict %s", item.conflict_id)
            result.errors.append(f"{item.conflict_id}: {exc}")
            continue

        if resolution.action == "replaced":
            result.replaced += 1
        elif resolution.action == "kept_old":
            result.kept_old += 1
        elif resolution.action == "created":
            result.created += 1
        else:
            result.not_found += 1

    # Commit first, then unlink: a file must not vanish before the database
    # stops pointing at it.
    await db.commit()
    service.apply_deferred_deletes()
    return result


# ---------------------------------------------------------------------------
# Clean-up
# ---------------------------------------------------------------------------


@router.post(
    "/admin/cleanup",
    response_model=CleanupResult,
    summary="Delete audio files that no track refers to",
)
async def cleanup(db: DbSession, admin: AdminUser, storage: FileStorage) -> CleanupResult:
    registry = get_conflict_registry()
    staged = [item.prepared.stored.relative_path for item in registry.all()]
    try:
        removed, freed = await cleanup_orphans(db, storage, keep=staged)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return CleanupResult(files_removed=removed, bytes_freed=freed)


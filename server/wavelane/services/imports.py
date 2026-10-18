"""Importing a whole folder of music as a background job.

A music folder can hold thousands of files and analysing each takes seconds, so
the import runs as a task with progress rather than inside one HTTP request that
would time out long before it finished.

Each file goes through two phases. Reading tags and analysing audio touches no
database state, so several files run through it side by side. Writing the
result to the catalogue is quick and must not overlap, since two files by the
same new artist would both try to create it, so that step takes a lock.
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import anyio

from ..config import get_settings
from ..db import get_session_factory
from ..utils import now_utc
from .conflicts import get_conflict_registry
from .ingest import ConflictPolicy, IngestService
from .storage import AUDIO_EXTENSIONS, get_storage

logger = logging.getLogger(__name__)

MAX_ERRORS_KEPT = 50
MAX_JOBS_KEPT = 20


def default_workers() -> int:
    configured = get_settings().import_workers
    if configured > 0:
        return configured
    # Analysis is CPU and ffmpeg work; leave half the machine for everything else.
    return max(1, min(4, (os.cpu_count() or 2) // 2))


def collect_audio_files(root: Path, recursive: bool) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    return sorted(
        path
        for path in root.glob(pattern)
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
    )


@dataclass(slots=True)
class ImportJob:
    id: str
    user_id: uuid.UUID
    path: str
    analyze: bool
    state: str = "scanning"      # scanning | running | done | cancelled | failed
    total: int = 0
    processed: int = 0
    imported: int = 0
    duplicates: int = 0
    conflicts: int = 0
    failed: int = 0
    current: str = ""
    errors: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=now_utc)
    finished_at: datetime | None = None
    cancel_requested: bool = False
    task: asyncio.Task | None = None

    @property
    def finished(self) -> bool:
        return self.state in ("done", "cancelled", "failed")

    def note_error(self, message: str) -> None:
        self.failed += 1
        if len(self.errors) < MAX_ERRORS_KEPT:
            self.errors.append(message)


class ImportManager:
    def __init__(self) -> None:
        self.jobs: dict[str, ImportJob] = {}
        self.db_lock = asyncio.Lock()

    def active(self) -> ImportJob | None:
        return next((job for job in self.jobs.values() if not job.finished), None)

    def get(self, job_id: str) -> ImportJob | None:
        return self.jobs.get(job_id)

    def recent(self) -> list[ImportJob]:
        return sorted(self.jobs.values(), key=lambda job: job.started_at, reverse=True)

    def start(
        self, *, user_id: uuid.UUID, path: Path, analyze: bool, recursive: bool
    ) -> ImportJob:
        job = ImportJob(
            id=secrets.token_urlsafe(8), user_id=user_id, path=str(path), analyze=analyze
        )
        self.jobs[job.id] = job
        self._trim()
        job.task = asyncio.create_task(self._run(job, path, recursive))
        return job

    def cancel(self, job_id: str) -> ImportJob | None:
        job = self.jobs.get(job_id)
        if job is not None and not job.finished:
            job.cancel_requested = True
        return job

    def _trim(self) -> None:
        finished = [job for job in self.recent() if job.finished]
        for job in finished[MAX_JOBS_KEPT:]:
            self.jobs.pop(job.id, None)

    # --- the job itself -----------------------------------------------------

    async def _run(self, job: ImportJob, root: Path, recursive: bool) -> None:
        try:
            files = await anyio.to_thread.run_sync(collect_audio_files, root, recursive)
            job.total = len(files)
            job.state = "running"

            queue: asyncio.Queue[Path] = asyncio.Queue()
            for path in files:
                queue.put_nowait(path)

            workers = [
                asyncio.create_task(self._worker(job, queue))
                for _ in range(min(default_workers(), max(1, len(files))))
            ]
            await asyncio.gather(*workers)

            job.state = "cancelled" if job.cancel_requested else "done"
        except Exception as exc:  # the job must always reach a terminal state
            logger.exception("import %s failed", job.id)
            job.state = "failed"
            job.note_error(f"import aborted: {exc}")
        finally:
            job.current = ""
            job.finished_at = now_utc()

    async def _worker(self, job: ImportJob, queue: asyncio.Queue[Path]) -> None:
        while not job.cancel_requested:
            try:
                path = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            job.current = path.name
            try:
                await self._import_one(job, path)
            except Exception as exc:
                logger.warning("import of %s failed: %s", path, exc)
                job.note_error(f"{path.name}: {exc}")
            finally:
                job.processed += 1

    async def _import_one(self, job: ImportJob, path: Path) -> None:
        storage = get_storage()
        stored = await anyio.to_thread.run_sync(storage.import_existing, path)

        factory = get_session_factory()
        async with factory() as session:
            service = IngestService(session, storage=storage, db_lock=self.db_lock)
            result = await service.ingest_file(
                stored,
                uploaded_by_id=job.user_id,
                source_hint=path,
                analyze=job.analyze,
                on_conflict=ConflictPolicy.ASK,
                commit_now=True,
            )
            if result.status == "conflict":
                get_conflict_registry().add(
                    user_id=job.user_id,
                    filename=path.name,
                    prepared=result.prepared,
                    existing_track_id=result.conflict_with.id,
                    job_id=job.id,
                )
                job.conflicts += 1
            elif result.status == "duplicate":
                job.duplicates += 1
            else:
                job.imported += 1


_manager: ImportManager | None = None


def get_import_manager() -> ImportManager:
    global _manager
    if _manager is None:
        _manager = ImportManager()
    return _manager

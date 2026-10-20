"""Content-addressed file storage for audio, covers and avatars.

Files are laid out by the first bytes of their SHA-256 (``ab/cd/<hash>.mp3``) so
no directory ever holds a million entries, and identical uploads collapse onto
the same path instead of being stored twice.
"""

from __future__ import annotations

import hashlib
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from ..config import Settings, get_settings

AUDIO_EXTENSIONS = {
    ".mp3": "mpeg",
    ".flac": "flac",
    ".m4a": "mp4",
    ".mp4": "mp4",
    ".aac": "aac",
    ".ogg": "ogg",
    ".oga": "ogg",
    ".opus": "opus",
    ".wav": "wav",
    ".wma": "wma",
    ".alac": "mp4",
    ".aiff": "aiff",
}

LOSSLESS_EXTENSIONS = {".flac", ".wav", ".alac", ".aiff"}

CONTENT_TYPES = {
    "mpeg": "audio/mpeg",
    "flac": "audio/flac",
    "mp4": "audio/mp4",
    "aac": "audio/aac",
    "ogg": "audio/ogg",
    "opus": "audio/opus",
    "wav": "audio/wav",
    "wma": "audio/x-ms-wma",
    "aiff": "audio/aiff",
}

_HASH_CHUNK = 1024 * 1024


class StorageError(Exception):
    pass


class UnsupportedFormatError(StorageError):
    pass


@dataclass(slots=True)
class StoredFile:
    relative_path: str
    absolute_path: Path
    content_hash: str
    size: int
    extension: str
    container: str
    lossless: bool

    @property
    def content_type(self) -> str:
        return CONTENT_TYPES.get(self.container, "application/octet-stream")


def sniff_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in AUDIO_EXTENSIONS:
        raise UnsupportedFormatError(
            f"unsupported audio format {ext or '(none)'}; "
            f"supported: {', '.join(sorted(AUDIO_EXTENSIONS))}"
        )
    return ext


def hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def shard_path(content_hash: str, extension: str) -> str:
    return f"{content_hash[:2]}/{content_hash[2:4]}/{content_hash}{extension}"


class Storage:
    """Thin filesystem layer. Swapping in S3 later means reimplementing this class."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.settings.ensure_directories()

    # --- staging ------------------------------------------------------------

    def stage_upload(self, source: BinaryIO, filename: str, max_bytes: int | None = None) -> Path:
        """Stream an upload to a temp file so we never hold a track in memory."""
        extension = sniff_extension(filename)
        limit = max_bytes if max_bytes is not None else self.settings.max_upload_bytes
        temp_path = self.settings.incoming_dir / f"{uuid.uuid4().hex}{extension}"

        written = 0
        try:
            with temp_path.open("wb") as handle:
                while chunk := source.read(_HASH_CHUNK):
                    written += len(chunk)
                    if written > limit:
                        raise StorageError(f"upload exceeds {limit} bytes")
                    handle.write(chunk)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

        if written == 0:
            temp_path.unlink(missing_ok=True)
            raise StorageError("uploaded file is empty")
        return temp_path

    # --- commit -------------------------------------------------------------

    def commit_audio(self, temp_path: Path, extension: str | None = None) -> StoredFile:
        """Move a staged file to its content-addressed home."""
        ext = (extension or temp_path.suffix).lower()
        if ext not in AUDIO_EXTENSIONS:
            raise UnsupportedFormatError(f"unsupported audio format {ext}")

        content_hash, size = hash_file(temp_path)
        relative = shard_path(content_hash, ext)
        target = self.settings.audio_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists():
            # Byte-identical upload already stored: drop the duplicate.
            temp_path.unlink(missing_ok=True)
        else:
            shutil.move(str(temp_path), str(target))

        return StoredFile(
            relative_path=relative,
            absolute_path=target,
            content_hash=content_hash,
            size=size,
            extension=ext,
            container=AUDIO_EXTENSIONS[ext],
            lossless=ext in LOSSLESS_EXTENSIONS,
        )

    def import_existing(self, source: Path) -> StoredFile:
        """Copy a file already on disk (folder-scan ingest) into storage."""
        if not source.is_file():
            raise StorageError(f"not a file: {source}")
        ext = source.suffix.lower()
        if ext not in AUDIO_EXTENSIONS:
            raise UnsupportedFormatError(f"unsupported audio format {ext}")

        content_hash, size = hash_file(source)
        relative = shard_path(content_hash, ext)
        target = self.settings.audio_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(source, target)

        return StoredFile(
            relative_path=relative,
            absolute_path=target,
            content_hash=content_hash,
            size=size,
            extension=ext,
            container=AUDIO_EXTENSIONS[ext],
            lossless=ext in LOSSLESS_EXTENSIONS,
        )

    # --- images -------------------------------------------------------------

    def save_cover(self, data: bytes, mime: str | None = None) -> str:
        return self._save_image(data, self.settings.cover_dir, mime)

    def save_avatar(self, data: bytes, mime: str | None = None) -> str:
        return self._save_image(data, self.settings.avatar_dir, mime)

    def _save_image(self, data: bytes, directory: Path, mime: str | None) -> str:
        if not data:
            raise StorageError("empty image payload")
        ext = _image_extension(data, mime)
        content_hash = hashlib.sha256(data).hexdigest()
        relative = shard_path(content_hash, ext)
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(data)
        return relative

    # --- lookups ------------------------------------------------------------

    def audio_path(self, relative_path: str) -> Path:
        return self._safe_join(self.settings.audio_dir, relative_path)

    def cover_path(self, relative_path: str) -> Path:
        return self._safe_join(self.settings.cover_dir, relative_path)

    def avatar_path(self, relative_path: str) -> Path:
        return self._safe_join(self.settings.avatar_dir, relative_path)

    @staticmethod
    def _safe_join(root: Path, relative_path: str) -> Path:
        """Resolve inside ``root`` only — a stored path must never escape it."""
        candidate = (root / relative_path).resolve()
        root_resolved = root.resolve()
        if not candidate.is_relative_to(root_resolved):
            raise StorageError(f"path escapes storage root: {relative_path}")
        return candidate

    def delete_audio(self, relative_path: str) -> None:
        self.audio_path(relative_path).unlink(missing_ok=True)


_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"
_WEBP_MAGIC = b"WEBP"


def looks_like_image(data: bytes) -> bool:
    """Whether the bytes really are a PNG, JPEG or WebP picture, whatever they are called."""
    return (
        data.startswith(_PNG_MAGIC)
        or data.startswith(_JPEG_MAGIC)
        or (data[:4] == b"RIFF" and data[8:12] == _WEBP_MAGIC)
    )


def _image_extension(data: bytes, mime: str | None) -> str:
    if data.startswith(_PNG_MAGIC):
        return ".png"
    if data.startswith(_JPEG_MAGIC):
        return ".jpg"
    if data[8:12] == _WEBP_MAGIC:
        return ".webp"
    if mime:
        lowered = mime.lower()
        if "png" in lowered:
            return ".png"
        if "webp" in lowered:
            return ".webp"
        if "jpeg" in lowered or "jpg" in lowered:
            return ".jpg"
    return ".jpg"


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = Storage()
    return _storage

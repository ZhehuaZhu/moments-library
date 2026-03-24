from __future__ import annotations

import mimetypes
from datetime import datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from werkzeug.datastructures import FileStorage

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm"}
DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt"}
ALLOWED_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | DOCUMENT_EXTENSIONS


class UploadValidationError(ValueError):
    pass


def media_kind_for_extension(extension: str) -> str:
    if extension in IMAGE_EXTENSIONS:
        return "image"
    if extension in VIDEO_EXTENSIONS:
        return "video"
    return "document"


def normalize_original_name(filename: str) -> str:
    return Path(filename).name.strip()


def resolve_storage_path(upload_root: str, relative_path: str) -> Path:
    relative = PurePosixPath(relative_path)
    parts = relative.parts
    if parts and parts[0] == "uploads":
        parts = parts[1:]
    return Path(upload_root).joinpath(*parts)


def save_upload(file_storage: FileStorage, upload_root: str) -> dict[str, str | int]:
    original_name = normalize_original_name(file_storage.filename or "")
    extension = Path(original_name).suffix.lower()

    if not original_name or extension not in ALLOWED_EXTENSIONS:
        raise UploadValidationError("Unsupported attachment format.")

    year = datetime.utcnow().strftime("%Y")
    month = datetime.utcnow().strftime("%m")
    relative_dir = PurePosixPath("uploads") / year / month
    stored_name = f"{uuid4().hex}{extension}"

    target_dir = Path(upload_root) / year / month
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / stored_name
    file_storage.save(target_path)

    mime_type = (
        file_storage.mimetype
        or mimetypes.guess_type(original_name)[0]
        or "application/octet-stream"
    )
    relative_path = (relative_dir / stored_name).as_posix()

    return {
        "absolute_path": str(target_path),
        "original_name": original_name,
        "stored_name": stored_name,
        "relative_path": relative_path,
        "mime_type": mime_type,
        "media_kind": media_kind_for_extension(extension),
        "size_bytes": target_path.stat().st_size,
    }


def cleanup_files(paths: list[str]) -> None:
    for path in paths:
        file_path = Path(path)
        if file_path.exists():
            file_path.unlink()


def delete_attachment_file(upload_root: str, relative_path: str) -> None:
    path = resolve_storage_path(upload_root, relative_path)
    if not path.exists():
        return

    path.unlink()

    uploads_root = Path(upload_root)
    current_dir = path.parent
    while current_dir != uploads_root and current_dir.exists():
        try:
            next(current_dir.iterdir())
            break
        except StopIteration:
            current_dir.rmdir()
            current_dir = current_dir.parent

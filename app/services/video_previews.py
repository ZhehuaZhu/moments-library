from __future__ import annotations

import mimetypes
import subprocess
from datetime import datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from ..models import Attachment, VideoEntry
from .storage import delete_attachment_file, resolve_storage_path

try:
    from imageio_ffmpeg import get_ffmpeg_exe
except ImportError:  # pragma: no cover - dependency can be absent in some environments
    get_ffmpeg_exe = None


HEVC_MARKERS = (b"hvc1", b"hev1")
SCAN_WINDOW_BYTES = 8 * 1024 * 1024


def _prepare_generated_asset(upload_root: str, extension: str, mime_type: str) -> dict[str, str]:
    year = datetime.utcnow().strftime("%Y")
    month = datetime.utcnow().strftime("%m")
    relative_dir = PurePosixPath("uploads") / year / month
    stored_name = f"{uuid4().hex}{extension}"
    target_dir = Path(upload_root) / year / month
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / stored_name
    return {
        "absolute_path": str(target_path),
        "relative_path": (relative_dir / stored_name).as_posix(),
        "mime_type": mime_type,
    }


def _read_marker_window(source_path: Path) -> bytes:
    size = source_path.stat().st_size
    if size <= SCAN_WINDOW_BYTES * 2:
        return source_path.read_bytes()

    with source_path.open("rb") as handle:
        head = handle.read(SCAN_WINDOW_BYTES)
        handle.seek(max(0, size - SCAN_WINDOW_BYTES))
        tail = handle.read(SCAN_WINDOW_BYTES)
    return head + tail


def detect_video_codec_hint(source_path: Path) -> str | None:
    if not source_path.exists():
        return None

    try:
        window = _read_marker_window(source_path)
    except OSError:
        return None

    if any(marker in window for marker in HEVC_MARKERS):
        return "hevc"
    if b"avc1" in window:
        return "h264"
    if b"vp09" in window:
        return "vp9"
    if b"av01" in window:
        return "av1"
    return None


def _should_generate_browser_preview(attachment: Attachment, source_path: Path) -> bool:
    extension = source_path.suffix.lower()
    if extension == ".mov" or attachment.mime_type == "video/quicktime":
        return True

    return detect_video_codec_hint(source_path) == "hevc"


def _run_ffmpeg(args: list[str]) -> bool:
    if get_ffmpeg_exe is None:
        return False

    ffmpeg_exe = get_ffmpeg_exe()
    completed = subprocess.run(
        [ffmpeg_exe, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return completed.returncode == 0


def _generate_mp4_preview(source_path: Path, upload_root: str) -> dict[str, str] | None:
    target = _prepare_generated_asset(upload_root, ".mp4", "video/mp4")
    success = _run_ffmpeg(
        [
            "-y",
            "-i",
            str(source_path),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-vf",
            "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            target["absolute_path"],
        ]
    )
    if not success or not Path(target["absolute_path"]).exists():
        Path(target["absolute_path"]).unlink(missing_ok=True)
        return None
    return target


def _generate_poster(source_path: Path, upload_root: str) -> dict[str, str] | None:
    target = _prepare_generated_asset(upload_root, ".jpg", "image/jpeg")
    success = _run_ffmpeg(
        [
            "-y",
            "-ss",
            "0.1",
            "-i",
            str(source_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            target["absolute_path"],
        ]
    )
    if not success or not Path(target["absolute_path"]).exists():
        Path(target["absolute_path"]).unlink(missing_ok=True)
        return None
    return target


def ensure_attachment_video_preview(attachment: Attachment, upload_root: str) -> list[str]:
    if attachment.media_kind != "video":
        return []

    source_path = resolve_storage_path(upload_root, attachment.relative_path)
    if not source_path.exists():
        return []

    created_paths: list[str] = []

    preview_exists = bool(
        attachment.preview_relative_path
        and resolve_storage_path(upload_root, attachment.preview_relative_path).exists()
    )
    poster_exists = bool(
        attachment.poster_relative_path
        and resolve_storage_path(upload_root, attachment.poster_relative_path).exists()
    )

    preview_source = source_path
    if _should_generate_browser_preview(attachment, source_path) and not preview_exists:
        preview_asset = _generate_mp4_preview(source_path, upload_root)
        if preview_asset is not None:
            if attachment.preview_relative_path:
                delete_attachment_file(upload_root, attachment.preview_relative_path)
            attachment.preview_relative_path = preview_asset["relative_path"]
            attachment.preview_mime_type = preview_asset["mime_type"]
            created_paths.append(preview_asset["absolute_path"])
            preview_source = Path(preview_asset["absolute_path"])
            preview_exists = True
        else:
            preview_source = source_path
    elif preview_exists and attachment.preview_relative_path:
        preview_source = resolve_storage_path(upload_root, attachment.preview_relative_path)

    if not poster_exists:
        poster_asset = _generate_poster(preview_source, upload_root)
        if poster_asset is not None:
            if attachment.poster_relative_path:
                delete_attachment_file(upload_root, attachment.poster_relative_path)
            attachment.poster_relative_path = poster_asset["relative_path"]
            attachment.poster_mime_type = poster_asset["mime_type"]
            created_paths.append(poster_asset["absolute_path"])

    if not attachment.preview_relative_path:
        attachment.preview_mime_type = attachment.mime_type

    return created_paths


def ensure_video_entry_preview(video: VideoEntry, upload_root: str) -> list[str]:
    source_path = resolve_storage_path(upload_root, video.relative_path)
    if not source_path.exists():
        return []

    created_paths: list[str] = []

    preview_exists = bool(
        video.preview_relative_path
        and resolve_storage_path(upload_root, video.preview_relative_path).exists()
    )
    poster_exists = bool(
        video.poster_relative_path
        and resolve_storage_path(upload_root, video.poster_relative_path).exists()
    )

    preview_source = source_path
    if not preview_exists and (
        source_path.suffix.lower() == ".mov"
        or video.mime_type == "video/quicktime"
        or detect_video_codec_hint(source_path) == "hevc"
    ):
        preview_asset = _generate_mp4_preview(source_path, upload_root)
        if preview_asset is not None:
            if video.preview_relative_path:
                delete_attachment_file(upload_root, video.preview_relative_path)
            video.preview_relative_path = preview_asset["relative_path"]
            video.preview_mime_type = preview_asset["mime_type"]
            created_paths.append(preview_asset["absolute_path"])
            preview_source = Path(preview_asset["absolute_path"])
            preview_exists = True
    elif preview_exists and video.preview_relative_path:
        preview_source = resolve_storage_path(upload_root, video.preview_relative_path)

    if not poster_exists:
        poster_asset = _generate_poster(preview_source, upload_root)
        if poster_asset is not None:
            if video.poster_relative_path:
                delete_attachment_file(upload_root, video.poster_relative_path)
            video.poster_relative_path = poster_asset["relative_path"]
            video.poster_mime_type = poster_asset["mime_type"]
            created_paths.append(poster_asset["absolute_path"])

    if not video.preview_relative_path:
        video.preview_mime_type = video.mime_type

    return created_paths

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .storage import resolve_storage_path

BOOK_ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".md", ".epub", ".mobi"}
AUDIO_ALLOWED_EXTENSIONS = {".mp3", ".m4a", ".wav", ".ogg", ".webm", ".flac"}
LYRICS_ALLOWED_EXTENSIONS = {".lrc"}
VIDEO_ALLOWED_EXTENSIONS = {".mp4", ".mov", ".webm"}

BOOK_STATUS_CHOICES = [
    ("want_to_read", "Want to Read"),
    ("reading", "Reading"),
    ("finished", "Finished"),
    ("paused", "Paused"),
]

ANNOTATION_TAG_CHOICES = [
    ("favorite", "Favorite"),
    ("question", "Question"),
    ("idea", "Idea"),
    ("character", "Character"),
    ("foreshadowing", "Foreshadowing"),
]

LRC_TIMESTAMP_RE = re.compile(r"\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]")
LRC_METADATA_RE = re.compile(r"^\[(ti|ar|al|by|offset):", re.IGNORECASE)


def parse_optional_date(value: str | None) -> date | None:
    if value in {None, ""}:
        return None
    return date.fromisoformat(value)


def parse_optional_timestamp(value: str | None) -> int | None:
    if value in {None, ""}:
        return None

    raw = value.strip()
    if not raw:
        return None

    if ":" not in raw:
        return max(int(raw), 0)

    parts = [part.strip() for part in raw.split(":")]
    if len(parts) == 2:
        minutes, seconds = parts
        return max(int(minutes) * 60 + int(seconds), 0)
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return max(int(hours) * 3600 + int(minutes) * 60 + int(seconds), 0)

    raise ValueError("Unsupported timestamp format.")


def seconds_to_clock(seconds: int | None) -> str:
    if seconds is None:
        return ""

    total = max(int(seconds), 0)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def read_text_asset(upload_root: str, relative_path: str) -> str:
    path = resolve_storage_path(upload_root, relative_path)
    raw = path.read_bytes()

    for encoding in ("utf-8", "utf-8-sig", "utf-16", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue

    return raw.decode("utf-8", errors="ignore")


def file_url_from_relative(static_url_root: str, relative_path: str) -> str:
    cleaned = relative_path.lstrip("/")
    return f"{static_url_root.rstrip('/')}/{cleaned}"


def parse_lrc_text(text: str) -> list[dict[str, object]]:
    parsed_lines: list[dict[str, object]] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or LRC_METADATA_RE.match(line):
            continue

        matches = list(LRC_TIMESTAMP_RE.finditer(line))
        if not matches:
            continue

        lyric_text = LRC_TIMESTAMP_RE.sub("", line).strip()
        if not lyric_text:
            continue

        for match in matches:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            fraction_raw = match.group(3) or ""
            fraction = int(fraction_raw) / (10 ** len(fraction_raw)) if fraction_raw else 0
            total_seconds = minutes * 60 + seconds + fraction
            parsed_lines.append(
                {
                    "seconds": round(total_seconds, 3),
                    "timestamp_label": f"{minutes:02d}:{seconds:02d}",
                    "text": lyric_text,
                }
            )

    parsed_lines.sort(key=lambda item: float(item["seconds"]))
    return parsed_lines

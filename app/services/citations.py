from __future__ import annotations

from flask import url_for
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from ..models import Book, BookAnnotation, Track, TrackComment, VideoComment, VideoEntry
from .i18n import translate

DEFAULT_SCOPE = "all"
VALID_SCOPES = {"all", "books", "quotes", "music", "videos"}


def normalize_citation_scope(raw_scope: str | None) -> str:
    scope = (raw_scope or "").strip().lower()
    return scope if scope in VALID_SCOPES else DEFAULT_SCOPE


def format_timestamp_label(total_seconds: int | None) -> str | None:
    if total_seconds is None:
        return None
    minutes, seconds = divmod(max(total_seconds, 0), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _cover_url(relative_path: str | None) -> str | None:
    if not relative_path:
        return None
    return url_for("static", filename=relative_path)


def serialize_book_citation(book: Book) -> dict[str, str | int | None]:
    return {
        "kind": "book",
        "group": "books",
        "id": book.id,
        "label": translate("citation.book"),
        "title": book.title,
        "subtitle": book.author_name or book.source_format.upper(),
        "excerpt": book.overall_review or book.description or None,
        "href": url_for("library.book_detail", book_id=book.id),
        "cover": _cover_url(book.cover_relative_path),
    }


def serialize_annotation_citation(note: BookAnnotation) -> dict[str, str | int | None]:
    href = f'{url_for("library.book_detail", book_id=note.book.id)}#book-note-{note.id}'
    if note.has_text_anchor and note.section_index is not None:
        href = url_for(
            "library.book_reader",
            book_id=note.book.id,
            section=note.section_index + 1,
            annotation=note.id,
        )
    subtitle_parts = [part for part in [note.chapter_label, note.book.author_name] if part]
    return {
        "kind": "book_annotation",
        "group": "quotes",
        "id": note.id,
        "label": translate("citation.book_quote"),
        "title": note.book.title,
        "subtitle": " · ".join(subtitle_parts) or translate("citation.saved_annotation"),
        "excerpt": note.quoted_text or note.comment,
        "href": href,
        "cover": _cover_url(note.book.cover_relative_path),
    }


def serialize_track_citation(track: Track) -> dict[str, str | int | None]:
    return {
        "kind": "track",
        "group": "music",
        "id": track.id,
        "label": translate("citation.track"),
        "title": track.title,
        "subtitle": track.artist_name or translate("citation.music_library"),
        "excerpt": track.overall_review or track.description or None,
        "href": url_for("library.track_detail", track_id=track.id),
        "cover": _cover_url(track.cover_relative_path),
    }


def serialize_track_comment_citation(note: TrackComment) -> dict[str, str | int | None]:
    timestamp = format_timestamp_label(note.timestamp_seconds)
    subtitle_parts = [part for part in [note.track.artist_name, timestamp] if part]
    return {
        "kind": "track_comment",
        "group": "music",
        "id": note.id,
        "label": translate("citation.track_note"),
        "title": note.track.title,
        "subtitle": " · ".join(subtitle_parts) or translate("citation.saved_music_note"),
        "excerpt": note.comment,
        "href": f'{url_for("library.track_detail", track_id=note.track.id)}#track-note-{note.id}',
        "cover": _cover_url(note.track.cover_relative_path),
    }


def serialize_video_citation(video: VideoEntry) -> dict[str, str | int | None]:
    return {
        "kind": "video",
        "group": "videos",
        "id": video.id,
        "label": translate("citation.video"),
        "title": video.title,
        "subtitle": video.category.name if video.category else translate("citation.video_library"),
        "excerpt": video.overall_review or video.description or None,
        "href": url_for("library.video_detail", video_id=video.id),
        "cover": None,
    }


def serialize_video_comment_citation(note: VideoComment) -> dict[str, str | int | None]:
    timestamp = format_timestamp_label(note.timestamp_seconds)
    return {
        "kind": "video_comment",
        "group": "videos",
        "id": note.id,
        "label": translate("citation.video_note"),
        "title": note.video.title,
        "subtitle": timestamp or translate("citation.saved_video_note"),
        "excerpt": note.comment,
        "href": f'{url_for("library.video_detail", video_id=note.video.id)}#video-note-{note.id}',
        "cover": None,
    }


def resolve_citation_payload(kind: str | None, target_id: int | None):
    if not kind or target_id is None:
        return None

    normalized_kind = kind.strip().lower()
    if normalized_kind == "book":
        book = db_get_book(target_id)
        return serialize_book_citation(book) if book else None
    if normalized_kind == "book_annotation":
        note = db_get_annotation(target_id)
        return serialize_annotation_citation(note) if note else None
    if normalized_kind == "track":
        track = db_get_track(target_id)
        return serialize_track_citation(track) if track else None
    if normalized_kind == "track_comment":
        note = db_get_track_comment(target_id)
        return serialize_track_comment_citation(note) if note else None
    if normalized_kind == "video":
        video = db_get_video(target_id)
        return serialize_video_citation(video) if video else None
    if normalized_kind == "video_comment":
        note = db_get_video_comment(target_id)
        return serialize_video_comment_citation(note) if note else None
    return None


def search_citation_payloads(
    search_query: str,
    *,
    scope: str = DEFAULT_SCOPE,
    limit: int = 24,
    offset: int = 0,
):
    scope = normalize_citation_scope(scope)
    query = (search_query or "").strip()
    limit = max(limit, 1)
    offset = max(offset, 0)
    request_window = limit + offset + 1
    per_group_limit = max(4, request_window)
    results: list[dict[str, str | int | None]] = []

    if scope in {"all", "books"}:
        results.extend(search_books(query, per_group_limit))
    if scope in {"all", "quotes"}:
        results.extend(search_annotations(query, per_group_limit))
    if scope in {"all", "music"}:
        results.extend(search_tracks(query, per_group_limit))
        results.extend(search_track_comments(query, per_group_limit))
    if scope in {"all", "videos"}:
        results.extend(search_videos(query, per_group_limit))
        results.extend(search_video_comments(query, per_group_limit))

    window = results[offset: offset + limit]
    has_more = len(results) > offset + limit
    return window, has_more


def search_books(query: str, limit: int):
    request_query = (
        Book.query.options(selectinload(Book.category))
        .order_by(Book.updated_at.desc(), Book.created_at.desc())
    )
    if query:
        pattern = f"%{query}%"
        request_query = request_query.filter(
            or_(
                Book.title.ilike(pattern),
                Book.author_name.ilike(pattern),
                Book.description.ilike(pattern),
                Book.overall_review.ilike(pattern),
            )
        )
    return [serialize_book_citation(book) for book in request_query.limit(limit).all()]


def search_annotations(query: str, limit: int):
    request_query = (
        BookAnnotation.query.options(selectinload(BookAnnotation.book))
        .order_by(BookAnnotation.created_at.desc())
    )
    if query:
        pattern = f"%{query}%"
        request_query = request_query.filter(
            or_(
                BookAnnotation.quoted_text.ilike(pattern),
                BookAnnotation.comment.ilike(pattern),
                BookAnnotation.chapter_label.ilike(pattern),
                BookAnnotation.book.has(Book.title.ilike(pattern)),
            )
        )
    return [serialize_annotation_citation(note) for note in request_query.limit(limit).all()]


def search_tracks(query: str, limit: int):
    request_query = Track.query.order_by(Track.updated_at.desc(), Track.created_at.desc())
    if query:
        pattern = f"%{query}%"
        request_query = request_query.filter(
            or_(
                Track.title.ilike(pattern),
                Track.artist_name.ilike(pattern),
                Track.description.ilike(pattern),
                Track.overall_review.ilike(pattern),
                Track.mood.ilike(pattern),
            )
        )
    return [serialize_track_citation(track) for track in request_query.limit(limit).all()]


def search_track_comments(query: str, limit: int):
    request_query = (
        TrackComment.query.options(selectinload(TrackComment.track))
        .order_by(TrackComment.created_at.desc())
    )
    if query:
        pattern = f"%{query}%"
        request_query = request_query.filter(
            or_(
                TrackComment.comment.ilike(pattern),
                TrackComment.track.has(Track.title.ilike(pattern)),
                TrackComment.track.has(Track.artist_name.ilike(pattern)),
            )
        )
    return [serialize_track_comment_citation(note) for note in request_query.limit(limit).all()]


def search_videos(query: str, limit: int):
    request_query = VideoEntry.query.options(selectinload(VideoEntry.category)).order_by(
        VideoEntry.updated_at.desc(),
        VideoEntry.created_at.desc(),
    )
    if query:
        pattern = f"%{query}%"
        request_query = request_query.filter(
            or_(
                VideoEntry.title.ilike(pattern),
                VideoEntry.description.ilike(pattern),
                VideoEntry.overall_review.ilike(pattern),
            )
        )
    return [serialize_video_citation(video) for video in request_query.limit(limit).all()]


def search_video_comments(query: str, limit: int):
    request_query = (
        VideoComment.query.options(selectinload(VideoComment.video))
        .order_by(VideoComment.created_at.desc())
    )
    if query:
        pattern = f"%{query}%"
        request_query = request_query.filter(
            or_(
                VideoComment.comment.ilike(pattern),
                VideoComment.video.has(VideoEntry.title.ilike(pattern)),
            )
        )
    return [serialize_video_comment_citation(note) for note in request_query.limit(limit).all()]


def db_get_book(book_id: int):
    return Book.query.options(selectinload(Book.category)).filter(Book.id == book_id).first()


def db_get_annotation(annotation_id: int):
    return (
        BookAnnotation.query.options(selectinload(BookAnnotation.book))
        .filter(BookAnnotation.id == annotation_id)
        .first()
    )


def db_get_track(track_id: int):
    return Track.query.filter(Track.id == track_id).first()


def db_get_track_comment(comment_id: int):
    return (
        TrackComment.query.options(selectinload(TrackComment.track))
        .filter(TrackComment.id == comment_id)
        .first()
    )


def db_get_video(video_id: int):
    return VideoEntry.query.options(selectinload(VideoEntry.category)).filter(VideoEntry.id == video_id).first()


def db_get_video_comment(comment_id: int):
    return (
        VideoComment.query.options(selectinload(VideoComment.video))
        .filter(VideoComment.id == comment_id)
        .first()
    )

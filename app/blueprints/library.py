from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import Book, BookAnnotation, Category, Track, TrackComment, VideoComment, VideoEntry
from ..permissions import admin_required
from ..services.books import (
    ensure_book_reader_ready,
    extract_book_identity,
    normalize_book_upload,
    read_reader_sections,
    render_reader_section_markup,
)
from ..services.i18n import get_annotation_tag_choices, translate
from ..services.library import (
    AUDIO_ALLOWED_EXTENSIONS,
    LYRICS_ALLOWED_EXTENSIONS,
    VIDEO_ALLOWED_EXTENSIONS,
    parse_lrc_text,
    parse_optional_timestamp,
    read_text_asset,
)
from ..services.storage import (
    IMAGE_EXTENSIONS,
    UploadValidationError,
    cleanup_files,
    delete_attachment_file,
    save_upload,
)
from ..services.video_previews import ensure_video_entry_preview
from .main import build_sidebar_context

library_bp = Blueprint("library", __name__)

BOOK_READING_START_THRESHOLD_SECONDS = 5 * 60
BOOK_FINISH_PROGRESS_THRESHOLD = 0.99


def redirect_back(default_endpoint: str):
    target = request.form.get("next") or request.referrer
    return redirect(target or url_for(default_endpoint))


def redirect_back_with_added_tracks(default_endpoint: str, track_ids: list[int]):
    target = request.form.get("next") or request.referrer or url_for(default_endpoint)
    if not track_ids:
        return redirect(target)

    url = urlsplit(target)
    params = [(key, value) for key, value in parse_qsl(url.query, keep_blank_values=True) if key != "added"]
    params.append(("added", ",".join(str(track_id) for track_id in track_ids)))
    return redirect(urlunsplit((url.scheme, url.netloc, url.path, urlencode(params), url.fragment)))


def resolve_category(category_raw: str | None) -> Category | None:
    if category_raw in {None, ""}:
        return None
    return db.session.get(Category, int(category_raw))


def normalize_track_audio_mime(metadata: dict[str, object]) -> dict[str, object]:
    normalized = dict(metadata)
    extension = Path(str(normalized.get("original_name") or "")).suffix.lower()
    if extension == ".mp4":
        normalized["mime_type"] = "audio/mp4"
    return normalized


def infer_track_title_from_filename(filename: str) -> str:
    stem = Path(filename).stem.strip()
    if not stem:
        return ""

    cleaned = re.sub(r"[_-]+", " ", stem)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or stem


def collect_uploaded_track_files() -> list:
    files = []
    for field_name in ("audio_files", "audio_file"):
        for file_storage in request.files.getlist(field_name):
            if file_storage is not None and file_storage.filename:
                files.append(file_storage)
    return files


def parse_section_index(raw_value: str | None, total: int, *, one_based: bool = False) -> int:
    if total <= 0:
        return 0

    try:
        value = int(raw_value or ("1" if one_based else "0"))
    except (TypeError, ValueError):
        value = 1 if one_based else 0

    if one_based:
        value -= 1

    return max(0, min(value, total - 1))


def parse_optional_int(raw_value: str | None, *, minimum: int | None = None) -> int | None:
    value = (raw_value or "").strip()
    if not value:
        return None

    parsed = int(value)
    if minimum is not None and parsed < minimum:
        raise ValueError
    return parsed


def parse_optional_float(
    raw_value: str | None,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    value = (raw_value or "").strip()
    if not value:
        return None

    parsed = float(value)
    if minimum is not None and parsed < minimum:
        raise ValueError
    if maximum is not None and parsed > maximum:
        raise ValueError
    return parsed


def pick_default_reader_section_index(sections: list[dict[str, object]]) -> int:
    for index, section in enumerate(sections):
        if not section.get("is_front_matter"):
            return index
    return 0


def serialize_reader_annotations(book: Book) -> list[dict[str, object]]:
    serialized: list[dict[str, object]] = []

    for note in book.annotations:
        if not note.has_text_anchor:
            continue
        serialized.append(
            {
                "id": note.id,
                "annotation_type": note.annotation_type,
                "chapter_label": note.chapter_label,
                "page_label": note.page_label,
                "section_index": note.section_index,
                "paragraph_id": note.paragraph_id,
                "selection_start": note.selection_start,
                "selection_end": note.selection_end,
                "quoted_text": note.quoted_text,
                "comment": note.comment,
                "tag": note.tag,
                "created_at": note.created_at.strftime("%Y-%m-%d %H:%M"),
            }
        )

    return serialized


def clamp_progress_ratio(value: float | None) -> float | None:
    if value is None:
        return None
    return max(0.0, min(float(value), 1.0))


def compute_book_completion_ratio(
    book: Book,
    upload_root: str,
    *,
    section_index: int | None = None,
    scroll_ratio: float | None = None,
) -> float | None:
    ratio = clamp_progress_ratio(scroll_ratio)
    if ratio is None:
        return None

    if book.reader_kind == "html":
        sections = read_reader_sections(upload_root, book.reader_asset_path)
        if not sections:
            return None
        active_index = parse_section_index(str(section_index or 0), len(sections))
        return clamp_progress_ratio((active_index + ratio) / len(sections))

    if book.reader_kind in {"text", "docx"}:
        return ratio

    return None


def apply_book_reading_progress(
    book: Book,
    upload_root: str,
    *,
    section_index: int | None = None,
    scroll_ratio: float | None = None,
    session_key: str | None = None,
    session_elapsed_seconds: int | None = None,
) -> tuple[bool, float | None]:
    changed = False
    normalized_session_key = (session_key or "").strip() or None
    normalized_elapsed_seconds = max(int(session_elapsed_seconds or 0), 0)

    if normalized_session_key is not None:
        if book.last_read_session_key == normalized_session_key:
            delta_seconds = max(normalized_elapsed_seconds - (book.last_read_session_seconds or 0), 0)
        else:
            delta_seconds = normalized_elapsed_seconds
            book.last_read_session_key = normalized_session_key
            changed = True

        if delta_seconds:
            book.total_reading_seconds = max((book.total_reading_seconds or 0) + delta_seconds, 0)
            changed = True

        if (book.last_read_session_seconds or 0) != normalized_elapsed_seconds:
            book.last_read_session_seconds = normalized_elapsed_seconds
            changed = True

    progress_ratio = compute_book_completion_ratio(
        book,
        upload_root,
        section_index=section_index,
        scroll_ratio=scroll_ratio,
    )

    if progress_ratio is not None and progress_ratio >= BOOK_FINISH_PROGRESS_THRESHOLD:
        if book.started_at is None:
            book.started_at = date.today()
            changed = True
        if book.status != "finished":
            book.status = "finished"
            changed = True
        if book.finished_at is None:
            book.finished_at = date.today()
            changed = True
    elif (book.total_reading_seconds or 0) >= BOOK_READING_START_THRESHOLD_SECONDS:
        if book.started_at is None:
            book.started_at = date.today()
            changed = True
        if book.status in {"want_to_read", "paused"}:
            book.status = "reading"
            changed = True

    return changed, progress_ratio


def book_query(search_query: str):
    query = Book.query.options(
        selectinload(Book.category),
        selectinload(Book.owner),
        selectinload(Book.annotations),
    )
    if search_query:
        pattern = f"%{search_query}%"
        query = query.filter(
            or_(
                Book.title.ilike(pattern),
                Book.author_name.ilike(pattern),
                Book.description.ilike(pattern),
                Book.overall_review.ilike(pattern),
            )
        )
    return query.order_by(Book.updated_at.desc(), Book.created_at.desc())


def track_query(search_query: str):
    query = Track.query.options(
        selectinload(Track.category),
        selectinload(Track.owner),
        selectinload(Track.comments),
    )
    if search_query:
        pattern = f"%{search_query}%"
        query = query.filter(
            or_(
                Track.title.ilike(pattern),
                Track.artist_name.ilike(pattern),
                Track.description.ilike(pattern),
                Track.overall_review.ilike(pattern),
                Track.mood.ilike(pattern),
            )
        )
    return query.order_by(Track.updated_at.desc(), Track.created_at.desc())


def video_query(search_query: str, category_id: int | None = None):
    query = VideoEntry.query.options(
        selectinload(VideoEntry.category),
        selectinload(VideoEntry.owner),
        selectinload(VideoEntry.comments),
    )
    if category_id is not None:
        query = query.filter(VideoEntry.category_id == category_id)
    if search_query:
        pattern = f"%{search_query}%"
        query = query.filter(
            or_(
                VideoEntry.title.ilike(pattern),
                VideoEntry.description.ilike(pattern),
                VideoEntry.overall_review.ilike(pattern),
            )
        )
    return query.order_by(VideoEntry.updated_at.desc(), VideoEntry.created_at.desc())


def ensure_library_video_previews(videos: list[VideoEntry]) -> None:
    changed = False
    upload_root = current_app.config["UPLOAD_FOLDER"]

    for video in videos:
        created_paths = ensure_video_entry_preview(video, upload_root)
        if created_paths:
            changed = True

    if changed:
        db.session.commit()


def get_book_or_404(book_id: int) -> Book:
    return (
        Book.query.options(
            selectinload(Book.category),
            selectinload(Book.owner),
            selectinload(Book.annotations).selectinload(BookAnnotation.owner),
        )
        .filter(Book.id == book_id)
        .first_or_404()
    )


def get_track_or_404(track_id: int) -> Track:
    return (
        Track.query.options(
            selectinload(Track.category),
            selectinload(Track.owner),
            selectinload(Track.comments).selectinload(TrackComment.owner),
        )
        .filter(Track.id == track_id)
        .first_or_404()
    )


def get_video_or_404(video_id: int) -> VideoEntry:
    return (
        VideoEntry.query.options(
            selectinload(VideoEntry.category),
            selectinload(VideoEntry.owner),
            selectinload(VideoEntry.comments).selectinload(VideoComment.owner),
        )
        .filter(VideoEntry.id == video_id)
        .first_or_404()
    )


@library_bp.route("/books")
def books():
    search_query = (request.args.get("q") or "").strip()
    books_list = book_query(search_query).all()
    reading_count = sum(1 for book in books_list if book.status == "reading")
    finished_count = sum(1 for book in books_list if book.status == "finished")
    want_to_read_count = sum(1 for book in books_list if book.status == "want_to_read")
    paused_count = sum(1 for book in books_list if book.status == "paused")
    recent_book = (
        max(
            books_list,
            key=lambda book: book.last_read_at or book.updated_at or book.created_at,
        )
        if books_list
        else None
    )
    context = build_sidebar_context(
        active_nav="books",
        search_query=search_query,
        search_action="library.books",
    )
    return render_template(
        "books.html",
        title=translate("module.books"),
        body_class="books-page",
        books=books_list,
        result_count=len(books_list),
        reading_count=reading_count,
        finished_count=finished_count,
        want_to_read_count=want_to_read_count,
        paused_count=paused_count,
        recent_book=recent_book,
        **context,
    )


@library_bp.route("/books", methods=["POST"])
@admin_required
def create_book():
    file_storage = request.files.get("source_file")
    if file_storage is None or not file_storage.filename:
        flash("Upload a book source file.", "error")
        return redirect_back("library.books")

    try:
        category = resolve_category(request.form.get("category_id"))
        assets = normalize_book_upload(
            file_storage,
            current_app.config["UPLOAD_FOLDER"],
            cover_file=request.files.get("cover_file"),
        )
    except (ValueError, TypeError):
        flash("Book collection selection is invalid.", "error")
        return redirect_back("library.books")
    except UploadValidationError as error:
        flash(str(error), "error")
        return redirect_back("library.books")

    metadata = assets["source"]
    reader_metadata = assets["reader"]
    cover_metadata = assets["cover"]
    identity = extract_book_identity(current_app.config["UPLOAD_FOLDER"], metadata)
    status = "want_to_read"
    title = (request.form.get("title") or "").strip() or (identity["title"] or "").strip()
    author_name = (request.form.get("author_name") or "").strip() or (
        (identity["author"] or "").strip() or None
    )
    if not title:
        flash("Book title could not be inferred. Add a title and try again.", "error")
        return redirect_back("library.books")

    book = Book(
        title=title,
        author_name=author_name,
        description=(request.form.get("description") or "").strip() or None,
        overall_review=(request.form.get("overall_review") or "").strip() or None,
        status=status,
        started_at=None,
        finished_at=None,
        category=category,
        owner_id=current_user.id,
        source_format=Path(metadata["original_name"]).suffix.lower().lstrip("."),
        original_name=metadata["original_name"],
        stored_name=metadata["stored_name"],
        relative_path=metadata["relative_path"],
        mime_type=metadata["mime_type"],
        reader_relative_path=reader_metadata["relative_path"] if reader_metadata else None,
        reader_mime_type=reader_metadata["mime_type"] if reader_metadata else None,
        reader_format=Path(str(reader_metadata["original_name"])).suffix.lower().lstrip(".")
        if reader_metadata
        else None,
        cover_original_name=cover_metadata["original_name"] if cover_metadata else None,
        cover_stored_name=cover_metadata["stored_name"] if cover_metadata else None,
        cover_relative_path=cover_metadata["relative_path"] if cover_metadata else None,
        cover_mime_type=cover_metadata["mime_type"] if cover_metadata else None,
        size_bytes=metadata["size_bytes"],
    )
    db.session.add(book)
    db.session.commit()

    flash("Book added to the library.", "success")
    return redirect(url_for("library.book_detail", book_id=book.id))


@library_bp.route("/books/<int:book_id>")
def book_detail(book_id: int):
    book = get_book_or_404(book_id)
    if ensure_book_reader_ready(book, current_app.config["UPLOAD_FOLDER"]):
        db.session.commit()
    context = build_sidebar_context(active_nav="books", search_action="library.books")
    return render_template(
        "book_detail.html",
        title=book.title,
        book=book,
        annotation_tag_choices=get_annotation_tag_choices(),
        **context,
    )


@library_bp.route("/books/<int:book_id>/reader")
def book_reader(book_id: int):
    book = get_book_or_404(book_id)
    book_changed = ensure_book_reader_ready(book, current_app.config["UPLOAD_FOLDER"])
    if book_changed:
        db.session.commit()

    text_content = None
    html_content = None
    section_manifest = []
    active_section_index = 0
    current_section_markup = None
    reader_annotations = []
    reader_focus_annotation_id = None
    reader_resume_scroll_ratio = 0.0
    requested_annotation_id = request.args.get("annotation", type=int)
    focus_annotation = next(
        (
            note
            for note in book.annotations
            if note.id == requested_annotation_id and note.has_text_anchor
        ),
        None,
    )
    if book.reader_kind == "text":
        text_content = read_text_asset(current_app.config["UPLOAD_FOLDER"], book.reader_asset_path)
        reader_resume_scroll_ratio = max(0.0, min(book.last_read_scroll_ratio or 0.0, 1.0))
    elif book.reader_kind == "html":
        sections = read_reader_sections(current_app.config["UPLOAD_FOLDER"], book.reader_asset_path)
        section_manifest = [
            {
                "index": index,
                "label": section["label"],
                "is_front_matter": bool(section.get("is_front_matter")),
            }
            for index, section in enumerate(sections)
        ]
        requested_section = request.args.get("section")
        if requested_section not in {None, ""}:
            active_section_index = parse_section_index(
                requested_section,
                len(section_manifest),
                one_based=True,
            )
            if (
                book.last_read_section_index is not None
                and active_section_index
                == parse_section_index(str(book.last_read_section_index), len(section_manifest))
            ):
                reader_resume_scroll_ratio = max(0.0, min(book.last_read_scroll_ratio or 0.0, 1.0))
        elif focus_annotation is not None and focus_annotation.section_index is not None:
            active_section_index = parse_section_index(
                str(focus_annotation.section_index),
                len(section_manifest),
            )
        elif book.last_read_section_index is not None:
            active_section_index = parse_section_index(
                str(book.last_read_section_index),
                len(section_manifest),
            )
            reader_resume_scroll_ratio = max(0.0, min(book.last_read_scroll_ratio or 0.0, 1.0))
        else:
            active_section_index = pick_default_reader_section_index(sections)
        if sections:
            current_section_markup = render_reader_section_markup(sections[active_section_index])
            reader_annotations = serialize_reader_annotations(book)
            if focus_annotation is not None:
                reader_focus_annotation_id = focus_annotation.id
        else:
            html_content = f'<p class="helper-text">{translate("books.reader_preparing")}</p>'
    elif book.reader_kind == "docx":
        reader_resume_scroll_ratio = max(0.0, min(book.last_read_scroll_ratio or 0.0, 1.0))

    context = build_sidebar_context(active_nav="books", search_action="library.books")
    return render_template(
        "book_reader.html",
        title=f'{translate("common.read")} {book.title}',
        book=book,
        body_class="book-reader-page",
        text_content=text_content,
        html_content=html_content,
        section_manifest=section_manifest,
        active_section_index=active_section_index,
        current_section_label=section_manifest[active_section_index]["label"]
        if section_manifest
        else book.title,
        current_section_markup=current_section_markup,
        reader_annotations=reader_annotations,
        reader_focus_annotation_id=reader_focus_annotation_id,
        reader_source_path=book.reader_asset_path,
        reader_resume_scroll_ratio=reader_resume_scroll_ratio,
        reader_return_target=(
            url_for("library.book_reader", book_id=book.id, section=active_section_index + 1)
            if book.reader_kind == "html" and section_manifest
            else (request.full_path if request.query_string else request.path)
        ),
        annotation_tag_choices=get_annotation_tag_choices(),
        **context,
    )


@library_bp.route("/books/<int:book_id>/reader/section")
def book_reader_section(book_id: int):
    book = get_book_or_404(book_id)
    if ensure_book_reader_ready(book, current_app.config["UPLOAD_FOLDER"]):
        db.session.commit()

    if book.reader_kind != "html":
        return jsonify({"error": "Sections are only available for fast HTML reader editions."}), 404

    sections = read_reader_sections(current_app.config["UPLOAD_FOLDER"], book.reader_asset_path)
    if not sections:
        return jsonify({"error": "This reader edition is still being prepared."}), 404

    active_section_index = parse_section_index(request.args.get("index"), len(sections))
    section = sections[active_section_index]
    return jsonify(
        {
            "index": active_section_index,
            "number": active_section_index + 1,
            "total": len(sections),
            "label": section["label"],
            "is_front_matter": bool(section.get("is_front_matter")),
            "html": render_reader_section_markup(section),
        }
    )


@library_bp.route("/books/<int:book_id>/reader/progress", methods=["POST"])
def save_book_reader_progress(book_id: int):
    if not current_user.is_authenticated:
        return jsonify({"error": "Sign in required."}), 401

    book = get_book_or_404(book_id)
    if not current_user.is_admin and book.owner_id != current_user.id:
        return jsonify({"error": "You cannot update this reading progress."}), 403

    payload = request.get_json(silent=True) or {}
    try:
        section_index = parse_optional_int(
            str(payload.get("section_index")) if payload.get("section_index") is not None else None,
            minimum=0,
        )
        scroll_ratio = parse_optional_float(
            str(payload.get("scroll_ratio")) if payload.get("scroll_ratio") is not None else None,
            minimum=0.0,
            maximum=1.0,
        )
        session_elapsed_seconds = parse_optional_int(
            str(payload.get("session_elapsed_seconds"))
            if payload.get("session_elapsed_seconds") is not None
            else None,
            minimum=0,
        )
    except (TypeError, ValueError):
        return jsonify({"error": "Reader progress is invalid."}), 400

    if scroll_ratio is None:
        return jsonify({"error": "Reader progress is incomplete."}), 400

    if book.reader_kind == "html":
        book.last_read_section_index = section_index if section_index is not None else 0
    else:
        book.last_read_section_index = None

    book.last_read_scroll_ratio = scroll_ratio
    book.last_read_at = datetime.utcnow()
    book_changed, progress_ratio = apply_book_reading_progress(
        book,
        current_app.config["UPLOAD_FOLDER"],
        section_index=section_index,
        scroll_ratio=scroll_ratio,
        session_key=(payload.get("session_key") or "").strip() or None,
        session_elapsed_seconds=session_elapsed_seconds,
    )
    if book_changed:
        book.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify(
        {
            "ok": True,
            "section_index": book.last_read_section_index,
            "scroll_ratio": book.last_read_scroll_ratio,
            "status": book.status,
            "progress_ratio": progress_ratio,
        }
    )


@library_bp.route("/books/<int:book_id>/annotations", methods=["POST"])
@admin_required
def create_book_annotation(book_id: int):
    book = get_book_or_404(book_id)
    comment = (request.form.get("comment") or "").strip()
    if not comment:
        flash("Write a note before saving it.", "error")
        return redirect_back("library.book_detail")

    try:
        section_index = parse_optional_int(request.form.get("section_index"), minimum=0)
        selection_start = parse_optional_int(request.form.get("selection_start"), minimum=0)
        selection_end = parse_optional_int(request.form.get("selection_end"), minimum=0)
    except ValueError:
        flash("The saved highlight position is invalid. Select the passage again.", "error")
        return redirect_back("library.book_detail")

    paragraph_id = (request.form.get("paragraph_id") or "").strip() or None
    requested_type = (request.form.get("annotation_type") or "text_selection").strip() or "text_selection"
    has_anchor_payload = any(
        value not in {None, ""}
        for value in (
            request.form.get("section_index"),
            request.form.get("paragraph_id"),
            request.form.get("selection_start"),
            request.form.get("selection_end"),
        )
    )
    has_precise_anchor = (
        book.reader_kind == "html"
        and section_index is not None
        and paragraph_id is not None
        and selection_start is not None
        and selection_end is not None
        and selection_end > selection_start
    )
    if has_anchor_payload and not has_precise_anchor:
        flash("This highlight anchor is incomplete. Select the passage again, then save.", "error")
        return redirect_back("library.book_detail")

    annotation = BookAnnotation(
        book_id=book.id,
        owner_id=current_user.id,
        annotation_type="text_anchor" if has_precise_anchor else requested_type,
        chapter_label=(request.form.get("chapter_label") or "").strip() or None,
        page_label=(request.form.get("page_label") or "").strip() or None,
        section_index=section_index if has_precise_anchor else None,
        paragraph_id=paragraph_id if has_precise_anchor else None,
        selection_start=selection_start if has_precise_anchor else None,
        selection_end=selection_end if has_precise_anchor else None,
        quoted_text=(request.form.get("quoted_text") or "").strip() or None,
        comment=comment,
        tag=(request.form.get("tag") or "").strip() or None,
    )
    db.session.add(annotation)
    db.session.commit()

    flash("Reading note saved.", "success")
    return redirect_back("library.book_detail")


@library_bp.route("/books/<int:book_id>/edit", methods=["POST"])
@admin_required
def update_book(book_id: int):
    book = get_book_or_404(book_id)
    fallback_target = url_for("library.book_detail", book_id=book.id)
    title = (request.form.get("title") or "").strip() or book.title
    cover_file = request.files.get("cover_file")

    if not title:
        flash("Book title is required.", "error")
        return redirect(request.form.get("next") or request.referrer or fallback_target)

    try:
        category = resolve_category(request.form.get("category_id"))
    except (ValueError, TypeError):
        flash("Book collection selection is invalid.", "error")
        return redirect(request.form.get("next") or request.referrer or fallback_target)

    new_cover_metadata = None
    saved_paths: list[str] = []
    try:
        if cover_file is not None and cover_file.filename:
            new_cover_metadata = save_upload(
                cover_file,
                current_app.config["UPLOAD_FOLDER"],
                allowed_extensions=IMAGE_EXTENSIONS,
            )
            saved_paths.append(str(new_cover_metadata["absolute_path"]))
    except UploadValidationError as error:
        cleanup_files(saved_paths)
        flash(str(error), "error")
        return redirect(request.form.get("next") or request.referrer or fallback_target)

    previous_cover_path = book.cover_relative_path if new_cover_metadata else None

    book.title = title
    book.author_name = (request.form.get("author_name") or "").strip() or None
    book.description = (request.form.get("description") or "").strip() or None
    book.overall_review = (request.form.get("overall_review") or "").strip() or None
    book.category = category

    if new_cover_metadata:
        book.cover_original_name = new_cover_metadata["original_name"]
        book.cover_stored_name = new_cover_metadata["stored_name"]
        book.cover_relative_path = new_cover_metadata["relative_path"]
        book.cover_mime_type = new_cover_metadata["mime_type"]

    db.session.commit()

    if previous_cover_path:
        delete_attachment_file(current_app.config["UPLOAD_FOLDER"], previous_cover_path)

    flash("Book updated.", "success")
    return redirect(request.form.get("next") or request.referrer or fallback_target)


@library_bp.route("/music")
def tracks():
    search_query = (request.args.get("q") or "").strip()
    tracks_list = track_query(search_query).all()
    added_track_ids = {
        int(raw_id)
        for raw_id in (request.args.get("added") or "").split(",")
        if raw_id.isdigit()
    }
    context = build_sidebar_context(
        active_nav="music",
        search_query=search_query,
        search_action="library.tracks",
    )
    return render_template(
        "tracks.html",
        title=translate("module.music"),
        tracks=tracks_list,
        result_count=len(tracks_list),
        added_track_ids=added_track_ids,
        **context,
    )


@library_bp.route("/music/player-window")
@admin_required
def music_player_window():
    context = build_sidebar_context(active_nav="music")
    return render_template(
        "music_player_window.html",
        title=translate("player.mini_player"),
        show_sidebar=False,
        player_variant="window",
        **context,
    )


@library_bp.route("/music", methods=["POST"])
@admin_required
def create_track():
    title = (request.form.get("title") or "").strip()
    audio_files = collect_uploaded_track_files()
    if not audio_files:
        flash("Upload an audio file first.", "error")
        return redirect_back("library.tracks")

    is_bulk_upload = len(audio_files) > 1
    lyrics_file = request.files.get("lyrics_file")
    cover_file = request.files.get("cover_file")
    if is_bulk_upload and (
        (lyrics_file is not None and lyrics_file.filename) or
        (cover_file is not None and cover_file.filename)
    ):
        flash("Cover and lyrics can only be attached when uploading one track at a time.", "error")
        return redirect_back("library.tracks")

    saved_paths: list[str] = []
    created_tracks: list[Track] = []
    try:
        category = resolve_category(request.form.get("category_id"))
        lyrics_metadata = None
        if not is_bulk_upload and lyrics_file is not None and lyrics_file.filename:
            lyrics_metadata = save_upload(
                lyrics_file,
                current_app.config["UPLOAD_FOLDER"],
                allowed_extensions=LYRICS_ALLOWED_EXTENSIONS,
            )
            saved_paths.append(str(lyrics_metadata["absolute_path"]))
        cover_metadata = None
        if not is_bulk_upload and cover_file is not None and cover_file.filename:
            cover_metadata = save_upload(
                cover_file,
                current_app.config["UPLOAD_FOLDER"],
                allowed_extensions=IMAGE_EXTENSIONS,
            )
            saved_paths.append(str(cover_metadata["absolute_path"]))

        for file_storage in audio_files:
            metadata = save_upload(
                file_storage,
                current_app.config["UPLOAD_FOLDER"],
                allowed_extensions=AUDIO_ALLOWED_EXTENSIONS,
            )
            metadata = normalize_track_audio_mime(metadata)
            saved_paths.append(str(metadata["absolute_path"]))

            track_title = (
                title if len(audio_files) == 1 and title
                else infer_track_title_from_filename(str(metadata["original_name"]))
            )

            track = Track(
                title=track_title,
                artist_name=(request.form.get("artist_name") or "").strip() or None,
                description=(request.form.get("description") or "").strip() or None,
                overall_review=(request.form.get("overall_review") or "").strip() or None,
                mood=(request.form.get("mood") or "").strip() or None,
                category=category,
                owner_id=current_user.id,
                original_name=metadata["original_name"],
                stored_name=metadata["stored_name"],
                relative_path=metadata["relative_path"],
                mime_type=metadata["mime_type"],
                lyrics_original_name=lyrics_metadata["original_name"] if lyrics_metadata else None,
                lyrics_stored_name=lyrics_metadata["stored_name"] if lyrics_metadata else None,
                lyrics_relative_path=lyrics_metadata["relative_path"] if lyrics_metadata else None,
                lyrics_mime_type=lyrics_metadata["mime_type"] if lyrics_metadata else None,
                cover_original_name=cover_metadata["original_name"] if cover_metadata else None,
                cover_stored_name=cover_metadata["stored_name"] if cover_metadata else None,
                cover_relative_path=cover_metadata["relative_path"] if cover_metadata else None,
                cover_mime_type=cover_metadata["mime_type"] if cover_metadata else None,
                size_bytes=metadata["size_bytes"],
            )
            db.session.add(track)
            created_tracks.append(track)
    except (ValueError, TypeError):
        cleanup_files(saved_paths)
        flash("Track collection selection is invalid.", "error")
        return redirect_back("library.tracks")
    except UploadValidationError as error:
        cleanup_files(saved_paths)
        flash(str(error), "error")
        return redirect_back("library.tracks")
    db.session.commit()

    if len(created_tracks) == 1:
        flash("Track added to the music library.", "success")
        return redirect(url_for("library.track_detail", track_id=created_tracks[0].id))

    flash(f"{len(created_tracks)} tracks added to the music library.", "success")
    return redirect_back_with_added_tracks(
        "library.tracks",
        [track.id for track in created_tracks],
    )


@library_bp.route("/music/<int:track_id>")
def track_detail(track_id: int):
    track = get_track_or_404(track_id)
    related_tracks = Track.query.order_by(Track.created_at.desc()).all()
    lyrics_text = None
    lyrics_lines = []
    if track.lyrics_asset_path:
        lyrics_text = read_text_asset(current_app.config["UPLOAD_FOLDER"], track.lyrics_asset_path)
        lyrics_lines = parse_lrc_text(lyrics_text)
    context = build_sidebar_context(active_nav="music", search_action="library.tracks")
    return render_template(
        "track_detail.html",
        title=track.title,
        track=track,
        related_tracks=related_tracks,
        lyrics_text=lyrics_text,
        lyrics_lines=lyrics_lines,
        **context,
    )


@library_bp.route("/music/<int:track_id>/edit", methods=["POST"])
@admin_required
def update_track(track_id: int):
    track = get_track_or_404(track_id)
    fallback_target = url_for("library.track_detail", track_id=track.id)
    title = (request.form.get("title") or "").strip()
    if not title:
        flash("Track title is required.", "error")
        return redirect(request.form.get("next") or request.referrer or fallback_target)

    lyrics_file = request.files.get("lyrics_file")
    cover_file = request.files.get("cover_file")

    try:
        track.category = resolve_category(request.form.get("category_id"))
    except (ValueError, TypeError):
        flash("Track collection selection is invalid.", "error")
        return redirect(request.form.get("next") or request.referrer or fallback_target)

    saved_paths: list[str] = []
    new_lyrics_metadata = None
    new_cover_metadata = None

    try:
        if lyrics_file is not None and lyrics_file.filename:
            new_lyrics_metadata = save_upload(
                lyrics_file,
                current_app.config["UPLOAD_FOLDER"],
                allowed_extensions=LYRICS_ALLOWED_EXTENSIONS,
            )
            saved_paths.append(str(new_lyrics_metadata["absolute_path"]))
        if cover_file is not None and cover_file.filename:
            new_cover_metadata = save_upload(
                cover_file,
                current_app.config["UPLOAD_FOLDER"],
                allowed_extensions=IMAGE_EXTENSIONS,
            )
            saved_paths.append(str(new_cover_metadata["absolute_path"]))
    except UploadValidationError as error:
        cleanup_files(saved_paths)
        flash(str(error), "error")
        return redirect(request.form.get("next") or request.referrer or fallback_target)

    previous_lyrics_path = track.lyrics_relative_path if new_lyrics_metadata else None
    previous_cover_path = track.cover_relative_path if new_cover_metadata else None

    track.title = title
    track.artist_name = (request.form.get("artist_name") or "").strip() or None
    track.mood = (request.form.get("mood") or "").strip() or None
    track.description = (request.form.get("description") or "").strip() or None
    track.overall_review = (request.form.get("overall_review") or "").strip() or None

    if new_lyrics_metadata:
        track.lyrics_original_name = new_lyrics_metadata["original_name"]
        track.lyrics_stored_name = new_lyrics_metadata["stored_name"]
        track.lyrics_relative_path = new_lyrics_metadata["relative_path"]
        track.lyrics_mime_type = new_lyrics_metadata["mime_type"]

    if new_cover_metadata:
        track.cover_original_name = new_cover_metadata["original_name"]
        track.cover_stored_name = new_cover_metadata["stored_name"]
        track.cover_relative_path = new_cover_metadata["relative_path"]
        track.cover_mime_type = new_cover_metadata["mime_type"]

    db.session.commit()

    if previous_lyrics_path:
        delete_attachment_file(current_app.config["UPLOAD_FOLDER"], previous_lyrics_path)
    if previous_cover_path:
        delete_attachment_file(current_app.config["UPLOAD_FOLDER"], previous_cover_path)

    flash("Track updated.", "success")
    return redirect(request.form.get("next") or request.referrer or fallback_target)


@library_bp.route("/music/<int:track_id>/comments", methods=["POST"])
@admin_required
def create_track_comment(track_id: int):
    track = get_track_or_404(track_id)
    comment = (request.form.get("comment") or "").strip()
    if not comment:
        flash("Write something about this moment in the track.", "error")
        return redirect_back("library.track_detail")

    try:
        timestamp_seconds = parse_optional_timestamp(request.form.get("timestamp_seconds"))
    except ValueError:
        flash("Use a timestamp like 01:24.", "error")
        return redirect_back("library.track_detail")

    db.session.add(
        TrackComment(
            track_id=track.id,
            owner_id=current_user.id,
            timestamp_seconds=timestamp_seconds,
            comment=comment,
        )
    )
    db.session.commit()
    flash("Track comment saved.", "success")
    next_target = request.form.get("next") or request.referrer
    return redirect(next_target or url_for("library.track_detail", track_id=track.id))


@library_bp.route("/videos")
def videos():
    search_query = (request.args.get("q") or "").strip()
    selected_video_folder_id = None
    try:
        selected_video_folder = resolve_category(request.args.get("folder_id"))
    except (TypeError, ValueError):
        selected_video_folder = None
    if selected_video_folder is not None:
        selected_video_folder_id = selected_video_folder.id

    videos_list = video_query(search_query, selected_video_folder_id).all()
    ensure_library_video_previews(videos_list)
    context = build_sidebar_context(
        active_nav="videos",
        search_query=search_query,
        search_action="library.videos",
    )
    return render_template(
        "videos.html",
        title=translate("module.videos"),
        videos=videos_list,
        result_count=len(videos_list),
        selected_video_folder_id=selected_video_folder_id,
        **context,
    )


@library_bp.route("/videos", methods=["POST"])
@admin_required
def create_video():
    title = (request.form.get("title") or "").strip()
    if not title:
        flash("Video title is required.", "error")
        return redirect_back("library.videos")

    file_storage = request.files.get("video_file")
    if file_storage is None or not file_storage.filename:
        flash("Upload a video first.", "error")
        return redirect_back("library.videos")

    try:
        category = resolve_category(request.form.get("category_id"))
        metadata = save_upload(
            file_storage,
            current_app.config["UPLOAD_FOLDER"],
            allowed_extensions=VIDEO_ALLOWED_EXTENSIONS,
        )
    except (ValueError, TypeError):
        flash("Video collection selection is invalid.", "error")
        return redirect_back("library.videos")
    except UploadValidationError as error:
        flash(str(error), "error")
        return redirect_back("library.videos")

    video = VideoEntry(
        title=title,
        description=(request.form.get("description") or "").strip() or None,
        overall_review=(request.form.get("overall_review") or "").strip() or None,
        category=category,
        owner_id=current_user.id,
        original_name=metadata["original_name"],
        stored_name=metadata["stored_name"],
        relative_path=metadata["relative_path"],
        mime_type=metadata["mime_type"],
        size_bytes=metadata["size_bytes"],
    )
    ensure_video_entry_preview(video, current_app.config["UPLOAD_FOLDER"])
    db.session.add(video)
    db.session.commit()

    flash("Video added to the library.", "success")
    return redirect(url_for("library.video_detail", video_id=video.id))


@library_bp.route("/videos/<int:video_id>")
def video_detail(video_id: int):
    video = get_video_or_404(video_id)
    ensure_library_video_previews([video])
    context = build_sidebar_context(active_nav="videos", search_action="library.videos")
    return render_template(
        "video_detail.html",
        title=video.title,
        video=video,
        **context,
    )


@library_bp.route("/videos/<int:video_id>/comments", methods=["POST"])
@admin_required
def create_video_comment(video_id: int):
    video = get_video_or_404(video_id)
    comment = (request.form.get("comment") or "").strip()
    if not comment:
        flash("Write a note for this video moment.", "error")
        return redirect_back("library.video_detail")

    try:
        timestamp_seconds = parse_optional_timestamp(request.form.get("timestamp_seconds"))
    except ValueError:
        flash("Use a timestamp like 00:42.", "error")
        return redirect_back("library.video_detail")

    db.session.add(
        VideoComment(
            video_id=video.id,
            owner_id=current_user.id,
            timestamp_seconds=timestamp_seconds,
            comment=comment,
        )
    )
    db.session.commit()
    flash("Video note saved.", "success")
    next_target = request.form.get("next") or request.referrer
    return redirect(next_target or url_for("library.video_detail", video_id=video.id))

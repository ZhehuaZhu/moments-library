from __future__ import annotations

from sqlalchemy import inspect, text

from ..extensions import db
from ..models import MomentRevision
from .folders import serialize_folder_snapshot


def ensure_local_schema() -> None:
    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())

    if "categories" in existing_tables:
        category_columns = {column["name"] for column in inspector.get_columns("categories")}
        if "description" not in category_columns:
            db.session.execute(text("ALTER TABLE categories ADD COLUMN description TEXT"))
        if "parent_id" not in category_columns:
            db.session.execute(text("ALTER TABLE categories ADD COLUMN parent_id INTEGER"))

    if "users" in existing_tables:
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        if "workspace_name" not in user_columns:
            db.session.execute(text("ALTER TABLE users ADD COLUMN workspace_name TEXT"))
        if "workspace_tagline" not in user_columns:
            db.session.execute(text("ALTER TABLE users ADD COLUMN workspace_tagline TEXT"))
        if "feed_label" not in user_columns:
            db.session.execute(text("ALTER TABLE users ADD COLUMN feed_label TEXT"))
        if "books_label" not in user_columns:
            db.session.execute(text("ALTER TABLE users ADD COLUMN books_label TEXT"))
        if "music_label" not in user_columns:
            db.session.execute(text("ALTER TABLE users ADD COLUMN music_label TEXT"))
        if "videos_label" not in user_columns:
            db.session.execute(text("ALTER TABLE users ADD COLUMN videos_label TEXT"))

    if "books" in existing_tables:
        book_columns = {column["name"] for column in inspector.get_columns("books")}
        if "reader_relative_path" not in book_columns:
            db.session.execute(text("ALTER TABLE books ADD COLUMN reader_relative_path TEXT"))
        if "reader_mime_type" not in book_columns:
            db.session.execute(text("ALTER TABLE books ADD COLUMN reader_mime_type TEXT"))
        if "reader_format" not in book_columns:
            db.session.execute(text("ALTER TABLE books ADD COLUMN reader_format TEXT"))
        if "cover_original_name" not in book_columns:
            db.session.execute(text("ALTER TABLE books ADD COLUMN cover_original_name TEXT"))
        if "cover_stored_name" not in book_columns:
            db.session.execute(text("ALTER TABLE books ADD COLUMN cover_stored_name TEXT"))
        if "cover_relative_path" not in book_columns:
            db.session.execute(text("ALTER TABLE books ADD COLUMN cover_relative_path TEXT"))
        if "cover_mime_type" not in book_columns:
            db.session.execute(text("ALTER TABLE books ADD COLUMN cover_mime_type TEXT"))
        if "last_read_section_index" not in book_columns:
            db.session.execute(text("ALTER TABLE books ADD COLUMN last_read_section_index INTEGER"))
        if "last_read_scroll_ratio" not in book_columns:
            db.session.execute(text("ALTER TABLE books ADD COLUMN last_read_scroll_ratio FLOAT"))
        if "last_read_at" not in book_columns:
            db.session.execute(text("ALTER TABLE books ADD COLUMN last_read_at DATETIME"))
        if "total_reading_seconds" not in book_columns:
            db.session.execute(text("ALTER TABLE books ADD COLUMN total_reading_seconds INTEGER NOT NULL DEFAULT 0"))
        if "last_read_session_key" not in book_columns:
            db.session.execute(text("ALTER TABLE books ADD COLUMN last_read_session_key TEXT"))
        if "last_read_session_seconds" not in book_columns:
            db.session.execute(text("ALTER TABLE books ADD COLUMN last_read_session_seconds INTEGER NOT NULL DEFAULT 0"))

    if "moments" in existing_tables:
        moment_columns = {column["name"] for column in inspector.get_columns("moments")}
        if "cross_post_targets" not in moment_columns:
            db.session.execute(text("ALTER TABLE moments ADD COLUMN cross_post_targets TEXT"))
        if "country_code" not in moment_columns:
            db.session.execute(text("ALTER TABLE moments ADD COLUMN country_code TEXT"))
        if "country_name" not in moment_columns:
            db.session.execute(text("ALTER TABLE moments ADD COLUMN country_name TEXT"))
        if "admin_area" not in moment_columns:
            db.session.execute(text("ALTER TABLE moments ADD COLUMN admin_area TEXT"))
        if "city_name" not in moment_columns:
            db.session.execute(text("ALTER TABLE moments ADD COLUMN city_name TEXT"))
        if "district_name" not in moment_columns:
            db.session.execute(text("ALTER TABLE moments ADD COLUMN district_name TEXT"))
        if "place_key" not in moment_columns:
            db.session.execute(text("ALTER TABLE moments ADD COLUMN place_key TEXT"))
        if "location_source" not in moment_columns:
            db.session.execute(text("ALTER TABLE moments ADD COLUMN location_source TEXT"))
        if "citation_kind" not in moment_columns:
            db.session.execute(text("ALTER TABLE moments ADD COLUMN citation_kind TEXT"))
        if "citation_target_id" not in moment_columns:
            db.session.execute(text("ALTER TABLE moments ADD COLUMN citation_target_id INTEGER"))
        if "citation_label" not in moment_columns:
            db.session.execute(text("ALTER TABLE moments ADD COLUMN citation_label TEXT"))
        if "citation_title" not in moment_columns:
            db.session.execute(text("ALTER TABLE moments ADD COLUMN citation_title TEXT"))
        if "citation_subtitle" not in moment_columns:
            db.session.execute(text("ALTER TABLE moments ADD COLUMN citation_subtitle TEXT"))
        if "citation_excerpt" not in moment_columns:
            db.session.execute(text("ALTER TABLE moments ADD COLUMN citation_excerpt TEXT"))
        if "citation_href" not in moment_columns:
            db.session.execute(text("ALTER TABLE moments ADD COLUMN citation_href TEXT"))
        if "citation_cover_path" not in moment_columns:
            db.session.execute(text("ALTER TABLE moments ADD COLUMN citation_cover_path TEXT"))

    if "attachments" in existing_tables:
        attachment_columns = {column["name"] for column in inspector.get_columns("attachments")}
        if "preview_relative_path" not in attachment_columns:
            db.session.execute(text("ALTER TABLE attachments ADD COLUMN preview_relative_path TEXT"))
        if "preview_mime_type" not in attachment_columns:
            db.session.execute(text("ALTER TABLE attachments ADD COLUMN preview_mime_type TEXT"))
        if "poster_relative_path" not in attachment_columns:
            db.session.execute(text("ALTER TABLE attachments ADD COLUMN poster_relative_path TEXT"))
        if "poster_mime_type" not in attachment_columns:
            db.session.execute(text("ALTER TABLE attachments ADD COLUMN poster_mime_type TEXT"))

    if "tracks" in existing_tables:
        track_columns = {column["name"] for column in inspector.get_columns("tracks")}
        if "lyrics_original_name" not in track_columns:
            db.session.execute(text("ALTER TABLE tracks ADD COLUMN lyrics_original_name TEXT"))
        if "lyrics_stored_name" not in track_columns:
            db.session.execute(text("ALTER TABLE tracks ADD COLUMN lyrics_stored_name TEXT"))
        if "lyrics_relative_path" not in track_columns:
            db.session.execute(text("ALTER TABLE tracks ADD COLUMN lyrics_relative_path TEXT"))
        if "lyrics_mime_type" not in track_columns:
            db.session.execute(text("ALTER TABLE tracks ADD COLUMN lyrics_mime_type TEXT"))
        if "cover_original_name" not in track_columns:
            db.session.execute(text("ALTER TABLE tracks ADD COLUMN cover_original_name TEXT"))
        if "cover_stored_name" not in track_columns:
            db.session.execute(text("ALTER TABLE tracks ADD COLUMN cover_stored_name TEXT"))
        if "cover_relative_path" not in track_columns:
            db.session.execute(text("ALTER TABLE tracks ADD COLUMN cover_relative_path TEXT"))
        if "cover_mime_type" not in track_columns:
            db.session.execute(text("ALTER TABLE tracks ADD COLUMN cover_mime_type TEXT"))

    if "videos" in existing_tables:
        video_columns = {column["name"] for column in inspector.get_columns("videos")}
        if "preview_relative_path" not in video_columns:
            db.session.execute(text("ALTER TABLE videos ADD COLUMN preview_relative_path TEXT"))
        if "preview_mime_type" not in video_columns:
            db.session.execute(text("ALTER TABLE videos ADD COLUMN preview_mime_type TEXT"))
        if "poster_relative_path" not in video_columns:
            db.session.execute(text("ALTER TABLE videos ADD COLUMN poster_relative_path TEXT"))
        if "poster_mime_type" not in video_columns:
            db.session.execute(text("ALTER TABLE videos ADD COLUMN poster_mime_type TEXT"))

    if "book_annotations" in existing_tables:
        annotation_columns = {
            column["name"] for column in inspector.get_columns("book_annotations")
        }
        if "section_index" not in annotation_columns:
            db.session.execute(text("ALTER TABLE book_annotations ADD COLUMN section_index INTEGER"))
        if "paragraph_id" not in annotation_columns:
            db.session.execute(text("ALTER TABLE book_annotations ADD COLUMN paragraph_id TEXT"))
        if "selection_start" not in annotation_columns:
            db.session.execute(text("ALTER TABLE book_annotations ADD COLUMN selection_start INTEGER"))
        if "selection_end" not in annotation_columns:
            db.session.execute(text("ALTER TABLE book_annotations ADD COLUMN selection_end INTEGER"))

    if "moment_revisions" in existing_tables:
        revision_columns = {column["name"] for column in inspector.get_columns("moment_revisions")}
        if "country_code" not in revision_columns:
            db.session.execute(text("ALTER TABLE moment_revisions ADD COLUMN country_code TEXT"))
        if "country_name" not in revision_columns:
            db.session.execute(text("ALTER TABLE moment_revisions ADD COLUMN country_name TEXT"))
        if "admin_area" not in revision_columns:
            db.session.execute(text("ALTER TABLE moment_revisions ADD COLUMN admin_area TEXT"))
        if "city_name" not in revision_columns:
            db.session.execute(text("ALTER TABLE moment_revisions ADD COLUMN city_name TEXT"))
        if "district_name" not in revision_columns:
            db.session.execute(text("ALTER TABLE moment_revisions ADD COLUMN district_name TEXT"))
        if "place_key" not in revision_columns:
            db.session.execute(text("ALTER TABLE moment_revisions ADD COLUMN place_key TEXT"))
        if "location_source" not in revision_columns:
            db.session.execute(text("ALTER TABLE moment_revisions ADD COLUMN location_source TEXT"))
        if "folder_snapshot" not in revision_columns:
            db.session.execute(text("ALTER TABLE moment_revisions ADD COLUMN folder_snapshot TEXT"))

    db.session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS moment_folders (
                moment_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                PRIMARY KEY (moment_id, category_id)
            )
            """
        )
    )
    db.session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_moment_folders_category_id ON moment_folders (category_id)"
        )
    )
    if "book_annotations" in existing_tables:
        db.session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_book_annotations_section_index ON book_annotations (section_index)"
            )
        )
        db.session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_book_annotations_paragraph_id ON book_annotations (paragraph_id)"
            )
        )
    if "moments" in existing_tables:
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_moments_country_code ON moments (country_code)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS ix_moments_place_key ON moments (place_key)"))
        db.session.execute(
            text("CREATE INDEX IF NOT EXISTS ix_moments_citation_kind ON moments (citation_kind)")
        )
        db.session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_moments_citation_target_id ON moments (citation_target_id)"
            )
        )
    db.session.execute(
        text(
            """
            INSERT OR IGNORE INTO moment_folders (moment_id, category_id)
            SELECT id, category_id
            FROM moments
            WHERE category_id IS NOT NULL
            """
        )
    )
    db.session.commit()

    revisions = MomentRevision.query.filter(MomentRevision.folder_snapshot.is_(None)).all()
    for revision in revisions:
        snapshot = serialize_folder_snapshot(
            [revision.category] if revision.category is not None else []
        )
        revision.folder_snapshot = snapshot

    db.session.commit()

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from flask_login import UserMixin

from .extensions import db


moment_folders = db.Table(
    "moment_folders",
    db.Column("moment_id", db.Integer, db.ForeignKey("moments.id"), primary_key=True),
    db.Column("category_id", db.Integer, db.ForeignKey("categories.id"), primary_key=True),
)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    workspace_name = db.Column(db.String(120), nullable=True)
    workspace_tagline = db.Column(db.String(120), nullable=True)
    feed_label = db.Column(db.String(40), nullable=True)
    books_label = db.Column(db.String(40), nullable=True)
    music_label = db.Column(db.String(40), nullable=True)
    videos_label = db.Column(db.String(40), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    moments = db.relationship("Moment", back_populates="author", lazy="dynamic")
    revisions = db.relationship("MomentRevision", back_populates="editor", lazy="dynamic")
    books = db.relationship("Book", back_populates="owner", lazy="dynamic")
    book_annotations = db.relationship("BookAnnotation", back_populates="owner", lazy="dynamic")
    tracks = db.relationship("Track", back_populates="owner", lazy="dynamic")
    track_comments = db.relationship("TrackComment", back_populates="owner", lazy="dynamic")
    videos = db.relationship("VideoEntry", back_populates="owner", lazy="dynamic")
    video_comments = db.relationship("VideoComment", back_populates="owner", lazy="dynamic")

    @property
    def resolved_workspace_name(self) -> str:
        return (self.workspace_name or "").strip() or "Quiet Atlas"

    @property
    def resolved_workspace_tagline(self) -> str:
        return (self.workspace_tagline or "").strip() or "Private archive"

    @property
    def resolved_feed_label(self) -> str:
        return (self.feed_label or "").strip() or "Feed"

    @property
    def resolved_books_label(self) -> str:
        return (self.books_label or "").strip() or "Books"

    @property
    def resolved_music_label(self) -> str:
        return (self.music_label or "").strip() or "Music"

    @property
    def resolved_videos_label(self) -> str:
        return (self.videos_label or "").strip() or "Videos"

    @property
    def resolved_module_labels(self) -> dict[str, str]:
        return {
            "feed": self.resolved_feed_label,
            "books": self.resolved_books_label,
            "music": self.resolved_music_label,
            "videos": self.resolved_videos_label,
        }


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80, collation="NOCASE"), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    parent_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    parent = db.relationship("Category", remote_side=[id], back_populates="children")
    children = db.relationship(
        "Category",
        back_populates="parent",
        order_by="Category.name.asc()",
    )
    moments = db.relationship("Moment", secondary=moment_folders, back_populates="categories")


class Moment(db.Model):
    __tablename__ = "moments"

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=True)
    cross_post_targets = db.Column(db.Text, nullable=True)
    location_label = db.Column(db.String(255), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    country_code = db.Column(db.String(16), nullable=True, index=True)
    country_name = db.Column(db.String(120), nullable=True)
    admin_area = db.Column(db.String(120), nullable=True)
    city_name = db.Column(db.String(120), nullable=True)
    district_name = db.Column(db.String(120), nullable=True)
    place_key = db.Column(db.String(64), nullable=True, index=True)
    location_source = db.Column(db.String(24), nullable=True)
    citation_kind = db.Column(db.String(40), nullable=True, index=True)
    citation_target_id = db.Column(db.Integer, nullable=True, index=True)
    citation_label = db.Column(db.String(80), nullable=True)
    citation_title = db.Column(db.String(255), nullable=True)
    citation_subtitle = db.Column(db.String(255), nullable=True)
    citation_excerpt = db.Column(db.Text, nullable=True)
    citation_href = db.Column(db.String(255), nullable=True)
    citation_cover_path = db.Column(db.String(255), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    is_deleted = db.Column(db.Boolean, nullable=False, default=False, index=True)
    deleted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    author = db.relationship("User", back_populates="moments")
    category = db.relationship("Category", foreign_keys=[category_id])
    categories = db.relationship(
        "Category",
        secondary=moment_folders,
        back_populates="moments",
        order_by="Category.name.asc()",
    )
    attachments = db.relationship(
        "Attachment",
        back_populates="moment",
        cascade="all, delete-orphan",
        order_by="Attachment.created_at.asc()",
    )
    revisions = db.relationship(
        "MomentRevision",
        back_populates="moment",
        cascade="all, delete-orphan",
        order_by="MomentRevision.edited_at.desc()",
    )

    @property
    def is_edited(self) -> bool:
        return bool(self.revisions)

    @property
    def assigned_categories(self) -> list[Category]:
        assigned = list(self.categories)

        if self.category is not None:
            if not any(category.id == self.category.id for category in assigned):
                assigned.insert(0, self.category)
            else:
                assigned.sort(
                    key=lambda category: (
                        0 if category.id == self.category.id else 1,
                        category.name.lower(),
                        category.id,
                    )
                )

        return assigned

    @property
    def category_ids_list(self) -> list[int]:
        return [category.id for category in self.assigned_categories]

    @property
    def primary_category(self) -> Category | None:
        return self.category or (self.assigned_categories[0] if self.assigned_categories else None)

    @property
    def primary_category_name(self) -> str:
        primary = self.primary_category
        return primary.name if primary else "Uncategorized"

    @property
    def has_citation(self) -> bool:
        return bool(self.citation_kind and self.citation_title)

    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    @property
    def citation_card(self) -> dict[str, str | int | None] | None:
        if not self.has_citation:
            return None
        return {
            "kind": self.citation_kind,
            "target_id": self.citation_target_id,
            "label": self.citation_label,
            "title": self.citation_title,
            "subtitle": self.citation_subtitle,
            "excerpt": self.citation_excerpt,
            "href": self.citation_href,
            "cover_path": self.citation_cover_path,
        }

    def set_categories(self, categories: list[Category]) -> None:
        unique_categories: list[Category] = []
        seen_ids: set[int] = set()

        for category in categories:
            if category.id in seen_ids:
                continue
            unique_categories.append(category)
            seen_ids.add(category.id)

        self.categories = unique_categories
        self.category = unique_categories[0] if unique_categories else None


class MomentRevision(db.Model):
    __tablename__ = "moment_revisions"

    id = db.Column(db.Integer, primary_key=True)
    moment_id = db.Column(db.Integer, db.ForeignKey("moments.id"), nullable=False, index=True)
    content = db.Column(db.Text, nullable=True)
    location_label = db.Column(db.String(255), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    country_code = db.Column(db.String(16), nullable=True)
    country_name = db.Column(db.String(120), nullable=True)
    admin_area = db.Column(db.String(120), nullable=True)
    city_name = db.Column(db.String(120), nullable=True)
    district_name = db.Column(db.String(120), nullable=True)
    place_key = db.Column(db.String(64), nullable=True)
    location_source = db.Column(db.String(24), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True, index=True)
    folder_snapshot = db.Column(db.Text, nullable=True)
    edited_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    edited_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    moment = db.relationship("Moment", back_populates="revisions")
    category = db.relationship("Category")
    editor = db.relationship("User", back_populates="revisions")

    @property
    def snapshot_categories(self) -> list[dict[str, int | str | None]]:
        if self.folder_snapshot:
            try:
                payload = json.loads(self.folder_snapshot)
            except json.JSONDecodeError:
                payload = []

            if isinstance(payload, list):
                normalized: list[dict[str, int | str | None]] = []
                for item in payload:
                    if isinstance(item, dict) and item.get("name"):
                        normalized.append(
                            {
                                "id": item.get("id"),
                                "name": item["name"],
                            }
                        )
                    elif isinstance(item, str) and item:
                        normalized.append({"id": None, "name": item})
                if normalized:
                    return normalized

        if self.category is not None:
            return [{"id": self.category.id, "name": self.category.name}]

        return []


class Attachment(db.Model):
    __tablename__ = "attachments"

    id = db.Column(db.Integer, primary_key=True)
    moment_id = db.Column(db.Integer, db.ForeignKey("moments.id"), nullable=False, index=True)
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False, unique=True)
    relative_path = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(120), nullable=False)
    media_kind = db.Column(db.String(20), nullable=False)
    preview_relative_path = db.Column(db.String(255), nullable=True)
    preview_mime_type = db.Column(db.String(120), nullable=True)
    poster_relative_path = db.Column(db.String(255), nullable=True)
    poster_mime_type = db.Column(db.String(120), nullable=True)
    size_bytes = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    moment = db.relationship("Moment", back_populates="attachments")

    @property
    def extension(self) -> str:
        return Path(self.original_name).suffix.lower()

    @property
    def is_pdf(self) -> bool:
        return self.extension == ".pdf"

    @property
    def preview_asset_path(self) -> str:
        return self.preview_relative_path or self.relative_path

    @property
    def preview_asset_mime_type(self) -> str:
        return self.preview_mime_type or self.mime_type

    @property
    def poster_asset_path(self) -> str | None:
        return self.poster_relative_path

    @property
    def managed_relative_paths(self) -> list[str]:
        values = [
            self.relative_path,
            self.preview_relative_path,
            self.poster_relative_path,
        ]
        return [value for value in values if value]


class Book(db.Model):
    __tablename__ = "books"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    author_name = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    overall_review = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(40), nullable=False, default="reading", index=True)
    started_at = db.Column(db.Date, nullable=True)
    finished_at = db.Column(db.Date, nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True, index=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    source_format = db.Column(db.String(20), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False, unique=True)
    relative_path = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(120), nullable=False)
    reader_relative_path = db.Column(db.String(255), nullable=True)
    reader_mime_type = db.Column(db.String(120), nullable=True)
    reader_format = db.Column(db.String(20), nullable=True)
    cover_original_name = db.Column(db.String(255), nullable=True)
    cover_stored_name = db.Column(db.String(255), nullable=True)
    cover_relative_path = db.Column(db.String(255), nullable=True)
    cover_mime_type = db.Column(db.String(120), nullable=True)
    last_read_section_index = db.Column(db.Integer, nullable=True)
    last_read_scroll_ratio = db.Column(db.Float, nullable=True)
    last_read_at = db.Column(db.DateTime, nullable=True)
    size_bytes = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    owner = db.relationship("User", back_populates="books")
    category = db.relationship("Category")
    annotations = db.relationship(
        "BookAnnotation",
        back_populates="book",
        cascade="all, delete-orphan",
        order_by="BookAnnotation.created_at.desc()",
    )

    @property
    def extension(self) -> str:
        return Path(self.original_name).suffix.lower()

    @property
    def effective_format(self) -> str:
        return (self.reader_format or self.source_format or "").lower()

    @property
    def reader_asset_path(self) -> str:
        return self.reader_relative_path or self.relative_path

    @property
    def reader_kind(self) -> str:
        if self.effective_format == "pdf":
            return "pdf"
        if self.effective_format in {"txt", "md"}:
            return "text"
        if self.effective_format == "docx":
            return "docx"
        if self.effective_format == "epub":
            return "epub"
        if self.effective_format == "html":
            return "html"
        if self.effective_format == "mobi":
            return "mobi"
        return "document"

    @property
    def supports_selection_notes(self) -> bool:
        return self.reader_kind in {"text", "docx", "html"}

    @property
    def supports_precise_selection_notes(self) -> bool:
        return self.reader_kind == "html"

    @property
    def cover_seed(self) -> str:
        words = [segment for segment in self.title.split() if segment]
        if len(words) >= 2:
            return f"{words[0][0]}{words[1][0]}".upper()
        if words:
            return words[0][:2].upper()
        return "BK"


class BookAnnotation(db.Model):
    __tablename__ = "book_annotations"

    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey("books.id"), nullable=False, index=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    annotation_type = db.Column(db.String(40), nullable=False, default="text_selection")
    chapter_label = db.Column(db.String(255), nullable=True)
    page_label = db.Column(db.String(50), nullable=True)
    section_index = db.Column(db.Integer, nullable=True, index=True)
    paragraph_id = db.Column(db.String(120), nullable=True, index=True)
    selection_start = db.Column(db.Integer, nullable=True)
    selection_end = db.Column(db.Integer, nullable=True)
    quoted_text = db.Column(db.Text, nullable=True)
    comment = db.Column(db.Text, nullable=False)
    tag = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    book = db.relationship("Book", back_populates="annotations")
    owner = db.relationship("User", back_populates="book_annotations")

    @property
    def has_text_anchor(self) -> bool:
        return (
            self.section_index is not None
            and bool(self.paragraph_id)
            and self.selection_start is not None
            and self.selection_end is not None
            and self.selection_end > self.selection_start
        )


class Track(db.Model):
    __tablename__ = "tracks"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    artist_name = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    overall_review = db.Column(db.Text, nullable=True)
    mood = db.Column(db.String(120), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True, index=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False, unique=True)
    relative_path = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(120), nullable=False)
    lyrics_original_name = db.Column(db.String(255), nullable=True)
    lyrics_stored_name = db.Column(db.String(255), nullable=True)
    lyrics_relative_path = db.Column(db.String(255), nullable=True)
    lyrics_mime_type = db.Column(db.String(120), nullable=True)
    cover_original_name = db.Column(db.String(255), nullable=True)
    cover_stored_name = db.Column(db.String(255), nullable=True)
    cover_relative_path = db.Column(db.String(255), nullable=True)
    cover_mime_type = db.Column(db.String(120), nullable=True)
    size_bytes = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    owner = db.relationship("User", back_populates="tracks")
    category = db.relationship("Category")
    comments = db.relationship(
        "TrackComment",
        back_populates="track",
        cascade="all, delete-orphan",
        order_by="TrackComment.timestamp_seconds.asc(), TrackComment.created_at.asc()",
    )

    @property
    def extension(self) -> str:
        return Path(self.original_name).suffix.lower()

    @property
    def has_lyrics(self) -> bool:
        return bool(self.lyrics_relative_path)

    @property
    def lyrics_asset_path(self) -> str | None:
        return self.lyrics_relative_path

    @property
    def cover_asset_path(self) -> str | None:
        return self.cover_relative_path

    @property
    def cover_seed(self) -> str:
        words = [segment for segment in self.title.split() if segment]
        if len(words) >= 2:
            return f"{words[0][0]}{words[1][0]}".upper()
        if words:
            return words[0][:2].upper()
        return "MU"


class TrackComment(db.Model):
    __tablename__ = "track_comments"

    id = db.Column(db.Integer, primary_key=True)
    track_id = db.Column(db.Integer, db.ForeignKey("tracks.id"), nullable=False, index=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    timestamp_seconds = db.Column(db.Integer, nullable=True, index=True)
    comment = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    track = db.relationship("Track", back_populates="comments")
    owner = db.relationship("User", back_populates="track_comments")


class VideoEntry(db.Model):
    __tablename__ = "videos"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    overall_review = db.Column(db.Text, nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True, index=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False, unique=True)
    relative_path = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(120), nullable=False)
    preview_relative_path = db.Column(db.String(255), nullable=True)
    preview_mime_type = db.Column(db.String(120), nullable=True)
    poster_relative_path = db.Column(db.String(255), nullable=True)
    poster_mime_type = db.Column(db.String(120), nullable=True)
    size_bytes = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    owner = db.relationship("User", back_populates="videos")
    category = db.relationship("Category")
    comments = db.relationship(
        "VideoComment",
        back_populates="video",
        cascade="all, delete-orphan",
        order_by="VideoComment.timestamp_seconds.asc(), VideoComment.created_at.asc()",
    )

    @property
    def preview_asset_path(self) -> str:
        return self.preview_relative_path or self.relative_path

    @property
    def preview_asset_mime_type(self) -> str:
        return self.preview_mime_type or self.mime_type

    @property
    def poster_asset_path(self) -> str | None:
        return self.poster_relative_path

    @property
    def cover_seed(self) -> str:
        words = [segment for segment in self.title.split() if segment]
        if len(words) >= 2:
            return f"{words[0][0]}{words[1][0]}".upper()
        if words:
            return words[0][:2].upper()
        return "VD"


class VideoComment(db.Model):
    __tablename__ = "video_comments"

    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey("videos.id"), nullable=False, index=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    timestamp_seconds = db.Column(db.Integer, nullable=True, index=True)
    comment = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    video = db.relationship("VideoEntry", back_populates="comments")
    owner = db.relationship("User", back_populates="video_comments")

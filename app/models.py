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
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    moments = db.relationship("Moment", back_populates="author", lazy="dynamic")
    revisions = db.relationship("MomentRevision", back_populates="editor", lazy="dynamic")


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
    location_label = db.Column(db.String(255), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
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
    size_bytes = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    moment = db.relationship("Moment", back_populates="attachments")

    @property
    def extension(self) -> str:
        return Path(self.original_name).suffix.lower()

    @property
    def is_pdf(self) -> bool:
        return self.extension == ".pdf"

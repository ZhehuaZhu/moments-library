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

    if "moment_revisions" in existing_tables:
        revision_columns = {column["name"] for column in inspector.get_columns("moment_revisions")}
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

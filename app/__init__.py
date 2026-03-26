from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

import click
from flask import Flask, jsonify, redirect, request, url_for
from flask import g
from flask_wtf.csrf import CSRFError
from sqlalchemy.orm import selectinload
from werkzeug.security import generate_password_hash

from .blueprints.api import api_bp
from .blueprints.auth import auth_bp
from .blueprints.library import library_bp
from .blueprints.main import main_bp
from .extensions import csrf, db, login_manager, migrate
from .models import Book, Moment, Track, User, VideoEntry
from .services.i18n import (
    LANGUAGE_COOKIE_NAME,
    LANGUAGE_OPTIONS,
    build_client_translations,
    get_annotation_tag_choices,
    get_book_status_choices,
    get_current_language,
    normalize_language,
    translate,
)
from .services.library import seconds_to_clock
from .services.schema import ensure_local_schema
from .services.storage import delete_attachment_file


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)

    os.makedirs(app.instance_path, exist_ok=True)

    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-change-me"),
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{Path(app.instance_path) / 'app.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=200 * 1024 * 1024,
        NOMINATIM_USER_AGENT=os.environ.get(
            "NOMINATIM_USER_AGENT", "personal-moments-library/1.0 (local)"
        ),
    )
    app.config["UPLOAD_FOLDER"] = str(Path(app.static_folder) / "uploads")

    if test_config:
        app.config.update(test_config)

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    register_blueprints(app)
    register_filters(app)
    register_i18n(app)
    register_cli_commands(app)
    register_error_handlers(app)

    with app.app_context():
        db.create_all()
        ensure_local_schema()

    @app.shell_context_processor
    def shell_context() -> dict[str, object]:
        return {
            "db": db,
            "User": User,
            "Moment": Moment,
            "Book": Book,
            "Track": Track,
            "VideoEntry": VideoEntry,
        }

    return app


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(main_bp)
    app.register_blueprint(library_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)


def register_filters(app: Flask) -> None:
    @app.template_filter("datetimeformat")
    def datetimeformat(value: datetime | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
        if value is None:
            return ""
        return value.strftime(fmt)

    @app.template_filter("dateformat")
    def dateformat(value, fmt: str = "%Y-%m-%d") -> str:
        if value is None:
            return ""
        return value.strftime(fmt)

    @app.template_filter("clockformat")
    def clockformat(value: int | None) -> str:
        return seconds_to_clock(value)


def register_i18n(app: Flask) -> None:
    @app.before_request
    def load_current_language() -> None:
        g.current_language = normalize_language(request.cookies.get(LANGUAGE_COOKIE_NAME))

    @app.context_processor
    def inject_i18n_context() -> dict[str, object]:
        current_lang = get_current_language()
        available_languages = [
            {
                **option,
                "label": translate(option["label_key"]),
            }
            for option in LANGUAGE_OPTIONS
        ]
        return {
            "t": translate,
            "current_lang": current_lang,
            "available_languages": available_languages,
            "client_translations": build_client_translations(),
            "book_status_label": lambda value: translate(f"book_status.{value}") if value else "",
            "annotation_tag_label": (
                lambda value: translate(f"annotation_tag.{value}") if value else ""
            ),
            "localized_book_status_choices": get_book_status_choices(),
            "localized_annotation_tag_choices": get_annotation_tag_choices(),
        }


def register_cli_commands(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db() -> None:
        """Create all database tables."""
        db.create_all()
        ensure_local_schema()
        click.echo("Database initialized.")

    @app.cli.command("init-admin")
    @click.option("--username", prompt=True, default="admin", show_default=True)
    @click.option(
        "--password",
        prompt=True,
        hide_input=True,
        confirmation_prompt=True,
    )
    def init_admin(username: str, password: str) -> None:
        """Create or update the local admin account."""
        db.create_all()
        ensure_local_schema()
        username = username.strip()
        if not username:
            raise click.BadParameter("Username cannot be empty.")

        user = User.query.filter_by(username=username).first()
        if user is None:
            user = User(
                username=username,
                password_hash=generate_password_hash(password),
                is_admin=True,
            )
            db.session.add(user)
            action = "created"
        else:
            user.password_hash = generate_password_hash(password)
            user.is_admin = True
            action = "updated"

        db.session.commit()
        click.echo(f"Admin {action}: {username}")

    @app.cli.command("purge-recycle-bin")
    @click.option("--days", default=30, type=int, show_default=True)
    def purge_recycle_bin(days: int) -> None:
        """Permanently delete soft-deleted content older than N days."""
        if days < 0:
            raise click.BadParameter("Days must be zero or greater.")

        db.create_all()
        ensure_local_schema()
        cutoff = datetime.utcnow() - timedelta(days=days)
        moments = (
            Moment.query.filter(
                Moment.is_deleted.is_(True),
                Moment.deleted_at.is_not(None),
                Moment.deleted_at <= cutoff,
            )
            .options(selectinload(Moment.attachments))
            .all()
        )

        attachment_count = 0
        for moment in moments:
            for attachment in moment.attachments:
                for relative_path in attachment.managed_relative_paths:
                    delete_attachment_file(app.config["UPLOAD_FOLDER"], relative_path)
                attachment_count += 1
            db.session.delete(moment)

        db.session.commit()
        click.echo(
            f"Purged {len(moments)} moments and {attachment_count} attachments older than {days} days."
        )


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(CSRFError)
    def handle_csrf_error(error: CSRFError):
        if request.path.startswith("/api/"):
            return jsonify({"error": f"CSRF validation failed: {error.description}"}), 400

        return redirect(url_for("main.index"))

    @app.errorhandler(413)
    def handle_large_file(_error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Uploaded file is too large. Keep it under 200MB."}), 413
        return redirect(url_for("main.index"))


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    if not user_id.isdigit():
        return None
    return db.session.get(User, int(user_id))

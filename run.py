from __future__ import annotations

import getpass
import os
import sys

from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import User
from app.services.schema import ensure_local_schema


def configure_local_defaults() -> None:
    os.environ.setdefault("SECRET_KEY", "dev-secret-change-this")
    os.environ.setdefault(
        "NOMINATIM_USER_AGENT",
        "personal-moments-library/1.0 (your-name-or-email)",
    )


configure_local_defaults()
app = create_app()


def find_admin() -> User | None:
    return User.query.filter_by(is_admin=True).order_by(User.id.asc()).first()


def prompt_non_empty(prompt_text: str, default: str | None = None) -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        value = input(f"{prompt_text}{suffix}: ").strip()
        if value:
            return value
        if default:
            return default
        print("This field cannot be empty.")


def prompt_password() -> str:
    while True:
        password = getpass.getpass("Admin password: ")
        if len(password) < 4:
            print("Password must be at least 4 characters.")
            continue

        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords do not match. Please try again.")
            continue

        return password


def create_or_update_admin(interactive_title: str, existing_user: User | None = None) -> User:
    print(interactive_title)
    username_default = existing_user.username if existing_user is not None else "admin"
    username = prompt_non_empty("Admin username", default=username_default)
    password = prompt_password()

    user = User.query.filter_by(username=username).first()
    if user is None:
        user = existing_user or User(username=username)
        db.session.add(user)
    elif existing_user is not None and user.id != existing_user.id:
        existing_user.is_admin = False

    user.username = username
    user.password_hash = generate_password_hash(password)
    user.is_admin = True
    db.session.commit()

    print(f"Admin account ready: {user.username}")
    return user


def ensure_local_setup() -> None:
    with app.app_context():
        db.create_all()
        ensure_local_schema()
        admin = find_admin()
        if admin is not None:
            return

        if not sys.stdin.isatty():
            print("No admin account found.")
            print("Run this file in an interactive terminal once to create the admin account.")
            raise SystemExit(1)

        create_or_update_admin("No admin account found. Let's create one now.")


def reset_admin() -> None:
    with app.app_context():
        db.create_all()
        ensure_local_schema()
        admin = find_admin()
        title = "Reset admin account" if admin is not None else "Create admin account"
        create_or_update_admin(title, existing_user=admin)


def print_help() -> None:
    print("Usage:")
    print("  python run.py               Start the app and auto-create tables.")
    print("  python run.py --reset-admin Create or reset the admin account.")


def is_debugger_attached() -> bool:
    return sys.gettrace() is not None or bool(os.environ.get("DEBUGPY_LAUNCHER_PORT"))


def main() -> None:
    if "--help" in sys.argv or "-h" in sys.argv:
        print_help()
        return

    if "--reset-admin" in sys.argv:
        reset_admin()
        return

    ensure_local_setup()
    print("Starting local app at http://127.0.0.1:5000")
    use_reloader = not is_debugger_attached()
    if not use_reloader:
        print("Debugger detected. Flask auto-reload is disabled to avoid duplicate launches.")
    app.run(debug=True, use_reloader=use_reloader)


if __name__ == "__main__":
    main()

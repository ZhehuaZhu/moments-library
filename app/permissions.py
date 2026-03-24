from __future__ import annotations

from functools import wraps
from urllib.parse import urljoin, urlparse

from flask import jsonify, redirect, request, url_for
from flask_login import current_user


def _is_safe_redirect(target: str | None) -> bool:
    if not target:
        return False

    host_url = urlparse(request.host_url)
    redirect_url = urlparse(urljoin(request.host_url, target))
    return redirect_url.scheme in {"http", "https"} and host_url.netloc == redirect_url.netloc


def safe_redirect_target(target: str | None) -> str | None:
    if _is_safe_redirect(target):
        return target
    return None


def _api_error(message: str, status_code: int):
    return jsonify({"error": message}), status_code


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.path.startswith("/api/"):
                return _api_error("Authentication required.", 401)

            next_url = request.full_path if request.query_string else request.path
            return redirect(url_for("auth.login", next=next_url))

        if not getattr(current_user, "is_admin", False):
            if request.path.startswith("/api/"):
                return _api_error("Admin access required.", 403)
            return redirect(url_for("main.index"))

        return view(*args, **kwargs)

    return wrapped_view

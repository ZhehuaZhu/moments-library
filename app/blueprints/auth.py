from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from werkzeug.security import check_password_hash

from ..models import User
from ..permissions import safe_redirect_target

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for("main.index"))

    next_url = safe_redirect_target(request.args.get("next") or request.form.get("next"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        user = User.query.filter_by(username=username).first()
        if user and user.is_admin and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(next_url or url_for("main.index"))

        flash("Invalid username or password.", "error")

    return render_template(
        "login.html",
        title="Admin Login",
        show_sidebar=False,
        next_url=next_url or url_for("main.index"),
    )


@auth_bp.route("/logout", methods=["POST"])
def logout():
    if current_user.is_authenticated:
        logout_user()
    return redirect(url_for("main.index"))

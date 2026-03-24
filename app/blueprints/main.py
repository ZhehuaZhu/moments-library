from __future__ import annotations

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import Attachment, Category, Moment, MomentRevision, moment_folders
from ..permissions import admin_required
from ..services.folders import (
    build_folder_tree,
    calculate_folder_counts,
    descendant_folder_ids,
    extract_folder_values,
    flatten_folder_tree,
    normalize_folder_description,
    normalize_folder_name,
    resolve_folders,
    serialize_folder_snapshot,
)
from ..services.storage import UploadValidationError, cleanup_files, save_upload

main_bp = Blueprint("main", __name__)


def build_sidebar_context(
    *,
    active_nav: str = "feed",
    selected_folder_key: str = "all",
    selected_filter_mode: str = "all",
    selected_folder_id: int | None = None,
    categories: list[Category] | None = None,
    search_query: str = "",
    search_action: str = "main.index",
) -> dict:
    categories = categories or Category.query.order_by(Category.name.asc()).all()
    folder_counts = calculate_folder_counts(categories, include_deleted=False)
    folder_tree = build_folder_tree(categories, folder_counts)
    folder_choices = flatten_folder_tree(folder_tree)
    total_count = Moment.query.filter(Moment.is_deleted.is_(False)).count()
    uncategorized_count = (
        Moment.query.filter(
            Moment.is_deleted.is_(False),
            ~Moment.categories.any(),
            Moment.category_id.is_(None),
        ).count()
    )

    return {
        "sidebar_categories": categories,
        "sidebar_folder_tree": folder_tree,
        "sidebar_folder_choices": folder_choices,
        "folder_counts": folder_counts,
        "folder_tree_mode": len(categories) >= 6 or any(node["children"] for node in folder_tree),
        "total_count": total_count,
        "uncategorized_count": uncategorized_count,
        "active_nav": active_nav,
        "selected_folder_key": selected_folder_key,
        "selected_filter_mode": selected_filter_mode,
        "selected_folder_id": selected_folder_id,
        "search_query": search_query,
        "search_action": search_action,
        "can_manage": current_user.is_authenticated and current_user.is_admin,
    }


def redirect_back(default_endpoint: str = "main.index"):
    target = request.form.get("next") or request.referrer
    return redirect(target or url_for(default_endpoint))


def parse_optional_coordinate(value: str | None) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)


def resolve_parent_folder(parent_raw: str | None) -> Category | None:
    if parent_raw in {None, ""}:
        return None

    parent = db.session.get(Category, int(parent_raw))
    if parent is None:
        raise ValueError("Selected parent folder does not exist.")
    return parent


def load_feed_query(*, include_deleted: bool = False):
    query = Moment.query.options(
        selectinload(Moment.attachments),
        selectinload(Moment.category),
        selectinload(Moment.categories),
        selectinload(Moment.author),
        selectinload(Moment.revisions),
    )
    query = query.filter(Moment.is_deleted.is_(include_deleted))

    if include_deleted:
        return query.order_by(Moment.deleted_at.desc(), Moment.created_at.desc())

    return query.order_by(Moment.created_at.desc())


def apply_search_filter(query, search_query: str):
    if not search_query:
        return query

    pattern = f"%{search_query}%"
    return query.filter(
        or_(
            Moment.content.ilike(pattern),
            Moment.location_label.ilike(pattern),
            Moment.attachments.any(Attachment.original_name.ilike(pattern)),
            Moment.categories.any(
                or_(
                    Category.name.ilike(pattern),
                    Category.description.ilike(pattern),
                )
            ),
            Moment.category.has(
                or_(
                    Category.name.ilike(pattern),
                    Category.description.ilike(pattern),
                )
            ),
        )
    )


def get_moment_or_404(moment_id: int, *, allow_deleted: bool = False) -> Moment:
    moment = (
        Moment.query.options(
            selectinload(Moment.attachments),
            selectinload(Moment.category),
            selectinload(Moment.categories),
            selectinload(Moment.author),
            selectinload(Moment.revisions),
        )
        .filter(Moment.id == moment_id)
        .first()
    )
    if moment is None:
        abort(404)
    if moment.is_deleted and not allow_deleted:
        abort(404)
    return moment


def snapshot_moment(moment: Moment, editor_id: int) -> None:
    revision = MomentRevision(
        moment_id=moment.id,
        content=moment.content,
        location_label=moment.location_label,
        latitude=moment.latitude,
        longitude=moment.longitude,
        category_id=moment.primary_category.id if moment.primary_category else None,
        folder_snapshot=serialize_folder_snapshot(moment.assigned_categories),
        edited_by_id=editor_id,
    )
    db.session.add(revision)


@main_bp.route("/")
def index():
    all_categories = Category.query.order_by(Category.name.asc()).all()
    selected_folder = None
    selected_folder_key = "all"
    selected_folder_name = "All Moments"
    filter_mode = "all"
    filter_key = ""
    search_query = (request.args.get("q") or "").strip()

    moments_query = apply_search_filter(load_feed_query(include_deleted=False), search_query)

    if request.args.get("category") == "uncategorized":
        moments_query = moments_query.filter(
            ~Moment.categories.any(),
            Moment.category_id.is_(None),
        )
        selected_folder_key = "uncategorized"
        selected_folder_name = "Uncategorized"
        filter_mode = "uncategorized"
    else:
        folder_id = request.args.get("folder_id", type=int) or request.args.get(
            "category_id", type=int
        )
        if folder_id:
            selected_folder = db.session.get(Category, folder_id)
            if selected_folder is not None:
                related_ids = descendant_folder_ids(selected_folder, all_categories)
                moments_query = moments_query.filter(
                    or_(
                        Moment.categories.any(Category.id.in_(related_ids)),
                        Moment.category_id.in_(related_ids),
                    )
                )
                selected_folder_key = f"folder:{selected_folder.id}"
                selected_folder_name = selected_folder.name
                filter_mode = "folder"
                filter_key = str(selected_folder.id)

    moments = moments_query.all()
    context = build_sidebar_context(
        active_nav="feed",
        selected_folder_key=selected_folder_key,
        selected_filter_mode=filter_mode,
        selected_folder_id=selected_folder.id if selected_folder else None,
        categories=all_categories,
        search_query=search_query,
        search_action="main.index",
    )

    return render_template(
        "index.html",
        title="Feed",
        moments=moments,
        selected_folder=selected_folder,
        selected_folder_name=selected_folder_name,
        filter_mode=filter_mode,
        filter_key=filter_key,
        result_count=len(moments),
        **context,
    )


@main_bp.route("/categories", methods=["POST"])
@admin_required
def create_category():
    name = normalize_folder_name(request.form.get("name"))
    description = normalize_folder_description(request.form.get("description"))

    if not name:
        flash("Folder name cannot be empty.", "error")
        return redirect_back()

    try:
        parent = resolve_parent_folder(request.form.get("parent_id"))
    except (ValueError, TypeError):
        flash("Selected parent folder is invalid.", "error")
        return redirect_back()

    existing = Category.query.filter(db.func.lower(Category.name) == name.lower()).first()
    if existing:
        flash("Folder name already exists.", "error")
        return redirect_back()

    folder = Category(name=name, description=description, parent=parent)
    db.session.add(folder)

    try:
        db.session.commit()
        flash("Folder created.", "success")
    except IntegrityError:
        db.session.rollback()
        flash("Folder name already exists.", "error")

    return redirect_back()


@main_bp.route("/categories/<int:category_id>/delete", methods=["POST"])
@admin_required
def delete_category(category_id: int):
    folder = (
        Category.query.options(
            selectinload(Category.children),
        )
        .filter(Category.id == category_id)
        .first()
    )
    if folder is None:
        flash("Folder not found.", "error")
        return redirect_back()

    affected_moments = (
        Moment.query.options(selectinload(Moment.categories), selectinload(Moment.category))
        .filter(
            or_(
                Moment.category_id == folder.id,
                Moment.categories.any(Category.id == folder.id),
            )
        )
        .all()
    )

    for moment in affected_moments:
        remaining = [category for category in moment.assigned_categories if category.id != folder.id]
        moment.set_categories(remaining)

    MomentRevision.query.filter(MomentRevision.category_id == folder.id).update(
        {"category_id": None},
        synchronize_session=False,
    )

    for child in list(folder.children):
        child.parent = folder.parent

    db.session.execute(
        moment_folders.delete().where(moment_folders.c.category_id == folder.id)
    )
    db.session.delete(folder)
    db.session.commit()

    flash("Folder deleted. Child folders were moved up and existing moments were preserved.", "success")
    return redirect_back()


@main_bp.route("/moments", methods=["POST"])
@admin_required
def create_moment():
    content = (request.form.get("content") or "").strip()
    files = [file for file in request.files.getlist("files") if file and file.filename]

    if not content and not files:
        flash("Add text or upload at least one attachment.", "error")
        return redirect_back()

    try:
        folders = resolve_folders(extract_folder_values(request.form))
        latitude = parse_optional_coordinate(request.form.get("latitude"))
        longitude = parse_optional_coordinate(request.form.get("longitude"))
    except (ValueError, TypeError):
        flash("Submitted data is invalid.", "error")
        return redirect_back()

    if (latitude is None) ^ (longitude is None):
        flash("Location data is incomplete. Please fetch it again.", "error")
        return redirect_back()

    location_label = (request.form.get("location_label") or "").strip() or None

    moment = Moment(
        content=content or None,
        author_id=current_user.id,
        location_label=location_label,
        latitude=latitude,
        longitude=longitude,
    )
    moment.set_categories(folders)

    saved_paths: list[str] = []

    try:
        db.session.add(moment)
        db.session.flush()

        for file_storage in files:
            metadata = save_upload(file_storage, current_app.config["UPLOAD_FOLDER"])
            saved_paths.append(metadata["absolute_path"])
            attachment = Attachment(
                moment=moment,
                original_name=metadata["original_name"],
                stored_name=metadata["stored_name"],
                relative_path=metadata["relative_path"],
                mime_type=metadata["mime_type"],
                media_kind=metadata["media_kind"],
                size_bytes=metadata["size_bytes"],
            )
            db.session.add(attachment)

        db.session.commit()
        flash("Moment published.", "success")
    except UploadValidationError as error:
        db.session.rollback()
        cleanup_files(saved_paths)
        flash(str(error), "error")
    except Exception:
        db.session.rollback()
        cleanup_files(saved_paths)
        flash("Publishing failed. Please try again.", "error")

    return redirect_back()


@main_bp.route("/moments/<int:moment_id>/edit")
@admin_required
def edit_moment(moment_id: int):
    moment = get_moment_or_404(moment_id)
    context = build_sidebar_context(active_nav="feed")
    return render_template(
        "edit_moment.html",
        title="Edit Moment",
        moment=moment,
        selected_folder_ids=moment.category_ids_list,
        **context,
    )


@main_bp.route("/moments/<int:moment_id>/edit", methods=["POST"])
@admin_required
def update_moment(moment_id: int):
    moment = get_moment_or_404(moment_id)
    content = (request.form.get("content") or "").strip() or None

    if not content and not moment.attachments:
        flash("Text cannot be empty for a moment without attachments.", "error")
        return redirect(url_for("main.edit_moment", moment_id=moment.id))

    try:
        folders = resolve_folders(extract_folder_values(request.form))
        latitude = parse_optional_coordinate(request.form.get("latitude"))
        longitude = parse_optional_coordinate(request.form.get("longitude"))
    except (ValueError, TypeError):
        flash("Submitted data is invalid.", "error")
        return redirect(url_for("main.edit_moment", moment_id=moment.id))

    if (latitude is None) ^ (longitude is None):
        flash("Location data is incomplete. Please fetch it again.", "error")
        return redirect(url_for("main.edit_moment", moment_id=moment.id))

    location_label = (request.form.get("location_label") or "").strip() or None
    incoming_folder_ids = [folder.id for folder in folders]

    has_changes = any(
        [
            moment.content != content,
            moment.location_label != location_label,
            moment.latitude != latitude,
            moment.longitude != longitude,
            moment.category_ids_list != incoming_folder_ids,
        ]
    )

    if not has_changes:
        flash("No changes detected.", "error")
        return redirect(url_for("main.edit_moment", moment_id=moment.id))

    snapshot_moment(moment, current_user.id)
    moment.content = content
    moment.location_label = location_label
    moment.latitude = latitude
    moment.longitude = longitude
    moment.set_categories(folders)
    db.session.commit()

    flash("Moment updated. A revision snapshot was saved.", "success")
    return redirect(url_for("main.index"))


@main_bp.route("/moments/<int:moment_id>/history")
@admin_required
def moment_history(moment_id: int):
    moment = (
        Moment.query.options(
            selectinload(Moment.attachments),
            selectinload(Moment.category),
            selectinload(Moment.categories),
            selectinload(Moment.author),
            selectinload(Moment.revisions).selectinload(MomentRevision.category),
            selectinload(Moment.revisions).selectinload(MomentRevision.editor),
        )
        .filter(Moment.id == moment_id)
        .first()
    )
    if moment is None:
        abort(404)

    context = build_sidebar_context(active_nav="feed")
    return render_template(
        "moment_history.html",
        title="Moment History",
        moment=moment,
        revisions=moment.revisions,
        **context,
    )


@main_bp.route("/recycle-bin")
@admin_required
def recycle_bin():
    search_query = (request.args.get("q") or "").strip()
    moments = apply_search_filter(load_feed_query(include_deleted=True), search_query).all()
    context = build_sidebar_context(
        active_nav="recycle",
        selected_folder_key="all",
        selected_filter_mode="recycle",
        search_query=search_query,
        search_action="main.recycle_bin",
    )
    return render_template(
        "recycle_bin.html",
        title="Recycle Bin",
        moments=moments,
        result_count=len(moments),
        **context,
    )

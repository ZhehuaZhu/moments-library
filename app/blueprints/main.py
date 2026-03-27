from __future__ import annotations

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import load_only, selectinload

from ..extensions import db
from ..models import (
    Attachment,
    Book,
    Category,
    Moment,
    MomentRevision,
    Track,
    User,
    VideoEntry,
    moment_folders,
)
from ..permissions import admin_required
from ..services.citations import resolve_citation_payload
from ..services.cross_post import (
    build_cross_post_plan,
    clear_cross_post_publication_marks,
    get_cross_post_platform_options,
    normalize_cross_post_targets,
    set_cross_post_targets,
)
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
from ..services.footprints import (
    apply_place_fields,
    build_footprint_payload,
    ensure_moment_place_metadata,
    parse_place_form_data,
)
from ..services.image_previews import ensure_attachment_image_preview
from ..services.i18n import LANGUAGE_COOKIE_NAME, normalize_language, translate
from ..services.storage import UploadValidationError, cleanup_files, save_upload
from ..services.video_previews import ensure_attachment_video_preview

main_bp = Blueprint("main", __name__)


def resolve_workspace_owner() -> User | None:
    if current_user.is_authenticated:
        return current_user  # type: ignore[return-value]
    return User.query.order_by(User.id.asc()).first()


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
    workspace_owner = resolve_workspace_owner()
    module_labels = {
        "feed": (
            (workspace_owner.feed_label or "").strip()
            if workspace_owner is not None
            else ""
        )
        or translate("module.feed"),
        "books": (
            (workspace_owner.books_label or "").strip()
            if workspace_owner is not None
            else ""
        )
        or translate("module.books"),
        "music": (
            (workspace_owner.music_label or "").strip()
            if workspace_owner is not None
            else ""
        )
        or translate("module.music"),
        "videos": (
            (workspace_owner.videos_label or "").strip()
            if workspace_owner is not None
            else ""
        )
        or translate("module.videos"),
    }
    workspace_name = (
        (workspace_owner.workspace_name or "").strip()
        if workspace_owner is not None
        else ""
    ) or translate("workspace.default_name")
    workspace_tagline = (
        (workspace_owner.workspace_tagline or "").strip()
        if workspace_owner is not None
        else ""
    ) or translate("workspace.default_tagline")
    categories = categories or Category.query.order_by(Category.name.asc()).all()
    folder_counts = calculate_folder_counts(categories, include_deleted=False)
    folder_tree = build_folder_tree(categories, folder_counts)
    folder_choices = flatten_folder_tree(folder_tree)
    total_count = Moment.query.filter(Moment.is_deleted.is_(False)).count()
    footprint_count = (
        Moment.query.filter(
            Moment.is_deleted.is_(False),
            Moment.latitude.is_not(None),
            Moment.longitude.is_not(None),
        ).count()
    )
    book_count = Book.query.count()
    track_count = Track.query.count()
    video_count = VideoEntry.query.count()
    uncategorized_count = (
        Moment.query.filter(
            Moment.is_deleted.is_(False),
            ~Moment.categories.any(),
            Moment.category_id.is_(None),
        ).count()
    )
    track_catalog_payload = [
        {
            "id": track.id,
            "title": track.title,
            "artist": track.artist_name or "",
            "src": url_for("static", filename=track.relative_path),
            "cover": (
                url_for("static", filename=track.cover_relative_path)
                if track.cover_relative_path
                else None
            ),
        }
        for track in Track.query.order_by(Track.created_at.desc()).all()
    ]

    return {
        "sidebar_categories": categories,
        "sidebar_folder_tree": folder_tree,
        "sidebar_folder_choices": folder_choices,
        "folder_counts": folder_counts,
        "folder_tree_mode": len(categories) >= 6 or any(node["children"] for node in folder_tree),
        "total_count": total_count,
        "footprint_count": footprint_count,
        "book_count": book_count,
        "track_count": track_count,
        "video_count": video_count,
        "uncategorized_count": uncategorized_count,
        "active_nav": active_nav,
        "selected_folder_key": selected_folder_key,
        "selected_filter_mode": selected_filter_mode,
        "selected_folder_id": selected_folder_id,
        "search_query": search_query,
        "search_action": search_action,
        "can_manage": current_user.is_authenticated and current_user.is_admin,
        "workspace_owner": workspace_owner,
        "workspace_name": workspace_name,
        "workspace_tagline": workspace_tagline,
        "module_labels": module_labels,
        "track_catalog_payload": track_catalog_payload,
        "cross_post_platforms": get_cross_post_platform_options(),
    }


def redirect_back(default_endpoint: str = "main.index"):
    target = request.form.get("next") or request.referrer
    return redirect(target or url_for(default_endpoint))


def ensure_feed_media_previews(moments: list[Moment]) -> None:
    changed = False
    upload_root = current_app.config["UPLOAD_FOLDER"]

    for moment in moments:
        for attachment in moment.attachments:
            image_paths = ensure_attachment_image_preview(attachment, upload_root)
            if image_paths:
                changed = True
            created_paths = ensure_attachment_video_preview(attachment, upload_root)
            if created_paths:
                changed = True

    if changed:
        db.session.commit()


def attach_cross_post_plans(moments: list[Moment]) -> None:
    for moment in moments:
        moment.cross_post_plan = build_cross_post_plan(moment)
        moment.cross_post_share_options = build_cross_post_plan(moment, selected_only=False)


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


def normalize_workspace_copy(value: str | None, limit: int) -> str | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    return cleaned[:limit]


def load_feed_query(*, include_deleted: bool = False):
    query = Moment.query.options(
        selectinload(Moment.attachments),
        selectinload(Moment.category),
        selectinload(Moment.categories),
        selectinload(Moment.author),
        selectinload(Moment.revisions).load_only(MomentRevision.id),
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
            Moment.citation_title.ilike(pattern),
            Moment.citation_subtitle.ilike(pattern),
            Moment.citation_excerpt.ilike(pattern),
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
            selectinload(Moment.revisions).load_only(MomentRevision.id),
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
        country_code=moment.country_code,
        country_name=moment.country_name,
        admin_area=moment.admin_area,
        city_name=moment.city_name,
        district_name=moment.district_name,
        place_key=moment.place_key,
        location_source=moment.location_source,
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
    selected_folder_name = translate("folders.all_moments")
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
        selected_folder_name = translate("folders.uncategorized")
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
    ensure_feed_media_previews(moments)
    if current_user.is_authenticated and current_user.is_admin:
        attach_cross_post_plans(moments)
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
        title=translate("module.feed"),
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
        flash("Collection name cannot be empty.", "error")
        return redirect_back()

    try:
        parent = resolve_parent_folder(request.form.get("parent_id"))
    except (ValueError, TypeError):
        flash("Selected parent collection is invalid.", "error")
        return redirect_back()

    existing = Category.query.filter(db.func.lower(Category.name) == name.lower()).first()
    if existing:
        flash("Collection name already exists.", "error")
        return redirect_back()

    folder = Category(name=name, description=description, parent=parent)
    db.session.add(folder)

    try:
        db.session.commit()
        flash("Collection created.", "success")
    except IntegrityError:
        db.session.rollback()
        flash("Collection name already exists.", "error")
        return redirect_back()

    if request.form.get("video_folder_redirect") == "1":
        return redirect(url_for("library.videos", folder_id=folder.id))

    return redirect_back()


@main_bp.route("/workspace/preferences", methods=["POST"])
@admin_required
def update_workspace_preferences():
    current_user.workspace_name = normalize_workspace_copy(request.form.get("workspace_name"), 120)
    current_user.workspace_tagline = normalize_workspace_copy(
        request.form.get("workspace_tagline"),
        120,
    )
    current_user.feed_label = normalize_workspace_copy(request.form.get("feed_label"), 40)
    current_user.books_label = normalize_workspace_copy(request.form.get("books_label"), 40)
    current_user.music_label = normalize_workspace_copy(request.form.get("music_label"), 40)
    current_user.videos_label = normalize_workspace_copy(request.form.get("videos_label"), 40)
    db.session.commit()
    flash("Workspace style updated.", "success")
    return redirect_back()


@main_bp.route("/preferences/language", methods=["POST"])
def update_language_preference():
    language = normalize_language(request.form.get("language"))
    response = redirect(request.form.get("next") or request.referrer or url_for("main.index"))
    response.set_cookie(
        LANGUAGE_COOKIE_NAME,
        language,
        max_age=60 * 60 * 24 * 365,
        samesite="Lax",
    )
    return response


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
        flash("Collection not found.", "error")
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

    flash("Collection deleted. Child collections were moved up and existing items were preserved.", "success")
    return redirect_back()


@main_bp.route("/moments", methods=["POST"])
@admin_required
def create_moment():
    content = (request.form.get("content") or "").strip()
    files = [file for file in request.files.getlist("files") if file and file.filename]
    requested_cross_posts = normalize_cross_post_targets(request.form.getlist("cross_post_targets"))

    try:
        folders = resolve_folders(extract_folder_values(request.form))
        latitude = parse_optional_coordinate(request.form.get("latitude"))
        longitude = parse_optional_coordinate(request.form.get("longitude"))
        citation_target_id = request.form.get("citation_target_id", type=int)
    except (ValueError, TypeError):
        flash("Submitted data is invalid.", "error")
        return redirect_back()

    if (latitude is None) ^ (longitude is None):
        flash("Location data is incomplete. Please fetch it again.", "error")
        return redirect_back()

    location_label = (request.form.get("location_label") or "").strip() or None
    place_fields = parse_place_form_data(request.form)
    citation_payload = resolve_citation_payload(
        request.form.get("citation_kind"),
        citation_target_id,
    )
    if request.form.get("citation_kind") and citation_payload is None:
        flash("The selected citation is no longer available. Pick it again.", "error")
        return redirect_back()

    if not content and not files and citation_payload is None:
        flash("Add text, upload at least one attachment, or cite something.", "error")
        return redirect_back()

    moment = Moment(
        content=content or None,
        author_id=current_user.id,
        location_label=location_label,
        latitude=latitude,
        longitude=longitude,
        citation_kind=citation_payload["kind"] if citation_payload else None,
        citation_target_id=citation_payload["id"] if citation_payload else None,
        citation_label=citation_payload["label"] if citation_payload else None,
        citation_title=citation_payload["title"] if citation_payload else None,
        citation_subtitle=citation_payload["subtitle"] if citation_payload else None,
        citation_excerpt=citation_payload["excerpt"] if citation_payload else None,
        citation_href=citation_payload["href"] if citation_payload else None,
        citation_cover_path=citation_payload["cover"] if citation_payload else None,
    )
    apply_place_fields(moment, place_fields if latitude is not None else {})
    moment.set_categories(folders)
    set_cross_post_targets(moment, requested_cross_posts)

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
            saved_paths.extend(
                ensure_attachment_image_preview(attachment, current_app.config["UPLOAD_FOLDER"])
            )
            saved_paths.extend(
                ensure_attachment_video_preview(attachment, current_app.config["UPLOAD_FOLDER"])
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
    place_fields = parse_place_form_data(request.form)
    incoming_folder_ids = [folder.id for folder in folders]

    has_changes = any(
        [
            moment.content != content,
            moment.location_label != location_label,
            moment.latitude != latitude,
            moment.longitude != longitude,
            moment.country_code != place_fields.get("country_code"),
            moment.country_name != place_fields.get("country_name"),
            moment.admin_area != place_fields.get("admin_area"),
            moment.city_name != place_fields.get("city_name"),
            moment.district_name != place_fields.get("district_name"),
            moment.place_key != place_fields.get("place_key"),
            moment.location_source != place_fields.get("location_source"),
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
    apply_place_fields(moment, place_fields if latitude is not None else {})
    moment.set_categories(folders)
    cross_post_reset = clear_cross_post_publication_marks(moment)
    db.session.commit()

    if cross_post_reset:
        flash("Moment updated. A revision snapshot was saved, and cross-post publish marks were reset.", "success")
    else:
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
    ensure_feed_media_previews(moments)
    context = build_sidebar_context(
        active_nav="recycle",
        selected_folder_key="all",
        selected_filter_mode="recycle",
        search_query=search_query,
        search_action="main.recycle_bin",
    )
    return render_template(
        "recycle_bin.html",
        title=translate("nav.trash"),
        moments=moments,
        result_count=len(moments),
        **context,
    )


@main_bp.route("/footprints")
def footprints():
    search_query = (request.args.get("q") or "").strip()
    moments = (
        apply_search_filter(load_feed_query(include_deleted=False), search_query)
        .filter(
            Moment.latitude.is_not(None),
            Moment.longitude.is_not(None),
        )
        .all()
    )
    ensure_feed_media_previews(moments)
    if not current_app.config.get("TESTING"):
        metadata_changed = ensure_moment_place_metadata(
            moments,
            user_agent=current_app.config["NOMINATIM_USER_AGENT"],
        )
        if metadata_changed:
            db.session.commit()

    payload = build_footprint_payload(moments)
    default_view = payload["default_view"]
    default_summary = payload["views"][default_view]
    context = build_sidebar_context(
        active_nav="footprints",
        search_query=search_query,
        search_action="main.footprints",
    )
    return render_template(
        "footprints.html",
        title=translate("nav.footprints"),
        footprint_payload=payload,
        place_count=default_summary["place_count"],
        mapped_moment_count=default_summary["mapped_moment_count"],
        **context,
    )

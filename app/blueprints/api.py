from __future__ import annotations

from datetime import datetime

from flask import Blueprint, current_app, jsonify, request

from ..extensions import db
from ..models import Category, Moment
from ..permissions import admin_required
from ..services.citations import normalize_citation_scope, search_citation_payloads
from ..services.cross_post import (
    evaluate_cross_post_platform,
    mark_cross_post_published,
    reset_cross_post_publication,
)
from ..services.folders import resolve_folders
from ..services.footprints import normalize_reverse_geocode_result
from ..services.geocoding import GeocodingError, reverse_geocode

api_bp = Blueprint("api", __name__)


@api_bp.route("/api/geocode", methods=["POST"])
@admin_required
def geocode():
    payload = request.get_json(silent=True) or {}

    try:
        latitude = float(payload.get("lat"))
        longitude = float(payload.get("lon"))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid latitude or longitude."}), 400

    try:
        result = reverse_geocode(
            latitude,
            longitude,
            user_agent=current_app.config["NOMINATIM_USER_AGENT"],
        )
    except GeocodingError as error:
        return jsonify({"error": str(error)}), 502

    return jsonify(
        {
            **result,
            **normalize_reverse_geocode_result(result, source="browser"),
        }
    )


@api_bp.route("/api/citations/search")
@admin_required
def citation_search():
    search_query = (request.args.get("q") or "").strip()
    scope = normalize_citation_scope(request.args.get("scope"))
    try:
        offset = max(int(request.args.get("offset", 0)), 0)
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = min(max(int(request.args.get("limit", 8)), 1), 24)
    except (TypeError, ValueError):
        limit = 8

    items, has_more = search_citation_payloads(
        search_query,
        scope=scope,
        limit=limit,
        offset=offset,
    )
    return jsonify(
        {
            "items": items,
            "scope": scope,
            "offset": offset,
            "limit": limit,
            "has_more": has_more,
        }
    )


def _update_moment_folders(moment_id: int, payload: dict):
    moment = db.session.get(Moment, moment_id)
    if moment is None or moment.is_deleted:
        return jsonify({"error": "Moment not found."}), 404

    raw_folder_ids = payload.get("folder_ids")
    if raw_folder_ids is None:
        category_raw = payload.get("category_id")
        raw_folder_ids = [] if category_raw in {None, ""} else [str(category_raw)]

    if not isinstance(raw_folder_ids, list):
        return jsonify({"error": "Invalid folder payload."}), 400

    try:
        folders = resolve_folders([str(item) for item in raw_folder_ids])
    except (ValueError, TypeError):
        return jsonify({"error": "Selected folder does not exist."}), 400

    moment.set_categories(folders)
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "moment_id": moment.id,
            "folder_ids": [folder.id for folder in moment.assigned_categories],
            "folder_names": [folder.name for folder in moment.assigned_categories],
            "primary_folder_name": moment.primary_category_name,
            "folders_label": ", ".join(folder.name for folder in moment.assigned_categories)
            or "Uncategorized",
        }
    )


@api_bp.route("/api/moments/<int:moment_id>/folders", methods=["PATCH"])
@admin_required
def update_moment_folders(moment_id: int):
    payload = request.get_json(silent=True) or {}
    return _update_moment_folders(moment_id, payload)


@api_bp.route("/api/moments/<int:moment_id>/category", methods=["PATCH"])
@admin_required
def update_moment_category(moment_id: int):
    payload = request.get_json(silent=True) or {}
    return _update_moment_folders(moment_id, payload)


@api_bp.route("/api/moments/<int:moment_id>", methods=["DELETE"])
@admin_required
def delete_moment(moment_id: int):
    moment = db.session.get(Moment, moment_id)
    if moment is None or moment.is_deleted:
        return jsonify({"error": "Moment not found."}), 404

    moment.is_deleted = True
    moment.deleted_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"success": True, "moment_id": moment.id})


@api_bp.route("/api/moments/<int:moment_id>/restore", methods=["POST"])
@admin_required
def restore_moment(moment_id: int):
    moment = db.session.get(Moment, moment_id)
    if moment is None or not moment.is_deleted:
        return jsonify({"error": "Moment not found or already active."}), 404

    moment.is_deleted = False
    moment.deleted_at = None
    db.session.commit()

    return jsonify({"success": True, "moment_id": moment.id})


@api_bp.route("/api/moments/<int:moment_id>/cross-post/<platform>", methods=["POST"])
@admin_required
def update_cross_post_status(moment_id: int, platform: str):
    moment = db.session.get(Moment, moment_id)
    if moment is None or moment.is_deleted:
        return jsonify({"error": "Moment not found."}), 404

    payload = request.get_json(silent=True) or {}
    action = (payload.get("action") or "").strip()

    try:
        evaluation = evaluate_cross_post_platform(moment, platform)
    except ValueError:
        return jsonify({"error": "Unsupported platform."}), 400

    if action == "publish":
        if not evaluation["eligible"]:
            return jsonify({"error": "This platform is not ready for the current draft."}), 400
        mark_cross_post_published(moment, platform)
    elif action == "reset":
        reset_cross_post_publication(moment, platform)
    else:
        return jsonify({"error": "Unsupported action."}), 400

    db.session.commit()

    return jsonify(
        {
            "success": True,
            "moment_id": moment.id,
            "platform": platform,
            "published": action == "publish",
        }
    )

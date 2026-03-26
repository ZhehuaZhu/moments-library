from __future__ import annotations

from datetime import datetime

from flask import Blueprint, current_app, jsonify, request

from ..extensions import db
from ..models import Category, Moment
from ..permissions import admin_required
from ..services.citations import normalize_citation_scope, search_citation_payloads
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
    items = search_citation_payloads(search_query, scope=scope, limit=24)
    return jsonify({"items": items, "scope": scope})


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

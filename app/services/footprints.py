from __future__ import annotations

import hashlib
import re
from typing import Any

from flask import url_for

from ..models import Attachment, Moment
from .geocoding import GeocodingError, reverse_geocode
from .i18n import translate

PLACE_FIELD_NAMES = (
    "country_code",
    "country_name",
    "admin_area",
    "city_name",
    "district_name",
    "place_key",
    "location_source",
)


def _clean_text(value: object) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned or None


def build_place_key(
    *,
    country_code: str | None = None,
    country_name: str | None = None,
    admin_area: str | None = None,
    city_name: str | None = None,
) -> str | None:
    parts = [
        _clean_text(country_code),
        _clean_text(country_name),
        _clean_text(admin_area),
        _clean_text(city_name),
    ]
    basis = " | ".join(part.casefold() for part in parts if part)
    if not basis:
        return None
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def normalize_place_fields(
    *,
    country_code: object = None,
    country_name: object = None,
    admin_area: object = None,
    city_name: object = None,
    district_name: object = None,
    place_key: object = None,
    location_source: object = None,
) -> dict[str, str | None]:
    normalized_country_code = _clean_text(country_code)
    if normalized_country_code:
        normalized_country_code = normalized_country_code.upper()

    normalized_country_name = _clean_text(country_name)
    normalized_admin_area = _clean_text(admin_area)
    normalized_city_name = _clean_text(city_name)
    normalized_district_name = _clean_text(district_name)
    normalized_place_key = _clean_text(place_key) or build_place_key(
        country_code=normalized_country_code,
        country_name=normalized_country_name,
        admin_area=normalized_admin_area,
        city_name=normalized_city_name,
    )

    return {
        "country_code": normalized_country_code,
        "country_name": normalized_country_name,
        "admin_area": normalized_admin_area,
        "city_name": normalized_city_name,
        "district_name": normalized_district_name,
        "place_key": normalized_place_key,
        "location_source": _clean_text(location_source),
    }


def normalize_reverse_geocode_result(
    payload: dict[str, Any],
    *,
    source: str | None = "browser",
) -> dict[str, str | None]:
    return normalize_place_fields(
        country_code=payload.get("country_code"),
        country_name=payload.get("country"),
        admin_area=payload.get("province"),
        city_name=payload.get("city"),
        district_name=payload.get("district"),
        location_source=source,
    )


def parse_place_form_data(form) -> dict[str, str | None]:
    return normalize_place_fields(
        country_code=form.get("location_country_code"),
        country_name=form.get("location_country_name"),
        admin_area=form.get("location_admin_area"),
        city_name=form.get("location_city_name"),
        district_name=form.get("location_district_name"),
        place_key=form.get("location_place_key"),
        location_source=form.get("location_source"),
    )


def apply_place_fields(moment: Moment, fields: dict[str, str | None]) -> None:
    for field_name in PLACE_FIELD_NAMES:
        setattr(moment, field_name, fields.get(field_name))


def _infer_place_fields_from_label(moment: Moment) -> dict[str, str | None]:
    location_label = _clean_text(moment.location_label)
    tokens = [
        token
        for token in re.split(r"[\s,，]+", location_label or "")
        if token
    ]

    admin_area = None
    city_name = None
    district_name = None

    if len(tokens) >= 3:
        admin_area = tokens[0]
        city_name = tokens[1]
        district_name = tokens[2]
    elif len(tokens) == 2:
        admin_area = tokens[0]
        city_name = tokens[1]
    elif len(tokens) == 1:
        city_name = tokens[0]

    return normalize_place_fields(
        country_code=moment.country_code,
        country_name=moment.country_name,
        admin_area=moment.admin_area or admin_area,
        city_name=moment.city_name or city_name,
        district_name=moment.district_name or district_name,
        place_key=moment.place_key,
        location_source=moment.location_source,
    )


def ensure_moment_place_metadata(moments: list[Moment], *, user_agent: str) -> bool:
    changed = False

    for moment in moments:
        if not moment.has_coordinates:
            continue

        inferred_fields = normalize_place_fields(
            country_code=moment.country_code,
            country_name=moment.country_name,
            admin_area=moment.admin_area,
            city_name=moment.city_name,
            district_name=moment.district_name,
            place_key=moment.place_key,
            location_source=moment.location_source,
        )
        if inferred_fields["place_key"]:
            if moment.place_key != inferred_fields["place_key"]:
                moment.place_key = inferred_fields["place_key"]
                changed = True
            continue

        try:
            geocode_payload = reverse_geocode(
                float(moment.latitude),
                float(moment.longitude),
                user_agent=user_agent,
            )
        except (GeocodingError, TypeError, ValueError):
            continue

        normalized_fields = normalize_reverse_geocode_result(
            geocode_payload,
            source=moment.location_source or "browser",
        )
        apply_place_fields(moment, normalized_fields)
        if not _clean_text(moment.location_label):
            moment.location_label = _clean_text(geocode_payload.get("formatted_address"))
        changed = True

    return changed


def _build_media_preview(attachments: list[Attachment]) -> dict[str, str] | None:
    for attachment in attachments:
        if attachment.media_kind == "image":
            return {
                "kind": "image",
                "src": url_for("static", filename=attachment.preview_asset_path),
                "alt": attachment.original_name,
            }
        if attachment.media_kind == "video":
            if attachment.poster_asset_path:
                return {
                    "kind": "image",
                    "src": url_for("static", filename=attachment.poster_asset_path),
                    "alt": attachment.original_name,
                }
            return {
                "kind": "video",
                "src": url_for("static", filename=attachment.preview_asset_path),
                "alt": attachment.original_name,
            }
    return None


def _build_moment_excerpt(moment: Moment) -> str:
    raw_text = (
        _clean_text(moment.content)
        or _clean_text(moment.citation_excerpt)
        or _clean_text(moment.citation_title)
        or _clean_text(moment.location_label)
        or ""
    )
    compact = raw_text.replace("\r", " ").replace("\n", " ")
    compact = re.sub(r"\s+", " ", compact).strip()
    if len(compact) <= 140:
        return compact
    return f"{compact[:137]}..."


def _resolve_place_snapshot(moment: Moment) -> dict[str, str | None]:
    normalized_fields = normalize_place_fields(
        country_code=moment.country_code,
        country_name=moment.country_name,
        admin_area=moment.admin_area,
        city_name=moment.city_name,
        district_name=moment.district_name,
        place_key=moment.place_key,
        location_source=moment.location_source,
    )
    if not normalized_fields["place_key"]:
        normalized_fields = _infer_place_fields_from_label(moment)

    place_key = normalized_fields["place_key"]
    if not place_key and moment.has_coordinates:
        place_key = f"coord:{float(moment.latitude):.2f}:{float(moment.longitude):.2f}"

    city_display_name = (
        normalized_fields["city_name"]
        or normalized_fields["admin_area"]
        or normalized_fields["district_name"]
        or _clean_text(moment.location_label)
        or translate("footprints.unknown_place")
    )

    city_subtitle_parts: list[str] = []
    for value in (
        normalized_fields["district_name"],
        normalized_fields["admin_area"],
        normalized_fields["country_name"],
    ):
        if value and value != city_display_name and value not in city_subtitle_parts:
            city_subtitle_parts.append(value)

    city_subtitle = " | ".join(city_subtitle_parts)
    if not city_subtitle and _clean_text(moment.location_label) and moment.location_label != city_display_name:
        city_subtitle = _clean_text(moment.location_label) or ""

    country_display_name = (
        normalized_fields["country_name"]
        or normalized_fields["country_code"]
        or city_display_name
    )

    return {
        **normalized_fields,
        "place_key": place_key,
        "city_display_name": city_display_name,
        "city_subtitle": city_subtitle,
        "country_display_name": country_display_name,
    }


def _build_moment_entry(moment: Moment) -> dict[str, object]:
    media = _build_media_preview(moment.attachments)
    return {
        "id": moment.id,
        "created_at": moment.created_at.strftime("%Y-%m-%d %H:%M"),
        "created_at_sort": moment.created_at.isoformat(timespec="seconds"),
        "location_label": _clean_text(moment.location_label),
        "excerpt": _build_moment_excerpt(moment),
        "content": _clean_text(moment.content),
        "href": url_for("main.index", _anchor=f"moment-{moment.id}"),
        "media": media,
        "has_media": media is not None,
        "attachment_count": len(moment.attachments),
    }


def _group_config(snapshot: dict[str, str | None], level: str, moment: Moment) -> dict[str, object]:
    if level == "country":
        identifier = snapshot["country_code"] or snapshot["country_name"] or f"country:{moment.id}"
        return {
            "id": f"country:{identifier}",
            "name": snapshot["country_display_name"],
            "subtitle": "",
            "city_name": None,
            "admin_area": None,
            "country_name": snapshot["country_name"],
            "country_code": snapshot["country_code"],
            "child_name": snapshot["city_name"] or snapshot["admin_area"],
        }

    return {
        "id": snapshot["place_key"] or f"city:{moment.id}",
        "name": snapshot["city_display_name"],
        "subtitle": snapshot["city_subtitle"],
        "city_name": snapshot["city_name"],
        "admin_area": snapshot["admin_area"],
        "country_name": snapshot["country_name"],
        "country_code": snapshot["country_code"],
        "child_name": None,
    }


def _serialize_group(
    *,
    group: dict[str, object],
    ordered_moments: list[dict[str, object]],
    level: str,
) -> dict[str, object]:
    latitude_values = group.pop("latitude_values")
    longitude_values = group.pop("longitude_values")
    latest_created_at = group.pop("latest_created_at")
    earliest_created_at = group.pop("earliest_created_at")
    child_names = sorted(group.pop("child_names"))
    preview_names = child_names[:3]

    subtitle = group.get("subtitle") or ""
    if level == "country":
        subtitle_parts = []
        if child_names:
            subtitle_parts.append(
                translate("footprints.city_group_summary", count=len(child_names))
            )
        if preview_names:
            subtitle_parts.append(" | ".join(preview_names))
        subtitle = " | ".join(part for part in subtitle_parts if part)

    media_moment_count = sum(1 for moment in ordered_moments if moment.get("has_media"))

    return {
        **group,
        "scope": level,
        "subtitle": subtitle,
        "latitude": round(sum(latitude_values) / len(latitude_values), 6),
        "longitude": round(sum(longitude_values) / len(longitude_values), 6),
        "moment_count": len(ordered_moments),
        "media_moment_count": media_moment_count,
        "child_count": len(child_names),
        "child_preview": preview_names,
        "latest_created_at": latest_created_at.strftime("%Y-%m-%d %H:%M"),
        "latest_created_at_sort": latest_created_at.isoformat(timespec="seconds"),
        "earliest_created_at_sort": earliest_created_at.isoformat(timespec="seconds"),
        "moments": ordered_moments,
    }


def _aggregate_places(moments: list[Moment], level: str) -> dict[str, object]:
    grouped_places: dict[str, dict[str, object]] = {}

    for moment in moments:
        if not moment.has_coordinates:
            continue

        snapshot = _resolve_place_snapshot(moment)
        config = _group_config(snapshot, level, moment)
        group = grouped_places.setdefault(
            config["id"],
            {
                "id": config["id"],
                "name": config["name"],
                "subtitle": config["subtitle"],
                "city_name": config["city_name"],
                "admin_area": config["admin_area"],
                "country_name": config["country_name"],
                "country_code": config["country_code"],
                "latitude_values": [],
                "longitude_values": [],
                "moments": [],
                "latest_created_at": moment.created_at,
                "earliest_created_at": moment.created_at,
                "child_names": set(),
            },
        )

        group["name"] = group["name"] or config["name"]
        group["subtitle"] = group["subtitle"] or config["subtitle"]
        group["city_name"] = group["city_name"] or config["city_name"]
        group["admin_area"] = group["admin_area"] or config["admin_area"]
        group["country_name"] = group["country_name"] or config["country_name"]
        group["country_code"] = group["country_code"] or config["country_code"]
        group["latitude_values"].append(float(moment.latitude))
        group["longitude_values"].append(float(moment.longitude))
        group["latest_created_at"] = max(group["latest_created_at"], moment.created_at)
        group["earliest_created_at"] = min(group["earliest_created_at"], moment.created_at)
        if config["child_name"]:
            group["child_names"].add(config["child_name"])
        group["moments"].append(_build_moment_entry(moment))

    places: list[dict[str, object]] = []
    for group in grouped_places.values():
        ordered_moments = sorted(
            group["moments"],
            key=lambda item: (item["created_at_sort"], item["id"]),
            reverse=True,
        )
        places.append(_serialize_group(group=group, ordered_moments=ordered_moments, level=level))

    places.sort(
        key=lambda item: (
            item["latest_created_at_sort"],
            item["moment_count"],
            item["name"] or "",
        ),
        reverse=True,
    )

    return {
        "places": places,
        "place_count": len(places),
        "mapped_moment_count": sum(place["moment_count"] for place in places),
    }


def build_footprint_payload(moments: list[Moment]) -> dict[str, object]:
    city_view = _aggregate_places(moments, "city")
    country_view = _aggregate_places(moments, "country")

    return {
        "default_view": "city",
        "views": {
            "city": city_view,
            "country": country_view,
        },
    }

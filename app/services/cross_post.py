from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any


PLATFORM_ORDER = ("wechat_moments", "instagram", "xiaohongshu")

PLATFORM_METADATA: dict[str, dict[str, str]] = {
    "wechat_moments": {
        "label_key": "cross_post.platform.wechat_moments",
        "requirements_key": "cross_post.requirements.wechat_moments",
    },
    "instagram": {
        "label_key": "cross_post.platform.instagram",
        "requirements_key": "cross_post.requirements.instagram",
    },
    "xiaohongshu": {
        "label_key": "cross_post.platform.xiaohongshu",
        "requirements_key": "cross_post.requirements.xiaohongshu",
    },
}


def get_cross_post_platform_options() -> list[dict[str, str]]:
    return [
        {
            "key": key,
            **PLATFORM_METADATA[key],
        }
        for key in PLATFORM_ORDER
    ]


def normalize_cross_post_targets(values: list[str] | tuple[str, ...] | None) -> list[str]:
    if not values:
        return []

    normalized: list[str] = []
    seen: set[str] = set()

    for value in values:
        key = (value or "").strip()
        if key not in PLATFORM_ORDER or key in seen:
            continue
        normalized.append(key)
        seen.add(key)

    return normalized


def _parse_stored_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def load_cross_post_state(value: str | None) -> dict[str, dict[str, Any]]:
    if not value:
        return {}

    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return {}

    if not isinstance(payload, dict):
        return {}

    state: dict[str, dict[str, Any]] = {}
    for key in PLATFORM_ORDER:
        item = payload.get(key)
        if not isinstance(item, dict):
            continue

        selected = bool(item.get("selected"))
        published_at = _parse_stored_datetime(item.get("published_at"))

        if not selected and published_at is None:
            continue

        state[key] = {
            "selected": selected,
            "published_at": published_at,
        }

    return state


def dump_cross_post_state(state: dict[str, dict[str, Any]]) -> str | None:
    payload: dict[str, dict[str, Any]] = {}

    for key in PLATFORM_ORDER:
        item = state.get(key)
        if not isinstance(item, dict):
            continue

        selected = bool(item.get("selected"))
        published_at = item.get("published_at")

        if not selected and published_at is None:
            continue

        payload[key] = {
            "selected": selected,
            "published_at": (
                published_at.isoformat(timespec="seconds")
                if isinstance(published_at, datetime)
                else None
            ),
        }

    if not payload:
        return None

    return json.dumps(payload, sort_keys=True)


def set_cross_post_targets(moment, requested_targets: list[str] | tuple[str, ...] | None) -> None:
    selected = set(normalize_cross_post_targets(list(requested_targets or [])))
    current_state = load_cross_post_state(getattr(moment, "cross_post_targets", None))
    next_state: dict[str, dict[str, Any]] = {}

    for key in PLATFORM_ORDER:
        if key not in selected:
            continue
        next_state[key] = {
            "selected": True,
            "published_at": current_state.get(key, {}).get("published_at"),
        }

    moment.cross_post_targets = dump_cross_post_state(next_state)


def clear_cross_post_publication_marks(moment) -> bool:
    state = load_cross_post_state(getattr(moment, "cross_post_targets", None))
    changed = False

    for key in PLATFORM_ORDER:
        entry = state.get(key)
        if not isinstance(entry, dict):
            continue
        if entry.get("published_at") is None:
            continue
        entry["published_at"] = None
        changed = True

    if changed:
        moment.cross_post_targets = dump_cross_post_state(state)

    return changed


def mark_cross_post_published(moment, platform: str) -> None:
    if platform not in PLATFORM_ORDER:
        raise ValueError("Unsupported platform.")

    state = load_cross_post_state(getattr(moment, "cross_post_targets", None))
    entry = state.setdefault(platform, {})
    entry["selected"] = True
    entry["published_at"] = datetime.utcnow()
    moment.cross_post_targets = dump_cross_post_state(state)


def reset_cross_post_publication(moment, platform: str) -> None:
    if platform not in PLATFORM_ORDER:
        raise ValueError("Unsupported platform.")

    state = load_cross_post_state(getattr(moment, "cross_post_targets", None))
    entry = state.setdefault(platform, {})
    entry["selected"] = True
    entry["published_at"] = None
    moment.cross_post_targets = dump_cross_post_state(state)


def selected_cross_post_targets(moment) -> list[str]:
    state = load_cross_post_state(getattr(moment, "cross_post_targets", None))
    return [key for key in PLATFORM_ORDER if state.get(key, {}).get("selected")]


def _build_hashtags(moment) -> str:
    tags: list[str] = []

    for category in getattr(moment, "assigned_categories", [])[:5]:
        token = re.sub(r"[^\w\u4e00-\u9fff]+", "", category.name, flags=re.UNICODE)
        if token:
            tags.append(f"#{token}")

    return " ".join(tags)


def build_cross_post_caption(moment, platform: str) -> str:
    content = (getattr(moment, "content", None) or "").strip()
    citation_title = (getattr(moment, "citation_title", None) or "").strip()
    citation_excerpt = (getattr(moment, "citation_excerpt", None) or "").strip()
    location_label = (getattr(moment, "location_label", None) or "").strip()
    hashtags = _build_hashtags(moment)

    citation_copy = ""
    if citation_title and citation_excerpt:
        citation_copy = f"{citation_title}\n{citation_excerpt}"
    else:
        citation_copy = citation_title or citation_excerpt

    parts: list[str] = []
    if content:
        parts.append(content)
    elif citation_copy:
        parts.append(citation_copy)

    if content and citation_copy:
        parts.append(f"From: {citation_copy}")

    if location_label:
        parts.append(f"Location: {location_label}")

    if platform in {"instagram", "xiaohongshu"} and hashtags:
        parts.append(hashtags)

    return "\n\n".join(part for part in parts if part)


def _summarize_media(moment) -> dict[str, Any]:
    attachments = list(getattr(moment, "attachments", []) or [])
    image_attachments = [attachment for attachment in attachments if attachment.media_kind == "image"]
    video_attachments = [attachment for attachment in attachments if attachment.media_kind == "video"]
    document_attachments = [
        attachment for attachment in attachments if attachment.media_kind not in {"image", "video"}
    ]

    return {
        "images": image_attachments,
        "videos": video_attachments,
        "documents": document_attachments,
        "social_media": image_attachments + video_attachments,
        "image_count": len(image_attachments),
        "video_count": len(video_attachments),
        "document_count": len(document_attachments),
        "media_count": len(image_attachments) + len(video_attachments),
    }


def evaluate_cross_post_platform(moment, platform: str) -> dict[str, Any]:
    if platform not in PLATFORM_ORDER:
        raise ValueError("Unsupported platform.")

    summary = _summarize_media(moment)
    caption = build_cross_post_caption(moment, platform)
    has_caption = bool(caption.strip())

    image_count = summary["image_count"]
    video_count = summary["video_count"]
    document_count = summary["document_count"]
    media_count = summary["media_count"]
    share_attachments = list(summary["social_media"])

    reason_key: str | None = None

    if document_count:
        reason_key = "cross_post.reason.documents"
    elif platform == "wechat_moments":
        if image_count and video_count:
            reason_key = "cross_post.reason.mixed_media"
        elif image_count > 9:
            reason_key = "cross_post.reason.wechat_image_limit"
        elif video_count > 1:
            reason_key = "cross_post.reason.single_video_only"
        elif media_count == 0 and not has_caption:
            reason_key = "cross_post.reason.need_text_or_supported_media"
    elif platform == "instagram":
        if media_count == 0:
            reason_key = "cross_post.reason.need_media"
        elif media_count > 10:
            reason_key = "cross_post.reason.instagram_limit"
    elif platform == "xiaohongshu":
        if media_count == 0:
            reason_key = "cross_post.reason.need_media"
        elif image_count and video_count:
            reason_key = "cross_post.reason.mixed_media"
        elif image_count > 9:
            reason_key = "cross_post.reason.xiaohongshu_image_limit"
        elif video_count > 1:
            reason_key = "cross_post.reason.single_video_only"

    return {
        "eligible": reason_key is None,
        "reason_key": reason_key,
        "caption": caption,
        "caption_available": has_caption,
        "media_attachments": summary["social_media"],
        "share_asset_paths": [
            attachment.relative_path
            if attachment.media_kind == "image"
            else attachment.preview_asset_path
            for attachment in share_attachments
        ],
        "media_count": media_count,
        "image_count": image_count,
        "video_count": video_count,
        "document_count": document_count,
        "requirements_key": PLATFORM_METADATA[platform]["requirements_key"],
        "label_key": PLATFORM_METADATA[platform]["label_key"],
    }


def build_cross_post_plan(moment, *, selected_only: bool = True) -> list[dict[str, Any]]:
    state = load_cross_post_state(getattr(moment, "cross_post_targets", None))
    selected_targets = (
        [key for key in PLATFORM_ORDER if state.get(key, {}).get("selected")]
        if selected_only
        else list(PLATFORM_ORDER)
    )
    plans: list[dict[str, Any]] = []

    for platform in selected_targets:
        evaluation = evaluate_cross_post_platform(moment, platform)
        published_at = state.get(platform, {}).get("published_at")

        plans.append(
            {
                "platform": platform,
                "published_at": published_at,
                "published": published_at is not None,
                "status_key": (
                    "cross_post.status.published"
                    if published_at is not None
                    else (
                        "cross_post.status.ready"
                        if evaluation["eligible"]
                        else "cross_post.status.blocked"
                    )
                ),
                **evaluation,
            }
        )

    return plans

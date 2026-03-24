from __future__ import annotations

import json

from sqlalchemy import func

from ..extensions import db
from ..models import Category, Moment, moment_folders


def normalize_folder_name(value: str | None) -> str:
    return (value or "").strip()


def normalize_folder_description(value: str | None) -> str | None:
    description = (value or "").strip()
    return description or None


def parse_folder_ids(raw_values: list[str] | tuple[str, ...]) -> list[int]:
    folder_ids: list[int] = []
    seen_ids: set[int] = set()

    for raw in raw_values:
        if raw in {None, ""}:
            continue

        folder_id = int(raw)
        if folder_id in seen_ids:
            continue

        seen_ids.add(folder_id)
        folder_ids.append(folder_id)

    return folder_ids


def resolve_folders(raw_values: list[str] | tuple[str, ...]) -> list[Category]:
    folder_ids = parse_folder_ids(raw_values)
    if not folder_ids:
        return []

    folders = Category.query.filter(Category.id.in_(folder_ids)).all()
    folders_by_id = {folder.id: folder for folder in folders}

    if len(folders_by_id) != len(folder_ids):
        raise ValueError("Selected folder does not exist.")

    return [folders_by_id[folder_id] for folder_id in folder_ids]


def extract_folder_values(form) -> list[str]:
    values = form.getlist("folder_ids")
    if values:
        return values

    legacy_value = form.get("category_id")
    if legacy_value not in {None, ""}:
        return [legacy_value]

    return []


def serialize_folder_snapshot(folders: list[Category]) -> str | None:
    if not folders:
        return None

    return json.dumps(
        [{"id": folder.id, "name": folder.name} for folder in folders],
        ensure_ascii=True,
    )


def deserialize_folder_snapshot(snapshot: str | None) -> list[dict[str, int | str | None]]:
    if not snapshot:
        return []

    try:
        payload = json.loads(snapshot)
    except json.JSONDecodeError:
        return []

    if not isinstance(payload, list):
        return []

    normalized: list[dict[str, int | str | None]] = []
    for item in payload:
        if isinstance(item, dict) and item.get("name"):
            normalized.append({"id": item.get("id"), "name": item["name"]})
        elif isinstance(item, str) and item:
            normalized.append({"id": None, "name": item})

    return normalized


def build_folder_tree(categories: list[Category], counts: dict[int, int] | None = None) -> list[dict]:
    counts = counts or {}
    nodes = {
        category.id: {
            "folder": category,
            "count": counts.get(category.id, 0),
            "children": [],
            "depth": 0,
        }
        for category in categories
    }

    roots: list[dict] = []

    for category in sorted(categories, key=lambda item: (item.name.lower(), item.id)):
        node = nodes[category.id]
        parent_node = nodes.get(category.parent_id)
        if parent_node is None:
            roots.append(node)
            continue

        node["depth"] = parent_node["depth"] + 1
        parent_node["children"].append(node)

    def sort_children(nodes_to_sort: list[dict]) -> None:
        nodes_to_sort.sort(key=lambda item: (item["folder"].name.lower(), item["folder"].id))
        for child in nodes_to_sort:
            sort_children(child["children"])

    sort_children(roots)
    return roots


def flatten_folder_tree(tree: list[dict]) -> list[dict]:
    flattened: list[dict] = []

    def walk(node: dict) -> None:
        folder = node["folder"]
        flattened.append(
            {
                "id": folder.id,
                "name": folder.name,
                "description": folder.description,
                "depth": node["depth"],
            }
        )
        for child in node["children"]:
            walk(child)

    for root in tree:
        walk(root)

    return flattened


def calculate_folder_counts(categories: list[Category], *, include_deleted: bool = False) -> dict[int, int]:
    moment_query = (
        db.session.query(moment_folders.c.category_id, func.count(func.distinct(Moment.id)))
        .join(Moment, moment_folders.c.moment_id == Moment.id)
        .group_by(moment_folders.c.category_id)
    )

    if not include_deleted:
        moment_query = moment_query.filter(Moment.is_deleted.is_(False))
    else:
        moment_query = moment_query.filter(Moment.is_deleted.is_(True))

    direct_counts = {category_id: count for category_id, count in moment_query.all()}
    tree = build_folder_tree(categories, direct_counts)
    totals: dict[int, int] = {}

    def accumulate(node: dict) -> int:
        total = direct_counts.get(node["folder"].id, 0)
        for child in node["children"]:
            total += accumulate(child)
        totals[node["folder"].id] = total
        return total

    for root in tree:
        accumulate(root)

    return totals


def descendant_folder_ids(folder: Category, all_categories: list[Category]) -> list[int]:
    children_by_parent: dict[int | None, list[Category]] = {}
    for category in all_categories:
        children_by_parent.setdefault(category.parent_id, []).append(category)

    collected: list[int] = []

    def walk(category: Category) -> None:
        collected.append(category.id)
        for child in children_by_parent.get(category.id, []):
            walk(child)

    walk(folder)
    return collected

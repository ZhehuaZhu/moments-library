from __future__ import annotations

import shutil
from copy import deepcopy
from html import escape
from pathlib import Path, PurePosixPath

from lxml import html as lxml_html

from .library import BOOK_ALLOWED_EXTENSIONS
from .storage import (
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    UploadValidationError,
    VIDEO_EXTENSIONS,
    resolve_storage_path,
    save_upload,
    store_generated_asset,
)

try:
    import mobi
except ImportError:  # pragma: no cover - dependency is installed via requirements in app use
    mobi = None

try:
    from ebooklib import ITEM_COVER, ITEM_IMAGE, epub
except ImportError:  # pragma: no cover - dependency is installed via requirements in app use
    ITEM_COVER = None
    ITEM_IMAGE = None
    epub = None

FRONT_MATTER_HINTS = (
    "cover",
    "copyright",
    "contents",
    "toc",
    "nav",
    "titlepage",
    "title page",
    "colophon",
    "preface",
    "foreword",
    "introduction",
    "dedication",
    "acknowledgement",
    "acknowledgment",
    "acknowledgements",
    "acknowledgments",
    "author's note",
    "about the author",
    "\u5c01\u9762",
    "\u7248\u6743",
    "\u76ee\u5f55",
    "\u6249\u9875",
    "\u524d\u8a00",
    "\u5e8f",
    "\u5f15\u8a00",
    "\u81f4\u8c22",
)

ANNOTATABLE_BLOCK_TAGS = {"p", "li", "blockquote", "pre"}
EMBEDDABLE_EPUB_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS
EMBEDDABLE_LOCAL_DOCUMENT_EXTENSIONS = EMBEDDABLE_EPUB_EXTENSIONS | {".html", ".htm"}


def normalize_book_upload(
    source_file,
    upload_root: str,
    *,
    cover_file=None,
) -> dict[str, dict[str, str | int] | None]:
    source_meta = save_upload(
        source_file,
        upload_root,
        allowed_extensions=BOOK_ALLOWED_EXTENSIONS,
    )
    reader_meta = normalize_reader_asset(upload_root, source_meta)

    if cover_file is not None and getattr(cover_file, "filename", ""):
        cover_meta = save_upload(
            cover_file,
            upload_root,
            allowed_extensions=IMAGE_EXTENSIONS,
        )
    else:
        cover_meta = extract_cover_from_epub(upload_root, reader_meta or source_meta)
        if cover_meta is None:
            cover_meta = extract_cover_from_mobi(upload_root, source_meta)

    return {
        "source": source_meta,
        "reader": reader_meta,
        "cover": cover_meta,
    }


def extract_book_identity(
    upload_root: str,
    asset_meta: dict[str, str | int],
) -> dict[str, str | None]:
    original_name = str(asset_meta["original_name"])
    fallback_title = (
        Path(original_name).stem.replace("_", " ").replace("-", " ").strip() or None
    )
    identity = {
        "title": fallback_title,
        "author": None,
    }

    if epub is None or Path(original_name).suffix.lower() != ".epub":
        return identity

    asset_path = resolve_storage_path(upload_root, str(asset_meta["relative_path"]))
    try:
        book = epub.read_epub(str(asset_path))
    except Exception:
        return identity

    title_value = read_epub_metadata_value(book.get_metadata("DC", "title"))
    author_value = read_epub_metadata_value(book.get_metadata("DC", "creator"))
    if title_value:
        identity["title"] = title_value
    if author_value:
        identity["author"] = author_value
    return identity


def read_epub_metadata_value(metadata_items) -> str | None:
    for item in metadata_items or []:
        if not isinstance(item, tuple) or not item:
            continue
        value = str(item[0] or "").strip()
        if value:
            return value
    return None


def normalize_reader_asset(
    upload_root: str,
    source_meta: dict[str, str | int],
) -> dict[str, str | int] | None:
    original_name = str(source_meta["original_name"])
    extension = Path(original_name).suffix.lower()
    source_path = resolve_storage_path(upload_root, str(source_meta["relative_path"]))

    if extension == ".epub":
        return build_epub_reader_asset(source_path, upload_root, Path(original_name).stem)

    if extension != ".mobi" or mobi is None:
        return None

    tempdir = None
    try:
        tempdir, extracted_path = mobi.extract(str(source_path))
        extracted = Path(extracted_path)
        if not extracted.exists():
            return None

        normalized_extension = extracted.suffix.lower()
        if normalized_extension == ".epub":
            return build_epub_reader_asset(extracted, upload_root, f"{Path(original_name).stem}-reader")
        if normalized_extension == ".html":
            reader_meta = build_html_reader_asset(
                extracted,
                upload_root,
                f"{Path(original_name).stem}-reader",
            )
            if reader_meta is not None:
                return reader_meta
        if normalized_extension not in {".pdf", ".html"}:
            return None

        return store_generated_asset(
            extracted.read_bytes(),
            upload_root,
            f"{Path(original_name).stem}-reader{normalized_extension}",
        )
    except Exception:
        return None
    finally:
        if tempdir:
            shutil.rmtree(tempdir, ignore_errors=True)


def extract_cover_from_epub(
    upload_root: str,
    asset_meta: dict[str, str | int],
) -> dict[str, str | int] | None:
    if epub is None:
        return None

    original_name = str(asset_meta["original_name"])
    if Path(original_name).suffix.lower() != ".epub":
        return None

    asset_path = resolve_storage_path(upload_root, str(asset_meta["relative_path"]))
    return extract_cover_from_epub_file(
        asset_path,
        upload_root,
        fallback_name=f"{Path(original_name).stem}-cover.jpg",
    )


def extract_cover_from_epub_file(
    epub_path: Path,
    upload_root: str,
    *,
    fallback_name: str,
) -> dict[str, str | int] | None:
    if epub is None or not epub_path.exists():
        return None

    try:
        book = epub.read_epub(str(epub_path))
    except Exception:
        return None

    cover_item = resolve_epub_cover_item(book)
    if cover_item is None:
        return None

    file_name = getattr(cover_item, "file_name", None) or fallback_name
    media_type = getattr(cover_item, "media_type", None)
    content = cover_item.get_content()
    if not content:
        return None

    try:
        return store_generated_asset(
            content,
            upload_root,
            Path(file_name).name,
            mime_type=media_type,
        )
    except UploadValidationError:
        return None


def extract_cover_from_mobi(
    upload_root: str,
    asset_meta: dict[str, str | int],
) -> dict[str, str | int] | None:
    original_name = str(asset_meta["original_name"])
    if Path(original_name).suffix.lower() != ".mobi" or mobi is None:
        return None

    source_path = resolve_storage_path(upload_root, str(asset_meta["relative_path"]))
    tempdir = None
    try:
        tempdir, extracted_path = mobi.extract(str(source_path))
        extracted = Path(extracted_path)
        if not extracted.exists():
            return None

        normalized_extension = extracted.suffix.lower()
        if normalized_extension == ".epub":
            return extract_cover_from_epub_file(
                extracted,
                upload_root,
                fallback_name=f"{Path(original_name).stem}-cover.jpg",
            )
        if normalized_extension == ".html":
            return extract_cover_from_html_file(
                extracted,
                upload_root,
                fallback_name=f"{Path(original_name).stem}-cover.jpg",
            )
        return None
    except Exception:
        return None
    finally:
        if tempdir:
            shutil.rmtree(tempdir, ignore_errors=True)


def ensure_book_reader_ready(book, upload_root: str) -> bool:
    changed = False

    if not book.reader_relative_path:
        source_meta = {
            "original_name": book.original_name,
            "relative_path": book.relative_path,
        }
        reader_meta = normalize_reader_asset(upload_root, source_meta)
        if reader_meta:
            book.reader_relative_path = reader_meta["relative_path"]
            book.reader_mime_type = reader_meta["mime_type"]
            book.reader_format = Path(str(reader_meta["original_name"])).suffix.lower().lstrip(".")
            changed = True

    if not book.cover_relative_path:
        source_meta = {
            "original_name": book.original_name,
            "relative_path": book.relative_path,
        }
        cover_meta = extract_cover_from_epub(upload_root, source_meta)
        if cover_meta is None:
            cover_meta = extract_cover_from_mobi(upload_root, source_meta)
        if cover_meta:
            book.cover_original_name = cover_meta["original_name"]
            book.cover_stored_name = cover_meta["stored_name"]
            book.cover_relative_path = cover_meta["relative_path"]
            book.cover_mime_type = cover_meta["mime_type"]
            changed = True

    return changed


def resolve_epub_cover_item(book) -> object | None:
    if ITEM_COVER is not None:
        for item in book.get_items():
            if item.get_type() == ITEM_COVER:
                return item

    for _, metadata in book.get_metadata("OPF", "cover"):
        if isinstance(metadata, dict):
            cover_id = metadata.get("content")
            if cover_id:
                item = book.get_item_with_id(cover_id)
                if item is not None:
                    return item

    if ITEM_IMAGE is not None:
        for item in book.get_items():
            name = (getattr(item, "file_name", "") or "").lower()
            identifier = (getattr(item, "id", "") or "").lower()
            if item.get_type() == ITEM_IMAGE and ("cover" in name or "cover" in identifier):
                return item

    return None


def normalize_epub_path(value: str) -> str:
    parts: list[str] = []
    for part in PurePosixPath(str(value or "").replace("\\", "/")).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return PurePosixPath(*parts).as_posix() if parts else ""


def is_external_epub_resource(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized.startswith(("http://", "https://", "//", "data:", "mailto:", "tel:"))


def resolve_epub_resource_path(base_file_name: str, reference: str) -> str | None:
    candidate = normalize_href(reference).strip()
    if not candidate or candidate.startswith("#") or is_external_epub_resource(candidate):
        return None

    if candidate.startswith("/"):
        return normalize_epub_path(candidate)

    base_path = normalize_epub_path(base_file_name)
    if not base_path:
        return normalize_epub_path(candidate)

    return normalize_epub_path(str(PurePosixPath(base_path).parent / candidate))


def merge_class_names(node, *class_names: str) -> None:
    existing = [part for part in str(node.get("class") or "").split() if part]
    for class_name in class_names:
        if class_name and class_name not in existing:
            existing.append(class_name)
    if existing:
        node.set("class", " ".join(existing))


def replace_node(target, replacement) -> None:
    parent = target.getparent()
    if parent is None:
        return
    target.addprevious(replacement)
    parent.remove(target)


def create_reader_placeholder(message: str) -> object:
    placeholder = lxml_html.Element("p")
    placeholder.set("class", "book-reader-media-placeholder")
    placeholder.text = message
    return placeholder


def ensure_media_wrapper(node, kind: str):
    parent = node.getparent()
    if parent is None:
        return node

    wrapper = parent if parent.tag == "figure" else None
    if wrapper is None:
        wrapper = lxml_html.Element("figure")
        node.addprevious(wrapper)
        parent.remove(node)
        wrapper.append(node)

    merge_class_names(wrapper, "book-reader-media-card", f"book-reader-media-card--{kind}")
    wrapper.set("data-book-inline-media", kind)
    return wrapper


def append_media_caption(wrapper, caption: str | None) -> None:
    text = " ".join(str(caption or "").split())
    if not text:
        return

    existing = wrapper.xpath("./figcaption")
    if existing:
        merge_class_names(existing[0], "book-reader-media-card__caption")
        return

    caption_node = lxml_html.Element("figcaption")
    caption_node.set("class", "book-reader-media-card__caption")
    caption_node.text = text
    wrapper.append(caption_node)


def resolve_epub_media_asset(
    asset_map: dict[str, dict[str, str]],
    base_file_name: str,
    reference: str | None,
) -> dict[str, str] | None:
    candidate = str(reference or "").strip()
    if not candidate:
        return None

    if is_external_epub_resource(candidate):
        return {
            "src": candidate,
            "mime_type": "",
        }

    resolved_path = resolve_epub_resource_path(base_file_name, candidate)
    if resolved_path is None:
        return None

    return asset_map.get(resolved_path)


def build_local_document_asset_map(
    document,
    document_path: Path,
    upload_root: str,
) -> dict[str, dict[str, str]]:
    references: set[str] = set()
    for attribute in ("src", "poster"):
        for node in document.xpath(f".//*[@{attribute}]"):
            value = str(node.get(attribute) or "").strip()
            if value:
                references.add(value)

    asset_map: dict[str, dict[str, str]] = {}
    for reference in references:
        resolved_path = resolve_epub_resource_path(document_path.name, reference)
        if resolved_path is None or resolved_path in asset_map:
            continue

        candidate_path = document_path.parent.joinpath(*PurePosixPath(resolved_path).parts)
        if not candidate_path.exists() or not candidate_path.is_file():
            continue
        if candidate_path.suffix.lower() not in EMBEDDABLE_LOCAL_DOCUMENT_EXTENSIONS:
            continue

        try:
            generated = store_generated_asset(
                candidate_path.read_bytes(),
                upload_root,
                candidate_path.name,
            )
        except (OSError, UploadValidationError):
            continue

        asset_map[resolved_path] = {
            "src": f"/static/{generated['relative_path']}",
            "mime_type": str(generated["mime_type"] or ""),
        }

    return asset_map


def find_html_cover_candidate(document, html_path: Path) -> Path | None:
    prioritized: list[tuple[int, int, Path]] = []
    for index, image in enumerate(document.xpath(".//img[@src]")):
        reference = str(image.get("src") or "").strip()
        resolved_path = resolve_epub_resource_path(html_path.name, reference)
        if resolved_path is None:
            continue

        candidate_path = html_path.parent.joinpath(*PurePosixPath(resolved_path).parts)
        if not candidate_path.exists() or not candidate_path.is_file():
            continue
        if candidate_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        descriptor = " ".join(
            part for part in (
                candidate_path.name,
                image.get("alt"),
                image.get("title"),
                image.get("class"),
                image.get("id"),
            )
            if part
        ).lower()
        priority = 0 if "cover" in descriptor else 10
        prioritized.append((priority, index, candidate_path))

    if prioritized:
        prioritized.sort(key=lambda item: (item[0], item[1]))
        return prioritized[0][2]

    for candidate_path in html_path.parent.rglob("*"):
        if (
            candidate_path.is_file()
            and candidate_path.suffix.lower() in IMAGE_EXTENSIONS
            and "cover" in candidate_path.name.lower()
        ):
            return candidate_path

    return None


def extract_cover_from_html_file(
    html_path: Path,
    upload_root: str,
    *,
    fallback_name: str,
) -> dict[str, str | int] | None:
    try:
        raw = html_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = html_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

    try:
        document = lxml_html.fromstring(raw)
    except Exception:
        return None

    candidate_path = find_html_cover_candidate(document, html_path)
    if candidate_path is None:
        return None

    try:
        return store_generated_asset(
            candidate_path.read_bytes(),
            upload_root,
            candidate_path.name or fallback_name,
        )
    except (OSError, UploadValidationError):
        return None


def build_epub_asset_map(book, upload_root: str) -> dict[str, dict[str, str]]:
    asset_map: dict[str, dict[str, str]] = {}

    for item in book.get_items():
        file_name = normalize_epub_path(getattr(item, "file_name", "") or "")
        if not file_name:
            continue

        media_type = str(getattr(item, "media_type", "") or "")
        extension = Path(file_name).suffix.lower()
        if not (
            extension in EMBEDDABLE_EPUB_EXTENSIONS
            or media_type.startswith(("image/", "video/", "audio/"))
        ):
            continue

        try:
            content = item.get_content()
        except Exception:
            continue

        if not content:
            continue

        try:
            generated = store_generated_asset(
                content,
                upload_root,
                Path(file_name).name,
                mime_type=media_type or None,
            )
        except UploadValidationError:
            continue

        asset_map[file_name] = {
            "src": f"/static/{generated['relative_path']}",
            "mime_type": str(generated["mime_type"] or ""),
        }

    return asset_map


def rewrite_epub_media_nodes(
    body,
    file_name: str,
    asset_map: dict[str, dict[str, str]],
) -> None:
    for image in list(body.xpath(".//img")):
        alt_text = image.get("alt") or image.get("title") or ""
        resolved_asset = resolve_epub_media_asset(asset_map, file_name, image.get("src"))
        if resolved_asset is None:
            replace_node(
                image.getparent() if image.getparent() is not None and image.getparent().tag == "figure" else image,
                create_reader_placeholder(
                    alt_text or "Illustration omitted in the fast reader.",
                ),
            )
            continue

        image.set("src", resolved_asset["src"])
        image.attrib.pop("srcset", None)
        image.set("loading", "lazy")
        image.set("decoding", "async")
        merge_class_names(image, "book-reader-inline-image")
        wrapper = ensure_media_wrapper(image, "image")
        append_media_caption(wrapper, alt_text)

    for video in list(body.xpath(".//video")):
        wrapper = ensure_media_wrapper(video, "video")
        merge_class_names(video, "book-reader-inline-video")
        video.attrib.pop("autoplay", None)
        video.set("controls", "controls")
        video.set("playsinline", "playsinline")
        video.set("preload", "metadata")

        poster_asset = resolve_epub_media_asset(asset_map, file_name, video.get("poster"))
        if poster_asset is not None:
            video.set("poster", poster_asset["src"])
        elif video.get("poster"):
            video.attrib.pop("poster", None)

        has_source = False
        direct_asset = resolve_epub_media_asset(asset_map, file_name, video.get("src"))
        if direct_asset is not None:
            video.set("src", direct_asset["src"])
            has_source = True
        elif video.get("src"):
            video.attrib.pop("src", None)

        for source in list(video.xpath("./source")):
            resolved_asset = resolve_epub_media_asset(asset_map, file_name, source.get("src"))
            if resolved_asset is None:
                source_parent = source.getparent()
                if source_parent is not None:
                    source_parent.remove(source)
                continue

            source.set("src", resolved_asset["src"])
            if resolved_asset["mime_type"]:
                source.set("type", resolved_asset["mime_type"])
            has_source = True

        if not has_source:
            replace_node(wrapper, create_reader_placeholder("Embedded video is unavailable in the fast reader."))
            continue

        append_media_caption(wrapper, video.get("title") or video.get("aria-label"))

    for audio in list(body.xpath(".//audio")):
        wrapper = ensure_media_wrapper(audio, "audio")
        merge_class_names(audio, "book-reader-inline-audio")
        audio.set("controls", "controls")
        audio.set("preload", "metadata")

        has_source = False
        direct_asset = resolve_epub_media_asset(asset_map, file_name, audio.get("src"))
        if direct_asset is not None:
            audio.set("src", direct_asset["src"])
            has_source = True
        elif audio.get("src"):
            audio.attrib.pop("src", None)

        for source in list(audio.xpath("./source")):
            resolved_asset = resolve_epub_media_asset(asset_map, file_name, source.get("src"))
            if resolved_asset is None:
                source_parent = source.getparent()
                if source_parent is not None:
                    source_parent.remove(source)
                continue

            source.set("src", resolved_asset["src"])
            if resolved_asset["mime_type"]:
                source.set("type", resolved_asset["mime_type"])
            has_source = True

        if not has_source:
            replace_node(wrapper, create_reader_placeholder("Embedded audio is unavailable in the fast reader."))
            continue

        append_media_caption(wrapper, audio.get("title") or audio.get("aria-label"))

    for iframe in list(body.xpath(".//iframe")):
        resolved_asset = resolve_epub_media_asset(asset_map, file_name, iframe.get("src"))
        if resolved_asset is None:
            replace_node(
                iframe.getparent() if iframe.getparent() is not None and iframe.getparent().tag == "figure" else iframe,
                create_reader_placeholder("Interactive embed unavailable in the fast reader."),
            )
            continue

        iframe.set("src", resolved_asset["src"])
        iframe.set("loading", "lazy")
        iframe.set("allowfullscreen", "allowfullscreen")
        iframe.set(
            "allow",
            "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; fullscreen",
        )
        iframe.set("referrerpolicy", "strict-origin-when-cross-origin")
        merge_class_names(iframe, "book-reader-inline-embed")
        wrapper = ensure_media_wrapper(iframe, "embed")
        append_media_caption(wrapper, iframe.get("title") or iframe.get("aria-label"))


def render_reader_body_section(
    body,
    *,
    file_name: str,
    label: str,
    index: int,
    asset_map: dict[str, dict[str, str]],
) -> dict[str, object] | None:
    anchor = f"reader-section-{index + 1}"
    rewrite_epub_media_nodes(body, file_name, asset_map)
    text_content = " ".join(body.text_content().split())
    has_embedded_media = bool(
        body.xpath(".//*[contains(concat(' ', normalize-space(@class), ' '), ' book-reader-media-card ')]")
    )
    if not text_content and not has_embedded_media:
        return None

    annotate_section_blocks(body, anchor)

    inner_html = "".join(
        lxml_html.tostring(child, encoding="unicode", method="html")
        for child in body
    ).strip()
    if not inner_html:
        inner_html = (
            f'<p data-reader-paragraph-id="{escape(anchor)}-p-1" data-reader-block-index="1">'
            f"{escape(text_content)}</p>"
        )

    return {
        "anchor": anchor,
        "label": label,
        "html": inner_html,
        "source_href": normalize_href(file_name),
        "is_front_matter": is_front_matter(file_name, label),
    }


def build_html_reader_asset(
    html_path: Path,
    upload_root: str,
    file_stem: str,
) -> dict[str, str | int] | None:
    try:
        raw = html_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = html_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

    try:
        document = lxml_html.fromstring(raw)
    except Exception:
        return None

    if document.xpath(
        ".//section[contains(concat(' ', normalize-space(@class), ' '), ' book-reader-section ')]"
    ):
        return store_generated_asset(
            raw.encode("utf-8"),
            upload_root,
            f"{file_stem}.html",
            mime_type="text/html",
        )

    body = document.find(".//body")
    if body is None:
        body = document

    for node in body.xpath(".//script|.//style|.//svg"):
        parent = node.getparent()
        if parent is not None:
            parent.remove(node)

    asset_map = build_local_document_asset_map(document, html_path, upload_root)
    label = resolve_section_label(body, None, html_path.name, 0)
    section = render_reader_body_section(
        body,
        file_name=html_path.name,
        label=label,
        index=0,
        asset_map=asset_map,
    )
    if section is None:
        return None

    fragment = build_reader_fragment([section])
    return store_generated_asset(
        fragment.encode("utf-8"),
        upload_root,
        f"{file_stem}.html",
        mime_type="text/html",
    )


def build_epub_reader_asset(
    epub_path: Path,
    upload_root: str,
    file_stem: str,
) -> dict[str, str | int] | None:
    if epub is None:
        return None

    try:
        book = epub.read_epub(str(epub_path))
    except Exception:
        return None

    navigation_map = build_navigation_map(book.toc)
    asset_map = build_epub_asset_map(book, upload_root)
    sections: list[dict[str, object]] = []
    section_index = 0

    for spine_item in book.spine:
        item_id = spine_item[0] if isinstance(spine_item, tuple) else spine_item
        item = book.get_item_with_id(item_id)
        if item is None:
            continue

        file_name = getattr(item, "file_name", "") or ""
        if not file_name.lower().endswith((".xhtml", ".html", ".htm")):
            continue

        section = render_epub_section(item, navigation_map, section_index, asset_map)
        if section is None:
            continue

        sections.append(section)
        section_index += 1

    if not sections:
        return None

    fragment = build_reader_fragment(sections)
    return store_generated_asset(
        fragment.encode("utf-8"),
        upload_root,
        f"{file_stem}.html",
        mime_type="text/html",
    )


def build_navigation_map(toc_items) -> dict[str, str]:
    mapping: dict[str, str] = {}

    def visit(items):
        for item in items:
            if isinstance(item, tuple) and len(item) == 2:
                section, children = item
                label = getattr(section, "title", None) or str(section)
                href = getattr(section, "href", None)
                if href:
                    mapping[normalize_href(href)] = label
                if children:
                    visit(children)
                continue

            href = getattr(item, "href", None)
            label = getattr(item, "title", None) or href
            if href:
                mapping[normalize_href(href)] = label

    visit(list(toc_items or []))
    return mapping


def render_epub_section(
    item,
    navigation_map: dict[str, str],
    index: int,
    asset_map: dict[str, dict[str, str]],
) -> dict[str, object] | None:
    try:
        document = lxml_html.fromstring(item.get_content())
    except Exception:
        return None

    body = document.find(".//body")
    if body is None:
        body = document

    for node in body.xpath(".//script|.//style|.//svg"):
        parent = node.getparent()
        if parent is not None:
            parent.remove(node)

    file_name = getattr(item, "file_name", "") or ""
    label = resolve_section_label(body, navigation_map.get(normalize_href(file_name)), file_name, index)
    return render_reader_body_section(
        body,
        file_name=file_name,
        label=label,
        index=index,
        asset_map=asset_map,
    )


def resolve_section_label(body, nav_label: str | None, file_name: str, index: int) -> str:
    if nav_label:
        return nav_label

    heading = body.xpath(".//h1|.//h2|.//h3")
    if heading:
        heading_text = " ".join(heading[0].text_content().split())
        if heading_text:
            return heading_text

    stem = Path(file_name).stem.replace("_", " ").replace("-", " ").strip()
    return stem.title() if stem else f"Section {index + 1}"


def build_reader_fragment(sections: list[dict[str, object]]) -> str:
    rendered_sections = []
    for index, section in enumerate(sections):
        source_href = escape(str(section.get("source_href") or ""))
        is_section_front_matter = "true" if section.get("is_front_matter") else "false"
        rendered_sections.append(
            (
                f'<section class="book-reader-section" id="{escape(str(section["anchor"]))}" '
                f'data-section-index="{index}" '
                f'data-section-label="{escape(str(section["label"]))}" '
                f'data-source-href="{source_href}" '
                f'data-front-matter="{is_section_front_matter}">'
                f'<header class="book-reader-section__header"><h2>{escape(str(section["label"]))}</h2></header>'
                f'{section["html"]}'
                "</section>"
            )
        )

    return '<article class="book-reader-article">' + "".join(rendered_sections) + "</article>"


def read_reader_sections(upload_root: str, relative_path: str) -> list[dict[str, object]]:
    asset_path = resolve_storage_path(upload_root, relative_path)
    if not asset_path.exists():
        return []

    try:
        raw = asset_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw = asset_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    try:
        document = lxml_html.fromstring(raw)
    except Exception:
        return []

    sections: list[dict[str, object]] = []
    nodes = document.xpath(
        ".//section[contains(concat(' ', normalize-space(@class), ' '), ' book-reader-section ')]"
    )

    for index, node in enumerate(nodes):
        label = (node.get("data-section-label") or "").strip() or f"Section {index + 1}"
        anchor = (node.get("id") or "").strip() or f"reader-section-{index + 1}"
        source_href = normalize_href(node.get("data-source-href") or "")
        front_matter_value = (node.get("data-front-matter") or "").strip().lower()
        content_node = deepcopy(node)
        block_index = 0
        content_parts: list[str] = []

        for child in content_node:
            class_name = child.get("class", "") if hasattr(child, "get") else ""
            if child.tag == "header" and "book-reader-section__header" in class_name:
                continue
            block_index = annotate_section_blocks(child, anchor, block_index)
            content_parts.append(lxml_html.tostring(child, encoding="unicode", method="html"))

        content_html = "".join(content_parts).strip()
        if not content_html:
            text_content = " ".join(node.text_content().split())
            if text_content:
                content_html = (
                    f'<p data-reader-paragraph-id="{escape(anchor)}-p-1" data-reader-block-index="1">'
                    f"{escape(text_content)}</p>"
                )
            else:
                content_html = '<p class="helper-text">This section is empty.</p>'

        sections.append(
            {
                "anchor": anchor,
                "label": label,
                "html": content_html,
                "source_href": source_href,
                "is_front_matter": (
                    front_matter_value == "true"
                    if front_matter_value in {"true", "false"}
                    else is_front_matter(source_href, label)
                ),
            }
        )

    return sections


def render_reader_section_markup(section: dict[str, object]) -> str:
    source_href = escape(str(section.get("source_href") or ""))
    is_section_front_matter = "true" if section.get("is_front_matter") else "false"
    return (
        f'<section class="book-reader-section is-active" id="{escape(str(section["anchor"]))}" '
        f'data-section-label="{escape(str(section["label"]))}" '
        f'data-source-href="{source_href}" '
        f'data-front-matter="{is_section_front_matter}">'
        f'<header class="book-reader-section__header"><h2>{escape(str(section["label"]))}</h2></header>'
        f'{section["html"]}'
        "</section>"
    )


def normalize_href(value: str) -> str:
    return str(value or "").split("#")[0]


def annotate_section_blocks(root, section_anchor: str, start_index: int = 0) -> int:
    block_index = start_index

    for node in root.iter():
        if not isinstance(node.tag, str):
            continue
        if node.tag.lower() not in ANNOTATABLE_BLOCK_TAGS:
            continue

        text_content = " ".join(node.text_content().split())
        if not text_content:
            continue

        block_index += 1
        existing_id = (node.get("data-reader-paragraph-id") or "").strip()
        node.set("data-reader-paragraph-id", existing_id or f"{section_anchor}-p-{block_index}")
        node.set("data-reader-block-index", str(block_index))

    return block_index


def is_front_matter(file_name: str, label: str) -> bool:
    haystack = f"{file_name} {label}".lower()
    return any(hint in haystack for hint in FRONT_MATTER_HINTS)

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from ..models import Attachment
from .storage import delete_attachment_file, resolve_storage_path, store_generated_asset

try:
    from PIL import Image, ImageOps, UnidentifiedImageError
except ImportError:  # pragma: no cover - dependency can be absent in some environments
    Image = None
    ImageOps = None
    UnidentifiedImageError = OSError


if Image is not None:  # pragma: no branch
    RESAMPLING = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
else:  # pragma: no cover - used only when Pillow is unavailable
    RESAMPLING = None


MAX_SOURCE_EDGE = 3000
MAX_PREVIEW_EDGE = 1600
JPEG_QUALITY = 86
WEBP_QUALITY = 82


def _load_image(source_path: Path):
    if Image is None or ImageOps is None:
        return None

    try:
        with Image.open(source_path) as opened:
            normalized = ImageOps.exif_transpose(opened)
            normalized.load()
            return normalized.copy()
    except (UnidentifiedImageError, OSError):
        return None


def _has_alpha(image) -> bool:
    if image.mode in {"RGBA", "LA"}:
        return True
    return image.mode == "P" and "transparency" in image.info


def _resize_image(image, max_edge: int):
    prepared = image.copy()
    if max(prepared.size) > max_edge:
        prepared.thumbnail((max_edge, max_edge), RESAMPLING)
    return prepared


def _build_temp_path(source_path: Path) -> Path:
    return source_path.with_name(f"{source_path.stem}.tmp{source_path.suffix}")


def optimize_uploaded_image(source_path: Path) -> int | None:
    if Image is None or RESAMPLING is None:
        return None

    extension = source_path.suffix.lower()
    if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
        return None

    image = _load_image(source_path)
    if image is None:
        return None

    prepared = _resize_image(image, MAX_SOURCE_EDGE)
    original_size = source_path.stat().st_size
    temp_path = _build_temp_path(source_path)

    try:
        if extension in {".jpg", ".jpeg"}:
            if prepared.mode not in {"RGB", "L"}:
                prepared = prepared.convert("RGB")
            prepared.save(
                temp_path,
                format="JPEG",
                quality=JPEG_QUALITY,
                optimize=True,
                progressive=True,
            )
        elif extension == ".png":
            if prepared.mode not in {"RGB", "RGBA", "L", "LA", "P"}:
                prepared = prepared.convert("RGBA" if _has_alpha(prepared) else "RGB")
            prepared.save(
                temp_path,
                format="PNG",
                optimize=True,
                compress_level=8,
            )
        elif extension == ".webp":
            prepared.save(
                temp_path,
                format="WEBP",
                quality=WEBP_QUALITY,
                method=6,
            )
    except OSError:
        temp_path.unlink(missing_ok=True)
        return None

    temp_size = temp_path.stat().st_size
    if temp_size <= original_size or prepared.size != image.size:
        temp_path.replace(source_path)
        return source_path.stat().st_size

    temp_path.unlink(missing_ok=True)
    return original_size


def _generate_preview_asset(source_path: Path, upload_root: str, original_name: str):
    if Image is None or RESAMPLING is None:
        return None

    image = _load_image(source_path)
    if image is None:
        return None

    preview = _resize_image(image, MAX_PREVIEW_EDGE)
    buffer = BytesIO()

    if _has_alpha(preview):
        preview.save(buffer, format="WEBP", quality=WEBP_QUALITY, method=6)
        extension = ".webp"
        mime_type = "image/webp"
    else:
        if preview.mode not in {"RGB", "L"}:
            preview = preview.convert("RGB")
        preview.save(
            buffer,
            format="JPEG",
            quality=JPEG_QUALITY,
            optimize=True,
            progressive=True,
        )
        extension = ".jpg"
        mime_type = "image/jpeg"

    stem = Path(original_name).stem or "image"
    preview_name = f"{stem}-preview{extension}"
    return store_generated_asset(buffer.getvalue(), upload_root, preview_name, mime_type=mime_type)


def ensure_attachment_image_preview(attachment: Attachment, upload_root: str) -> list[str]:
    if attachment.media_kind != "image":
        return []

    source_path = resolve_storage_path(upload_root, attachment.relative_path)
    if not source_path.exists():
        return []

    preview_exists = bool(
        attachment.preview_relative_path
        and resolve_storage_path(upload_root, attachment.preview_relative_path).exists()
    )
    if preview_exists:
        return []

    optimized_size = optimize_uploaded_image(source_path)
    if optimized_size is not None:
        attachment.size_bytes = optimized_size

    preview_asset = _generate_preview_asset(source_path, upload_root, attachment.original_name)
    if preview_asset is None:
        return []

    if attachment.preview_relative_path:
        delete_attachment_file(upload_root, attachment.preview_relative_path)

    attachment.preview_relative_path = preview_asset["relative_path"]
    attachment.preview_mime_type = preview_asset["mime_type"]
    return [preview_asset["absolute_path"]]

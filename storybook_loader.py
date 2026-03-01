"""Utilities for loading local storybook folders.

The loader supports two directory conventions:
- Format A: paired files at the book root (e.g., ``001.png`` + ``001.md``)
- Format B: nested page folders (e.g., ``pages/001/image.png`` + ``pages/001/text.md``)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTENSIONS = {".mp4"}
TEXT_EXTENSIONS = {".txt", ".md"}


@dataclass
class Page:
    """Represents a single page in a storybook."""

    page_id: str
    image_path: Path | None = None
    video_path: Path | None = None
    text_path: Path | None = None


@dataclass
class BookMetadata:
    """Top-level optional metadata for a storybook."""

    title: str
    author: str = ""
    description: str = ""
    cover_image_path: Path | None = None


@dataclass
class Book:
    """Loaded storybook data and non-fatal loader warnings."""

    root_path: Path
    metadata: BookMetadata
    pages: list[Page]
    warnings: list[str] = field(default_factory=list)


def list_sample_books(sample_root: str | Path = "sample_books") -> list[Path]:
    """Return available sample-book directories sorted by natural order."""
    root = Path(sample_root)
    if not root.exists() or not root.is_dir():
        return []

    books = [path for path in root.iterdir() if path.is_dir()]
    return sorted(books, key=lambda path: _natural_sort_key(path.name))


def load_book(book_path: str | Path) -> Book:
    """Load a storybook from disk without raising on malformed input.

    Returns a ``Book`` object with best-effort parsing and warnings for recoverable
    issues (missing files, malformed manifest, duplicate assets, etc).
    """

    warnings: list[str] = []
    root = Path(book_path).expanduser()

    if not root.exists() or not root.is_dir():
        warnings.append(f"Book path is not a directory: {root}")
        metadata = BookMetadata(title=root.name or "Untitled Book")
        return Book(root_path=root, metadata=metadata, pages=[], warnings=warnings)

    manifest_data = _load_manifest(root, warnings)

    metadata = BookMetadata(
        title=_coerce_string(manifest_data.get("title")) or root.name,
        author=_coerce_string(manifest_data.get("author")),
        description=_coerce_string(manifest_data.get("description")),
        cover_image_path=_resolve_cover_image(root, manifest_data, warnings),
    )

    pages_map: dict[str, Page] = {}
    _merge_pages(pages_map, _discover_nested_pages(root, warnings), warnings, "nested")
    _merge_pages(
        pages_map,
        _discover_flat_pages(root, warnings, metadata.cover_image_path),
        warnings,
        "flat",
    )

    page_ids = _resolve_page_order(pages_map, manifest_data, warnings)
    pages = [pages_map[page_id] for page_id in page_ids]

    if not pages:
        warnings.append("No pages were found in this folder.")

    # Best-effort cover image inference if manifest did not define it.
    if metadata.cover_image_path is None:
        metadata.cover_image_path = _infer_cover_image(root)

    return Book(root_path=root, metadata=metadata, pages=pages, warnings=warnings)


def read_page_text(page: Page) -> tuple[str, list[str]]:
    """Read page text content and return ``(text, warnings)``."""
    warnings: list[str] = []
    if page.text_path is None:
        return "", warnings

    if not page.text_path.exists():
        warnings.append(f"Text file not found for page {page.page_id}: {page.text_path}")
        return "", warnings

    try:
        text = page.text_path.read_text(encoding="utf-8")
        return text, warnings
    except UnicodeDecodeError:
        warnings.append(
            f"Could not decode text file as UTF-8 for page {page.page_id}: {page.text_path}"
        )
    except OSError as exc:
        warnings.append(f"Could not read text file for page {page.page_id}: {exc}")

    return "", warnings


def _load_manifest(root: Path, warnings: list[str]) -> dict[str, Any]:
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        return {}

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        warnings.append(f"Could not parse manifest.json: {exc}")
        return {}

    if not isinstance(data, dict):
        warnings.append("manifest.json must contain a top-level JSON object.")
        return {}

    return data


def _resolve_cover_image(
    root: Path, manifest_data: dict[str, Any], warnings: list[str]
) -> Path | None:
    raw_cover = manifest_data.get("cover_image")
    if not isinstance(raw_cover, str) or not raw_cover.strip():
        return None

    candidate = Path(raw_cover.strip())
    if not candidate.is_absolute():
        candidate = root / candidate

    if not candidate.exists():
        warnings.append(f"Manifest cover image not found: {candidate}")
        return None

    if candidate.suffix.lower() not in IMAGE_EXTENSIONS:
        warnings.append(
            f"Manifest cover image has unsupported extension: {candidate.suffix}"
        )
        return None

    return candidate


def _infer_cover_image(root: Path) -> Path | None:
    cover_candidates = [
        path
        for path in root.iterdir()
        if path.is_file()
        and path.stem.lower() in {"cover", "front", "000"}
        and path.suffix.lower() in IMAGE_EXTENSIONS
    ]
    if not cover_candidates:
        return None
    return sorted(cover_candidates, key=lambda path: _natural_sort_key(path.name))[0]


def _discover_flat_pages(
    root: Path,
    warnings: list[str],
    manifest_cover_image: Path | None = None,
) -> dict[str, Page]:
    pages: dict[str, Page] = {}
    cover_path: Path | None = None
    if manifest_cover_image is not None:
        try:
            cover_path = manifest_cover_image.resolve()
        except OSError:
            cover_path = manifest_cover_image

    files = [path for path in root.iterdir() if path.is_file()]
    files = sorted(files, key=lambda path: _natural_sort_key(path.name))

    for file_path in files:
        if cover_path is not None:
            try:
                candidate = file_path.resolve()
            except OSError:
                candidate = file_path
            if candidate == cover_path:
                continue

        suffix = file_path.suffix.lower()
        if (
            suffix not in IMAGE_EXTENSIONS
            and suffix not in VIDEO_EXTENSIONS
            and suffix not in TEXT_EXTENSIONS
        ):
            continue

        page_id = file_path.stem
        if page_id.lower() == "cover":
            continue

        page = pages.setdefault(page_id, Page(page_id=page_id))
        if suffix in IMAGE_EXTENSIONS:
            if page.image_path is not None:
                warnings.append(
                    f"Duplicate image for flat page {page_id}; keeping first: {page.image_path}"
                )
            else:
                page.image_path = file_path
        elif suffix in VIDEO_EXTENSIONS:
            if page.video_path is not None:
                warnings.append(
                    f"Duplicate video for flat page {page_id}; keeping first: {page.video_path}"
                )
            else:
                page.video_path = file_path
        else:
            if page.text_path is not None:
                warnings.append(
                    f"Duplicate text for flat page {page_id}; keeping first: {page.text_path}"
                )
            else:
                page.text_path = file_path

    return pages


def _discover_nested_pages(root: Path, warnings: list[str]) -> dict[str, Page]:
    pages_dir = root / "pages"
    if not pages_dir.exists() or not pages_dir.is_dir():
        return {}

    pages: dict[str, Page] = {}

    page_dirs = [path for path in pages_dir.iterdir() if path.is_dir()]
    page_dirs = sorted(page_dirs, key=lambda path: _natural_sort_key(path.name))

    for page_dir in page_dirs:
        page_id = page_dir.name

        image_files = sorted(
            [
                path
                for path in page_dir.iterdir()
                if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
            ],
            key=lambda path: _natural_sort_key(path.name),
        )
        video_files = sorted(
            [
                path
                for path in page_dir.iterdir()
                if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
            ],
            key=lambda path: _natural_sort_key(path.name),
        )
        text_files = sorted(
            [
                path
                for path in page_dir.iterdir()
                if path.is_file() and path.suffix.lower() in TEXT_EXTENSIONS
            ],
            key=lambda path: _natural_sort_key(path.name),
        )

        image_path = image_files[0] if image_files else None
        video_path = video_files[0] if video_files else None
        text_path = text_files[0] if text_files else None

        if len(image_files) > 1:
            warnings.append(
                f"Multiple images found in {page_dir}; using {image_files[0].name}."
            )
        if len(video_files) > 1:
            warnings.append(
                f"Multiple videos found in {page_dir}; using {video_files[0].name}."
            )
        if len(text_files) > 1:
            warnings.append(f"Multiple text files found in {page_dir}; using {text_files[0].name}.")

        if image_path is None and video_path is None and text_path is None:
            warnings.append(f"No image/video/text found in nested page folder: {page_dir}")
            continue

        pages[page_id] = Page(
            page_id=page_id,
            image_path=image_path,
            video_path=video_path,
            text_path=text_path,
        )

    return pages


def _resolve_page_order(
    pages_map: dict[str, Page], manifest_data: dict[str, Any], warnings: list[str]
) -> list[str]:
    if not pages_map:
        return []

    raw_order = manifest_data.get("page_order")
    if not isinstance(raw_order, list):
        return sorted(pages_map.keys(), key=_natural_sort_key)

    ordered_ids: list[str] = []
    seen: set[str] = set()

    for raw_value in raw_order:
        normalized = _normalize_manifest_page_id(raw_value)
        if normalized is None:
            continue
        if normalized in pages_map and normalized not in seen:
            ordered_ids.append(normalized)
            seen.add(normalized)
        elif normalized not in pages_map:
            warnings.append(f"Manifest page_order item not found in pages: {raw_value}")

    trailing_ids = [page_id for page_id in pages_map if page_id not in seen]
    trailing_ids = sorted(trailing_ids, key=_natural_sort_key)
    ordered_ids.extend(trailing_ids)
    return ordered_ids


def _normalize_manifest_page_id(raw_value: Any) -> str | None:
    if not isinstance(raw_value, str):
        return None

    value = raw_value.strip()
    if not value:
        return None

    value = Path(value).name
    suffix = Path(value).suffix.lower()
    if suffix in IMAGE_EXTENSIONS or suffix in VIDEO_EXTENSIONS or suffix in TEXT_EXTENSIONS:
        value = Path(value).stem

    return value


def _merge_pages(
    target: dict[str, Page],
    incoming: dict[str, Page],
    warnings: list[str],
    incoming_label: str,
) -> None:
    for page_id, incoming_page in incoming.items():
        current = target.get(page_id)
        if current is None:
            target[page_id] = incoming_page
            continue

        if current.image_path is None:
            current.image_path = incoming_page.image_path
        elif incoming_page.image_path is not None:
            warnings.append(
                f"Duplicate page image for {page_id} ({incoming_label} format ignored)."
            )

        if current.video_path is None:
            current.video_path = incoming_page.video_path
        elif incoming_page.video_path is not None:
            warnings.append(
                f"Duplicate page video for {page_id} ({incoming_label} format ignored)."
            )

        if current.text_path is None:
            current.text_path = incoming_page.text_path
        elif incoming_page.text_path is not None:
            warnings.append(
                f"Duplicate page text for {page_id} ({incoming_label} format ignored)."
            )


def _coerce_string(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def _natural_sort_key(value: str) -> tuple[Any, ...]:
    parts = re.split(r"(\d+)", value)
    key: list[Any] = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        else:
            key.append(part.lower())
    return tuple(key)

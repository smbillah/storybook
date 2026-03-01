"""Local Streamlit app for reading storybook folders from disk."""

from __future__ import annotations

import html
import struct
import time
from pathlib import Path
from functools import lru_cache

import streamlit as st
from PIL import Image, UnidentifiedImageError

from storybook_loader import (
    Book,
    Page,
    list_sample_books,
    load_book,
    read_page_text,
)

st.set_page_config(page_title="Storybook Reader", layout="wide")
DEFAULT_SAMPLE_BOOK = "squirrel_book"
AUTOPLAY_NON_VIDEO_DELAY_SECONDS = 4
FRAME_CHROME_WIDTH_PX = 40
MIN_FRAME_WIDTH_PX = 360
MAX_FRAME_WIDTH_PX = 1200
DEFAULT_STAGE_WIDTH_PX = 1120


def _current_book_path(
    sample_paths: list[Path],
    selected_sample_name: str,
) -> Path | None:
    for sample_path in sample_paths:
        if sample_path.name == selected_sample_name:
            return sample_path

    return None


def _inject_text_size_css(font_size: int, stage_width_px: int) -> None:
    caption_font_size = max(18, font_size + 2)
    st.markdown(
        f"""
        <style>
        :root {{
            --paper: #ffffff;
            --ink: #2b1f18;
            --accent: #7a4e2d;
            --panel: #ffffff;
            --panel-border: #e6e6e6;
            --reader-stage-width: {stage_width_px}px;
            --video-caption-size: {caption_font_size}px;
        }}

        .stApp {{
            background: #ffffff;
            color: var(--ink);
        }}

        [data-testid="stAppViewContainer"] .main .block-container {{
            padding-top: 0.75rem;
            padding-bottom: 0.75rem;
            max-width: 1400px;
        }}

        [data-testid="stAppViewContainer"] .main > div {{
            padding-top: 0.75rem;
            padding-bottom: 0.75rem;
        }}

        [data-testid="stSidebar"] {{
            background: #ffffff;
            border-right: 1px solid #e6e6e6;
        }}

        footer {{
            visibility: hidden;
            height: 0;
        }}

        .storybook-nav-meta {{
            text-align: center;
            margin-top: 0.25rem;
            margin-bottom: 0.4rem;
            color: #6f4f3a;
            font-weight: 600;
            font-family: "Palatino Linotype", "Book Antiqua", "Times New Roman", serif;
        }}

        .storybook-autoplay-meta {{
            text-align: center;
            margin-top: 0.1rem;
            margin-bottom: 0.2rem;
            color: #7f6149;
            font-size: 0.86rem;
        }}

        [data-testid="stCaptionContainer"] p {{
            margin-top: 0.15rem;
            margin-bottom: 0.4rem;
            color: #6f4f3a;
            font-weight: 600;
        }}

        section.main div[data-testid="stMarkdownContainer"] p,
        section.main div[data-testid="stMarkdownContainer"] li {{
            font-size: {font_size}px;
            line-height: 1.6;
            font-family: "Palatino Linotype", "Book Antiqua", "Times New Roman", serif;
            color: #2f231b;
        }}

        section.main [data-testid="stVerticalBlockBorderWrapper"] {{
            background: #ffffff;
            border: 1px solid #dfdfdf;
            border-radius: 16px;
            box-shadow: 0 6px 18px rgba(0, 0, 0, 0.06);
            padding: 0.7rem 0.95rem;
            margin-bottom: 0.5rem;
        }}

        section.main .st-key-reader_toolbar,
        section.main .st-key-reader_page,
        section.main .st-key-reader_cover {{
            width: min(100%, var(--reader-stage-width)) !important;
            margin-left: auto !important;
            margin-right: auto !important;
        }}

        section.main [data-testid="stImage"], section.main [data-testid="stVideo"] {{
            width: 100% !important;
            max-width: 100%;
            display: flex;
            justify-content: center;
            margin: 0.1rem auto;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 6px 24px rgba(47, 28, 16, 0.16);
        }}

        section.main [data-testid="stImage"] > div,
        section.main [data-testid="stVideo"] > div {{
            width: fit-content !important;
            max-width: 100%;
        }}

        section.main [data-testid="stImage"] img {{
            width: auto !important;
            max-width: 100%;
            height: auto !important;
            display: block;
            margin: 0 auto;
        }}

        section.main [data-testid="stVideo"] video {{
            width: auto !important;
            max-width: 100%;
            height: auto !important;
            display: block;
            margin: 0 auto;
        }}

        .storybook-video-caption-wrap {{
            display: flex;
            justify-content: center;
            margin-top: -10.3rem;
            margin-bottom: 0.1rem;
            position: relative;
            z-index: 5;
            pointer-events: none;
        }}

        .storybook-video-caption {{
            max-width: calc(min(100%, var(--reader-stage-width)) - 0.9rem);
            background: transparent;
            border: none;
            border-radius: 0;
            padding: 0.28rem 0.45rem 0.34rem;
            font-size: var(--video-caption-size);
            line-height: 1.06;
            text-align: center;
            font-family: "Comic Sans MS", "Chalkboard SE", "Marker Felt", cursive;
            font-weight: 700;
            color: #fffef7;
            text-shadow: 1.3px 1.3px 0 #3f2415, -0.8px -0.8px 0 #3f2415, 0 0 8px rgba(0, 0, 0, 0.35);
            letter-spacing: 0.01em;
            box-shadow: none;
        }}

        .storybook-image-caption-wrap {{
            display: flex;
            justify-content: center;
            margin-top: -6.9rem;
            margin-bottom: 0.1rem;
            position: relative;
            z-index: 5;
            pointer-events: none;
        }}

        .storybook-image-caption {{
            max-width: calc(min(100%, var(--reader-stage-width)) - 1.15rem);
            background: rgba(16, 22, 42, 0.52);
            border: 1px solid rgba(255, 255, 255, 0.28);
            border-radius: 10px;
            padding: 0.5rem 0.72rem 0.55rem;
            font-size: calc(var(--video-caption-size) - 2px);
            line-height: 1.12;
            text-align: center;
            font-family: "Comic Sans MS", "Chalkboard SE", "Marker Felt", cursive;
            font-weight: 700;
            color: #fffef7;
            text-shadow: 1px 1px 0 rgba(15, 12, 20, 0.65), 0 0 6px rgba(0, 0, 0, 0.22);
            letter-spacing: 0.01em;
            box-shadow: none;
        }}

        @media (max-width: 900px) {{
            .storybook-video-caption-wrap {{
                margin-top: -7.8rem;
                margin-bottom: 0.08rem;
            }}

            .storybook-video-caption {{
                max-width: calc(100% - 1.2rem);
                padding: 0.42rem 0.65rem 0.5rem;
            }}

            .storybook-image-caption-wrap {{
                margin-top: -5.1rem;
                margin-bottom: 0.08rem;
            }}

            .storybook-image-caption {{
                max-width: calc(100% - 1.2rem);
                padding: 0.42rem 0.6rem 0.5rem;
            }}
        }}

        [data-testid="stButton"] > button {{
            border-radius: 999px;
            border: 1px solid #d3d3d3;
            background: #ffffff;
            color: #3d2719;
            font-weight: 700;
            padding: 0.2rem 0.55rem;
        }}

        section.main [data-testid="stCheckbox"] label {{
            white-space: nowrap;
        }}

        section.main [data-testid="stCheckbox"] [data-testid="stMarkdownContainer"] p {{
            margin: 0;
            font-size: 0.92rem;
        }}

        section.main .st-key-reader_toolbar [data-testid="stSegmentedControl"] {{
            width: fit-content;
            margin-left: auto;
        }}

        section.main .st-key-reader_toolbar [data-testid="stSegmentedControl"] [role="radiogroup"] {{
            flex-wrap: nowrap !important;
            white-space: nowrap;
            gap: 0.15rem;
        }}

        section.main .st-key-reader_toolbar [data-testid="stSegmentedControl"] label {{
            min-width: 1.65rem;
            padding-left: 0.28rem;
            padding-right: 0.28rem;
        }}

        [data-testid="stButton"] > button:disabled {{
            opacity: 0.4;
            border-color: #cbb79f;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


@lru_cache(maxsize=256)
def _read_mp4_duration_seconds(video_path: str) -> float | None:
    """Return MP4 duration in seconds from `mvhd`, or None when unavailable."""
    path = Path(video_path)
    try:
        with path.open("rb") as file:
            file_size = path.stat().st_size
            moov_bounds = _find_mp4_box(file, file_size, b"moov")
            if moov_bounds is None:
                return None

            moov_start, moov_end = moov_bounds
            file.seek(moov_start)
            mvhd_bounds = _find_mp4_box(file, moov_end, b"mvhd")
            if mvhd_bounds is None:
                return None

            mvhd_start, _ = mvhd_bounds
            file.seek(mvhd_start)
            version_byte = file.read(1)
            if len(version_byte) != 1:
                return None
            version = version_byte[0]
            file.read(3)  # flags

            if version == 1:
                file.read(8)  # creation time
                file.read(8)  # modification time
                timescale_bytes = file.read(4)
                duration_bytes = file.read(8)
                if len(timescale_bytes) != 4 or len(duration_bytes) != 8:
                    return None
                timescale = struct.unpack(">I", timescale_bytes)[0]
                duration = struct.unpack(">Q", duration_bytes)[0]
            else:
                file.read(4)  # creation time
                file.read(4)  # modification time
                timescale_bytes = file.read(4)
                duration_bytes = file.read(4)
                if len(timescale_bytes) != 4 or len(duration_bytes) != 4:
                    return None
                timescale = struct.unpack(">I", timescale_bytes)[0]
                duration = struct.unpack(">I", duration_bytes)[0]

            if timescale <= 0:
                return None
            return duration / timescale
    except OSError:
        return None


def _find_mp4_box(
    file_obj, container_end: int, target_box_type: bytes
) -> tuple[int, int] | None:
    for box_type, payload_start, payload_end in _iter_mp4_boxes(file_obj, container_end):
        if box_type == target_box_type:
            return payload_start, payload_end

    return None


def _iter_mp4_boxes(file_obj, container_end: int):
    while file_obj.tell() < container_end:
        box_start = file_obj.tell()
        header = file_obj.read(8)
        if len(header) < 8:
            return

        box_size, box_type = struct.unpack(">I4s", header)
        header_size = 8

        if box_size == 1:
            extended = file_obj.read(8)
            if len(extended) < 8:
                return
            box_size = struct.unpack(">Q", extended)[0]
            header_size = 16
        elif box_size == 0:
            box_size = container_end - box_start

        if box_size < header_size:
            return

        payload_start = box_start + header_size
        payload_end = box_start + box_size
        if payload_end > container_end:
            return

        yield box_type, payload_start, payload_end
        file_obj.seek(payload_end)


@lru_cache(maxsize=256)
def _read_mp4_video_dimensions(video_path: str) -> tuple[int, int] | None:
    """Return MP4 video dimensions as `(width, height)` when available."""
    path = Path(video_path)
    try:
        with path.open("rb") as file:
            file_size = path.stat().st_size
            moov_bounds = _find_mp4_box(file, file_size, b"moov")
            if moov_bounds is None:
                return None

            moov_start, moov_end = moov_bounds
            file.seek(moov_start)
            for box_type, trak_start, trak_end in _iter_mp4_boxes(file, moov_end):
                if box_type != b"trak":
                    continue
                if not _is_video_trak(file, trak_start, trak_end):
                    continue
                dimensions = _read_trak_dimensions(file, trak_start, trak_end)
                if dimensions is not None:
                    return dimensions
    except OSError:
        return None

    return None


def _is_video_trak(file_obj, trak_start: int, trak_end: int) -> bool:
    file_obj.seek(trak_start)
    for box_type, mdia_start, mdia_end in _iter_mp4_boxes(file_obj, trak_end):
        if box_type != b"mdia":
            continue
        file_obj.seek(mdia_start)
        hdlr_bounds = _find_mp4_box(file_obj, mdia_end, b"hdlr")
        if hdlr_bounds is None:
            return False
        hdlr_start, _ = hdlr_bounds
        file_obj.seek(hdlr_start)
        header = file_obj.read(12)
        if len(header) < 12:
            return False
        handler_type = header[8:12]
        return handler_type == b"vide"
    return False


def _read_trak_dimensions(file_obj, trak_start: int, trak_end: int) -> tuple[int, int] | None:
    file_obj.seek(trak_start)
    tkhd_bounds = _find_mp4_box(file_obj, trak_end, b"tkhd")
    if tkhd_bounds is None:
        return None

    tkhd_start, tkhd_end = tkhd_bounds
    file_obj.seek(tkhd_start)
    payload = file_obj.read(tkhd_end - tkhd_start)
    if len(payload) < 8:
        return None

    width_fixed, height_fixed = struct.unpack(">II", payload[-8:])
    width = int(round(width_fixed / 65536))
    height = int(round(height_fixed / 65536))
    if width <= 0 or height <= 0:
        return None
    return width, height


@lru_cache(maxsize=256)
def _read_image_dimensions(image_path: str) -> tuple[int, int] | None:
    path = Path(image_path)
    try:
        with Image.open(path) as image:
            width, height = image.size
            if width <= 0 or height <= 0:
                return None
            return width, height
    except (OSError, UnidentifiedImageError):
        return None


def _page_media_dimensions(page: Page) -> tuple[int, int] | None:
    if page.video_path is not None and page.video_path.exists():
        return _read_mp4_video_dimensions(str(page.video_path.resolve()))
    if page.image_path is not None and page.image_path.exists():
        return _read_image_dimensions(str(page.image_path.resolve()))
    return None


def _infer_frame_width(page: Page | None) -> int | str:
    if page is None:
        return "stretch"

    dimensions = _page_media_dimensions(page)
    if dimensions is None:
        return "stretch"

    media_width, _ = dimensions
    inferred = media_width + FRAME_CHROME_WIDTH_PX
    return max(MIN_FRAME_WIDTH_PX, min(MAX_FRAME_WIDTH_PX, inferred))


def _autoplay_seconds_for_item(
    item_kind: str,
    page: Page | None,
    non_video_delay_seconds: int,
) -> float:
    if item_kind == "page" and page is not None and page.video_path is not None:
        if page.video_path.exists():
            duration = _read_mp4_duration_seconds(str(page.video_path.resolve()))
            if duration is not None and duration > 0:
                return max(1.0, duration + 0.25)
    return float(non_video_delay_seconds)


@st.fragment(run_every="1s")
def _autoplay_tick(
    enabled: bool,
    current_index: int,
    max_index: int,
    wait_seconds: float,
) -> None:
    if not enabled or max_index <= 0:
        return

    now = time.monotonic()
    anchor_index = st.session_state.get("autoplay_anchor_index")
    if anchor_index != current_index:
        st.session_state.autoplay_anchor_index = current_index
        st.session_state.autoplay_started_at = now
        return

    started_at = st.session_state.get("autoplay_started_at", now)
    elapsed_seconds = now - started_at

    if elapsed_seconds >= wait_seconds and current_index < max_index:
        st.session_state.current_item_index = current_index + 1
        st.session_state.autoplay_anchor_index = current_index + 1
        st.session_state.autoplay_started_at = now
        st.rerun()


def _render_page_media(page: Page, playback_mode: str) -> None:
    dimensions = _page_media_dimensions(page)
    media_width = dimensions[0] if dimensions is not None else None

    if page.video_path is not None:
        if not page.video_path.exists():
            st.warning(f"Video file missing: {page.video_path}")
            return
        is_auto = playback_mode == "auto"
        is_loop = playback_mode == "loop"
        st.video(
            str(page.video_path),
            format="video/mp4",
            autoplay=is_auto or is_loop,
            loop=is_loop,
            width=media_width if media_width is not None else "stretch",
        )
        return

    if page.image_path is not None:
        if not page.image_path.exists():
            st.warning(f"Image file missing: {page.image_path}")
            return
        st.image(str(page.image_path), width=media_width if media_width is not None else "content")
        return

    st.warning("This page has no image or video.")


def _render_page_text(page: Page, show_empty_warning: bool = True) -> None:
    if page.text_path is None:
        if show_empty_warning:
            st.warning("This page has no text.")
        return

    text, text_warnings = read_page_text(page)
    for warning in text_warnings:
        st.warning(warning)

    if not text:
        if show_empty_warning:
            st.warning("Text file is empty or unreadable.")
        return

    if page.text_path.suffix.lower() == ".txt":
        text = text.replace("\n", "  \n")

    st.markdown(text)


def _caption_text_from_page(
    page: Page,
    *,
    missing_text_warning: str,
    show_empty_warning: bool,
) -> str | None:
    """Return cleaned caption text for overlay rendering."""
    if page.text_path is None:
        if show_empty_warning:
            st.warning(missing_text_warning)
        return None

    text, text_warnings = read_page_text(page)
    for warning in text_warnings:
        st.warning(warning)

    if not text.strip():
        if show_empty_warning:
            st.warning("Text file is empty or unreadable.")
        return None

    cleaned_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        while line.startswith("#"):
            line = line[1:].lstrip()
        for marker in ("**", "__", "`", "*", "_"):
            line = line.replace(marker, "")
        cleaned_lines.append(line)

    caption_text = "\n".join(cleaned_lines).strip()
    if not caption_text:
        if show_empty_warning:
            st.warning("Text file is empty or unreadable.")
        return None
    return caption_text


def _render_caption_overlay(
    caption_text: str,
    *,
    wrap_class: str,
    caption_class: str,
) -> None:
    safe_caption = html.escape(caption_text).replace("\n", "<br>")
    st.markdown(
        (
            f'<div class="{wrap_class}">'
            f'<div class="{caption_class}">{safe_caption}</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _render_video_caption(page: Page, show_empty_warning: bool = True) -> None:
    """Render colorful, comic-style caption text over the lower part of video pages."""
    caption_text = _caption_text_from_page(
        page,
        missing_text_warning="This video page has no text.",
        show_empty_warning=show_empty_warning,
    )
    if caption_text is None:
        return

    _render_caption_overlay(
        caption_text,
        wrap_class="storybook-video-caption-wrap",
        caption_class="storybook-video-caption",
    )


def _render_image_caption(page: Page, show_empty_warning: bool = True) -> None:
    """Render caption text inside the lower part of image pages."""
    caption_text = _caption_text_from_page(
        page,
        missing_text_warning="This image page has no text.",
        show_empty_warning=show_empty_warning,
    )
    if caption_text is None:
        return

    _render_caption_overlay(
        caption_text,
        wrap_class="storybook-image-caption-wrap",
        caption_class="storybook-image-caption",
    )


def _reader_items(book: Book) -> list[tuple[str, Page | None]]:
    items: list[tuple[str, Page | None]] = []
    if book.metadata.cover_image_path is not None:
        items.append(("cover", None))
    for page in book.pages:
        items.append(("page", page))
    return items


def _item_label(index: int, items: list[tuple[str, Page | None]], total_pages: int) -> str:
    item_kind, page = items[index]
    if item_kind == "cover":
        return "Cover"

    if page is None:
        return f"Page {index + 1}"

    page_number = _page_number(index, items)
    return f"Page {page_number}/{total_pages}: {page.page_id}"


def _page_number(index: int, items: list[tuple[str, Page | None]]) -> int:
    has_cover = bool(items and items[0][0] == "cover")
    return index if has_cover else index + 1


def _render_cover(book: Book) -> None:
    with st.container(
        border=True,
        key="reader_cover",
        width="stretch",
        horizontal_alignment="center",
    ):
        st.subheader("Cover")
        cover_path = book.metadata.cover_image_path
        if cover_path is None or not cover_path.exists():
            st.warning("Cover image is configured but missing.")
            return

        cover_dimensions = _read_image_dimensions(str(cover_path.resolve()))
        cover_width = cover_dimensions[0] if cover_dimensions is not None else "content"
        st.image(str(cover_path), width=cover_width)
        st.markdown(f"### {book.metadata.title}")
        if book.metadata.author:
            st.markdown(f"**Author:** {book.metadata.author}")
        if book.metadata.description:
            st.markdown(book.metadata.description)


def _render_page(
    page: Page,
    side_by_side: bool,
    playback_mode: str,
) -> None:
    with st.container(
        border=True,
        width="stretch",
        key="reader_page",
        horizontal_alignment="center",
    ):
        if page.video_path is not None and not side_by_side:
            _render_page_media(page, playback_mode=playback_mode)
            _render_video_caption(page, show_empty_warning=False)
            return

        if side_by_side:
            image_col, text_col = st.columns(2)
            with image_col:
                _render_page_media(page, playback_mode=playback_mode)
            with text_col:
                _render_page_text(page, show_empty_warning=False)
            return

        _render_page_media(page, playback_mode=playback_mode)
        if page.image_path is not None and page.image_path.exists():
            _render_image_caption(page, show_empty_warning=False)


def main() -> None:
    sample_paths = list_sample_books("Books")
    sample_names = [path.name for path in sample_paths]

    if "sample_book_name" not in st.session_state:
        default_sample = (
            DEFAULT_SAMPLE_BOOK
            if DEFAULT_SAMPLE_BOOK in sample_names
            else (sample_names[0] if sample_names else "")
        )
        st.session_state.sample_book_name = default_sample
    if "current_item_index" not in st.session_state:
        st.session_state.current_item_index = 0
    if "active_book_key" not in st.session_state:
        st.session_state.active_book_key = ""
    if "autoplay_anchor_index" not in st.session_state:
        st.session_state.autoplay_anchor_index = 0
    if "autoplay_started_at" not in st.session_state:
        st.session_state.autoplay_started_at = time.monotonic()
    if "playback_mode_prev" not in st.session_state:
        st.session_state.playback_mode_prev = "off"
    if "playback_mode" not in st.session_state:
        st.session_state.playback_mode = "off"

    with st.sidebar:
        st.header("Book")
        if sample_names:
            st.selectbox("Sample books", options=sample_names, key="sample_book_name")
        else:
            st.info("No sample books found under Books/.")

    selected_book_path = _current_book_path(
        sample_paths=sample_paths,
        selected_sample_name=st.session_state.sample_book_name,
    )

    if selected_book_path is None:
        st.info("Select a sample book in the sidebar.")
        return

    book = load_book(selected_book_path)

    book_key = str(book.root_path.resolve()) if book.root_path.exists() else str(book.root_path)
    if st.session_state.active_book_key != book_key:
        st.session_state.active_book_key = book_key
        st.session_state.current_item_index = 0

    items = _reader_items(book)
    if not items:
        st.warning("No readable pages were found for this book.")

    max_index = max(len(items) - 1, 0)
    current_index = min(st.session_state.current_item_index, max_index)
    st.session_state.current_item_index = current_index

    with st.sidebar:
        st.header("Reader")
        side_by_side = st.checkbox("Side-by-side media and text", value=False)
        font_size = st.slider("Text size", min_value=12, max_value=40, value=18, step=1)

        if items:
            picker_options = list(range(len(items)))
            picked_index = st.selectbox(
                "Page picker",
                options=picker_options,
                index=current_index,
                format_func=lambda i: _item_label(i, items, len(book.pages)),
            )
            st.session_state.current_item_index = picked_index

        if book.warnings:
            with st.expander("Loader warnings", expanded=False):
                for warning in book.warnings:
                    st.warning(warning)

    has_video_pages = any(page.video_path is not None for page in book.pages)

    current_item_kind = ""
    current_item_page: Page | None = None
    if items:
        current_item_kind, current_item_page = items[st.session_state.current_item_index]

    page_frame_width: int | str = "stretch"
    if current_item_kind == "page" and not side_by_side:
        page_frame_width = _infer_frame_width(current_item_page)
    elif current_item_kind == "cover" and book.metadata.cover_image_path is not None:
        cover_dimensions = _read_image_dimensions(str(book.metadata.cover_image_path.resolve()))
        if cover_dimensions is not None:
            page_frame_width = max(
                MIN_FRAME_WIDTH_PX,
                min(MAX_FRAME_WIDTH_PX, cover_dimensions[0] + FRAME_CHROME_WIDTH_PX),
            )

    stage_width_px = page_frame_width if isinstance(page_frame_width, int) else DEFAULT_STAGE_WIDTH_PX
    _inject_text_size_css(font_size, stage_width_px=stage_width_px)

    with st.container(
        border=True,
        width="stretch",
        key="reader_toolbar",
        horizontal_alignment="center",
    ):
        nav_first, nav_prev, nav_meta, nav_next, nav_last = st.columns(
            [0.55, 0.55, 6.4, 0.55, 0.55],
            gap="small",
        )

        at_first = st.session_state.current_item_index <= 0
        at_last = st.session_state.current_item_index >= max_index

        playback_mode = "off"
        current_kind = ""
        current_page_for_autoplay: Page | None = None

        with nav_first:
            if st.button("«", width="stretch", disabled=at_first, help="First page"):
                st.session_state.current_item_index = 0
                st.rerun()
        with nav_prev:
            if st.button("‹", width="stretch", disabled=at_first, help="Previous page"):
                st.session_state.current_item_index = max(
                    0, st.session_state.current_item_index - 1
                )
                st.rerun()
        with nav_meta:
            if items:
                current_kind, current_page_for_autoplay = items[
                    st.session_state.current_item_index
                ]
                if has_video_pages:
                    meta_col, autoplay_col = st.columns([2.7, 1.3], gap="small")
                    with meta_col:
                        if current_kind == "cover":
                            st.markdown(
                                '<div class="storybook-nav-meta">Cover • '
                                f"{len(book.pages)} pages</div>",
                                unsafe_allow_html=True,
                            )
                        else:
                            current_page_number = _page_number(st.session_state.current_item_index, items)
                            st.markdown(
                                '<div class="storybook-nav-meta">Page '
                                f"{current_page_number} of {len(book.pages)}</div>",
                                unsafe_allow_html=True,
                            )

                    with autoplay_col:
                        selected_mode = st.segmented_control(
                            "Playback Mode",
                            options=["off", "auto", "loop"],
                            key="playback_mode",
                            format_func=lambda mode: {
                                "off": "⏹",
                                "auto": "▶",
                                "loop": "↻",
                            }[mode],
                            help="⏹ Off, ▶ Auto-next, ↻ Loop current video",
                            label_visibility="collapsed",
                            width="content",
                        )
                    playback_mode = selected_mode or "off"
                else:
                    if current_kind == "cover":
                        st.markdown(
                            '<div class="storybook-nav-meta">Cover • '
                            f"{len(book.pages)} pages</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        current_page_number = _page_number(st.session_state.current_item_index, items)
                        st.markdown(
                            '<div class="storybook-nav-meta">Page '
                            f"{current_page_number} of {len(book.pages)}</div>",
                            unsafe_allow_html=True,
                        )
                    st.session_state.playback_mode = "off"
                    playback_mode = "off"

                if st.session_state.playback_mode_prev != playback_mode:
                    st.session_state.playback_mode_prev = playback_mode
                    st.session_state.autoplay_anchor_index = st.session_state.current_item_index
                    st.session_state.autoplay_started_at = time.monotonic()

                autoplay_wait_seconds = _autoplay_seconds_for_item(
                    item_kind=current_kind,
                    page=current_page_for_autoplay,
                    non_video_delay_seconds=AUTOPLAY_NON_VIDEO_DELAY_SECONDS,
                )
                _autoplay_tick(
                    enabled=(playback_mode == "auto"),
                    current_index=st.session_state.current_item_index,
                    max_index=max_index,
                    wait_seconds=autoplay_wait_seconds,
                )
        with nav_next:
            if st.button("›", width="stretch", disabled=at_last, help="Next page"):
                st.session_state.current_item_index = min(
                    max_index, st.session_state.current_item_index + 1
                )
                st.rerun()
        with nav_last:
            if st.button("»", width="stretch", disabled=at_last, help="Last page"):
                st.session_state.current_item_index = max_index
                st.rerun()

    if not items:
        return

    current_kind, current_page = items[st.session_state.current_item_index]
    if current_kind == "cover":
        _render_cover(book)
    elif current_page is not None:
        _render_page(
            current_page,
            side_by_side=side_by_side,
            playback_mode=playback_mode,
        )


if __name__ == "__main__":
    main()

"""Tests for storybook loader behavior."""

from __future__ import annotations

from pathlib import Path

from storybook_loader import list_sample_books, load_book, read_page_text


def _touch(path: Path, content: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_load_book_flat_format_pairs_files_and_sorts(tmp_path: Path) -> None:
    book = tmp_path / "flat_book"
    book.mkdir()

    _touch(book / "010.png")
    _write_text(book / "010.md", "Ten")
    _touch(book / "002.jpg")
    _write_text(book / "002.txt", "Two")
    _touch(book / "001.webp")
    _write_text(book / "001.md", "One")

    loaded = load_book(book)

    assert [page.page_id for page in loaded.pages] == ["001", "002", "010"]
    assert loaded.pages[0].image_path and loaded.pages[0].image_path.name == "001.webp"
    assert loaded.pages[1].text_path and loaded.pages[1].text_path.name == "002.txt"
    assert loaded.warnings == []


def test_load_book_flat_format_supports_mp4_video(tmp_path: Path) -> None:
    book = tmp_path / "flat_video_book"
    book.mkdir()

    _touch(book / "001.mp4")
    _write_text(book / "001.txt", "Video page text")

    loaded = load_book(book)

    assert [page.page_id for page in loaded.pages] == ["001"]
    assert loaded.pages[0].video_path and loaded.pages[0].video_path.name == "001.mp4"
    assert loaded.pages[0].image_path is None


def test_load_book_nested_format_and_manifest_order(tmp_path: Path) -> None:
    book = tmp_path / "nested_book"
    pages = book / "pages"
    pages.mkdir(parents=True)

    _touch(book / "cover.png")
    _touch(pages / "001" / "image.png")
    _write_text(pages / "001" / "text.md", "One")
    _touch(pages / "002" / "image.jpg")
    _write_text(pages / "002" / "text.txt", "Two")

    _write_text(
        book / "manifest.json",
        """
        {
          "title": "Nested Demo",
          "author": "Alice",
          "description": "Book description",
          "cover_image": "cover.png",
          "page_order": ["002", "001"]
        }
        """,
    )

    loaded = load_book(book)

    assert loaded.metadata.title == "Nested Demo"
    assert loaded.metadata.author == "Alice"
    assert loaded.metadata.cover_image_path == book / "cover.png"
    assert [page.page_id for page in loaded.pages] == ["002", "001"]


def test_load_book_nested_format_supports_mp4_video(tmp_path: Path) -> None:
    book = tmp_path / "nested_video_book"
    pages = book / "pages"
    pages.mkdir(parents=True)

    _touch(pages / "001" / "video.mp4")
    _write_text(pages / "001" / "text.md", "Video page")

    loaded = load_book(book)

    assert [page.page_id for page in loaded.pages] == ["001"]
    assert loaded.pages[0].video_path and loaded.pages[0].video_path.name == "video.mp4"
    assert loaded.pages[0].image_path is None


def test_manifest_page_order_accepts_mp4_filename_entries(tmp_path: Path) -> None:
    book = tmp_path / "manifest_video_order_book"
    book.mkdir()

    _touch(book / "001.mp4")
    _write_text(book / "001.txt", "One")
    _touch(book / "002.png")
    _write_text(book / "002.md", "Two")

    _write_text(
        book / "manifest.json",
        """
        {
          "title": "Video Order",
          "page_order": ["002.png", "001.mp4"]
        }
        """,
    )

    loaded = load_book(book)

    assert [page.page_id for page in loaded.pages] == ["002", "001"]


def test_manifest_cover_image_not_named_cover_is_not_treated_as_page(
    tmp_path: Path,
) -> None:
    book = tmp_path / "cover_id_book"
    book.mkdir()

    _touch(book / "000.video.png")
    _touch(book / "001.png")
    _write_text(book / "001.md", "Page one")
    _write_text(
        book / "manifest.json",
        """
        {
          "title": "Custom Cover",
          "cover_image": "000.video.png",
          "page_order": ["001"]
        }
        """,
    )

    loaded = load_book(book)

    assert loaded.metadata.cover_image_path == book / "000.video.png"
    assert [page.page_id for page in loaded.pages] == ["001"]


def test_load_book_handles_invalid_manifest_without_crashing(tmp_path: Path) -> None:
    book = tmp_path / "bad_manifest"
    book.mkdir()

    _touch(book / "001.png")
    _write_text(book / "manifest.json", "{ this is not valid json")

    loaded = load_book(book)

    assert len(loaded.pages) == 1
    assert any("manifest.json" in warning for warning in loaded.warnings)


def test_load_book_non_directory_returns_warning(tmp_path: Path) -> None:
    loaded = load_book(tmp_path / "missing_folder")

    assert loaded.pages == []
    assert any("not a directory" in warning for warning in loaded.warnings)


def test_read_page_text_missing_file_returns_warning(tmp_path: Path) -> None:
    book = tmp_path / "book"
    book.mkdir()
    _touch(book / "001.png")

    loaded = load_book(book)
    text, warnings = read_page_text(loaded.pages[0])

    assert text == ""
    assert warnings == []


def test_list_sample_books_sorts_naturally(tmp_path: Path) -> None:
    sample_root = tmp_path / "sample_books"
    (sample_root / "book10").mkdir(parents=True)
    (sample_root / "book2").mkdir(parents=True)
    (sample_root / "book1").mkdir(parents=True)

    books = list_sample_books(sample_root)

    assert [book.name for book in books] == ["book1", "book2", "book10"]

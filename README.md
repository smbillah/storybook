# Storybook Reader (Local Streamlit Prototype)

Small local-only Streamlit app for reading storybook/e-book folders from disk.

## What it supports

- Two book-loading paths:
  - Choose from subfolders in `sample_books/` (defaults to `dino_storybook`).
- Two book folder formats:
  - Format A (flat): `001.png` + `001.md` at the book root.
  - Format B (nested): `pages/001/001.png` + `pages/001/text.md`.
- File types:
  - Images: `.png`, `.jpg`, `.jpeg`, `.webp`
  - Videos: `.mp4`
  - Text: `.txt`, `.md`
- Optional `manifest.json` fields:
  - `title`, `author`, `description`, `cover_image`, `page_order`
- Reader features:
  - Wide layout, sidebar controls, page picker
  - `First` / `Previous` / `Next` / `Last` navigation
  - Icon split control for playback mode on video books: `⏹` Off, `▶` Auto-next, `↻` Loop current video (Auto and Loop are mutually exclusive)
  - Default media-above-text layout (video preferred over image when both exist)
  - Optional side-by-side media and text layout
  - Adjustable text size
  - Current page persisted in `st.session_state`
  - Graceful warnings for malformed/missing content
  - Optional captions: missing `id.md` is allowed (useful when text is already embedded in images)
- Cover view if a cover image exists.

## Sample data

A runnable sample exists at:

- `sample_books/dino_storybook/`
- `sample_books/dino_video_storybook/`
- `sample_books/squirrel_book/`

All current sample books are flat (`id.extension`), with optional `id.md` caption files.

### Add your MP4 files

You can use either of these conventions:

1. Flat format (`sample_books/dino_video_storybook/`):
   - `001.mp4`
   - `002.mp4`
   - `003.mp4`
   - `004.mp4`
2. Nested format (still supported by the loader):
   - `001/001.mp4`
   - `002/002.mp4`
   - `003/003.mp4`
   - `004/004.mp4`

## Design choices (simple and robust)

- Loader is in `storybook_loader.py` and is separate from UI logic.
- Loader returns warnings instead of raising errors for malformed books.
- If `manifest.json` exists, it is used for metadata and optional `page_order`.
- If no `manifest.json` or no valid `page_order`, page order is inferred by natural sorting (`1, 2, 10`).
- If `page_order` is partial, listed pages come first and remaining discovered pages are appended.
- Missing media files are handled with warnings; missing caption files are allowed.
- If `manifest.json` does not set `cover_image`, the loader tries common names like `cover.*`.

## Run locally

1. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the app:

```bash
streamlit run app.py
```

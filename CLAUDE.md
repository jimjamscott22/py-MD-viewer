# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies (creates .venv automatically)
uv sync

# Search Files
rg <query>

# Install with dev extras (pytest)
uv sync --extra dev

# Run the server (serves markdown from current directory)
uv run md-preview

# Run the desktop app (needs the desktop extra: uv sync --extra desktop)
uv run md-viewer [PATH]

# Build the Linux AppImage (PyInstaller + appimagetool; --bundle stops after PyInstaller)
scripts/build-appimage.sh

# Run all tests (desktop tests need --extra desktop; they're skipped otherwise)
uv run pytest

# Run a specific test file
uv run pytest tests/test_app.py -v

# Add a dependency
uv add <package>

# Add a dev-only dependency
uv add --optional dev <package>
```

All package operations use `uv`, not `pip` directly. Never run `pip install` manually.

## Architecture

This is a local Flask server (`src/md_preview_server/`) that renders `.md` files from a chosen directory, with live reload via Server-Sent Events.

**Core modules:**
- `app.py` — Flask app factory (`create_app(base_dir)`) containing all routes and the `main()` CLI entrypoint. Routes are organized into phases (file listing, upload/create, rename/delete, directory picker, editor, export).
- `renderer.py` — Converts markdown to HTML using `python-markdown` with extensions: `fenced_code`, `codehilite`, `tables`, `toc`, `sane_lists`, `smarty`. Provides both `render_markdown(text)` (uncached, for live preview) and `render_markdown_cached(filepath)` (keyed by path+mtime, max 200 entries).
- `watcher.py` — Watchdog-based directory watcher with 0.5s debounce. Calls `notify_clients()` in `app.py` when `.md` files change.

**Live reload flow:** Browser connects to `/events` (SSE). `watcher.py` detects file changes → calls `notify_clients()` in `app.py` → pushes JSON events to all subscriber queues → browsers auto-reload.

**Caching:** Two independent caches exist:
1. File tree/list cache (`_file_cache` in `app.py`) — invalidated by `notify_clients()` on any file change.
2. Render cache (`_render_cache` in `renderer.py`) — keyed by `(filepath, mtime)`, evicts oldest half when full.

**Security:** All user-supplied file paths go through `validate_path(base_dir, rel_path)` in `app.py`, which resolves and checks `is_relative_to(base_dir)` to prevent path traversal. The server only accepts `.md` files for all write operations.

**Desktop app (`src/md_viewer_desktop/`):** PyQt6 shell over `md_preview_core`, roadmap in `docs/desktop-pyqt6-plan.md`. Documents are served through a custom `mdview://` URL scheme (`document_view.py`): `mdview://doc/<relpath>` renders `.md` files or serves sibling assets (always via `validate_path`), and `mdview://app/<path>` serves bundled CSS/fonts/vendored JS. `style.css`/`codehilite.css` are shared with the Flask app, not copied. `theme.py` generates the document CSS (`resources/css/theme-jamielab.css`, regenerate with `uv run python -m md_viewer_desktop.theme`), QSS and `QPalette` from `resources/design/jamielab.tokens.json`. Don't hand-type hex values. `watcher_bridge.py` turns watchdog callbacks into a Qt signal. Each tab keeps the root folder it was opened from and is served under its own `mdview://doc-<key>/` host (`SchemeHandler.add_root`), so tabs from different folders coexist; `main_window.py` runs one watcher per root in use. Other modules: `single_instance.py` (`QLocalServer` handoff so a second `md-viewer foo.md` opens a tab in the running window), `desktop_integration.py` (`--install-desktop`: `.desktop` entry from `linux/`, icon, MIME, `xdg-mime default`; uses `$APPIMAGE` as the launcher inside an AppImage), `editor.py` (Ctrl+E split editor: per-tab `MarkdownEditor`, unsaved text served to the preview through `SchemeHandler.overrides`, saves guarded by the storage revision), `toc_panel.py`, `find_bar.py`, `icons.py` (vendored Lucide SVGs recoloured from tokens). `theme.py` also generates the jamielab Pygments CSS (inside `theme-jamielab.css`) and the app icon `resources/icons/md-viewer.svg`. Connect page/watcher signals to bound methods, not lambdas, so they die with the window.

**Frontend:** Static JS in `static/js/` — `live-reload.js` (SSE client), `editor.js` (CodeMirror-based in-browser editor), `navigation.js`, `file-operations.js`, `directory-picker.js`. Templates in `templates/` use Jinja2 with `base.html` as the layout.

**REST API surface:**
- `GET /api/files` — file tree + flat list with metadata
- `GET /api/search?q=` — filename/path search
- `GET /api/search/content?q=` — full-text content search; returns `{path, line_number, snippet}` results (max 50, `truncated` flag); requires `len(q) >= 2`
- `POST /api/upload`, `POST /api/create` — add files
- `PUT /api/rename`, `DELETE /api/delete` — mutate files
- `GET /api/directories`, `POST /api/set-base-directory` — change watched directory at runtime
- `GET /api/content/<path>`, `PUT /api/save`, `POST /api/preview` — editor support
- `GET /api/export/html/<path>` — standalone HTML export with inlined CSS

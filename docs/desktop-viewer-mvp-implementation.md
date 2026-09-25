# Desktop Viewer MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Launch a fully offline Ubuntu desktop viewer for Markdown files and folders, with live reload and the jamielab theme.

**Architecture:** Qt widgets own the window, menus, and file tree. QWebEngine renders Markdown through a registered `mdview` URL scheme. A scheme handler reads only validated documents and local bundled assets; a QObject signal bridges watchdog events to the GUI thread.

**Tech Stack:** Python 3.10+, PyQt6, PyQt6-WebEngine, pytest-qt, watchdog, uv.

**Spec:** `docs/desktop-pyqt6-plan.md` §§3–5, especially Phase 2 and §4.6.

## Global Constraints

- Keep `md-preview` and Flask intact; add Qt as an optional `desktop` extra.
- Register the `mdview` scheme before creating `QApplication`.
- Runtime must not use a local HTTP server, CDN, or asset download.
- Generate jamielab CSS, QSS, and palette values from `docs/design/jamielab.tokens.json`. Use IBM Plex Mono throughout jamielab.
- Keep the app theme menu, with jamielab default and Paper as a light option. Do not automatically override the selection with the system theme.
- Document routes accept only `.md`; asset routes remain inside the selected folder; app routes remain inside packaged resources.
- Watchdog threads emit signals; GUI changes happen on the main thread.
- Tabs, editing, AI, and desktop registration belong to later phases.

## Review Focus

- `..` paths and symlinks escaping the folder are denied: Task 3 test.
- Missing files and non-Markdown document URLs produce controlled errors: Task 3 test.
- Nested documents resolve nearby images: Task 3 test.
- External changes and deletion update the active view safely: Task 5 test.
- Launch with an invalid or absent path leaves a usable window or a clear error: Tasks 1 and 4 tests.

---

### Task 1: Launch contract and packaging

**Files:** `pyproject.toml`, `uv.lock`, `src/md_viewer_desktop/{__init__,__main__,main}.py`, `tests/test_desktop_main.py`.

**Interfaces:** `resolve_launch_target(raw: str | None) -> tuple[Path, Path | None]` returns `(base_dir, initial_file)`; `main(argv: list[str] | None = None) -> int`. A file uses its parent as base, a directory has no initial file, and no argument uses the current directory.

- [ ] Test file, folder, no argument, and missing path; missing path raises `FileNotFoundError`.
- [ ] Run the focused test and confirm failure because the desktop module is absent.
- [ ] Add optional `desktop` dependencies, `pytest-qt` to `dev`, and package resources. Implement launch resolution. Add the `md-viewer`/`md-viewer-gui` entry points and scheme registration when Task 4 makes the window runnable.
- [ ] Run focused and full tests; commit.

### Task 2: Theme generation

**Files:** `src/md_viewer_desktop/theme.py`, `src/md_viewer_desktop/resources/design/jamielab.tokens.json`, generated `resources/css/theme-jamielab.css`, `tests/test_desktop_theme.py`.

**Interfaces:** `load_theme(path: Path) -> Theme`, `css_variables(theme: Theme) -> str`, `qss(theme: Theme) -> str`, `palette(theme: Theme) -> QPalette`, `apply(app: QApplication, theme: Theme) -> None` as specified in §4.6.

- [ ] Test missing token rejection, Plex Mono prose CSS, palette roles, complete QSS substitution, and generated CSS matching the bundled file.
- [ ] Run focused tests; confirm failure for missing theme code.
- [ ] Implement token parsing and generators; bundle the pinned Plex Mono TTF/WOFF2 files and license here, then apply Fusion, palette, QSS, and the font after QApplication creation.
- [ ] Run focused and full tests; commit.

### Task 3: Safe offline document rendering

**Files:** `src/md_viewer_desktop/document_view.py`, `resources/page_template.html`, packaged document CSS, `tests/test_desktop_document_view.py`.

**Interfaces:** `register_scheme() -> None`; `DocumentSchemeHandler(base_dir: Path, resources_dir: Path, parent: QObject | None = None)`; `resolve_request(url: QUrl) -> tuple[bytes, bytes]` returns MIME type and body. `requestStarted(job)` uses that resolver and retains its QBuffer until WebEngine finishes reading.

- [ ] Test nested Markdown rendering, nearby images, packaged CSS, traversal, escaping symlinks, unknown hosts, missing files, and non-`.md` document paths.
- [ ] Run focused tests; confirm expected failures.
- [ ] Implement `doc`, `asset`, and `app` routing using `md_preview_core.render_markdown_cached` and `validate_path`; use bundled CSS, Mermaid, and KaTeX references in the HTML shell.
- [ ] Run focused and full tests; commit.

### Task 4: Window and navigation

**Files:** `src/md_viewer_desktop/{main_window,file_tree}.py`, `tests/test_desktop_window.py`; complete `main.py`.

**Interfaces:** `MainWindow(base_dir: Path, initial_file: Path | None, theme: Theme)`, `open_file(path: Path) -> None`, `set_base_dir(path: Path) -> None`. One QWebEngineView is the central widget for the MVP.

- [ ] Test initial file and tree selection, folder-only launch, invalid path status, and Open File/Folder handlers.
- [ ] Run focused tests; confirm expected failures.
- [ ] Add tree dock, menus, shortcuts, drag-and-drop, QSettings theme menu, entry points, and scheme registration before QApplication. Open Markdown links in the viewer, HTTP(S) links in the system browser, and deny other schemes.
- [ ] Run focused and full tests; commit.

### Task 5: Live reload

**Files:** `src/md_viewer_desktop/watcher_bridge.py`, `main_window.py`, `tests/test_desktop_watcher.py`.

**Interfaces:** `WatcherBridge(base_dir: Path)` emits `file_changed(str, str, object)` and exposes `start() -> None`, `stop() -> None`.

- [ ] Test signal delivery, active-file reload, tree changes, and deletion of the open file.
- [ ] Run focused tests; confirm expected failures.
- [ ] Connect shared watcher events to queued Qt signals, preserve scroll position on reload, and stop the observer on window close.
- [ ] Run focused and full tests; commit.

### Task 6: Bundled assets and offline verification

**Files:** `scripts/vendor_assets.py`, pinned Mermaid and KaTeX assets and licenses under `resources/`, `README.md`, `tests/test_desktop_assets.py`.

**Interfaces:** `scripts/vendor_assets.py` fetches pinned versions, including the Task 2 Plex Mono fonts, only when explicitly run by a developer. Runtime uses only `mdview://app/` assets.

- [ ] Test that every referenced script, stylesheet, and font is packaged and that HTML contains no CDN URL.
- [ ] Run focused tests; confirm expected failures.
- [ ] Vendor assets and licenses, initialize Mermaid and KaTeX from local files, and document `uv sync --extra desktop` and `uv run md-viewer README.md`.
- [ ] Run focused and full tests, then manually inspect rendering, tree, links, nested images, theme, and live reload with network disabled on Ubuntu; commit.

## Self-review and handoff

Tasks 1–6 cover the Phase 2 MVP. Phase 3 owns tabs, single instance, TOC, recent files, and desktop integration; Phase 4 owns editing. Do not claim offline rendering verified unless the network-disabled launch was actually checked.

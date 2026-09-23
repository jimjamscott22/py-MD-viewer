# Plan: PyQt6 Desktop App (Linux / Ubuntu first)

**Status:** Proposal — no code yet
**Goal:** A native-feeling Markdown viewer for Ubuntu that opens `.md` files from the file manager, renders them the same way the web app does (Pygments code highlighting, tables, TOC, Mermaid, KaTeX, frontmatter), live-reloads on disk changes, and keeps the editor. It should work fully offline.

---

## 1. Current state (what we're converting)

| Layer | Today | Reusable in Qt? |
|---|---|---|
| `renderer.py` | Markdown → HTML (python-markdown + pymdownx, frontmatter, Mermaid preprocessing, mtime-keyed cache) | **Yes, as-is.** Doesn't depend on Flask. |
| `storage.py` | Stable reads, revision tokens, atomic writes | **Yes, as-is.** |
| `watcher.py` | watchdog observer, 0.5 s debounce, callback `(event, path, revision)` | **Yes.** The callback runs on a watchdog thread, so it has to hand off to the Qt main thread through a signal. |
| `app.py` | Flask routes, plus file scanning, tree building, search, path validation, SSE fan-out | **Partly.** About 200 lines of non-Flask logic (`_iter_markdown_files`, `_scan_files`, `build_file_tree`, `_search_markdown_file`, `validate_path`) should move into a shared module. |
| `templates/` + `static/js/` | Sidebar, theme menu, CodeMirror editor, file ops, dir picker, SSE client | **Mostly replaced** by Qt widgets. We keep `style.css` and `codehilite.css` for the rendered document. |
| CDN assets | Mermaid 10, KaTeX 0.16 loaded from jsDelivr in `view.html` | **Must vendor locally** so the app works offline. |

## 2. Architecture options

### Option A: "Browser in a box" (thin wrapper)
Start the existing Flask app on a random localhost port in a background thread and point a `QWebEngineView` at it.
- ✅ About a day of work, and every feature keeps working.
- ❌ It still runs a web server with web UI inside a window. It won't feel native (no real menus or dialogs, and Ctrl+O doesn't work), and it opens a local port.
- Good as a **throwaway spike**. It's the wrong thing to ship as the final app.

### Option B: Native shell + web-rendered document (**recommended**)
Qt widgets handle all the app chrome. A single `QWebEngineView` shows only the rendered Markdown.
- ✅ Native file tree, tabs, menus, shortcuts, dialogs, and system theme.
- ✅ Rendering matches the web app exactly, because Mermaid, KaTeX and CSS still run in Chromium.
- ✅ No HTTP server. Content is served through a custom URL scheme handler (see §4.3).
- ❌ More work, roughly 2–4 weekends for full parity.

### Option C: Fully native (`QTextBrowser`)
- ❌ `QTextBrowser` only supports a subset of HTML4/CSS2.1, so there's no Mermaid, no KaTeX and weak CSS. It would look worse than what you have now.
- Rejected.

**Decision: Option B.** You can do Option A as a 1-hour spike first to confirm QtWebEngine works on your machine (GPU and Wayland quirks, see §6).

## 3. Proposed package layout

```
src/
  md_preview_core/          # NEW – shared, no Flask/Qt imports
    __init__.py
    renderer.py             # moved from md_preview_server
    storage.py              # moved
    watcher.py              # moved
    files.py                # scan/tree/search/validate_path extracted from app.py
  md_preview_server/        # existing Flask app, now imports from core
    app.py, templates/, static/
  md_viewer_desktop/        # NEW – PyQt6 app
    __init__.py
    __main__.py             # `python -m md_viewer_desktop`
    main.py                 # QApplication setup, arg parsing, single-instance
    main_window.py          # QMainWindow: menus, toolbar, docks, tabs
    file_tree.py            # QTreeView + QFileSystemModel filtered to *.md
    document_view.py        # QWebEngineView subclass + scheme handler
    editor.py               # QPlainTextEdit + QSyntaxHighlighter
    search_panel.py         # filename + full-text search dock
    watcher_bridge.py       # QObject that turns watchdog callbacks into signals
    settings.py             # QSettings wrapper (theme, recent files, geometry)
    resources/
      css/                  # symlink/copy of style.css, codehilite.css
      vendor/mermaid/       # vendored mermaid.min.js
      vendor/katex/         # vendored katex js/css/fonts
      page_template.html    # minimal HTML shell for rendered docs
      icons/md-viewer.svg
    linux/
      md-viewer.desktop
      md-viewer.xml         # optional MIME glue
```

`pyproject.toml` changes:
```toml
[project.optional-dependencies]
desktop = ["PyQt6>=6.7", "PyQt6-WebEngine>=6.7"]
dev = ["pytest>=7.0", "pytest-qt>=4.4"]

[project.scripts]
md-preview = "md_preview_server.app:main"
md-viewer  = "md_viewer_desktop.main:main"

[project.gui-scripts]          # no terminal window when launched from the desktop
md-viewer-gui = "md_viewer_desktop.main:main"
```
Install with `uv sync --extra desktop`. Making the Qt packages an extra keeps the Flask server light for anyone who only wants the server.

> Also bump `requires-python` to `>=3.10`. `watcher.py` already uses `str | None` in a module-level type alias, which fails at import on 3.9. Ubuntu 22.04 ships 3.10 and 24.04 ships 3.12.

## 4. Key technical designs

### 4.1 Feature mapping (web → Qt)

| Web feature | Qt implementation |
|---|---|
| Sidebar file tree (`/api/files`) | `QFileSystemModel` + `QSortFilterProxyModel` (name filter `*.md`, hide dirs with no markdown) in a `QDockWidget` |
| Change directory (`directory-picker.js`) | `File → Open Folder…` → `QFileDialog.getExistingDirectory` (uses the native GTK/portal dialog on Ubuntu) |
| Open single file | `File → Open…`, CLI arg, or drag-and-drop onto the window |
| Filename search (`/api/search`) | `QLineEdit` feeding the proxy model's filter |
| Content search (`/api/search/content`) | Reuse `files.search_content()` in a `QThreadPool` worker, show results in a `QListView`, click to open the file at that line |
| Rendered view (`view.html`) | `QWebEngineView` loading `mdview://doc/<path>` |
| Live reload (SSE) | `watcher_bridge` emits `fileChanged(path)` → view re-renders and keeps scroll position via `runJavaScript` |
| Theme menu (localStorage) | `View → Theme` menu stored in `QSettings`, applied as a `data-theme` attribute in the page and optionally as a Qt palette (Fusion dark) for the chrome |
| CodeMirror editor | Split view: `QPlainTextEdit` + a small `QSyntaxHighlighter` for Markdown on the left, live preview on the right (debounced 300 ms via `QTimer`) |
| Save with conflict check (`/api/save` + revisions) | Reuse `storage.atomic_write_text` with the revision guard; on mismatch, show a `QMessageBox` offering Reload / Overwrite / Cancel |
| Create / rename / delete | File tree context menu. Delete goes through `QFile.moveToTrash()` (the XDG trash), which is safer than `unlink` |
| Upload | Not needed on desktop. Drag-and-drop replaces it |
| HTML export | Reuse the existing export logic → `QFileDialog.getSaveFileName` |
| **New: PDF export** | `QWebEnginePage.printToPdf()`, almost free (it's already listed in `future_upgrades.md`) |
| **New: Print** | `QPrintDialog` + `page.print()` |
| TOC | Dock with `QTreeWidget` built from python-markdown's `toc_tokens` (expose them from `renderer.py`); clicking scrolls via JS |
| AI assistant (`/api/ai/ask`) | Defer to a later phase. Put the OpenAI call behind a `QThread` worker when ported |

### 4.2 Threading
- watchdog callbacks run on a background thread and **must not touch widgets**. `WatcherBridge(QObject)` defines `fileChanged = pyqtSignal(str, str, str)`. The callback only calls `self.fileChanged.emit(...)`, and Qt queues the delivery to the GUI thread automatically.
- Rendering a large file and content search run on `QThreadPool`/`QRunnable` so the UI never freezes.
- An alternative to watchdog is `QFileSystemWatcher`, but it only watches paths you explicitly add and has no recursion. Keep watchdog, which uses inotify on Linux.

### 4.3 Serving rendered HTML (no HTTP server)
Don't use `setHtml()`. It has a ~2 MB limit, and relative images like `![](img/foo.png)` break without a good base URL. Instead:
1. Register a custom scheme `mdview` with `QWebEngineUrlScheme` **before** creating `QApplication`.
2. Implement `QWebEngineUrlSchemeHandler.requestStarted(job)`:
   - `mdview://doc/<relpath>` → `render_markdown_cached()` wrapped in `page_template.html`, returned as `text/html`
   - `mdview://asset/<relpath>` → local files next to the doc (images), after `validate_path`
   - `mdview://app/<path>` → bundled CSS, Mermaid and KaTeX from `resources/`
3. Because relative links in the doc resolve against `mdview://doc/dir/`, images resolve naturally once the handler maps them.
4. Intercept link clicks via `QWebEnginePage.acceptNavigationRequest`:
   - a link to another `.md` file → open it in a tab
   - an `http(s)` link → `QDesktopServices.openUrl` (the system browser)
   - everything else → block

### 4.4 Offline assets
Vendor Mermaid (`mermaid.min.js`, UMD build) and KaTeX (js, css, fonts) into `resources/vendor/` with a small `scripts/vendor_assets.py` that downloads pinned versions. Keep versions in sync with what `view.html` loads today.

### 4.5 Linux integration (the "decent viewer on Ubuntu" part)
- **`.desktop` file** installed to `~/.local/share/applications/md-viewer.desktop`:
  ```ini
  [Desktop Entry]
  Type=Application
  Name=MD Viewer
  Exec=md-viewer %F
  Icon=md-viewer
  MimeType=text/markdown;text/x-markdown;
  Categories=Office;Viewer;Utility;
  Terminal=false
  ```
  Then run `xdg-mime default md-viewer.desktop text/markdown` so double-clicking a `.md` file in Nautilus opens it in the app.
- **Single instance:** use `QLocalServer`/`QLocalSocket`. A second `md-viewer foo.md` sends the path to the running window, which opens it in a new tab instead of starting another app.
- **CLI:** `md-viewer [PATH ...]`. A file opens that file with its parent folder in the tree. A directory opens that folder. With no args, reopen the last session.
- **Icon:** SVG in `~/.local/share/icons/hicolor/scalable/apps/`.
- An `md-viewer --install-desktop` subcommand writes the `.desktop` file and icon, so there's no manual setup.

## 5. Implementation phases

| Phase | Scope | Done when… | Est. |
|---|---|---|---|
| **0. Spike** | Option A wrapper in about 40 lines, to prove QtWebEngine runs on your Ubuntu box | Window shows a rendered doc | 1–2 h |
| **1. Core extraction** | Create `md_preview_core`, move renderer/storage/watcher, extract `files.py` from `app.py`, and update imports. Leave re-export shims in `md_preview_server` so nothing breaks | `uv run pytest` passes and the Flask app behaves the same | 0.5 day |
| **2. MVP viewer** | `QMainWindow`, file tree dock, `mdview://` scheme handler, vendored assets, Open File/Folder, CLI args, live reload, link handling, themes | You can `md-viewer README.md` and browse a folder offline with Mermaid and math rendering | 2–3 days |
| **3. Linux polish** | `.desktop` + MIME, single instance, tabs, recent files, window geometry in `QSettings`, TOC dock, Ctrl+F find-in-page (`QWebEnginePage.findText`), zoom (Ctrl +/-), print/PDF | Double-clicking a `.md` in Nautilus opens it in an existing window | 1–2 days |
| **4. Editor** | Split editor/preview, Markdown highlighter, debounced live preview, save with revision guard, dirty-state `*` in tab title, prompt to save on close | Edit → save → external change detection all work | 2 days |
| **5. File ops + search** | Context menu new/rename/trash, filename filter, full-text search dock | Parity with the web sidebar | 1 day |
| **6. Packaging** | See §7 | Installable on a clean Ubuntu 24.04 VM | 1 day |
| *Later* | AI panel, git status in tree, scroll sync editor↔preview, presentation mode | – | – |

Every phase ends in a working, committable app. Phases 4 and 5 can happen in either order.

## 6. Linux / QtWebEngine gotchas to plan for
- **Missing xcb lib:** PyQt6 wheels bundle Qt, but Ubuntu needs `sudo apt install libxcb-cursor0` or the xcb platform plugin fails to load with a cryptic error. Document it in the README.
- **Wayland:** Qt 6 picks Wayland automatically on GNOME. If rendering glitches, `QT_QPA_PLATFORM=xcb` is the fallback. Expose it as a documented env var, don't hard-code it.
- **GPU / blank white view:** on some VMs or NVIDIA setups, WebEngine renders blank. The fix is `QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu"`. Add a `--safe-mode` CLI flag that sets it.
- **Sandbox when running as root / in containers:** needs `QTWEBENGINE_DISABLE_SANDBOX=1`. This matters mostly for CI.
- **Wheel size:** PyQt6-WebEngine is about 100 MB+ installed. That's acceptable for a desktop app, and it's another reason to keep it an optional extra.
- **Scheme registration order:** `QWebEngineUrlScheme.registerScheme()` must run before `QApplication()` exists, or custom URLs silently fail.

## 7. Distribution options (pick one to start)
1. **`uv tool install .[desktop]`** (simplest, recommended first): puts `md-viewer` on `PATH` in an isolated env. Pair it with `md-viewer --install-desktop`.
2. **AppImage** via PyInstaller + `appimagetool`: a single file you download, `chmod +x`, and run. Good for sharing. The existing `pyinstaller_entry.py` / `build-exe.bat` pattern extends naturally. You need the PyInstaller hooks for QtWebEngine, which are built in.
3. **Flatpak** (Flathub-quality integration, portal file dialogs): the most work, and a good stretch goal.
4. **.deb**: only worth it if you want `apt install ./md-viewer.deb`. Probably skip.

## 8. Testing strategy
- Core tests stay as they are, but import from `md_preview_core`.
- Add **pytest-qt** (`uv add --optional dev pytest-qt`) for:
  - the scheme handler returns rendered HTML and rejects path traversal (`mdview://asset/../../etc/passwd`)
  - `WatcherBridge` emits on file change (use `qtbot.waitSignal`)
  - save conflict path shows the dialog (monkeypatch `QMessageBox`)
  - opening a file via CLI args populates a tab
- Headless CI: `QT_QPA_PLATFORM=offscreen` and `QTWEBENGINE_DISABLE_SANDBOX=1`.

## 9. Licensing note ⚠️
PyQt6 is **GPL v3** (or commercial). This repo is **MIT**. Using PyQt6 in your own copy is fine. **Distributing** a bundled binary (AppImage/Flatpak) that includes PyQt6 means the distributed app has to be GPL-compatible. The code can stay MIT, but the combined binary falls under GPL terms.
If that matters, **PySide6** (the official Qt for Python, **LGPL**) has an almost identical API. Most of this plan works with a find-and-replace of `PyQt6` → `PySide6` and `pyqtSignal` → `Signal`. Decide this before Phase 2.

## 10. Open questions
1. Keep the Flask server long-term, or retire it once the desktop app reaches parity? (This plan assumes you keep both via the shared core.)
2. Tabs or a single document per window?
3. Follow the system light/dark theme automatically (`QStyleHints.colorScheme()`, Qt ≥ 6.5), or keep the app's own theme list?
4. Is the AI assistant needed in v1?

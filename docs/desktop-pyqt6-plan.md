# Plan: PyQt6 Desktop App (Linux / Ubuntu first)

**Status:** All six phases implemented (shared core, MVP viewer, Linux polish, editor, file operations and search, packaging). Flatpak and .deb remain optional stretch goals. See §11 onward for where the code departs from this plan.
**Goal:** A native-feeling Markdown viewer for Ubuntu that opens `.md` files from the file manager, renders them the same way the web app does (Pygments code highlighting, tables, TOC, Mermaid, KaTeX, frontmatter), live-reloads on disk changes, and keeps the editor. It should work fully offline, and wear the jamielab design system (§4.6).

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
- ✅ Native file tree, tabs, menus, shortcuts, dialogs, and app themes.
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
    theme.py                # jamielab design tokens → CSS vars, QSS, QPalette (§4.6)
    resources/
      design/               # jamielab.tokens.json (source of truth, §4.6)
      fonts/                # vendored IBM Plex Mono (ttf + woff2) + OFL.txt
      css/                  # symlink/copy of style.css, codehilite.css; generated theme-jamielab.css
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
| Theme menu (localStorage) | `View → Theme` menu stored in `QSettings`, applied as a `data-theme` attribute in the page **and** as a generated Qt palette + QSS for the chrome. Default: **`jamielab`** (§4.6) |
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

### 4.6 Design system: jamielab

The desktop build adopts the **jamielab** design system (the shared look of the jamielab.me tool suite: dark terminal, IBM Plex Mono, phosphor green / teal / amber, "museum specimen, clinical" feel). It ships as a new theme, **`jamielab`**, which becomes the **default** for the desktop app. The existing Terminal, Amber, Dracula, Nord and Paper themes stay available in `View → Theme`.

**Source of truth:** `docs/design/jamielab.tokens.json` (a snapshot of the design system's tokens). Nothing downstream hand-types a hex value. The CSS variables for the rendered document, the Qt stylesheet (QSS) and the `QPalette` are all *generated* from that file at startup by one module.

#### Tokens at a glance

| Token | Value | Use |
|---|---|---|
| `ground` | `#0b0f0e` | Window / page background |
| `panel` | `#121816` | Docks, tab bar, editor, code blocks, dialogs |
| `hairline` | `#2a3a34` | Decorative dividers, table rules, dock splitters (1.6:1, **never** a control border) |
| `edge` | `#5a6f66` | Borders of inputs, buttons, tree/list frames (≥3:1) |
| `ink` | `#d7e4dc` | Primary text (14.7:1 on ground) |
| `ink-muted` | `#8aa097` | Metadata, placeholders, status bar, line numbers (6.9:1) |
| `phosphor` | `#39ff88` | Primary action, focus ring, caret, selection, success. Text on it is `ground` |
| `teal` | `#2ec4b6` | Links, info, hovered/selected tree rows |
| `amber` | `#ffb000` | Warnings, unsaved `*`, "file changed on disk" banner |
| `danger` | `#ff5f56` | Errors and destructive actions only, always with text/icon |

Type: **IBM Plex Mono** only — `display` 48/52 600, `h1` 28/36 600, `h2` 20/28 600, `body` 15/24 400, `code` 14/22 400, `small` 13/20 400, `label` 11/16 500 (uppercase in UI). Spacing: `space-1` 4, `space-2` 8, `space-4` 16, `space-6` 24 px. Radius: `radius-none` 0, `radius-sm` 2, `radius-md` 4 px (4 px is the ceiling). **No shadows, gradients, glow or scanlines** — structure comes from `hairline`/`edge` lines.

This also closes the contrast finding in `docs/ui-design-review.md`: the old Terminal secondary text (`#4a7a4a`, ~3:1) is replaced by `ink-muted` at 6.9:1.

#### New files

```
src/md_viewer_desktop/
  theme.py                        # load tokens.json → Theme dataclass; build CSS vars, QSS, QPalette
  resources/
    design/jamielab.tokens.json   # copied from docs/design/ (or read from there in dev)
    fonts/IBMPlexMono-{Regular,Medium,SemiBold}.ttf    # for Qt (QFontDatabase)
    fonts/IBMPlexMono-{Regular,Medium,SemiBold}.woff2  # for the web view (@font-face)
    fonts/OFL.txt                 # Plex is SIL OFL 1.1 — ship the license
    css/theme-jamielab.css        # GENERATED by theme.py; do not edit
    icons/                        # Lucide SVGs (ISC), stroke 1.5, recolored at load
```

Fonts must be **vendored** (the app is offline-first — no Google Fonts `@import`). Add Plex to `scripts/vendor_assets.py` alongside Mermaid/KaTeX, pinned (IBM/plex GitHub release or `@fontsource/ibm-plex-mono`). Qt gets TTF because WOFF2 support in `QFontDatabase` is not reliable.

#### `theme.py` contract

```python
@dataclass(frozen=True)
class Theme:
    name: str
    color: dict[str, str]     # "ground" -> "#0b0f0e", ...
    space: dict[str, int]     # "space-4" -> 16
    radius: dict[str, int]
    type: dict[str, TextStyle]  # "body" -> TextStyle(size=15, line=24, weight=400)

def load_theme(path: Path) -> Theme: ...          # validates every token listed above exists
def css_variables(t: Theme) -> str: ...           # :root[data-theme="jamielab"] { ... } block
def qss(t: Theme) -> str: ...                     # app stylesheet (template below)
def palette(t: Theme) -> QPalette: ...
def apply(app: QApplication, t: Theme) -> None:   # Fusion style + palette + QSS + default font
```

Call `apply()` in `main.py` right after `QApplication()` is created (after scheme registration). Theme switching from `View → Theme` calls `apply()` again and sets `data-theme` in the page via `runJavaScript`.

#### Rendered document (QWebEngineView)

`page_template.html` loads `mdview://app/css/theme-jamielab.css` after `style.css`. The generated block maps tokens onto the variables `style.css` already uses, so no selector changes are needed:

| `style.css` variable | Token |
|---|---|
| `--color-bg`, `--color-sidebar-bg` | `ground` |
| `--color-bg-accent`, `--color-surface`, `--color-surface-strong`, `--color-code-bg`, `--color-table-alt` | `panel` |
| `--color-border` | `hairline` |
| `--color-border-strong`, `--color-blockquote-border` | `edge` |
| `--color-text` | `ink` |
| `--color-text-secondary` | `ink-muted` |
| `--color-link` | `teal` |
| `--color-accent`, `--color-accent-strong`, `--color-success` | `phosphor` |
| `--color-danger` | `danger` |
| `--font-display`, `--font-body`, `--font-mono`, `--font-prose` | `"IBM Plex Mono", ui-monospace, monospace` |
| `--color-shadow`, `--glow-sm`, `--glow-md`, `--scanline` | `none` |
| `--gradient-page` | `ground` (flat) · `--gradient-accent` → `phosphor` (flat) |

Also in the generated CSS: `@font-face` rules pointing at `mdview://app/fonts/*.woff2`; `.markdown-body` headings use the `h1`/`h2` styles, body the `body` style, `code`/`pre` the `code` style; `pre` gets `radius-none` and `space-4` padding; `:focus-visible { outline: 2px solid var(--phosphor); outline-offset: 2px; }`.

- **Prose font (decided):** Plex Mono everywhere — the generated block sets `--font-prose` to the same mono stack, overriding the sans stack in `style.css` for the jamielab theme only. Other themes keep their current prose fonts.
- **Light theme (decided):** jamielab is dark-only. `View → Theme → Paper` is the light option and is left unchanged.
- **Code highlighting:** generate a Pygments style (`JamielabStyle`) from tokens instead of hand-editing `codehilite.css`: keywords `phosphor`, strings `amber`, names/functions `teal`, comments `ink-muted` italic, errors `danger`, everything else `ink`, background `panel`.
- **Mermaid:** `mermaid.initialize({ theme: "base", themeVariables: {...} })` with `background`=ground, `primaryColor`=panel, `primaryTextColor`=ink, `primaryBorderColor`=edge, `lineColor`=ink-muted, `secondaryColor`=panel, `tertiaryColor`=ground, `fontFamily`=Plex Mono. Inject these from `theme.py` into the template.
- **KaTeX:** inherits `color: var(--color-text)`; nothing extra.

#### Qt chrome (widgets)

`app.setStyle("Fusion")`, then set the palette and stylesheet. Palette roles:

| QPalette role | Token |
|---|---|
| `Window`, `AlternateBase` | `ground` |
| `Base`, `Button`, `ToolTipBase` | `panel` |
| `WindowText`, `Text`, `ButtonText`, `ToolTipText` | `ink` |
| `PlaceholderText`, `Disabled` text roles | `ink-muted` |
| `Highlight` | `phosphor` · `HighlightedText` → `ground` |
| `Link`, `LinkVisited` | `teal` |
| `Mid`, `Dark` | `edge` · `Midlight`, `Light` → `hairline` |

QSS template (filled from tokens by `qss()`; keep it in `theme.py`, not a loose `.qss` file):

```css
* { font-family: "IBM Plex Mono"; font-size: {body.size}px; }
QMainWindow, QDockWidget { background: {ground}; color: {ink}; }
QDockWidget::title { background: {panel}; padding: {space-2}px {space-4}px;
                     font-size: {label.size}px; font-weight: 500; text-transform: uppercase; }
QSplitter::handle, QMainWindow::separator { background: {hairline}; width: 1px; height: 1px; }
QTreeView, QListView, QPlainTextEdit, QLineEdit {
  background: {panel}; border: 1px solid {edge}; border-radius: {radius-sm}px;
  selection-background-color: {phosphor}; selection-color: {ground}; }
QTreeView::item { padding: {space-1}px {space-2}px; }
QTreeView::item:hover { color: {teal}; }
QTreeView::item:selected { background: {panel}; color: {teal}; border-left: 2px solid {teal}; }
QLineEdit { padding: {space-2}px; }
QLineEdit:focus, QPlainTextEdit:focus, QTreeView:focus { border: 2px solid {phosphor}; }
QPushButton { background: {panel}; color: {ink}; border: 1px solid {edge};
              border-radius: {radius-sm}px; padding: {space-2}px {space-4}px; }
QPushButton:hover { border-color: {ink-muted}; }
QPushButton:focus { border: 2px solid {phosphor}; }
QPushButton[primary="true"] { background: {phosphor}; color: {ground}; border-color: {phosphor}; font-weight: 600; }
QPushButton[danger="true"]  { color: {danger}; border-color: {danger}; }
QTabBar::tab { background: {ground}; color: {ink-muted}; padding: {space-2}px {space-4}px;
               border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: {ink}; border-bottom-color: {phosphor}; }
QMenuBar, QMenu, QStatusBar { background: {panel}; color: {ink}; }
QMenu { border: 1px solid {edge}; } QMenu::item:selected { background: {phosphor}; color: {ground}; }
QStatusBar { color: {ink-muted}; font-size: {small.size}px; border-top: 1px solid {hairline}; }
QToolTip { background: {panel}; color: {ink}; border: 1px solid {edge}; }
QScrollBar:vertical { background: {ground}; width: 10px; }
QScrollBar::handle:vertical { background: {edge}; border-radius: {radius-sm}px; min-height: 24px; }
```

Notes for implementers:
- QSS has no `outline`; the focus ring is a 2 px `phosphor` border. Reduce padding by 1 px on focus if the jump is visible.
- Layout spacing uses tokens only: dock/pane content margins `space-4`, gutters between major regions `space-6`, list/item gaps `space-2`, icon-to-label `space-1`. No magic numbers in widget code — import them from the `Theme`.
- Mark primary buttons with `btn.setProperty("primary", True)` (e.g. **Edit**, **Save**; this also covers the "promote the primary action" item in the UI review). Destructive: `danger`.
- **Editor (`QPlainTextEdit`):** background `panel`, text `ink`, caret `phosphor` (`setCursorWidth(2)` + palette `Text`), current-line highlight `ground`, line numbers `ink-muted`. The Markdown `QSyntaxHighlighter` uses the same colors as the Pygments style (headings `phosphor` 600, emphasis `ink` italic, code spans `amber`, links `teal`, list markers/quotes `ink-muted`).
- **States:** unsaved tab `*` and the "changed on disk" bar in `amber`; save-conflict dialog uses `danger` only for the Overwrite button; live-reload success is silent (no green toasts).
- **Icons:** Lucide at 16 px, stroke 1.5, recolored to `ink-muted` (hover `ink`, active `phosphor`) by replacing `currentColor` in the SVG before building the `QIcon`. Text glyphs (`›`, `●`, `▸`) are fine for status and disclosure.
- **App icon / wordmark:** no logo exists yet. Until one does, the `md-viewer.svg` icon is a `phosphor` `›_` prompt on a `ground` square (`radius-md`) and the About dialog sets **jamielab** / **MD Viewer** in Plex Mono 600.
- **Voice:** status and error strings are terse, factual, no exclamation marks or emoji (`reloaded · README.md`, `save failed: file changed on disk`).

## 5. Implementation phases

| Phase | Scope | Done when… | Est. |
|---|---|---|---|
| **0. Spike** | Option A wrapper in about 40 lines, to prove QtWebEngine runs on your Ubuntu box | Window shows a rendered doc | 1–2 h |
| **1. Core extraction** | Create `md_preview_core`, move renderer/storage/watcher, extract `files.py` from `app.py`, and update imports. Leave re-export shims in `md_preview_server` so nothing breaks | `uv run pytest` passes and the Flask app behaves the same | 0.5 day |
| **2. MVP viewer** | `QMainWindow`, file tree dock, `mdview://` scheme handler, vendored assets (incl. IBM Plex Mono), Open File/Folder, CLI args, live reload, link handling, themes. **`theme.py` + jamielab applied to chrome and document from the first window** (§4.6) — build the look in, don't bolt it on | You can `md-viewer README.md` and browse a folder offline with Mermaid and math rendering | 2–3 days |
| **3. Linux polish** | jamielab Pygments style + Mermaid theme variables, Lucide icons, app icon, `.desktop` + MIME, single instance, tabs, recent files, window geometry in `QSettings`, TOC dock, Ctrl+F find-in-page (`QWebEnginePage.findText`), zoom (Ctrl +/-), print/PDF | Double-clicking a `.md` in Nautilus opens it in an existing window | 1–2 days |
| **4. Editor** | Split editor/preview, Markdown highlighter (jamielab colors, `phosphor` caret), debounced live preview, save with revision guard, dirty-state `*` in tab title, prompt to save on close | Edit → save → external change detection all work | 2 days |
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
  - `load_theme()` rejects a tokens file missing any required token, and `qss()` leaves no unfilled `{placeholder}`
  - contrast guard: `ink` and `ink-muted` ≥ 4.5:1 on `ground` and `panel`; `edge` and `phosphor` ≥ 3:1 (a tiny WCAG luminance helper, no dependency)
  - the generated `theme-jamielab.css` is up to date with `jamielab.tokens.json` (regenerate and diff)
- Headless CI: `QT_QPA_PLATFORM=offscreen` and `QTWEBENGINE_DISABLE_SANDBOX=1`.

## 9. Licensing note ⚠️
PyQt6 is **GPL v3** (or commercial). This repo is **MIT**. Using PyQt6 in your own copy is fine. **Distributing** a bundled binary (AppImage/Flatpak) that includes PyQt6 means the distributed app has to be GPL-compatible. The code can stay MIT, but the combined binary falls under GPL terms.
If that matters, **PySide6** (the official Qt for Python, **LGPL**) has an almost identical API. Most of this plan works with a find-and-replace of `PyQt6` → `PySide6` and `pyqtSignal` → `Signal`. Decide this before Phase 2.

## 10. Decisions

**Decided (2026-09-25):**
- **Flask server:** keep it long-term alongside the desktop app. Both use the shared core.
- **Documents:** use tabs in one window.
- **Themes:** keep the app's theme menu with jamielab as the default and Paper as the light option. System theme detection may be added later as an explicit Auto choice; it does not override a selected theme.
- **AI assistant:** defer it beyond v1. Prioritize the offline viewer and editor.

**Decided (2026-09-24):**
- **Prose font:** keep IBM Plex Mono everywhere, including `.markdown-body` prose. The `--font-prose` variable resolves to the mono stack in the jamielab theme; don't vendor a sans.
- **Light theme:** jamielab stays dark-only. Paper remains the light option as-is; more light themes may be added later.

## 11. Implementation notes (Phase 2)

Where the MVP departs from the plan above, and why:

- **Binding:** PyQt6, as written. The §9 licensing question (PyQt6 GPL vs PySide6 LGPL) is still open. It only matters once a bundled binary is distributed (Phase 6), and the port is mostly mechanical.
- **File tree:** built from `md_preview_core.files.scan_files()` into a `QStandardItemModel` instead of `QFileSystemModel` + proxy. This gives the same exclusions (`.git`, `node_modules`, `.venv`…) and hides empty folders exactly like the web sidebar, without a recursive proxy filter. It is rebuilt (keeping expanded folders) on `tree_changed` watcher events.
- **One `doc` host:** `mdview://doc/<relpath>` renders `.md` files and serves every other file (images) as-is, so relative links resolve with no separate `asset` host. Both paths go through `validate_path`.
- **Content-Security-Policy:** the page shell only runs scripts from `mdview://app`. A `<script>` embedded in a Markdown file is blocked, and so are inline event handlers. Remote images still load.
- **Offline CSS:** `style.css` is served straight from `md_preview_server/static/css` (shared, not copied), with its Google Fonts `@import` stripped so the app never makes that request.
- **Fonts for Qt:** the `@ibm/plex-mono` npm package ships no TTF, so Qt loads the WOFF (zlib) files and the web view uses WOFF2. `scripts/vendor_assets.py` pulls Mermaid 10.9.3, KaTeX 0.16.22 and Plex Mono 1.1.0 from the npm registry and checks each tarball's SHA-512 integrity hash. The outputs are committed so a fresh clone works offline.
- **Tests:** no `pytest-qt`. With it installed but no Qt binding present, it aborts the *whole* run at start-up, which would break `uv run pytest` for server-only installs. `tests/desktop/conftest.py` provides a `qapp` fixture and event-loop helpers instead, and skips the folder when PyQt6 is missing. Theme tests (`tests/test_desktop_theme.py`) are pure Python and always run.
- **Chrome per theme:** jamielab styles the chrome for every dark document theme. Paper switches the chrome to stock Fusion light. Per-theme chrome palettes can come later.
- **Pulled forward from Phase 3:** Mermaid `themeVariables` from tokens, and window geometry in `QSettings`.
- **Link clicks** are handed to the window through a queued connection. Starting a new `load()` from inside `acceptNavigationRequest` makes Chromium abort the process.

## 12. Implementation notes (Phase 3)

- **Tabs and roots:** every tab remembers the folder it was opened from (its *root*) and is served from its own host, `mdview://doc-<sha1(root)[:12]>/<relpath>`. This lets tabs from different folders coexist: opening a file outside the sidebar's folder moves the sidebar but leaves other tabs working (their links, images and live reload still resolve in their own root). One watchdog observer runs per root in use (sidebar folder plus tab roots), and stops when the last tab using it closes. The `doc` host from Phase 2 is still accepted by `resolve_request`.
- **Which tab:** sidebar click and in-document links replace the current tab. Middle-click or Ctrl+click in the sidebar, File → Open, Open Recent, drag-and-drop, CLI arguments and second launches open a new tab. A file that is already open just switches to its tab. Closing the last tab leaves a welcome tab.
- **Session:** `QSettings` stores the tabs as JSON (`root` + relative `path`) and the active index. It is only written once something has been opened or restored, so creating a window never wipes the previous session. Phase 2's single `session/file` is read as a fallback.
- **Single instance:** `QLocalServer` named `jamielab-md-viewer-<uid>` (a Unix socket, user-only access). A second launch sends `{"paths": [...]}` as one JSON line and waits for `ok`; if nobody answers, the socket is stale (crash) and the new process takes it over. `--new-instance` skips the handoff.
- **Desktop integration:** `md-viewer --install-desktop` writes the `.desktop` file (from `linux/md-viewer.desktop`, with `Exec` pointing at the `md-viewer` that ran it), the icon and `linux/md-viewer.xml` under `$XDG_DATA_HOME`, then runs `update-mime-database`, `update-desktop-database`, `gtk-update-icon-cache` and `xdg-mime default` when they exist. `--uninstall-desktop` removes the files. `StartupWMClass=md-viewer` matches `setDesktopFileName("md-viewer")`.
- **TOC:** headings are read from the rendered DOM (`mdviewHeadings()` in `page.js`), not from python-markdown's `toc_tokens`. No core change was needed, and the panel always matches what is on screen after a live reload.
- **Pygments:** `JamielabStyle` is built from tokens and emitted into `theme-jamielab.css` with only scoped rules (`get_style_defs()` also emits bare `pre`/line-number rules that would leak into other themes). A `Token` base colour and a weight/style reset stop `codehilite.css` from leaking through.
- **Print / PDF:** dark themes print as light text on white, so both switch the page to Paper (`data-theme="light"`), wait for Mermaid to redraw (`window.mdviewRendering`), print, then switch back. Code colours for print come from Pygments' stock `default` style in a `@media print` sheet (`mdview://app/css/print.css`, generated on request), so Paper on screen is unchanged. Page size is Letter for US locales and A4 elsewhere, with 15 mm margins.
- **Find:** Chromium only searches a visible page. The match count comes from `QWebEnginePage.findTextFinished`.
- **Icons:** Lucide 1.48.0 (`lucide-static` on npm, ISC) is vendored by `scripts/vendor_assets.py`. `icons.py` swaps `currentColor` for `ink-muted` / `ink` / `phosphor` / `edge` per `QIcon` mode (palette colours under Paper) and thins the stroke to 1.5. The app icon (`›_`) is generated by `theme.py` as strokes, so it needs no font.
- **Zoom** is one factor for all tabs (0.5–3×), stored in `QSettings`, and re-applied after each load.
- **Lifetime:** page, watcher and JavaScript callbacks can fire while a window is being torn down, and PyQt6 aborts on an exception in a slot. Signals connect to bound methods (Qt drops those with the window) and async callbacks check `sip.isdeleted`.

## 13. Implementation notes (Phase 5)

- **Filename/path filter:** a clearable input above the Files tree matches literal substrings of relative paths, case-insensitively. `FileTree` hides rows in the existing model instead of introducing a proxy model, preserving the path roles used for tab opening. Folders remain visible only when they contain matching files and expand while filtering. Clearing restores the previous expansion state and document selection. The filter remains active after watcher rebuilds and folder changes; edits to the filter do not rescan disk.
- **File operations:** right-click a folder, file, or empty tree area to create a `.md` file in that folder (a file uses its parent folder, empty space uses the sidebar root). Rename and Move to Trash apply only to files. New files open in a tab; `.md` is appended when no extension is supplied. Names cannot contain folder separators, only Markdown files can be modified, paths use core validation, and final symlinks are rejected. Exclusive creation and `QFile.rename()` prevent overwrites. `QFile.moveToTrash()` runs only after confirmation, with no permanent-delete fallback. Renames update matching open tabs even when their roots differ from the sidebar's root, along with recent files and the saved session. Trashing closes matching tabs (leaving welcome if needed) and removes the file from recents. File-tree filters remain active throughout. The menu captures both the root and relative path before opening so a folder change cannot redirect its action.
- **Full-text search:** Edit → Find in Folder… (Ctrl+Shift+F) opens a Search dock for the sidebar's root. `md_preview_core.files.search_content()` reuses the existing per-file search helper and excluded-folder traversal, limits output to 50 source-line matches, and checks one extra hit to report truncation accurately. Searches are debounced 300 ms and run in a `QThreadPool` worker; cancellation and generation checks discard results from obsolete queries, folder changes, and window shutdown. Disk changes and file operations refresh active queries. Results show relative paths, source line numbers and context snippets. Activation opens the document and uses Chromium find to locate the rendered source line, including repeated identical lines by occurrence. When Markdown source (such as an HTML comment) has no searchable rendered counterpart, the dock retains the exact source line/snippet and the status bar says `source match`; it does not invent a rendered location. The existing in-page Ctrl+F and web API response format remain unchanged.

## 14. Implementation notes (Phase 4)

- **Editor pane:** Edit → Edit Source (Ctrl+E) opens a `MarkdownEditor` (`editor.py`, `QPlainTextEdit` + `MarkdownHighlighter` coloured from tokens) in a splitter to the left of the tabs. Each tab owns its editor (`DocumentView.editor`), so undo history and dirty state survive tab switches; a `QStackedWidget` shows the current tab's editor.
- **Live preview:** typing stores the buffer in `SchemeHandler.overrides` (resolved path → text), and a 300 ms timer reloads the tab. `resolve_request` renders the override instead of the disk file, so the preview never needs a save. The override is dropped on save, close or reload from disk.
- **Save:** Ctrl+S calls `atomic_write_text(..., expected_revision=editor.base_revision)`. On `FileRevisionMismatch` a dialog offers Reload / Overwrite / Cancel. A `*` follows the tab name while the buffer is dirty (the `QTextDocument` modified flag, so undoing back to the saved text clears it).
- **External changes:** a watcher event under an open editor compares the disk revision with `base_revision`. Equal means our own save. A clean buffer reloads silently, and a dirty one only warns in the status bar (`changed on disk · … · save to resolve`) and keeps the buffer.
- **Prompts:** closing a dirty tab or the window asks Save / Discard / Cancel. Trashing a file closes its tab without asking. Renaming retargets the override.
- **Not done:** the phosphor caret (Qt's `QPlainTextEdit` draws the caret from the text colour, so a token-coloured caret needs a custom paint) and scroll sync between editor and preview (listed under *Later*).

## 15. Implementation notes (Phase 6)

- **`uv tool install '.[desktop]'`:** verified from a built wheel into a clean venv outside the checkout: the wheel carries every resource (fonts, vendored Mermaid/KaTeX, CSS, icons, `linux/` desktop and MIME files) and `md-viewer --version`, `--install-desktop` and a headless launch all work. On a clean Ubuntu the only extra step is `sudo apt install libxcb-cursor0 libegl1`.
- **AppImage:** `scripts/build-appimage.sh` runs PyInstaller (`--onedir`, entry `packaging/md_viewer_entry.py`, `--collect-data` for `md_viewer_desktop` and `md_preview_server` so the package-relative resource paths keep working; Flask and OpenAI are excluded), builds an AppDir with the same `.desktop` file and icon `--install-desktop` uses, and wraps it with `appimagetool` (downloaded into `build/` when missing). `--bundle` stops after the PyInstaller step. The result is about 200 MB (540 MB unpacked).
- **`AppRun`** exports `QTWEBENGINE_DISABLE_SANDBOX=1`, since the Chromium setuid sandbox can't be shipped in an AppImage.
- **`--install-desktop` inside an AppImage** writes `$APPIMAGE` into `Exec=`/`TryExec=`. The running binary lives in a temporary mount that vanishes on exit, so using `sys.argv[0]` would leave a dead launcher.
- **Verified here:** the frozen bundle and the AppImage both start (`--version` and a headless launch with a Mermaid document) with no errors. **Not verified:** a clean Ubuntu 24.04 VM with a real display, and visual rendering inside the frozen build. Do that check on a desktop session before publishing a release.
- **Licensing (§9):** the PyQt6 GPL question stays open. It now matters, because the AppImage is a distributable binary. Either release the app under GPL-compatible terms or switch to PySide6 (LGPL) before sharing it publicly.

# md-preview-server

A local Markdown preview server with live reload, syntax highlighting, and a file browser.

## Features

- Browse and select markdown files from a directory tree
- Render markdown to styled HTML with GitHub-flavored styling
- Syntax highlighting for code blocks (powered by Pygments)
- Live preview with auto-reload when files change
- Table of contents generation with `[TOC]` marker
- Responsive two-column layout with collapsible sidebar
- In-browser editor (CodeMirror) with live preview
- File operations: create, upload, rename, delete
- Search by filename or full-text content search with snippet preview
- Export documents to standalone HTML
- Multiple colour themes (Terminal, Amber, Dracula, Nord, Paper)
- AI assistant panel (requires a local or remote OpenAI-compatible LLM)

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager

### Installing uv

If you don't have `uv` installed yet:

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or via pip (if you have Python already)
pip install uv
```

## Installation

Clone the repo and sync dependencies:

```bash
git clone <repo-url>
cd py-MD-viewer
uv sync
```

`uv sync` reads `pyproject.toml` and `uv.lock`, creates a `.venv` automatically if one doesn't exist, and installs all pinned dependencies into it. You do **not** need to run `python -m venv .venv` or `pip install` manually.

### Including dev dependencies

To also install the development extras (e.g. pytest):

```bash
uv sync --extra dev
```

### Including AI assistant support

The AI assistant panel is optional. To enable it, install the `ai` extra:

```bash
uv sync --extra ai
```

Without it, the `/api/ai/ask` endpoint returns a 501 with an install hint.

## Usage

Navigate to any directory containing markdown files and run:

```bash
uv run md-preview
```

`uv run` executes the command inside the project's virtual environment without you needing to activate it first.

Then open <http://localhost:8000> in your browser.

The server watches for changes to `.md` files and automatically refreshes the browser when you save edits.

### Standalone Windows executable

Run `build-exe.bat` from the project root to create `dist\md-viewer.exe`. The executable includes the OpenAI client used by the AI assistant for OpenAI-compatible local or remote endpoints.

Runtime AI configuration still comes from the `OPENAI_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL` environment variables.

## Desktop app (preview, Linux first)

A native PyQt6 viewer that renders documents exactly like the web app, with no HTTP server and no network access. Mermaid, KaTeX, the IBM Plex Mono font and Lucide icons are bundled. It uses the **jamielab** theme by default; Terminal, Amber, Dracula, Nord and Paper are under **View → Theme**.

```bash
uv sync --extra desktop
uv run md-viewer README.md      # a file, in a tab, with its folder in the sidebar
uv run md-viewer a.md b.md      # several files, one tab each
uv run md-viewer ~/notes        # a folder
uv run md-viewer                # reopen the last session (folder + tabs)
```

Only one window runs at a time: launching `md-viewer foo.md` again opens `foo.md` as a new tab in the existing window (`--new-instance` starts a separate one).

- **File → Open…** (Ctrl+O), **File → Open Folder…** (Ctrl+Shift+O), **File → Open Recent**, or drop `.md` files or a folder on the window.
- Tabs: a click in the sidebar opens in the current tab; middle-click or Ctrl+click opens a new one. Ctrl+W closes, Ctrl+Tab / Ctrl+PgDown cycle.
- Filter the **Files** sidebar by filename or relative path (case-insensitive). Matching folders expand automatically; clear the filter to restore the full tree.
- Right-click the **Files** tree to create a Markdown file in that folder, rename a file, or move it to Trash after confirmation. Renaming updates open tabs; trashed files can be recovered from your file manager's Trash.
- **Edit → Find in Folder…** (Ctrl+Shift+F) searches Markdown contents in the sidebar folder, showing up to 50 matching source lines with snippets. Click a result to open the document and find the matching rendered line. Searches run in the background and refresh after disk changes.
- **Contents** panel (Ctrl+Shift+T) lists the document's headings; click one to jump to it.
- Find in page (Ctrl+F, then Enter / Shift+Enter or F3 / Shift+F3), zoom (Ctrl + / Ctrl − / Ctrl+0).
- **File → Print…** (Ctrl+P) and **File → Export PDF…** print in the light Paper theme.
- Documents reload automatically when they change on disk, including background tabs.
- Links to other `.md` files open in the viewer. `http(s)` links open in your browser. Other links are blocked.
- Scripts embedded in a Markdown file do not run.

### Open `.md` files from the file manager

```bash
uv tool install '.[desktop]'    # puts md-viewer on your PATH
md-viewer --install-desktop     # app menu entry, icon, default app for text/markdown
```

After that, double-clicking a `.md` file in Nautilus opens it in MD Viewer (in the running window, if there is one). `--install-desktop` writes to `~/.local/share` and uses whichever `md-viewer` you ran it with; `md-viewer --uninstall-desktop` removes the files again.

On Ubuntu, Qt's xcb plugin needs `sudo apt install libxcb-cursor0`. If the document area stays blank (some VMs and NVIDIA setups), run with `--safe-mode` to disable GPU acceleration. On Wayland, `QT_QPA_PLATFORM=xcb` is the fallback if rendering glitches.

### Install without cloning (Ubuntu / Linux)

```bash
# Option 1: uv (recommended). Installs from a checkout or a built wheel.
sudo apt install libxcb-cursor0 libegl1      # Qt runtime libraries on a clean Ubuntu
uv tool install '.[desktop]'
md-viewer --install-desktop

# Option 2: a single-file AppImage (about 200 MB, no Python or uv needed)
scripts/build-appimage.sh                    # writes dist/MD_Viewer-<version>-x86_64.AppImage
chmod +x dist/MD_Viewer-*.AppImage
./dist/MD_Viewer-*.AppImage --install-desktop   # menu entry points at the AppImage file
```

The AppImage still needs the host's `libxcb-cursor0` and `libegl1` (`sudo apt install libxcb-cursor0 libegl1`). Build it on the oldest Ubuntu you want to support (the bundle links against the build machine's glibc). On a host without FUSE, run it with `APPIMAGE_EXTRACT_AND_RUN=1`. The AppImage sets `QTWEBENGINE_DISABLE_SANDBOX=1` because Chromium's setuid sandbox helper can't ship inside one.

The roadmap is in [`docs/desktop-pyqt6-plan.md`](docs/desktop-pyqt6-plan.md). Every phase is implemented except the Flatpak/.deb stretch goals.

Vendored front-end assets are pinned in `scripts/vendor_assets.py`. To bump one, change the version there and run `uv run python scripts/vendor_assets.py`.

## Package Management

All package operations go through `uv` rather than `pip` directly.

### Add a dependency

```bash
uv add <package-name>
```

This updates `pyproject.toml` and regenerates `uv.lock` in one step.

### Add a dev-only dependency

```bash
uv add --optional dev <package-name>
```

### Remove a dependency

```bash
uv remove <package-name>
```

### Update all dependencies to their latest allowed versions

```bash
uv lock --upgrade
uv sync
```

### Upgrade a single package

```bash
uv lock --upgrade-package <package-name>
uv sync
```

### Manually create the virtual environment

In most cases `uv sync` handles this for you, but if you ever need to create the venv explicitly:

```bash
uv venv
```

This creates a `.venv` directory in the project root. To target a specific Python version:

```bash
uv venv --python 3.11
```

### Activating the venv (optional)

You rarely need to activate the venv when using `uv run`, but if you want a traditional activated shell:

```bash
source .venv/bin/activate   # Linux / macOS
.venv\Scripts\activate      # Windows
```

Deactivate with `deactivate` when done.

## Development

Install dev dependencies then run the test suite:

```bash
uv sync --extra dev
uv run pytest
```

The desktop tests in `tests/desktop/` also need the `desktop` extra (`uv sync --extra dev --extra desktop`). They run headless and are skipped when PyQt6 isn't installed.

Run a specific test file:

```bash
uv run pytest tests/test_app.py -v
```

## Project Structure

```
py-MD-viewer/
├── src/
│   ├── md_preview_core/     # Shared rendering, storage, watcher, file scanning
│   ├── md_preview_server/   # Flask web app
│   └── md_viewer_desktop/   # PyQt6 desktop app
├── scripts/                 # Maintenance scripts (asset vendoring)
├── tests/                   # Test suite
├── examples/                # Example markdown files
├── pyproject.toml           # Project metadata and dependencies
├── uv.lock                  # Pinned dependency lockfile (commit this)
└── README.md
```

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).

Bundled third-party assets (Mermaid, KaTeX, IBM Plex Mono, Lucide) keep their own licenses, shipped next to the files under `src/md_viewer_desktop/resources/`.

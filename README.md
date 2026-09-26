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

A native PyQt6 viewer that renders documents exactly like the web app, with no HTTP server and no network access. Mermaid, KaTeX and the IBM Plex Mono font are bundled. It uses the **jamielab** theme by default; Terminal, Amber, Dracula, Nord and Paper are under **View → Theme**.

```bash
uv sync --extra desktop
uv run md-viewer README.md      # a file, with its folder in the sidebar
uv run md-viewer ~/notes        # a folder
uv run md-viewer                # reopen the last session
```

- **File → Open…** (Ctrl+O), **File → Open Folder…** (Ctrl+Shift+O), or drop a `.md` file or folder on the window.
- Documents reload automatically when they change on disk.
- Links to other `.md` files open in the viewer. `http(s)` links open in your browser. Other links are blocked.
- Scripts embedded in a Markdown file do not run.

On Ubuntu, Qt's xcb plugin needs `sudo apt install libxcb-cursor0`. If the document area stays blank (some VMs and NVIDIA setups), run with `--safe-mode` to disable GPU acceleration. On Wayland, `QT_QPA_PLATFORM=xcb` is the fallback if rendering glitches.

The roadmap is in [`docs/desktop-pyqt6-plan.md`](docs/desktop-pyqt6-plan.md). Tabs, the `.desktop` entry, the editor and file operations come in later phases.

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

MIT

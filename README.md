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

- Python 3.9+
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

Run a specific test file:

```bash
uv run pytest tests/test_app.py -v
```

## Project Structure

```
py-MD-viewer/
├── src/
│   └── md_preview_server/   # Main application package
├── tests/                   # Test suite
├── examples/                # Example markdown files
├── pyproject.toml           # Project metadata and dependencies
├── uv.lock                  # Pinned dependency lockfile (commit this)
└── README.md
```

## License

MIT

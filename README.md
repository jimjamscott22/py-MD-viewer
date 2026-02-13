# md-preview-server

A local Markdown preview server with live reload, syntax highlighting, and a file browser.

## Features

- Browse and select markdown files from a directory tree
- Render markdown to styled HTML with GitHub-flavored styling
- Syntax highlighting for code blocks (powered by Pygments)
- Live preview with auto-reload when files change
- Table of contents generation with `[TOC]` marker
- Responsive two-column layout with collapsible sidebar

## Requirements

- Python 3.9+
- [uv](https://docs.astral.sh/uv/) package manager

## Installation

```bash
git clone <repo-url>
cd py-MD-viewer
uv sync
```

## Usage

Navigate to any directory containing markdown files and run:

```bash
uv run md-preview
```

Then open http://localhost:8000 in your browser.

The server will watch for changes to `.md` files and automatically refresh the browser when you save edits.

## Development

Run the tests:

```bash
uv run pytest
```

## License

MIT

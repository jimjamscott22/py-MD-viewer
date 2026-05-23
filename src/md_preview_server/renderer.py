"""Markdown-to-HTML rendering pipeline with optional caching."""

from collections import OrderedDict
import re
import threading
from pathlib import Path
from typing import Any

import markdown
import yaml

# Match ```mermaid fences (possibly indented or with trailing spaces)
_MERMAID_RE = re.compile(
    r"^```mermaid[ \t]*\r?\n(.*?)\r?\n```[ \t]*$",
    re.MULTILINE | re.DOTALL,
)


def _preprocess_mermaid(text: str) -> str:
    """Replace ```mermaid fences with raw HTML divs for client-side rendering."""

    def _replace(m: re.Match) -> str:
        return f'<div class="mermaid">\n{m.group(1)}\n</div>'

    return _MERMAID_RE.sub(_replace, text)

_render_cache: OrderedDict[tuple[str, int, int], tuple[str, dict[str, Any]]] = OrderedDict()
_render_cache_lock = threading.Lock()
_renderer_local = threading.local()
_MAX_CACHE_SIZE = 200

_EXTENSIONS = [
    "pymdownx.arithmatex",
    "fenced_code",
    "codehilite",
    "tables",
    "toc",
    "sane_lists",
    "smarty",
]
_EXTENSION_CONFIGS = {
    "codehilite": {
        "css_class": "codehilite",
        "linenums": False,
        "guess_lang": False,
    },
    "toc": {
        "permalink": True,
    },
    "pymdownx.arithmatex": {
        "generic": True,
    },
}

# Matches a YAML frontmatter block at the very start of a file
_FRONTMATTER_RE = re.compile(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n", re.DOTALL)


def extract_frontmatter(text: str) -> tuple[str, dict[str, Any]]:
    """Strip and parse YAML frontmatter from markdown text.

    Returns ``(body, metadata)`` where ``body`` is the markdown without the
    frontmatter block and ``metadata`` is a dict (empty if none found).
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return text, {}
    try:
        metadata = yaml.safe_load(m.group(1)) or {}
        if not isinstance(metadata, dict):
            metadata = {}
    except yaml.YAMLError:
        metadata = {}
    return text[m.end():], metadata


def render_markdown(text: str) -> str:
    """Convert markdown text to HTML (uncached, for live preview). Strips frontmatter."""
    body, _ = extract_frontmatter(text)
    return _do_render(body)


def render_markdown_with_meta(text: str) -> tuple[str, dict[str, Any]]:
    """Convert markdown text to (html, metadata), stripping and parsing frontmatter."""
    body, meta = extract_frontmatter(text)
    return _do_render(body), meta


def render_markdown_cached(filepath: Path) -> str:
    """Render a file's markdown with caching by path + mtime. Returns HTML only."""
    html, _ = render_markdown_cached_with_meta(filepath)
    return html


def render_markdown_cached_with_meta(filepath: Path) -> tuple[str, dict[str, Any]]:
    """Render a file's markdown with caching, returning (html, metadata)."""
    stat = filepath.stat()
    key = (str(filepath), stat.st_mtime_ns, stat.st_size)

    with _render_cache_lock:
        cached = _render_cache.get(key)
        if cached is not None:
            _render_cache.move_to_end(key)
            return cached

    text = filepath.read_text(encoding="utf-8")
    result = render_markdown_with_meta(text)

    with _render_cache_lock:
        if len(_render_cache) >= _MAX_CACHE_SIZE:
            _render_cache.popitem(last=False)
        _render_cache[key] = result

    return result


def invalidate_render_cache() -> None:
    """Clear the entire render cache."""
    with _render_cache_lock:
        _render_cache.clear()


def _do_render(text: str) -> str:
    """Core markdown rendering logic."""
    text = _preprocess_mermaid(text)
    renderer = getattr(_renderer_local, "markdown", None)
    if renderer is None:
        renderer = markdown.Markdown(
            extensions=_EXTENSIONS,
            extension_configs=_EXTENSION_CONFIGS,
        )
        _renderer_local.markdown = renderer
    renderer.reset()
    return renderer.convert(text)

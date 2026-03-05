"""Markdown-to-HTML rendering pipeline with optional caching."""

import threading
from pathlib import Path

import markdown

_render_cache: dict[tuple[str, float], str] = {}
_render_cache_lock = threading.Lock()
_MAX_CACHE_SIZE = 200


def render_markdown(text: str) -> str:
    """Convert markdown text to styled HTML (uncached, for live preview)."""
    return _do_render(text)


def render_markdown_cached(filepath: Path) -> str:
    """Render a file's markdown with caching by path + mtime."""
    stat = filepath.stat()
    key = (str(filepath), stat.st_mtime)

    with _render_cache_lock:
        cached = _render_cache.get(key)
        if cached is not None:
            return cached

    text = filepath.read_text(encoding="utf-8")
    html = _do_render(text)

    with _render_cache_lock:
        if len(_render_cache) >= _MAX_CACHE_SIZE:
            # Evict oldest half
            keys = list(_render_cache.keys())
            for k in keys[:len(keys) // 2]:
                del _render_cache[k]
        _render_cache[key] = html

    return html


def invalidate_render_cache() -> None:
    """Clear the entire render cache."""
    with _render_cache_lock:
        _render_cache.clear()


def _do_render(text: str) -> str:
    """Core markdown rendering logic."""
    extensions = [
        "fenced_code",
        "codehilite",
        "tables",
        "toc",
        "sane_lists",
        "smarty",
    ]
    extension_configs = {
        "codehilite": {
            "css_class": "codehilite",
            "linenums": False,
            "guess_lang": False,
        },
        "toc": {
            "permalink": True,
        },
    }
    return markdown.markdown(
        text,
        extensions=extensions,
        extension_configs=extension_configs,
    )

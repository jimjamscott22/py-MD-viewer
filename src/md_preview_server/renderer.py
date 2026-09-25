"""Compatibility exports for :mod:`md_preview_core.renderer`."""

from md_preview_core.renderer import (
    extract_frontmatter,
    invalidate_render_cache,
    render_markdown,
    render_markdown_cached,
    render_markdown_cached_with_meta,
    render_markdown_with_meta,
)

__all__ = [
    "extract_frontmatter",
    "invalidate_render_cache",
    "render_markdown",
    "render_markdown_cached",
    "render_markdown_cached_with_meta",
    "render_markdown_with_meta",
]

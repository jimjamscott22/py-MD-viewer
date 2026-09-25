"""Compatibility exports for :mod:`md_preview_core.watcher`."""

from md_preview_core.watcher import (
    MarkdownFileHandler,
    WatcherCallback,
    start_watcher,
    stop_watcher,
)

__all__ = [
    "MarkdownFileHandler",
    "WatcherCallback",
    "start_watcher",
    "stop_watcher",
]

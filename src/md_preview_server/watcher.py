"""File system watcher for markdown files."""

import os
import time
import threading
from pathlib import Path
from typing import Callable

from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from .storage import get_file_revision


WatcherCallback = Callable[[str, str, str | None], None]


class MarkdownFileHandler(FileSystemEventHandler):
    """Watches for .md file changes with debounce."""

    def __init__(self, callback: WatcherCallback, base_dir: Path):
        super().__init__()
        self.callback = callback
        self.base_dir = base_dir.resolve()
        self._last_events: dict[tuple[str, str, str | None], float] = {}
        self._lock = threading.Lock()
        self._debounce_seconds = 0.5

    def _markdown_path(self, raw_path: str | bytes) -> tuple[str, Path] | None:
        path = Path(os.fsdecode(raw_path))
        if path.suffix.lower() != ".md":
            return None
        try:
            rel_path = path.resolve().relative_to(self.base_dir)
        except ValueError:
            return None
        return rel_path.as_posix(), path

    @staticmethod
    def _revision(path: Path) -> str | None:
        try:
            return get_file_revision(path)
        except OSError:
            return None

    def _emit(
        self,
        rel_path: str,
        event_type: str,
        revision: str | None = None,
    ) -> None:
        now = time.monotonic()
        event_key = (rel_path, event_type, revision)
        with self._lock:
            cutoff = now - self._debounce_seconds
            self._last_events = {
                key: timestamp
                for key, timestamp in self._last_events.items()
                if timestamp > cutoff
            }
            last = self._last_events.get(event_key, 0)
            if now - last < self._debounce_seconds:
                return
            self._last_events[event_key] = now
        self.callback(rel_path, event_type, revision)

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        markdown_path = self._markdown_path(event.src_path)
        if markdown_path is None:
            return
        rel_path, path = markdown_path
        self._emit(rel_path, "file_modified", self._revision(path))

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        markdown_path = self._markdown_path(event.src_path)
        if markdown_path is not None:
            self._emit(markdown_path[0], "tree_changed")

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        markdown_path = self._markdown_path(event.src_path)
        if markdown_path is not None:
            self._emit(markdown_path[0], "tree_changed")

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        source = self._markdown_path(event.src_path)
        destination_raw = getattr(event, "dest_path", "")
        destination = self._markdown_path(destination_raw) if destination_raw else None

        if source is not None:
            changed_path = destination[0] if destination is not None else source[0]
            self._emit(changed_path, "tree_changed")
        elif destination is not None:
            # Atomic writes move a non-Markdown temporary file over the
            # Markdown destination. Report the destination as a content change.
            rel_path, path = destination
            self._emit(rel_path, "file_modified", self._revision(path))


def start_watcher(base_dir: Path, callback: WatcherCallback) -> BaseObserver:
    """Start watching base_dir for .md file changes. Runs as a daemon thread."""
    handler = MarkdownFileHandler(callback, base_dir)
    observer = Observer()
    observer.schedule(handler, str(base_dir), recursive=True)
    observer.daemon = True
    observer.start()
    return observer


def stop_watcher(observer: BaseObserver) -> None:
    """Stop a running file watcher."""
    observer.stop()
    observer.join(timeout=2)

"""File system watcher for markdown files."""

import time
import threading
from pathlib import Path
from typing import Callable

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent


class MarkdownFileHandler(FileSystemEventHandler):
    """Watches for .md file changes with debounce."""

    def __init__(self, callback: Callable[[str], None], base_dir: Path):
        super().__init__()
        self.callback = callback
        self.base_dir = base_dir
        self._last_events: dict[str, float] = {}
        self._lock = threading.Lock()
        self._debounce_seconds = 0.5

    def _handle_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        src_path = Path(event.src_path)
        if src_path.suffix.lower() != ".md":
            return
        try:
            rel_path = src_path.resolve().relative_to(self.base_dir.resolve())
        except ValueError:
            return
        rel_str = rel_path.as_posix()
        now = time.monotonic()
        with self._lock:
            last = self._last_events.get(rel_str, 0)
            if now - last < self._debounce_seconds:
                return
            self._last_events[rel_str] = now
        self.callback(rel_str)

    def on_modified(self, event: FileSystemEvent) -> None:
        self._handle_event(event)

    def on_created(self, event: FileSystemEvent) -> None:
        self._handle_event(event)


def start_watcher(base_dir: Path, callback: Callable[[str], None]) -> Observer:
    """Start watching base_dir for .md file changes. Runs as a daemon thread."""
    handler = MarkdownFileHandler(callback, base_dir)
    observer = Observer()
    observer.schedule(handler, str(base_dir), recursive=True)
    observer.daemon = True
    observer.start()
    return observer

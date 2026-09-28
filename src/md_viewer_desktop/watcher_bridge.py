"""Hand watchdog callbacks to the Qt GUI thread via a signal."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal
from watchdog.observers.api import BaseObserver

from md_preview_core.files import invalidate_file_cache
from md_preview_core.watcher import start_watcher, stop_watcher


class WatcherBridge(QObject):
    """Owns the watchdog observer for one base directory.

    ``fileChanged(rel_path, event_type, revision)`` is emitted from the
    watchdog thread; Qt queues delivery to receivers living on the GUI
    thread, so slots may touch widgets. ``revision`` is ``""`` when unknown.
    """

    fileChanged = pyqtSignal(str, str, str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._observer: BaseObserver | None = None
        self._base_dir: Path | None = None

    @property
    def base_dir(self) -> Path | None:
        return self._base_dir

    def start(self, base_dir: Path) -> None:
        self.stop()
        self._base_dir = base_dir.resolve()
        self._observer = start_watcher(self._base_dir, self._on_change)

    def stop(self) -> None:
        if self._observer is not None:
            stop_watcher(self._observer)
            self._observer = None

    def _on_change(self, rel_path: str, event_type: str, revision: str | None) -> None:
        # Runs on the watchdog thread: no widget access here.
        if event_type == "tree_changed":
            invalidate_file_cache()
        self.fileChanged.emit(rel_path, event_type, revision or "")

"""Debounced folder content search, with cancellable background workers."""

from __future__ import annotations

from pathlib import Path
from threading import Event

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from md_preview_core.files import search_content


class SearchSignals(QObject):
    finished = pyqtSignal(int, object, str)


class SearchWorker(QRunnable):
    def __init__(self, root: Path, query: str, generation: int, cancelled: Event):
        super().__init__()
        self.root, self.query, self.generation, self.cancelled = root, query, generation, cancelled
        self.signals = SearchSignals()

    def run(self) -> None:
        try:
            result = search_content(self.root, self.query, cancelled=self.cancelled.is_set)
            error = ""
        except Exception as exc:
            result, error = {}, str(exc)
        if not self.cancelled.is_set():
            self.signals.finished.emit(self.generation, result, error)


class SearchPanel(QWidget):
    resultActivated = pyqtSignal(object, object, str)  # root, result, query

    def __init__(self, parent=None):
        super().__init__(parent)
        self.root: Path | None = None
        self._generation = 0
        self._cancelled = Event()
        self._query = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText("Search Markdown contents…")
        self.edit.setAccessibleName("Search folder contents")
        self.edit.setClearButtonEnabled(True)
        self.scope = QLabel("Open a folder to search", self)
        self.scope.setWordWrap(True)
        self.status = QLabel("Enter at least 2 characters", self)
        self.results = QListWidget(self)
        self.results.setAccessibleName("Content search results")
        self.results.setWordWrap(True)
        for widget in (self.edit, self.scope, self.status, self.results):
            layout.addWidget(widget)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._start_search)
        self.edit.textChanged.connect(self.refresh)
        self.results.itemActivated.connect(self._activate)
        self.results.itemClicked.connect(self._activate)

    def set_root(self, root: Path) -> None:
        self.root = root
        self.scope.setText(str(root))
        self.scope.setToolTip(str(root))
        self.refresh()

    def refresh(self) -> None:
        self.cancel()
        self.results.clear()
        if self.root is None:
            self.status.setText("Open a folder to search")
        elif len(self.edit.text()) < 2:
            self.status.setText("Enter at least 2 characters")
        else:
            self.status.setText("Searching…")
            self._timer.start()

    def cancel(self) -> None:
        self._timer.stop()
        self._cancelled.set()
        self._generation += 1

    def _start_search(self) -> None:
        if self.root is None or len(self.edit.text()) < 2:
            return
        self._cancelled = Event()
        self._query = self.edit.text()
        worker = SearchWorker(self.root, self._query, self._generation, self._cancelled)
        worker.signals.finished.connect(self._finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)

    def _finished(self, generation: int, result: dict, error: str) -> None:
        if generation != self._generation:
            return
        self.results.clear()
        if error:
            self.status.setText(f"search failed: {error}")
            return
        for hit in result["results"]:
            item = QListWidgetItem(f"{hit['path']}:{hit['line_number']}\n{hit['snippet']}")
            item.setData(Qt.ItemDataRole.UserRole, hit)
            item.setToolTip(item.text())
            self.results.addItem(item)
        count = self.results.count()
        self.status.setText(
            "Showing first 50 matches" if result["truncated"] else
            (f"{count} matching lines" if count else "No matches")
        )

    def _activate(self, item: QListWidgetItem) -> None:
        if self.root is not None:
            self.resultActivated.emit(self.root, item.data(Qt.ItemDataRole.UserRole), self._query)

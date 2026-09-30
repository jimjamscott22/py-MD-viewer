"""Sidebar tree of Markdown files, built from ``md_preview_core.files``.

Uses the same scan as the web sidebar (``scan_files``), so excluded folders
(``.git``, ``node_modules``, ``.venv``…) and folders with no Markdown are
hidden exactly as they are in the browser.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QModelIndex, QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QAbstractItemView, QApplication, QMenu, QTreeView

from md_preview_core.files import build_file_tree

PATH_ROLE = Qt.ItemDataRole.UserRole + 1
IS_DIR_ROLE = Qt.ItemDataRole.UserRole + 2


class FileTree(QTreeView):
    """Click/Enter opens in the current tab; middle-click or Ctrl+click in a new one."""

    fileActivated = pyqtSignal(str)  # relative posix path
    fileActivatedInNewTab = pyqtSignal(str)
    createRequested = pyqtSignal(object, str)  # root + relative directory (empty for root)
    renameRequested = pyqtSignal(object, str)
    trashRequested = pyqtSignal(object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = QStandardItemModel(self)
        self.setModel(self._model)
        self.setHeaderHidden(True)
        self.setUniformRowHeights(True)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAccessibleName("Files")
        self.activated.connect(self._on_activated)
        self.clicked.connect(self._on_activated)
        self._base_dir: Path | None = None
        self._filter_text = ""
        self._expanded_before_filter: set[str] = set()
        self._selection_path: str | None = None
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def context_menu(self, index: QModelIndex) -> QMenu:
        # Capture paths now: watcher rebuilds can invalidate the index while
        # the menu is open. No selection change or document navigation needed.
        path = index.data(PATH_ROLE) if index.isValid() else ""
        root = self._base_dir
        is_file = index.isValid() and not index.data(IS_DIR_ROLE)
        directory = Path(path).parent.as_posix() if is_file else path
        if directory == ".":
            directory = ""
        menu = QMenu(self)
        create = menu.addAction("New Markdown File…")
        create.setEnabled(self._base_dir is not None)
        create.triggered.connect(lambda: self.createRequested.emit(root, directory))
        menu.addSeparator()
        rename = menu.addAction("Rename…")
        rename.setEnabled(is_file)
        rename.triggered.connect(lambda: self.renameRequested.emit(root, path))
        trash = menu.addAction("Move to Trash…")
        trash.setEnabled(is_file)
        trash.triggered.connect(lambda: self.trashRequested.emit(root, path))
        return menu

    def _show_context_menu(self, position: QPoint) -> None:
        menu = self.context_menu(self.indexAt(position))
        menu.exec(self.viewport().mapToGlobal(position))
        menu.deleteLater()

    @property
    def base_dir(self) -> Path | None:
        return self._base_dir

    def set_base_dir(self, base_dir: Path | None) -> None:
        self._base_dir = base_dir
        self._expanded_before_filter.clear()
        self._selection_path = None
        self.rebuild(keep_expanded=False)

    def rebuild(self, *, keep_expanded: bool = True) -> None:
        expanded = set()
        selected = None
        if keep_expanded:
            expanded = self._expanded_before_filter if self._filter_text else self._expanded_paths()
            selected = self.selected_path() or self._selection_path
        self._model.clear()
        if self._base_dir is None:
            return
        self._add_nodes(self._model.invisibleRootItem(), build_file_tree(self._base_dir), "")
        for path in expanded:
            index = self._find(path)
            if index.isValid():
                self.expand(index)
        self._apply_filter()
        if selected:
            self.select_path(selected)

    def set_filter_text(self, text: str) -> None:
        """Match literal, case-insensitive relative paths without rescanning disk."""
        text = text.casefold()
        if text == self._filter_text:
            return
        if not self._filter_text:
            self._expanded_before_filter = self._expanded_paths()
            self._selection_path = self.selected_path() or self._selection_path
        self._filter_text = text
        self._apply_filter()
        if not text:
            self.collapseAll()
            for path in self._expanded_before_filter:
                index = self._find(path)
                if index.isValid():
                    self.expand(index)
            self._expanded_before_filter.clear()
        self.select_path(self._selection_path)

    def _apply_filter(self, parent: QStandardItem | None = None) -> bool:
        parent = parent if parent is not None else self._model.invisibleRootItem()
        any_match = False
        for row in range(parent.rowCount()):
            item = parent.child(row)
            if item.data(IS_DIR_ROLE):
                matches = self._apply_filter(item)
            else:
                matches = self._filter_text in item.data(PATH_ROLE).casefold()
            self.setRowHidden(row, item.index().parent(), not matches)
            if self._filter_text and matches and item.data(IS_DIR_ROLE):
                self.expand(item.index())
            any_match = any_match or matches
        return any_match

    def _add_nodes(self, parent: QStandardItem, tree: dict, prefix: str) -> None:
        dirs = sorted((k for k, v in tree.items() if isinstance(v, dict)), key=str.lower)
        files = sorted((k for k, v in tree.items() if not isinstance(v, dict)), key=str.lower)
        for name in dirs:
            item = QStandardItem(name)
            path = f"{prefix}{name}"
            item.setData(path, PATH_ROLE)
            item.setData(True, IS_DIR_ROLE)
            item.setToolTip(path)
            parent.appendRow(item)
            self._add_nodes(item, tree[name], f"{path}/")
        for name in files:
            item = QStandardItem(name)
            item.setData(tree[name], PATH_ROLE)
            item.setData(False, IS_DIR_ROLE)
            item.setToolTip(tree[name])
            parent.appendRow(item)

    def _iter_items(self, parent: QStandardItem | None = None):
        parent = parent or self._model.invisibleRootItem()
        for row in range(parent.rowCount()):
            child = parent.child(row)
            yield child
            yield from self._iter_items(child)

    def _find(self, rel_path: str) -> QModelIndex:
        for item in self._iter_items():
            if item.data(PATH_ROLE) == rel_path:
                return item.index()
        return QModelIndex()

    def _expanded_paths(self) -> set[str]:
        return {
            item.data(PATH_ROLE)
            for item in self._iter_items()
            if item.data(IS_DIR_ROLE) and self.isExpanded(item.index())
        }

    def selected_path(self) -> str | None:
        indexes = self.selectedIndexes()
        if not indexes or indexes[0].data(IS_DIR_ROLE):
            return None
        return indexes[0].data(PATH_ROLE)

    def select_path(self, rel_path: str | None) -> None:
        self._selection_path = rel_path
        if rel_path is None:
            self.clearSelection()
            self.setCurrentIndex(QModelIndex())
            return
        index = self._find(rel_path)
        if not index.isValid() or self.isRowHidden(index.row(), index.parent()):
            self.clearSelection()
            self.setCurrentIndex(QModelIndex())
            return
        parent = index.parent()
        while parent.isValid():
            self.expand(parent)
            parent = parent.parent()
        self.setCurrentIndex(index)
        self.scrollTo(index)

    def file_paths(self) -> list[str]:
        return [item.data(PATH_ROLE) for item in self._iter_items() if not item.data(IS_DIR_ROLE)]

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt API)
        if event.button() == Qt.MouseButton.MiddleButton:
            index = self.indexAt(event.position().toPoint())
            if index.isValid() and not index.data(IS_DIR_ROLE):
                self.fileActivatedInNewTab.emit(index.data(PATH_ROLE))
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def _on_activated(self, index: QModelIndex) -> None:
        if not index.isValid() or index.data(IS_DIR_ROLE):
            return
        if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier:
            self.fileActivatedInNewTab.emit(index.data(PATH_ROLE))
        else:
            self.fileActivated.emit(index.data(PATH_ROLE))

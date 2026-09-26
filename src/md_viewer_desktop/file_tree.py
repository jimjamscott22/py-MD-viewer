"""Sidebar tree of Markdown files, built from ``md_preview_core.files``.

Uses the same scan as the web sidebar (``scan_files``), so excluded folders
(``.git``, ``node_modules``, ``.venv``…) and folders with no Markdown are
hidden exactly as they are in the browser.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QModelIndex, Qt, pyqtSignal
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import QAbstractItemView, QTreeView

from md_preview_core.files import build_file_tree

PATH_ROLE = Qt.ItemDataRole.UserRole + 1
IS_DIR_ROLE = Qt.ItemDataRole.UserRole + 2


class FileTree(QTreeView):
    fileActivated = pyqtSignal(str)  # relative posix path

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

    @property
    def base_dir(self) -> Path | None:
        return self._base_dir

    def set_base_dir(self, base_dir: Path | None) -> None:
        self._base_dir = base_dir
        self.rebuild(keep_expanded=False)

    def rebuild(self, *, keep_expanded: bool = True) -> None:
        expanded = self._expanded_paths() if keep_expanded else set()
        selected = self.selected_path()
        self._model.clear()
        if self._base_dir is None:
            return
        self._add_nodes(self._model.invisibleRootItem(), build_file_tree(self._base_dir), "")
        for path in expanded:
            index = self._find(path)
            if index.isValid():
                self.expand(index)
        if selected:
            self.select_path(selected)

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
        if rel_path is None:
            self.clearSelection()
            return
        index = self._find(rel_path)
        if not index.isValid():
            self.clearSelection()
            return
        parent = index.parent()
        while parent.isValid():
            self.expand(parent)
            parent = parent.parent()
        self.setCurrentIndex(index)
        self.scrollTo(index)

    def file_paths(self) -> list[str]:
        return [item.data(PATH_ROLE) for item in self._iter_items() if not item.data(IS_DIR_ROLE)]

    def _on_activated(self, index: QModelIndex) -> None:
        if index.isValid() and not index.data(IS_DIR_ROLE):
            self.fileActivated.emit(index.data(PATH_ROLE))

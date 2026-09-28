"""Contents dock: the current document's headings as a tree.

Headings are read from the rendered page (``window.mdviewHeadings()`` in
``page.js``), so the tree always matches what is on screen, including after
a live reload. Clicking a heading scrolls the page to it.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QAbstractItemView, QTreeWidget, QTreeWidgetItem

ANCHOR_ROLE = Qt.ItemDataRole.UserRole + 1


class TocPanel(QTreeWidget):
    headingActivated = pyqtSignal(str)  # heading id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setUniformRowHeights(True)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAccessibleName("Contents")
        self.itemActivated.connect(self._on_item)
        self.itemClicked.connect(self._on_item)

    def set_headings(self, headings: list[tuple[int, str, str]]) -> None:
        """Rebuild from ``(level, id, text)`` tuples in document order."""
        self.clear()
        # Stack of (level, item); a heading nests under the nearest shallower one.
        stack: list[tuple[int, QTreeWidgetItem]] = []
        for level, anchor, text in headings:
            while stack and stack[-1][0] >= level:
                stack.pop()
            item = QTreeWidgetItem([text])
            item.setData(0, ANCHOR_ROLE, anchor)
            item.setToolTip(0, text)
            if stack:
                stack[-1][1].addChild(item)
            else:
                self.addTopLevelItem(item)
            stack.append((level, item))
        self.expandAll()

    def anchors(self) -> list[str]:
        """Heading ids in tree (document) order."""
        result = []

        def walk(item: QTreeWidgetItem) -> None:
            result.append(item.data(0, ANCHOR_ROLE))
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.topLevelItemCount()):
            walk(self.topLevelItem(i))
        return result

    def _on_item(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        self.headingActivated.emit(item.data(0, ANCHOR_ROLE))

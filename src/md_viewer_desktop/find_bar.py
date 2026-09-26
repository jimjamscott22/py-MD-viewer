"""Find-in-page bar (Ctrl+F) over ``QWebEnginePage.findText``."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QToolButton, QWidget

from .theme import Theme


class FindLineEdit(QLineEdit):
    """Enter → next, Shift+Enter → previous, Esc → close."""

    nextRequested = pyqtSignal()
    previousRequested = pyqtSignal()
    closeRequested = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt API)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.previousRequested.emit()
            else:
                self.nextRequested.emit()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.closeRequested.emit()
            return
        super().keyPressEvent(event)


class FindBar(QWidget):
    """Search box + match count + previous/next/close.

    Emits ``findRequested(text, backward)``; the window runs the search on
    the current tab and reports back through :meth:`set_result`.
    """

    findRequested = pyqtSignal(str, bool)  # text, backward
    closed = pyqtSignal()

    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.setObjectName("find-bar")
        layout = QHBoxLayout(self)
        pad = theme.space["space-2"]
        layout.setContentsMargins(pad, pad, pad, pad)
        layout.setSpacing(theme.space["space-2"])

        self.edit = FindLineEdit(self)
        self.edit.setPlaceholderText("find in page")
        self.edit.setAccessibleName("Find in page")
        self.edit.setClearButtonEnabled(True)
        self.edit.textChanged.connect(lambda text: self.findRequested.emit(text, False))
        self.edit.nextRequested.connect(self.find_next)
        self.edit.previousRequested.connect(self.find_previous)
        self.edit.closeRequested.connect(self.close_bar)

        self.count_label = QLabel(self)
        self.count_label.setObjectName("find-count")
        self.count_label.setMinimumWidth(theme.space["space-6"] * 4)

        self.prev_button = self._button("previous match (Shift+Enter)", self.find_previous)
        self.next_button = self._button("next match (Enter)", self.find_next)
        self.close_button = self._button("close (Esc)", self.close_bar)

        layout.addWidget(self.edit, 1)
        layout.addWidget(self.count_label)
        layout.addWidget(self.prev_button)
        layout.addWidget(self.next_button)
        layout.addWidget(self.close_button)
        self.hide()

    def _button(self, tooltip: str, slot) -> QToolButton:
        button = QToolButton(self)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip.split(" (")[0])
        button.setAutoRaise(True)
        button.clicked.connect(slot)
        return button

    def set_icons(self, previous, following, close) -> None:
        self.prev_button.setIcon(previous)
        self.next_button.setIcon(following)
        self.close_button.setIcon(close)

    @property
    def text(self) -> str:
        return self.edit.text()

    def open_bar(self) -> None:
        self.show()
        self.edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.edit.selectAll()
        if self.text:
            self.findRequested.emit(self.text, False)

    def close_bar(self) -> None:
        self.hide()
        self._set_count("", "")
        self.closed.emit()

    def find_next(self) -> None:
        if self.isHidden():
            self.open_bar()
            return
        self.findRequested.emit(self.text, False)

    def find_previous(self) -> None:
        if self.isHidden():
            self.open_bar()
            return
        self.findRequested.emit(self.text, True)

    def set_result(self, active: int, total: int) -> None:
        if not self.text:
            self._set_count("", "")
        elif total == 0:
            self._set_count("no matches", "warning")
        else:
            self._set_count(f"{active}/{total}", "")

    def _set_count(self, text: str, state: str) -> None:
        self.count_label.setText(text)
        if self.count_label.property("state") != state:
            self.count_label.setProperty("state", state)
            self.count_label.style().unpolish(self.count_label)
            self.count_label.style().polish(self.count_label)

"""Markdown source editor: ``QPlainTextEdit`` + a small syntax highlighter."""

from __future__ import annotations

import re

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat, QTextDocument
from PyQt6.QtWidgets import QPlainTextEdit

from .theme import FONT_FAMILY, Theme

_FENCE_RE = re.compile(r"^\s{0,3}(```|~~~)")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}(\s|$)")
_QUOTE_RE = re.compile(r"^\s{0,3}>")
_LIST_RE = re.compile(r"^\s*([-*+]|\d+[.)])\s")
_RULE_RE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_INLINE_RULES = (
    ("code", re.compile(r"`[^`\n]+`")),
    ("bold", re.compile(r"(\*\*|__)(?=\S).+?(?<=\S)\1")),
    ("italic", re.compile(r"(?<![*\w])(\*|_)(?=[^\s*_]).+?(?<=[^\s*_])\1(?![*\w])")),
    ("link", re.compile(r"!?\[[^\]\n]*\]\([^)\n]*\)")),
)
_IN_FENCE = 1


class MarkdownHighlighter(QSyntaxHighlighter):
    """Colours Markdown syntax using jamielab tokens (no hand-typed hex)."""

    def __init__(self, document: QTextDocument, theme: Theme):
        super().__init__(document)
        color = theme.color

        def fmt(token: str, *, bold: bool = False, italic: bool = False) -> QTextCharFormat:
            f = QTextCharFormat()
            f.setForeground(QColor(color[token]))
            if bold:
                f.setFontWeight(QFont.Weight.DemiBold)
            f.setFontItalic(italic)
            return f

        self._formats = {
            "heading": fmt("phosphor", bold=True),
            "marker": fmt("phosphor"),
            "quote": fmt("ink-muted", italic=True),
            "rule": fmt("ink-muted"),
            "fence": fmt("ink-muted"),
            "fenced": fmt("teal"),
            "code": fmt("teal"),
            "bold": fmt("ink", bold=True),
            "italic": fmt("ink", italic=True),
            "link": fmt("teal"),
        }

    def highlightBlock(self, text: str) -> None:  # noqa: N802 (Qt API)
        in_fence = self.previousBlockState() == _IN_FENCE
        if _FENCE_RE.match(text):
            self.setFormat(0, len(text), self._formats["fence"])
            self.setCurrentBlockState(0 if in_fence else _IN_FENCE)
            return
        if in_fence:
            self.setFormat(0, len(text), self._formats["fenced"])
            self.setCurrentBlockState(_IN_FENCE)
            return
        self.setCurrentBlockState(0)

        if _HEADING_RE.match(text):
            self.setFormat(0, len(text), self._formats["heading"])
            return
        if _RULE_RE.match(text):
            self.setFormat(0, len(text), self._formats["rule"])
            return
        if _QUOTE_RE.match(text):
            self.setFormat(0, len(text), self._formats["quote"])
        elif (match := _LIST_RE.match(text)) is not None:
            self.setFormat(match.start(1), match.end(1) - match.start(1), self._formats["marker"])
        for name, pattern in _INLINE_RULES:
            for found in pattern.finditer(text):
                self.setFormat(found.start(), found.end() - found.start(), self._formats[name])


class MarkdownEditor(QPlainTextEdit):
    """Plain-text editor for one document.

    ``base_revision`` is the on-disk revision the buffer was loaded from or
    last saved as; it is what the save guard compares against.
    """

    def __init__(self, text: str, revision: str, theme: Theme, parent=None):
        super().__init__(parent)
        self.base_revision = revision
        self.setAccessibleName("Markdown source")
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        font = QFont(FONT_FAMILY)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPixelSize(theme.type["code"].size)
        self.setFont(font)
        self.setCursorWidth(2)
        self.setPlainText(text)
        self.document().setModified(False)
        self._highlighter = MarkdownHighlighter(self.document(), theme)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    @property
    def dirty(self) -> bool:
        return self.document().isModified()

    def set_clean(self, revision: str) -> None:
        self.base_revision = revision
        self.document().setModified(False)

    def replace_from_disk(self, text: str, revision: str) -> None:
        """Replace the buffer with disk content (drops the undo history)."""
        self.setPlainText(text)
        self.set_clean(revision)

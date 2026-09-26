"""Lucide icons (ISC, vendored in ``resources/icons/lucide``), recoloured at load.

The SVGs draw with ``stroke="currentColor"``. :func:`icon` swaps that for a
colour per ``QIcon`` mode and thins the stroke to 1.5, so the chrome never
carries a hand-typed hex: colours come from the :class:`~.theme.Theme`, or
from the palette when the chrome is stock Fusion (Paper theme).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QByteArray, QSize
from PyQt6.QtGui import QIcon, QPalette, QPixmap

from .theme import APP_ICON_PATH, RESOURCES, Theme

LUCIDE_DIR = RESOURCES / "icons" / "lucide"
ICON_SIZE = 16
STROKE_WIDTH = "1.5"


@dataclass(frozen=True)
class IconColors:
    normal: str  # idle
    active: str  # hover
    selected: str  # checked / pressed
    disabled: str

    @classmethod
    def from_theme(cls, t: Theme) -> "IconColors":
        c = t.color
        return cls(normal=c["ink-muted"], active=c["ink"], selected=c["phosphor"], disabled=c["edge"])

    @classmethod
    def from_palette(cls, pal: QPalette) -> "IconColors":
        Role, Group = QPalette.ColorRole, QPalette.ColorGroup
        return cls(
            normal=pal.color(Role.WindowText).name(),
            active=pal.color(Role.WindowText).name(),
            selected=pal.color(Role.Highlight).name(),
            disabled=pal.color(Group.Disabled, Role.WindowText).name(),
        )


def icon_path(name: str) -> Path:
    return LUCIDE_DIR / f"{name}.svg"


def recolor(svg: str, color: str) -> str:
    """Return ``svg`` drawn in ``color`` with the jamielab stroke width."""
    return svg.replace("currentColor", color).replace('stroke-width="2"', f'stroke-width="{STROKE_WIDTH}"')


def _pixmap(svg: str, size: int) -> QPixmap:
    pixmap = QPixmap()
    pixmap.loadFromData(QByteArray(svg.encode()), "SVG")
    return pixmap.scaled(QSize(size, size)) if pixmap.width() != size else pixmap


def _svg_with_size(svg: str, size: int) -> str:
    return svg.replace('width="24"', f'width="{size}"').replace('height="24"', f'height="{size}"')


def icon(name: str, colors: IconColors) -> QIcon:
    """Build a ``QIcon`` for Lucide icon ``name`` with per-mode colours."""
    source = icon_path(name).read_text(encoding="utf-8")
    result = QIcon()
    modes = (
        (QIcon.Mode.Normal, colors.normal),
        (QIcon.Mode.Active, colors.active),
        (QIcon.Mode.Selected, colors.selected),
        (QIcon.Mode.Disabled, colors.disabled),
    )
    for mode, color in modes:
        svg = recolor(source, color)
        for size in (ICON_SIZE, ICON_SIZE * 2):  # 2x for HiDPI
            result.addPixmap(_pixmap(_svg_with_size(svg, size), size), mode, QIcon.State.Off)
        if mode is QIcon.Mode.Normal:
            # Checked toggles (e.g. the TOC button) show phosphor.
            on = recolor(source, colors.selected)
            for size in (ICON_SIZE, ICON_SIZE * 2):
                result.addPixmap(_pixmap(_svg_with_size(on, size), size), mode, QIcon.State.On)
    return result


def app_icon() -> QIcon:
    return QIcon(str(APP_ICON_PATH))

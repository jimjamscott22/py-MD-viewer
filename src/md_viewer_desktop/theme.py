"""jamielab design tokens → document CSS, Qt stylesheet and palette.

``resources/design/jamielab.tokens.json`` is the single source of truth.
Nothing downstream hand-types a hex value: the CSS variables for the
rendered document, the QSS for the chrome and the ``QPalette`` are all
built from a :class:`Theme` loaded from that file.

Regenerate the checked-in document CSS after editing the tokens::

    uv run python -m md_viewer_desktop.theme
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from PyQt6.QtGui import QPalette
    from PyQt6.QtWidgets import QApplication

RESOURCES = Path(__file__).resolve().parent / "resources"
TOKENS_PATH = RESOURCES / "design" / "jamielab.tokens.json"
GENERATED_CSS_PATH = RESOURCES / "css" / "theme-jamielab.css"

REQUIRED_COLORS = (
    "ground",
    "panel",
    "hairline",
    "edge",
    "ink",
    "ink-muted",
    "phosphor",
    "teal",
    "amber",
    "danger",
)
REQUIRED_TYPE = ("display", "h1", "h2", "body", "code", "small", "label")
REQUIRED_SPACE = ("space-1", "space-2", "space-4", "space-6")
REQUIRED_RADIUS = ("radius-none", "radius-sm", "radius-md")

FONT_FAMILY = "IBM Plex Mono"
FONT_STACK = '"IBM Plex Mono", ui-monospace, monospace'

# (file stem, CSS weight, CSS style) for the vendored Plex Mono faces.
FONT_FACES = (
    ("IBMPlexMono-Regular", 400, "normal"),
    ("IBMPlexMono-Italic", 400, "italic"),
    ("IBMPlexMono-Medium", 500, "normal"),
    ("IBMPlexMono-SemiBold", 600, "normal"),
)


class ThemeError(ValueError):
    """Raised when a tokens file is missing or malformed."""


@dataclass(frozen=True)
class TextStyle:
    size: int
    line: int
    weight: int


@dataclass(frozen=True)
class Theme:
    name: str
    color: dict[str, str]
    space: dict[str, int]
    radius: dict[str, int]
    type: dict[str, TextStyle]


def _px(value: str | int, label: str) -> int:
    if isinstance(value, int):
        return value
    match = re.fullmatch(r"\s*(\d+)(?:px)?\s*", str(value))
    if not match:
        raise ThemeError(f"{label}: expected a pixel value, got {value!r}")
    return int(match.group(1))


def _require(found: dict, required: tuple[str, ...], group: str) -> None:
    missing = [name for name in required if name not in found]
    if missing:
        raise ThemeError(f"missing {group} token(s): {', '.join(missing)}")


def load_theme(path: Path = TOKENS_PATH) -> Theme:
    """Load and validate a jamielab-format tokens file."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ThemeError(f"cannot read tokens file {path}: {exc}") from exc

    try:
        color = {t["name"]: t["value"] for t in data["color"]["tokens"]}
        space = {t["name"]: _px(t["value"], t["name"]) for t in data["spacing"]["tokens"]}
        radius = {t["name"]: _px(t["value"], t["name"]) for t in data["radius"]["tokens"]}
        type_styles = {
            style["name"]: TextStyle(
                size=_px(style["fontSize"], style["name"]),
                line=_px(style["lineHeight"], style["name"]),
                weight=int(style["fontWeight"]),
            )
            for group in data["type"]["groups"]
            for style in group["styles"]
        }
    except (KeyError, TypeError) as exc:
        raise ThemeError(f"malformed tokens file {path}: {exc}") from exc

    _require(color, REQUIRED_COLORS, "color")
    _require(type_styles, REQUIRED_TYPE, "type")
    _require(space, REQUIRED_SPACE, "spacing")
    _require(radius, REQUIRED_RADIUS, "radius")
    for name in REQUIRED_COLORS:
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color[name]):
            raise ThemeError(f"color token {name} must be #rrggbb, got {color[name]!r}")

    return Theme(
        name=data.get("name", "jamielab"),
        color=color,
        space=space,
        radius=radius,
        type=type_styles,
    )


# ── Contrast (WCAG 2.x) ─────────────────────────────────────────────


def relative_luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted(
        (relative_luminance(foreground), relative_luminance(background)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


# ── Rendered document CSS ───────────────────────────────────────────


def css_variables(t: Theme) -> str:
    """Return the ``theme-jamielab.css`` stylesheet for the web view.

    Maps tokens onto the variables ``style.css`` already uses, so no
    selector in ``style.css`` has to change.
    """
    c = t.color
    ty = t.type
    root = f':root[data-theme="{t.name}"]'
    variables = {
        # Raw tokens, for rules below and for page scripts.
        **{f"--{name}": c[name] for name in REQUIRED_COLORS},
        "--color-bg": c["ground"],
        "--color-sidebar-bg": c["ground"],
        "--color-bg-accent": c["panel"],
        "--color-surface": c["panel"],
        "--color-surface-strong": c["panel"],
        "--color-code-bg": c["panel"],
        "--color-table-alt": c["panel"],
        "--color-border": c["hairline"],
        "--color-border-strong": c["edge"],
        "--color-blockquote-border": c["edge"],
        "--color-text": c["ink"],
        "--color-text-secondary": c["ink-muted"],
        "--color-link": c["teal"],
        "--color-accent": c["phosphor"],
        "--color-accent-strong": c["phosphor"],
        "--color-success": c["phosphor"],
        "--color-danger": c["danger"],
        "--font-display": FONT_STACK,
        "--font-body": FONT_STACK,
        "--font-mono": FONT_STACK,
        "--font-prose": FONT_STACK,
        "--color-shadow": "none",
        "--glow-sm": "none",
        "--glow-md": "none",
        "--scanline": "none",
        "--gradient-page": c["ground"],
        "--gradient-accent": c["phosphor"],
    }

    lines = [
        "/* GENERATED by md_viewer_desktop.theme from jamielab.tokens.json.",
        "   Do not edit; run `uv run python -m md_viewer_desktop.theme`. */",
        "",
    ]
    for stem, weight, style in FONT_FACES:
        lines += [
            "@font-face {",
            f'    font-family: "{FONT_FAMILY}";',
            f'    src: url("mdview://app/fonts/{stem}.woff2") format("woff2");',
            f"    font-weight: {weight};",
            f"    font-style: {style};",
            "    font-display: block;",
            "}",
        ]
    lines += ["", f"{root} {{"]
    lines += [f"    {name}: {value};" for name, value in variables.items()]
    lines += ["}", ""]

    def text_rule(selector: str, style: TextStyle) -> list[str]:
        return [
            f"{selector} {{",
            f"    font-size: {style.size}px;",
            f"    line-height: {style.line}px;",
            f"    font-weight: {style.weight};",
            "}",
        ]

    lines += [
        f"{root} html {{ font-size: {ty['body'].size}px; }}",
        f"{root} body {{ background: {c['ground']}; }}",
        f"{root} .surface-panel {{ box-shadow: none; border-radius: {t.radius['radius-md']}px; }}",
        f"{root} .surface-panel::before {{ display: none; }}",
    ]
    lines += text_rule(f"{root} .markdown-body", ty["body"])
    lines += text_rule(f"{root} .markdown-body h1", ty["h1"])
    lines += text_rule(f"{root} .markdown-body h2", ty["h2"])
    lines += text_rule(f"{root} .markdown-body code,\n{root} .markdown-body pre", ty["code"])
    lines += [
        f"{root} .markdown-body pre code {{ font-size: inherit; line-height: inherit; }}",
        f"{root} .markdown-body pre,",
        f"{root} .codehilite {{",
        f"    background: {c['panel']};",
        f"    border-radius: {t.radius['radius-none']}px;",
        f"    padding: {t.space['space-4']}px;",
        "}",
        f"{root} .codehilite pre {{ padding: 0; border: 0; margin: 0; }}",
        f"{root} .doc-meta, {root} .frontmatter-item dt {{",
        f"    font-size: {ty['label'].size}px;",
        f"    line-height: {ty['label'].line}px;",
        f"    font-weight: {ty['label'].weight};",
        "}",
        f"{root} :focus-visible {{ outline: 2px solid {c['phosphor']}; outline-offset: 2px; }}",
        f"{root} ::selection {{ background: {c['phosphor']}; color: {c['ground']}; }}",
        "",
    ]
    return "\n".join(lines)


def write_generated_css(t: Theme, path: Path = GENERATED_CSS_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(css_variables(t), encoding="utf-8")
    return path


# ── Qt chrome ───────────────────────────────────────────────────────

_QSS_TEMPLATE = """
* {{ font-family: "{family}"; font-size: {body_size}px; }}
QMainWindow, QDockWidget {{ background: {ground}; color: {ink}; }}
QDockWidget::title {{ background: {panel}; padding: {space_2}px {space_4}px;
                     font-size: {label_size}px; font-weight: 500; }}
QSplitter::handle, QMainWindow::separator {{ background: {hairline}; width: 1px; height: 1px; }}
QTreeView, QListView, QPlainTextEdit, QLineEdit {{
  background: {panel}; color: {ink}; border: 1px solid {edge}; border-radius: {radius_sm}px;
  selection-background-color: {phosphor}; selection-color: {ground}; }}
QTreeView::item {{ padding: {space_1}px {space_2}px; }}
QTreeView::item:hover {{ color: {teal}; }}
QTreeView::item:selected {{ background: {panel}; color: {teal}; border-left: 2px solid {teal}; }}
QLineEdit {{ padding: {space_2}px; }}
QLineEdit:focus, QPlainTextEdit:focus, QTreeView:focus {{ border: 2px solid {phosphor}; }}
QPushButton {{ background: {panel}; color: {ink}; border: 1px solid {edge};
              border-radius: {radius_sm}px; padding: {space_2}px {space_4}px; }}
QPushButton:hover {{ border-color: {ink_muted}; }}
QPushButton:focus {{ border: 2px solid {phosphor}; }}
QPushButton[primary="true"] {{ background: {phosphor}; color: {ground}; border-color: {phosphor}; font-weight: 600; }}
QPushButton[danger="true"]  {{ color: {danger}; border-color: {danger}; }}
QTabBar::tab {{ background: {ground}; color: {ink_muted}; padding: {space_2}px {space_4}px;
               border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {ink}; border-bottom-color: {phosphor}; }}
QMenuBar, QMenu, QStatusBar {{ background: {panel}; color: {ink}; }}
QMenuBar::item:selected {{ background: {ground}; color: {phosphor}; }}
QMenu {{ border: 1px solid {edge}; }} QMenu::item:selected {{ background: {phosphor}; color: {ground}; }}
QMenu::item:disabled {{ color: {ink_muted}; }}
QStatusBar {{ color: {ink_muted}; font-size: {small_size}px; border-top: 1px solid {hairline}; }}
QStatusBar QLabel {{ color: {ink_muted}; font-size: {small_size}px; padding: 0 {space_2}px; }}
QLabel[state="warning"] {{ color: {amber}; }}
QLabel[state="error"] {{ color: {danger}; }}
QToolTip {{ background: {panel}; color: {ink}; border: 1px solid {edge}; }}
QScrollBar:vertical {{ background: {ground}; width: 10px; }}
QScrollBar::handle:vertical {{ background: {edge}; border-radius: {radius_sm}px; min-height: 24px; }}
QScrollBar:horizontal {{ background: {ground}; height: 10px; }}
QScrollBar::handle:horizontal {{ background: {edge}; border-radius: {radius_sm}px; min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
"""


def qss(t: Theme) -> str:
    """Fill the app stylesheet template from tokens."""
    values = {name.replace("-", "_"): value for name, value in t.color.items()}
    values.update({name.replace("-", "_"): value for name, value in t.space.items()})
    values.update({name.replace("-", "_"): value for name, value in t.radius.items()})
    values.update(
        family=FONT_FAMILY,
        body_size=t.type["body"].size,
        small_size=t.type["small"].size,
        label_size=t.type["label"].size,
    )
    return _QSS_TEMPLATE.format(**values).strip() + "\n"


def palette(t: Theme) -> "QPalette":
    from PyQt6.QtGui import QColor, QPalette

    c = {name: QColor(value) for name, value in t.color.items()}
    Role = QPalette.ColorRole
    Group = QPalette.ColorGroup
    pal = QPalette()
    assignments = {
        Role.Window: "ground",
        Role.AlternateBase: "ground",
        Role.Base: "panel",
        Role.Button: "panel",
        Role.ToolTipBase: "panel",
        Role.WindowText: "ink",
        Role.Text: "ink",
        Role.ButtonText: "ink",
        Role.ToolTipText: "ink",
        Role.BrightText: "ink",
        Role.PlaceholderText: "ink-muted",
        Role.Highlight: "phosphor",
        Role.HighlightedText: "ground",
        Role.Link: "teal",
        Role.LinkVisited: "teal",
        Role.Mid: "edge",
        Role.Dark: "edge",
        Role.Midlight: "hairline",
        Role.Light: "hairline",
        Role.Shadow: "ground",
    }
    for role, token in assignments.items():
        pal.setColor(role, c[token])
    for role in (Role.WindowText, Role.Text, Role.ButtonText):
        pal.setColor(Group.Disabled, role, c["ink-muted"])
    return pal


def load_fonts() -> list[str]:
    """Register the vendored Plex Mono faces with Qt. Returns loaded families."""
    from PyQt6.QtGui import QFontDatabase

    families: set[str] = set()
    for stem, _, _ in FONT_FACES:
        font_id = QFontDatabase.addApplicationFont(str(RESOURCES / "fonts" / f"{stem}.woff"))
        if font_id >= 0:
            families.update(QFontDatabase.applicationFontFamilies(font_id))
    return sorted(families)


def apply(app: "QApplication", t: Theme) -> None:
    """Fusion style + palette + QSS + default font."""
    from PyQt6.QtGui import QFont

    app.setStyle("Fusion")
    app.setPalette(palette(t))
    app.setStyleSheet(qss(t))
    font = QFont(FONT_FAMILY)
    font.setPixelSize(t.type["body"].size)
    app.setFont(font)


def clear(app: "QApplication") -> None:
    """Drop jamielab styling, back to the stock Fusion light look."""
    app.setStyle("Fusion")
    app.setStyleSheet("")
    app.setPalette(app.style().standardPalette())


def main() -> int:
    path = write_generated_css(load_theme())
    print(f"wrote {path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

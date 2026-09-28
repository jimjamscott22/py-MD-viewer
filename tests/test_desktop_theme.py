"""jamielab theme generation. Pure Python: runs without the desktop extra."""

import json
import re
from pathlib import Path

import pytest

from md_viewer_desktop import theme
from md_viewer_desktop.theme import (
    REQUIRED_COLORS,
    ThemeError,
    contrast_ratio,
    css_variables,
    load_theme,
    qss,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def jamielab():
    return load_theme()


def test_load_theme_reads_all_tokens(jamielab):
    assert jamielab.name == "jamielab"
    assert jamielab.color["phosphor"] == "#39ff88"
    assert jamielab.space["space-4"] == 16
    assert jamielab.radius["radius-md"] == 4
    assert jamielab.type["body"].size == 15
    assert jamielab.type["h1"].weight == 600


def test_bundled_tokens_match_docs_snapshot():
    docs = json.loads((ROOT / "docs/design/jamielab.tokens.json").read_text())
    bundled = json.loads(theme.TOKENS_PATH.read_text())
    assert bundled == docs


@pytest.mark.parametrize("missing", ["amber", "space-2", "radius-sm", "label"])
def test_load_theme_rejects_missing_token(tmp_path, missing):
    data = json.loads(theme.TOKENS_PATH.read_text())
    data["color"]["tokens"] = [t for t in data["color"]["tokens"] if t["name"] != missing]
    data["spacing"]["tokens"] = [t for t in data["spacing"]["tokens"] if t["name"] != missing]
    data["radius"]["tokens"] = [t for t in data["radius"]["tokens"] if t["name"] != missing]
    for group in data["type"]["groups"]:
        group["styles"] = [s for s in group["styles"] if s["name"] != missing]
    path = tmp_path / "tokens.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ThemeError, match=missing):
        load_theme(path)


def test_load_theme_rejects_bad_color(tmp_path):
    data = json.loads(theme.TOKENS_PATH.read_text())
    data["color"]["tokens"][0]["value"] = "green"
    path = tmp_path / "tokens.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ThemeError, match="#rrggbb"):
        load_theme(path)


def test_qss_has_no_unfilled_placeholders(jamielab):
    stylesheet = qss(jamielab)
    assert not re.search(r"\{[a-z_\-]+\}", stylesheet)
    assert "#39ff88" in stylesheet


def test_generated_colors_all_come_from_tokens(jamielab):
    token_values = {value.lower() for value in jamielab.color.values()}
    for generated in (qss(jamielab), css_variables(jamielab)):
        used = {match.lower() for match in re.findall(r"#[0-9a-fA-F]{6}\b", generated)}
        assert used <= token_values


@pytest.mark.parametrize("background", ["ground", "panel"])
def test_contrast_guard(jamielab, background):
    c = jamielab.color
    assert contrast_ratio(c["ink"], c[background]) >= 4.5
    assert contrast_ratio(c["ink-muted"], c[background]) >= 4.5
    assert contrast_ratio(c["edge"], c[background]) >= 3
    assert contrast_ratio(c["phosphor"], c[background]) >= 3


def test_contrast_ratio_known_values():
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast_ratio("#777777", "#777777") == pytest.approx(1.0)


def test_css_maps_style_css_variables(jamielab):
    css = css_variables(jamielab)
    assert ':root[data-theme="jamielab"]' in css
    for name in REQUIRED_COLORS:
        assert f"--{name}: {jamielab.color[name]};" in css
    assert "--color-link: #2ec4b6;" in css
    assert '--font-prose: "IBM Plex Mono"' in css
    assert "--glow-sm: none;" in css
    assert "mdview://app/fonts/IBMPlexMono-Regular.woff2" in css


def test_generated_css_is_up_to_date(jamielab):
    on_disk = theme.GENERATED_CSS_PATH.read_text(encoding="utf-8")
    assert on_disk == css_variables(jamielab), (
        "theme-jamielab.css is stale; run `uv run python -m md_viewer_desktop.theme`"
    )


def test_vendored_fonts_exist():
    fonts = theme.RESOURCES / "fonts"
    for stem, _, _ in theme.FONT_FACES:
        assert (fonts / f"{stem}.woff").is_file()
        assert (fonts / f"{stem}.woff2").is_file()
    assert (fonts / "OFL.txt").is_file()


def test_codehilite_css_is_scoped_and_complete(jamielab):
    css = theme.codehilite_css(jamielab, ':root[data-theme="jamielab"] .codehilite')
    rules = [line for line in css.splitlines() if line.strip()]
    # Nothing unscoped (Pygments' bare `pre {}` / linenos rules would leak).
    assert all(line.startswith(':root[data-theme="jamielab"] .codehilite') for line in rules)
    # Bold/italic from codehilite.css is reset before the token rules.
    assert rules[0].endswith("* { font-weight: normal; font-style: normal }")
    c = {name: value.lower() for name, value in jamielab.color.items()}
    lowered = css.lower()
    assert f".codehilite .k {{ color: {c['phosphor']}" in lowered  # keyword
    assert f".codehilite .s2 {{ color: {c['amber']}" in lowered  # string
    assert f".codehilite .nf {{ color: {c['teal']}" in lowered  # function name
    assert f".codehilite .c {{ color: {c['ink-muted']}; font-style: italic" in lowered
    assert f".codehilite .err {{ color: {c['danger']}" in lowered
    # Tokens codehilite.css colours must be overridden, not left to leak.
    assert f".codehilite .nv {{ color: {c['ink']}" in lowered
    assert f".codehilite {{ background: {c['panel']}" in lowered


def test_generated_css_includes_code_style(jamielab):
    assert theme.codehilite_css(jamielab, ':root[data-theme="jamielab"] .codehilite') in css_variables(jamielab)


def test_app_icon_is_up_to_date(jamielab):
    svg = theme.APP_ICON_PATH.read_text(encoding="utf-8")
    assert svg == theme.app_icon_svg(jamielab), (
        "md-viewer.svg is stale; run `uv run python -m md_viewer_desktop.theme`"
    )
    assert jamielab.color["ground"] in svg and jamielab.color["phosphor"] in svg
    assert "<text" not in svg  # no font dependency on the host


def test_vendored_lucide_icons_exist():
    lucide = theme.RESOURCES / "icons" / "lucide"
    assert (lucide / "LICENSE").is_file()
    for name in ("search", "zoom-in", "zoom-out", "printer", "list-tree", "folder-open", "x"):
        svg = (lucide / f"{name}.svg").read_text(encoding="utf-8")
        assert 'stroke="currentColor"' in svg

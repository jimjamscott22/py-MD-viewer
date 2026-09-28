"""Contents panel, find in page, zoom, PDF export and icons."""

import pytest
from PyQt6 import sip
from PyQt6.QtGui import QIcon

from md_viewer_desktop import icons
from md_viewer_desktop.main_window import MainWindow
from md_viewer_desktop.theme import load_theme

LONG_DOC = (
    "# Guide\n\nintro\n\n## Install\n\nneedle one\n\n### Linux\n\ntext\n\n"
    + "filler\n\n" * 200
    + "## Usage\n\nneedle two and needle three\n\n```python\ndef f():\n    return 'x'\n```\n"
)


@pytest.fixture
def window(qapp, settings, tmp_path):
    (tmp_path / "guide.md").write_text(LONG_DOC, encoding="utf-8")
    win = MainWindow(qapp, load_theme(), settings)
    win.open_path(tmp_path / "guide.md")
    yield win
    win.close()
    sip.delete(win)


def loaded(window, helpers):
    return helpers.wait_until(
        lambda: window.view.url().path().endswith("guide.md")
        and helpers.run_js(window.view.page(), "document.readyState") == "complete"
    )


def test_toc_lists_nested_headings(window, helpers):
    assert loaded(window, helpers)
    assert helpers.wait_until(lambda: window.toc.anchors() == ["guide", "install", "linux", "usage"])
    top = window.toc.topLevelItem(0)
    assert top.text(0) == "Guide"
    assert [top.child(i).text(0) for i in range(top.childCount())] == ["Install", "Usage"]
    assert top.child(0).child(0).text(0) == "Linux"


def test_toc_click_scrolls_to_heading(window, helpers):
    assert loaded(window, helpers)
    assert helpers.wait_until(lambda: window.toc.anchors())
    window.toc.headingActivated.emit("usage")
    assert helpers.wait_until(lambda: helpers.run_js(window.view.page(), "window.scrollY") > 500)


def test_toc_clears_on_welcome(window, helpers):
    assert loaded(window, helpers)
    assert helpers.wait_until(lambda: window.toc.anchors())
    window.close_tab(0)
    assert window.toc.anchors() == []


def test_find_counts_matches_and_cycles(window, helpers):
    window.show()  # Chromium only searches a visible page
    assert loaded(window, helpers)
    window.find_bar.open_bar()
    assert not window.find_bar.isHidden()
    window.find_bar.edit.setText("needle")
    assert helpers.wait_until(lambda: window.find_bar.count_label.text() == "1/3")
    window.find_bar.find_next()
    assert helpers.wait_until(lambda: window.find_bar.count_label.text() == "2/3")
    window.find_bar.find_previous()
    assert helpers.wait_until(lambda: window.find_bar.count_label.text() == "1/3")
    window.find_bar.edit.setText("zzz-not-here")
    assert helpers.wait_until(lambda: window.find_bar.count_label.text() == "no matches")
    assert window.find_bar.count_label.property("state") == "warning"
    window.find_bar.close_bar()
    assert window.find_bar.isHidden()
    assert window.find_bar.count_label.text() == ""


def test_zoom_steps_apply_to_tabs_and_persist(window, settings, helpers, tmp_path):
    window.zoom_in()
    assert window.zoom == pytest.approx(1.1)
    assert window.view.zoomFactor() == pytest.approx(1.1)
    assert window.zoom_label.text() == "110%"
    window.zoom_out()
    window.zoom_out()
    assert window.zoom == pytest.approx(0.9)
    assert settings.zoom == pytest.approx(0.9)
    (tmp_path / "other.md").write_text("# other\n", encoding="utf-8")
    window.open_path(tmp_path / "other.md")
    assert window.view.zoomFactor() == pytest.approx(0.9)
    window.zoom_reset()
    assert window.zoom_label.text() == ""
    for _ in range(30):
        window.zoom_in()
    assert window.zoom == pytest.approx(3.0)


def test_export_pdf_writes_file_and_restores_theme(window, helpers, tmp_path):
    assert loaded(window, helpers)
    target = tmp_path / "out.pdf"
    window.export_pdf(target)
    assert helpers.wait_until(lambda: window.status_label.text() == "exported · out.pdf", 20000)
    assert target.read_bytes().startswith(b"%PDF")
    assert helpers.wait_until(
        lambda: helpers.run_js(window.view.page(), "document.documentElement.getAttribute('data-theme')")
        == "jamielab"
    )


def test_export_needs_a_document(window):
    window.close_tab(0)
    window.export_pdf(window.base_dir / "nothing.pdf")
    assert window.status_label.text() == "no document open"


def test_page_layout_is_a4_or_letter():
    layout = MainWindow.page_layout()
    assert layout.pageSize().id() in (layout.pageSize().PageSizeId.A4, layout.pageSize().PageSizeId.Letter)


def test_code_uses_jamielab_pygments_style(window, helpers):
    assert loaded(window, helpers)
    color = helpers.run_js(
        window.view.page(), "getComputedStyle(document.querySelector('.codehilite .k')).color"
    )
    assert color == "rgb(57, 255, 136)"  # phosphor


def test_icon_recolor_uses_theme_tokens():
    t = load_theme()
    svg = icons.recolor(icons.icon_path("search").read_text(), t.color["ink-muted"])
    assert "currentColor" not in svg
    assert t.color["ink-muted"] in svg
    assert 'stroke-width="1.5"' in svg


def test_icon_has_all_modes(qapp):
    icon = icons.icon("search", icons.IconColors.from_theme(load_theme()))
    for mode in (QIcon.Mode.Normal, QIcon.Mode.Active, QIcon.Mode.Disabled):
        assert not icon.pixmap(16, 16, mode).isNull()

"""Desktop editor: dirty state, live preview, save guard, external changes."""

import pytest
from PyQt6.QtWidgets import QMessageBox

from md_viewer_desktop.editor import MarkdownHighlighter
from md_viewer_desktop.main_window import MainWindow
from md_viewer_desktop.theme import load_theme
from md_preview_core.storage import get_file_revision


@pytest.fixture
def window(qapp, settings, tmp_path):
    from PyQt6 import sip

    base = tmp_path / "docs"
    base.mkdir()
    (base / "a.md").write_text("# A\n", encoding="utf-8")
    win = MainWindow(qapp, load_theme(), settings)
    win.open_path(base / "a.md")
    win.base = base
    yield win
    for view in win.views():
        if view.editor is not None:
            view.editor.document().setModified(False)
    win.close()
    sip.delete(win)


def edit(window, text):
    """Replace the buffer the way typing would (``setPlainText`` resets dirty)."""
    editor = window.view.editor
    editor.selectAll()
    editor.insertPlainText(text)


def answer(monkeypatch, button):
    monkeypatch.setattr(QMessageBox, "exec", lambda self: button)


def test_toggle_editor_loads_file_and_shows_pane(window):
    window.toggle_editor()
    editor = window.view.editor
    assert editor.toPlainText() == "# A\n"
    assert not editor.dirty
    assert not window.editor_stack.isHidden()
    window.toggle_editor()
    assert window.view.editor is None
    assert window.editor_stack.isHidden()


def test_dirty_marks_tab_and_save_clears_it(window):
    window.toggle_editor()
    edit(window, "# Changed\n")
    assert window.tabs.tabText(0) == "a.md*"
    assert window.save_view(window.view)
    assert window.tabs.tabText(0) == "a.md"
    assert (window.base / "a.md").read_text(encoding="utf-8") == "# Changed\n"
    assert not window._scheme_handler.overrides


def test_live_preview_override_is_served_before_save(window, helpers):
    window.toggle_editor()
    edit(window, "# Draft heading\n")
    assert helpers.wait_until(
        lambda: helpers.run_js(window.view.page(), "document.querySelector('h1') && document.querySelector('h1').textContent")
        == "Draft heading",
        timeout_ms=8000,
    )
    assert (window.base / "a.md").read_text(encoding="utf-8") == "# A\n"


def test_save_conflict_cancel_keeps_disk_and_buffer(window, monkeypatch):
    window.toggle_editor()
    edit(window, "mine\n")
    (window.base / "a.md").write_text("theirs, longer\n", encoding="utf-8")
    monkeypatch.setattr(window, "_ask_conflict", lambda view: "cancel")
    assert not window.save_view(window.view)
    assert (window.base / "a.md").read_text(encoding="utf-8") == "theirs, longer\n"
    assert window.view.editor.dirty


def test_save_conflict_overwrite_and_reload(window, monkeypatch):
    window.toggle_editor()
    edit(window, "mine\n")
    (window.base / "a.md").write_text("theirs, longer\n", encoding="utf-8")
    monkeypatch.setattr(window, "_ask_conflict", lambda view: "overwrite")
    assert window.save_view(window.view)
    assert (window.base / "a.md").read_text(encoding="utf-8") == "mine\n"

    edit(window, "again\n")
    (window.base / "a.md").write_text("external, much longer\n", encoding="utf-8")
    monkeypatch.setattr(window, "_ask_conflict", lambda view: "reload")
    assert not window.save_view(window.view)
    assert window.view.editor.toPlainText() == "external, much longer\n"
    assert not window.view.editor.dirty


def test_clean_editor_follows_external_change_dirty_one_does_not(window):
    window.toggle_editor()
    (window.base / "a.md").write_text("# External\n", encoding="utf-8")
    assert window._sync_editor_with_disk(window.view)
    assert window.view.editor.toPlainText() == "# External\n"

    edit(window, "typing\n")
    (window.base / "a.md").write_text("# External two, longer\n", encoding="utf-8")
    assert not window._sync_editor_with_disk(window.view)
    assert window.view.editor.toPlainText() == "typing\n"


def test_own_save_is_not_treated_as_external(window):
    window.toggle_editor()
    edit(window, "saved\n")
    window.save_view(window.view)
    assert window._sync_editor_with_disk(window.view)
    assert window.view.editor.base_revision == get_file_revision(window.base / "a.md")


def test_close_tab_prompts_when_dirty(window, monkeypatch):
    window.toggle_editor()
    edit(window, "dirty\n")
    answer(monkeypatch, QMessageBox.StandardButton.Cancel)
    assert not window.close_tab(0)
    assert window.view.editor is not None
    answer(monkeypatch, QMessageBox.StandardButton.Discard)
    assert window.close_tab(0)
    assert (window.base / "a.md").read_text(encoding="utf-8") == "# A\n"
    assert not window._scheme_handler.overrides


def test_close_tab_save_writes_file(window, monkeypatch):
    window.toggle_editor()
    edit(window, "kept\n")
    answer(monkeypatch, QMessageBox.StandardButton.Save)
    assert window.close_tab(0)
    assert (window.base / "a.md").read_text(encoding="utf-8") == "kept\n"


def test_highlighter_tracks_fenced_blocks(qapp):
    from PyQt6.QtGui import QTextDocument

    doc = QTextDocument()
    highlighter = MarkdownHighlighter(doc, load_theme())
    doc.setPlainText("```py\n# not a heading\n```\n# real")
    highlighter.rehighlight()
    assert [doc.findBlockByNumber(i).userState() for i in range(4)] == [1, 1, 0, 0]


def test_dirty_marks_window_title(window):
    window.toggle_editor()
    edit(window, "# Changed\n")
    assert window.windowTitle().startswith("*a.md")
    assert window.save_view(window.view)
    assert window.windowTitle().startswith("a.md")


def test_discarding_editor_clears_dirty_title(window, monkeypatch):
    window.toggle_editor()
    edit(window, "# Changed\n")
    assert window.windowTitle().startswith("*a.md")
    answer(monkeypatch, QMessageBox.StandardButton.Discard)
    window.toggle_editor()
    assert window.view.editor is None
    assert window.windowTitle().startswith("a.md")


def test_replacing_dirty_document_prompts(window, monkeypatch):
    (window.base / "b.md").write_text("# B\n", encoding="utf-8")
    window.toggle_editor()
    edit(window, "unsaved\n")
    root = window.base
    answer(monkeypatch, QMessageBox.StandardButton.Cancel)
    assert not window._show_document(root, "b.md")
    assert window.view.current_path == "a.md"
    assert window.view.editor.dirty
    answer(monkeypatch, QMessageBox.StandardButton.Save)
    assert window._show_document(root, "b.md")
    assert (root / "a.md").read_text(encoding="utf-8") == "unsaved\n"
    assert window.view.current_path == "b.md"
    assert window.view.editor is None
    assert not window._scheme_handler.overrides

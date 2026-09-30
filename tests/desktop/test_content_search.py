"""Background folder search and rendered result navigation."""

import threading

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QThread, Qt
from PyQt6.QtTest import QTest

from md_viewer_desktop.main_window import MainWindow
from md_viewer_desktop.search_panel import SearchPanel
from md_viewer_desktop.theme import load_theme


@pytest.fixture
def window(qapp, settings, tmp_path):
    (tmp_path / "notes.md").write_text("# Notes\n\nFirst **needle**\n\nSecond needle\n", encoding="utf-8")
    win = MainWindow(qapp, load_theme(), settings)
    win.show()
    win.open_path(tmp_path)
    yield win
    win.close()
    sip.delete(win)


def test_search_results_have_paths_source_lines_and_open_matching_location(window, helpers):
    window.open_content_search()
    QTest.keyClicks(window.search_panel.edit, "NEEDLE")
    assert helpers.wait_until(lambda: window.search_panel.results.count() == 2)
    assert "notes.md:3" in window.search_panel.results.item(0).text()
    assert "notes.md:5" in window.search_panel.results.item(1).text()
    item = window.search_panel.results.item(1)
    matches = []
    window.view.page().findTextFinished.connect(lambda hit: matches.append((hit.activeMatch(), hit.numberOfMatches())))
    QTest.mouseClick(window.search_panel.results.viewport(), Qt.MouseButton.LeftButton,
                     pos=window.search_panel.results.visualItemRect(item).center())
    assert window.view.current_path == "notes.md"
    assert helpers.wait_until(lambda: window.status_label.text() == "match · notes.md:5")
    assert matches[-1] == (1, 1)  # Entire rendered source line, not the first query hit.


def test_repeated_matching_line_scrolls_to_selected_occurrence(window, tmp_path, helpers):
    text = "same needle\n\n" + "\n\n".join(f"Paragraph {i}" for i in range(100)) + "\n\nsame needle\n"
    (tmp_path / "notes.md").write_text(text, encoding="utf-8")
    window.open_content_search()
    window.search_panel.edit.setText("needle")
    assert helpers.wait_until(lambda: window.search_panel.results.count() == 2)
    hit = window.search_panel.results.item(1).data(Qt.ItemDataRole.UserRole)
    assert hit["occurrence"] == 2
    window.search_panel._activate(window.search_panel.results.item(1))
    assert helpers.wait_until(lambda: window.status_label.text() == f"match · notes.md:{hit['line_number']}")
    assert helpers.wait_until(lambda: helpers.run_js(window.view.page(), "window.scrollY") > 1000)


def test_background_work_does_not_block_gui_and_stale_results_are_ignored(qapp, tmp_path, helpers, monkeypatch):
    from md_viewer_desktop import search_panel as module

    started, release = threading.Event(), threading.Event()
    worker_threads = []

    def slow_search(root, query, **kwargs):
        worker_threads.append(QThread.currentThread() != qapp.thread())
        started.set()
        release.wait(3)
        return {"results": [{"path": "old.md", "line_number": 1, "snippet": query}], "truncated": False}

    monkeypatch.setattr(module, "search_content", slow_search)
    panel = SearchPanel()
    try:
        panel.set_root(tmp_path)
        panel.edit.setText("old query")
        assert helpers.wait_until(started.is_set)
        panel.edit.clear()
        # Qt event loop remained responsive while the worker waited.
        assert panel.results.count() == 0
        panel._finished(panel._generation - 1, {"results": [], "truncated": False}, "obsolete error")
        assert panel.status.text() == "Enter at least 2 characters"
        assert worker_threads == [True]
        release.set()
    finally:
        release.set()
        panel.cancel()
        sip.delete(panel)


def test_search_refreshes_on_disk_changes_and_folder_switch(window, tmp_path, helpers):
    window.search_panel.edit.setText("needle")
    assert helpers.wait_until(lambda: window.search_panel.results.count() == 2)
    (tmp_path / "extra.md").write_text("needle", encoding="utf-8")
    assert helpers.wait_until(lambda: window.search_panel.results.count() == 3)
    (tmp_path / "notes.md").write_text("no match", encoding="utf-8")
    assert helpers.wait_until(lambda: window.search_panel.results.count() == 1)
    (tmp_path / "other").mkdir()
    window.open_path(tmp_path / "other")
    assert helpers.wait_until(lambda: window.search_panel.status.text() == "No matches")
    assert window.search_panel.results.count() == 0


def test_source_only_matches_and_vanished_results(window, tmp_path, helpers):
    (tmp_path / "notes.md").write_text("<!-- hidden needle -->", encoding="utf-8")
    window.open_content_search()
    window.search_panel.edit.setText("needle")
    assert helpers.wait_until(lambda: window.search_panel.results.count() == 1)
    hit = window.search_panel.results.item(0).data(Qt.ItemDataRole.UserRole)
    window.search_panel._activate(window.search_panel.results.item(0))
    assert helpers.wait_until(lambda: "source match · notes.md:1" in window.status_label.text())
    (tmp_path / "notes.md").unlink()
    window._open_search_result(tmp_path, hit, "needle")
    assert "search result unavailable" in window.status_label.text()
    assert window.status_label.property("state") == "error"


def test_search_error_clear_and_limit_states(qapp, tmp_path, helpers, monkeypatch):
    from md_viewer_desktop import search_panel as module

    panel = SearchPanel()
    try:
        panel.set_root(tmp_path)
        panel.edit.setText("one")
        monkeypatch.setattr(module, "search_content", lambda *a, **kw: (_ for _ in ()).throw(OSError("unreadable")))
        assert helpers.wait_until(lambda: panel.status.text() == "search failed: unreadable")
        panel.edit.clear()
        assert panel.results.count() == 0
        panel._finished(panel._generation, {"results": [], "truncated": True}, "")
        assert panel.status.text() == "Showing first 50 matches"
    finally:
        panel.cancel()
        sip.delete(panel)

"""Tabs, session restore, recent files and per-root live reload."""

import pytest
from PyQt6 import sip

from md_viewer_desktop.main_window import MainWindow
from md_viewer_desktop.theme import load_theme


@pytest.fixture
def docs(tmp_path):
    base = tmp_path / "docs"
    (base / "sub").mkdir(parents=True)
    (base / "README.md").write_text("# Readme\n\n[other](sub/other.md)\n", encoding="utf-8")
    (base / "second.md").write_text("# Second\n", encoding="utf-8")
    (base / "sub" / "other.md").write_text("# Other\n", encoding="utf-8")
    return base


def make_window(qapp, settings):
    return MainWindow(qapp, load_theme(), settings)


def close_and_delete(win):
    win.close()
    sip.delete(win)


@pytest.fixture
def window(qapp, settings):
    win = make_window(qapp, settings)
    yield win
    close_and_delete(win)


def h1(window, helpers, view=None):
    view = view or window.view
    if not view.url().path().endswith(".md"):
        return None  # still navigating; a script now could miss its reply
    return helpers.run_js(view.page(), "document.querySelector('h1') && document.querySelector('h1').textContent")


def tab_names(window):
    return [window.tabs.tabText(i) for i in range(window.tabs.count())]


def test_starts_with_one_welcome_tab(window):
    assert tab_names(window) == ["welcome"]
    assert window.view.current_path is None


def test_open_path_adds_tabs_and_reuses_open_ones(window, docs):
    window.open_path(docs / "README.md")
    assert tab_names(window) == ["README.md"]  # the welcome tab is reused
    window.open_path(docs / "second.md")
    assert tab_names(window) == ["README.md", "second.md"]
    window.open_path(docs / "README.md")
    assert window.tabs.count() == 2
    assert window.view.current_path == "README.md"
    assert window.windowTitle() == "README.md — MD Viewer"


def test_tree_click_replaces_current_tab_and_ctrl_click_adds(window, docs):
    window.open_path(docs / "README.md")
    window.tree.fileActivated.emit("second.md")
    assert tab_names(window) == ["second.md"]
    window.tree.fileActivatedInNewTab.emit("sub/other.md")
    assert tab_names(window) == ["second.md", "other.md"]
    assert window.tree.selected_path() == "sub/other.md"


def test_switching_tabs_syncs_tree_and_title(window, docs):
    window.open_path(docs / "README.md")
    window.open_path(docs / "second.md")
    window.tabs.setCurrentIndex(0)
    assert window.tree.selected_path() == "README.md"
    assert window.windowTitle() == "README.md — MD Viewer"


def test_close_tab_and_last_tab_becomes_welcome(window, docs, helpers):
    window.open_path(docs / "README.md")
    window.open_path(docs / "second.md")
    window.close_tab(1)
    assert tab_names(window) == ["README.md"]
    window.close_tab(0)
    assert tab_names(window) == ["welcome"]
    assert window.view.current_path is None
    assert helpers.wait_until(lambda: window.view.url().toString() == "mdview://app/welcome")


def test_tabs_from_different_folders_coexist(window, tmp_path, helpers):
    for name in ("one", "two"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "README.md").write_text(f"# {name}\n", encoding="utf-8")
    window.open_path(tmp_path / "one" / "README.md")
    first = window.view
    window.open_path(tmp_path / "two" / "README.md")
    second = window.view
    assert first is not second
    assert window.base_dir == (tmp_path / "two").resolve()
    assert helpers.wait_until(lambda: h1(window, helpers, second) == "two")
    # The first tab still resolves inside its own folder after the tree moved.
    window.tabs.setCurrentWidget(first)
    assert helpers.wait_until(lambda: h1(window, helpers, first) == "one")
    helpers.run_js(first.page(), "window.staleMarker = true")
    first.reload_document()
    fresh_h1 = "!window.staleMarker && document.querySelector('h1') && document.querySelector('h1').textContent"
    assert helpers.wait_until(lambda: helpers.run_js(first.page(), fresh_h1) == "one")
    assert window.watched_roots == {(tmp_path / "one").resolve(), (tmp_path / "two").resolve()}


def test_background_tab_from_other_folder_live_reloads(window, tmp_path, helpers):
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()
    (tmp_path / "one" / "a.md").write_text("# before\n", encoding="utf-8")
    (tmp_path / "two" / "b.md").write_text("# b\n", encoding="utf-8")
    window.open_path(tmp_path / "one" / "a.md")
    first = window.view
    assert helpers.wait_until(lambda: h1(window, helpers, first) == "before")
    window.open_path(tmp_path / "two" / "b.md")
    (tmp_path / "one" / "a.md").write_text("# after\n", encoding="utf-8")
    assert helpers.wait_until(lambda: h1(window, helpers, first) == "after")


def test_closing_tabs_stops_unused_watchers(window, tmp_path):
    for name in ("one", "two"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "x.md").write_text("# x\n", encoding="utf-8")
    window.open_path(tmp_path / "one" / "x.md")
    window.open_path(tmp_path / "two" / "x.md")
    window.close_tab(0)
    assert window.watched_roots == {(tmp_path / "two").resolve()}


def test_link_click_stays_in_tab_root(window, docs, helpers):
    window.open_path(docs / "README.md")
    assert helpers.wait_until(lambda: h1(window, helpers) == "Readme")
    helpers.run_js(window.view.page(), "document.querySelector('a[href=\"sub/other.md\"]').click()")
    assert helpers.wait_until(lambda: window.view.current_path == "sub/other.md")
    assert window.tabs.count() == 1


def test_session_restores_all_tabs_and_active_one(qapp, settings, docs, tmp_path):
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "far.md").write_text("# far\n", encoding="utf-8")
    first = make_window(qapp, settings)
    first.open_path(docs)
    first.open_path(docs / "README.md")
    first.open_path(docs / "sub" / "other.md")
    first.open_path(tmp_path / "elsewhere" / "far.md")  # moves the tree
    first.tabs.setCurrentIndex(1)
    close_and_delete(first)

    second = make_window(qapp, settings)
    try:
        second.restore_session()
        assert tab_names(second) == ["README.md", "other.md", "far.md"]
        assert second.tabs.currentIndex() == 1
        assert second.base_dir == (tmp_path / "elsewhere").resolve()
        # README keeps its own root, so its links still work.
        assert second.views()[0].root == docs.resolve()
        assert second.views()[1].current_path == "sub/other.md"
    finally:
        close_and_delete(second)


def test_building_a_window_does_not_wipe_the_session(qapp, settings, docs):
    first = make_window(qapp, settings)
    first.open_path(docs / "README.md")
    close_and_delete(first)
    close_and_delete(make_window(qapp, settings))  # never opened anything
    assert [t.path for t in settings.tabs] == ["README.md"]


def test_session_skips_missing_files(qapp, settings, docs):
    first = make_window(qapp, settings)
    first.open_path(docs / "README.md")
    first.open_path(docs / "second.md")
    close_and_delete(first)
    (docs / "second.md").unlink()
    second = make_window(qapp, settings)
    try:
        second.restore_session()
        assert tab_names(second) == ["README.md"]
    finally:
        close_and_delete(second)


def test_recent_files_menu(window, docs, settings):
    window.open_path(docs / "README.md")
    window.open_path(docs / "second.md")
    assert settings.recent_files[:2] == [docs.resolve() / "second.md", docs.resolve() / "README.md"]
    window._populate_recent_menu()
    labels = [a.text() for a in window.recent_menu.actions() if a.text()]
    assert labels[0].startswith("second.md")
    assert labels[-1] == "Clear Recent"
    window.recent_menu.actions()[-1].trigger()
    assert settings.recent_files == []
    window._populate_recent_menu()
    assert [a.text() for a in window.recent_menu.actions()] == ["no recent files"]


def test_open_paths_from_second_launch(window, docs):
    window.open_paths([docs / "README.md", docs / "second.md"])
    assert tab_names(window) == ["README.md", "second.md"]


def test_toolbar_actions_have_icons(window):
    for action in (window.open_action, window.find_action, window.zoom_in_action, window.print_action):
        assert not action.icon().isNull()
    assert not window.windowIcon().isNull()


def test_tab_close_button_closes_its_tab(window, docs):
    from PyQt6.QtWidgets import QTabBar

    window.open_path(docs / "README.md")
    window.open_path(docs / "second.md")
    button = window.tabs.tabBar().tabButton(0, QTabBar.ButtonPosition.RightSide)
    assert not button.icon().isNull()
    button.click()
    assert tab_names(window) == ["second.md"]

"""Sidebar filtering through real Qt widgets and the existing document flow."""

import pytest
from PyQt6 import sip
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

from md_preview_core.files import invalidate_file_cache
from md_viewer_desktop.file_tree import FileTree, IS_DIR_ROLE, PATH_ROLE


def visible_paths(tree):
    def walk(parent):
        paths = []
        for row in range(parent.rowCount()):
            item = parent.child(row)
            if tree.isRowHidden(row, item.index().parent()):
                continue
            if item.data(IS_DIR_ROLE):
                paths.extend(walk(item))
            else:
                paths.append(item.data(PATH_ROLE))
        return paths

    return walk(tree.model().invisibleRootItem())


@pytest.fixture
def tree(qapp, tmp_path):
    (tmp_path / "guides" / "nested").mkdir(parents=True)
    (tmp_path / "other").mkdir()
    for path in ("README.md", "guides/Setup.md", "guides/nested/API[1].md", "other/Notes.md"):
        (tmp_path / path).write_text("# Document", encoding="utf-8")
    widget = FileTree()
    widget.set_base_dir(tmp_path)
    yield widget
    sip.delete(widget)


def test_filter_matches_case_insensitive_paths_and_keeps_ancestors(tree):
    tree.set_filter_text("GUIDES/NESTED")
    assert visible_paths(tree) == ["guides/nested/API[1].md"]
    assert tree.isExpanded(tree._find("guides"))
    assert tree.isExpanded(tree._find("guides/nested"))
    tree.set_filter_text("[1]")
    assert visible_paths(tree) == ["guides/nested/API[1].md"]
    tree.set_filter_text("missing")
    assert visible_paths(tree) == []


def test_clear_restores_selection_and_expansion(tree):
    tree.select_path("README.md")
    tree.expand(tree._find("other"))
    tree.set_filter_text("setup")
    assert tree.selected_path() is None
    tree.set_filter_text("")
    assert visible_paths(tree) == tree.file_paths()
    assert tree.selected_path() == "README.md"
    assert tree.isExpanded(tree._find("other"))
    assert not tree.isExpanded(tree._find("guides"))


def test_filter_survives_rebuild_and_folder_change(tree, tmp_path):
    tree.set_filter_text("setup")
    (tmp_path / "other" / "Setup-new.md").write_text("# New", encoding="utf-8")
    invalidate_file_cache()  # WatcherBridge does this before requesting a rebuild.
    tree.rebuild()
    assert visible_paths(tree) == ["guides/Setup.md", "other/Setup-new.md"]
    (tmp_path / "guides" / "Setup.md").unlink()
    invalidate_file_cache()
    tree.rebuild()
    assert visible_paths(tree) == ["other/Setup-new.md"]
    tree.set_base_dir(tmp_path / "other")
    assert visible_paths(tree) == ["Setup-new.md"]


def test_filter_input_opens_matching_file_and_tracks_disk_updates(qapp, settings, tmp_path, helpers):
    from md_viewer_desktop.main_window import MainWindow
    from md_viewer_desktop.theme import load_theme

    (tmp_path / "README.md").write_text("# Readme", encoding="utf-8")
    (tmp_path / "Notes.md").write_text("# Notes", encoding="utf-8")
    window = MainWindow(qapp, load_theme(), settings)
    try:
        window.show()
        window.open_path(tmp_path)
        window.file_filter.setFocus()
        QTest.keyClicks(window.file_filter, "notes")
        assert visible_paths(window.tree) == ["Notes.md"]
        qapp.processEvents()
        index = window.tree._find("Notes.md")
        QTest.mouseClick(
            window.tree.viewport(), Qt.MouseButton.LeftButton,
            pos=window.tree.visualRect(index).center(),
        )
        assert window.view.current_path == "Notes.md"
        assert window.tree.selected_path() == "Notes.md"
        (tmp_path / "Notes-new.md").write_text("# New", encoding="utf-8")
        assert helpers.wait_until(lambda: "Notes-new.md" in visible_paths(window.tree))
        index = window.tree._find("Notes-new.md")
        QTest.mouseClick(
            window.tree.viewport(), Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.ControlModifier, pos=window.tree.visualRect(index).center(),
        )
        assert window.tabs.count() == 2
        assert window.view.current_path == "Notes-new.md"
        window.file_filter.clear()
        assert visible_paths(window.tree) == window.tree.file_paths()
        assert window.tree.selected_path() == "Notes-new.md"
    finally:
        window.close()
        sip.delete(window)

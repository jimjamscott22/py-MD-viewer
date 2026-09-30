"""File operations, dialogs, and tab state with real Qt widgets."""

from pathlib import Path
import os
import subprocess
import sys

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QFile, QModelIndex
from PyQt6.QtWidgets import QInputDialog, QMessageBox

from md_viewer_desktop import file_operations as ops
from md_viewer_desktop.main_window import MainWindow
from md_viewer_desktop.theme import load_theme


@pytest.fixture
def window(qapp, settings, tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "old.md").write_text("# Original", encoding="utf-8")
    (tmp_path / "keep.md").write_text("# Keep", encoding="utf-8")
    win = MainWindow(qapp, load_theme(), settings)
    win.open_path(tmp_path)
    yield win
    win.close()
    sip.delete(win)


def answer(monkeypatch, text, accepted=True):
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **kw: (text, accepted))


def test_new_file_uses_clicked_folder_and_opens_with_filter_active(window, tmp_path, monkeypatch):
    answer(monkeypatch, "new note")
    window.file_filter.setText("old")
    window.file_operations.create(tmp_path, "sub")
    assert (tmp_path / "sub" / "new note.md").read_text() == ""
    assert window.view.current_path == "sub/new note.md"
    assert "sub/new note.md" in window.tree.file_paths()
    assert window.tree.selected_path() is None  # still hidden by the active filter
    window.file_filter.clear()
    assert window.tree.selected_path() == "sub/new note.md"


@pytest.mark.parametrize("name", ["../escape", "/absolute.md", "sub/file.md", "bad\\name", "file.txt", "", "..", "a\x00.md"])
def test_create_rejects_invalid_names(tmp_path, name):
    with pytest.raises(ValueError):
        ops.create_file(tmp_path, "", name)
    assert not list(tmp_path.iterdir())


def test_collisions_preserve_both_files(tmp_path):
    (tmp_path / "one.md").write_text("one")
    (tmp_path / "two.md").write_text("two")
    with pytest.raises(OSError):
        ops.create_file(tmp_path, "", "one")
    with pytest.raises(OSError):
        ops.rename_file(tmp_path, "one.md", "two.md")
    assert (tmp_path / "one.md").read_text() == "one"
    assert (tmp_path / "two.md").read_text() == "two"


def test_paths_cannot_escape_or_mutate_symlink_targets(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("outside")
    (root / "link.md").symlink_to(outside)
    (root / "escape").symlink_to(tmp_path, target_is_directory=True)
    for path in ("../outside.md", "link.md"):
        with pytest.raises(ValueError):
            ops.rename_file(root, path, "renamed.md")
        with pytest.raises(ValueError):
            ops.trash_file(root, path)
    with pytest.raises(ValueError):
        ops.create_file(root, "escape", "new")
    assert outside.read_text() == "outside"


def test_cancelled_dialogs_make_no_changes(window, tmp_path, monkeypatch):
    answer(monkeypatch, "new", False)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.No)
    window.file_operations.create(tmp_path, "sub")
    window.file_operations.rename(tmp_path, "sub/old.md")
    window.file_operations.trash(tmp_path, "sub/old.md")
    assert (tmp_path / "sub" / "old.md").read_text() == "# Original"
    assert not (tmp_path / "sub" / "new.md").exists()


def test_rename_updates_tabs_from_different_roots_and_saved_session(window, tmp_path, settings, monkeypatch, helpers):
    window.open_path(tmp_path / "sub")
    window.open_document("old.md")
    nested = window.view
    window.open_path(tmp_path / "keep.md")
    active = window.view
    answer(monkeypatch, "renamed.MD")
    window.file_operations.rename(tmp_path, "sub/old.md")
    assert nested.current_path == "renamed.MD"
    assert [tab.file for tab in settings.tabs] == [tmp_path / "sub" / "renamed.MD", tmp_path / "keep.md"]
    assert settings.recent_files == [tmp_path / "keep.md", tmp_path / "sub" / "renamed.MD"]
    assert window.tabs.tabText(0) == "renamed.MD"
    assert window.view is active
    assert helpers.wait_until(lambda: helpers.run_js(nested.page(), "document.querySelector('h1')?.textContent") == "Original")
    (tmp_path / "sub" / "renamed.MD").write_text("# Updated", encoding="utf-8")
    assert helpers.wait_until(lambda: helpers.run_js(nested.page(), "document.querySelector('h1')?.textContent") == "Updated")


def test_trash_updates_tabs_and_preserves_recoverable_file(window, tmp_path, monkeypatch, settings):
    window.open_document("sub/old.md")
    window.open_document("keep.md", new_tab=True)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes)
    trash_path = tmp_path / "trashed-file"

    def fake_trash(file):
        Path(file.fileName()).rename(trash_path)
        file.setFileName(str(trash_path))
        return True

    monkeypatch.setattr(QFile, "moveToTrash", fake_trash)
    window.file_operations.trash(tmp_path, "sub/old.md")
    assert trash_path.read_text() == "# Original"
    assert not (tmp_path / "sub" / "old.md").exists()
    assert window.view.current_path == "keep.md"
    assert window.tabs.count() == 1
    assert "sub/old.md" not in window.tree.file_paths()
    assert [tab.path for tab in settings.tabs] == ["keep.md"]
    assert "recover" in window.status_label.text()


def test_trash_failure_keeps_file_and_tab(window, tmp_path, monkeypatch):
    window.open_document("sub/old.md")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QFile, "moveToTrash", lambda file: False)
    window.file_operations.trash(tmp_path, "sub/old.md")
    assert (tmp_path / "sub" / "old.md").exists()
    assert window.view.current_path == "sub/old.md"
    assert window.status_label.property("state") == "error"


def test_context_menu_targets_clicked_item_and_disables_directory_mutations(window):
    created, renamed, trashed = [], [], []
    window.tree.createRequested.connect(lambda root, path: created.append(path))
    window.tree.renameRequested.connect(lambda root, path: renamed.append(path))
    window.tree.trashRequested.connect(lambda root, path: trashed.append(path))
    # Disconnect the dialogs: exercise menu targeting without opening modal UI.
    window.tree.createRequested.disconnect(window._create_file)
    window.tree.renameRequested.disconnect(window._rename_file)
    window.tree.trashRequested.disconnect(window._trash_file)
    menu = window.tree.context_menu(window.tree._find("sub/old.md"))
    actions = [a for a in menu.actions() if not a.isSeparator()]
    for action in actions:
        action.trigger()
    assert created == ["sub"]
    assert renamed == trashed == ["sub/old.md"]
    menu = window.tree.context_menu(window.tree._find("sub"))
    actions = [a for a in menu.actions() if not a.isSeparator()]
    assert [a.isEnabled() for a in actions] == [True, False, False]
    menu = window.tree.context_menu(QModelIndex())
    menu.actions()[0].trigger()
    assert created == ["sub", ""]


def test_menu_captures_root_before_sidebar_folder_changes(window, tmp_path, monkeypatch):
    menu = window.tree.context_menu(window.tree._find("sub/old.md"))
    window.open_path(tmp_path / "sub")
    answer(monkeypatch, "renamed.md")
    menu.actions()[2].trigger()  # Rename, after New and separator.
    assert (tmp_path / "sub" / "renamed.md").exists()
    assert not (tmp_path / "sub" / "old.md").exists()


def test_trashing_last_document_leaves_welcome_and_empty_session(window, tmp_path, monkeypatch, settings):
    window.open_document("sub/old.md")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes)

    def fake_trash(file):
        Path(file.fileName()).rename(tmp_path / "recoverable")
        return True

    monkeypatch.setattr(QFile, "moveToTrash", fake_trash)
    window.file_operations.trash(tmp_path, "sub/old.md")
    assert window.tabs.count() == 1
    assert window.view.current_path is None
    assert settings.tabs == []


@pytest.mark.skipif(sys.platform != "linux", reason="FreeDesktop Trash layout is Linux-specific")
def test_native_trash_is_recoverable_in_isolated_data_directory(tmp_path):
    source = tmp_path / "native.md"
    source.write_text("recover me", encoding="utf-8")
    data_dir = tmp_path / "xdg-data"
    data_dir.mkdir()  # Qt creates Trash itself, but requires an existing data home.
    # Isolate Qt's standard paths in a fresh process; never touch the user's Trash.
    result = subprocess.run(
        [sys.executable, "-c",
         "from pathlib import Path; from md_viewer_desktop.file_operations import trash_file; "
         "import sys; trash_file(Path(sys.argv[1]), 'native.md')", str(tmp_path)],
        env={**os.environ, "XDG_DATA_HOME": str(data_dir)},
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert not source.exists()
    trashed = data_dir / "Trash" / "files" / "native.md"
    assert trashed.read_text() == "recover me"
    assert (data_dir / "Trash" / "info" / "native.md.trashinfo").is_file()

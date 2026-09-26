"""Main window behaviour against a real (headless) QtWebEngine."""

from pathlib import Path

import pytest
from PyQt6 import sip
from PyQt6.QtGui import QDesktopServices

from md_viewer_desktop import main as cli
from md_viewer_desktop.main_window import DOC_THEMES, MainWindow
from md_viewer_desktop.theme import load_theme


@pytest.fixture
def docs(tmp_path):
    base = tmp_path / "docs"
    (base / "sub").mkdir(parents=True)
    (base / "node_modules").mkdir()
    (base / "README.md").write_text(
        "# Readme\n\n[other](sub/other.md) · [site](https://example.com) · "
        "[pdf](file.pdf)\n",
        encoding="utf-8",
    )
    (base / "sub" / "other.md").write_text("# Other\n", encoding="utf-8")
    (base / "node_modules" / "skip.md").write_text("# hidden\n", encoding="utf-8")
    (base / "notes.txt").write_text("not markdown", encoding="utf-8")
    return base


@pytest.fixture
def window(qapp, settings):
    win = MainWindow(qapp, load_theme(), settings)
    yield win
    close_and_delete(win)


def close_and_delete(win):
    # The web page must be gone before the app-owned profile is released.
    win.close()
    sip.delete(win)


def wait_loaded(window, helpers, rel_path):
    assert helpers.wait_until(
        lambda: window.view.url().path().endswith(rel_path)
        and helpers.run_js(window.view.page(), "document.readyState") == "complete"
    )


def test_open_file_sets_folder_tree_and_view(window, docs, helpers):
    assert window.open_path(docs / "README.md")
    assert window.base_dir == docs.resolve()
    assert window.view.current_path == "README.md"
    assert window.tree.file_paths() == ["sub/other.md", "README.md"]
    assert window.tree.selected_path() == "README.md"
    assert window.windowTitle() == "README.md — MD Viewer"
    wait_loaded(window, helpers, "README.md")
    heading = helpers.run_js(window.view.page(), "document.querySelector('h1').textContent")
    assert heading == "Readme"


def test_open_folder_shows_welcome(window, docs, helpers):
    assert window.open_path(docs)
    assert window.base_dir == docs.resolve()
    assert window.view.current_path is None
    assert helpers.wait_until(lambda: window.view.url().toString() == "mdview://app/welcome")


def test_open_rejects_non_markdown_and_missing(window, docs):
    assert not window.open_path(docs / "notes.txt")
    assert "not a markdown file" in window.status_label.text()
    assert not window.open_path(docs / "missing.md")
    assert window.status_label.property("state") == "error"


def test_clicking_markdown_link_opens_document(window, docs, helpers):
    window.open_path(docs / "README.md")
    wait_loaded(window, helpers, "README.md")
    helpers.run_js(window.view.page(), "document.querySelector('a[href=\"sub/other.md\"]').click()")
    assert helpers.wait_until(lambda: window.view.current_path == "sub/other.md")
    assert window.tree.selected_path() == "sub/other.md"


def test_external_link_goes_to_system_browser(window, docs, helpers, monkeypatch):
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    window.open_path(docs / "README.md")
    wait_loaded(window, helpers, "README.md")
    helpers.run_js(window.view.page(), "document.querySelector('a[href^=\"https\"]').click()")
    assert helpers.wait_until(lambda: opened)
    assert opened == ["https://example.com/"]
    assert window.view.current_path == "README.md"


def test_other_links_are_blocked(window, docs, helpers):
    window.open_path(docs / "README.md")
    wait_loaded(window, helpers, "README.md")
    helpers.run_js(window.view.page(), "document.querySelector('a[href=\"file.pdf\"]').click()")
    assert helpers.wait_until(lambda: "link blocked" in window.status_label.text())
    assert window.view.url().path() == "/README.md"


def test_live_reload_on_disk_change(window, docs, helpers):
    window.open_path(docs / "README.md")
    wait_loaded(window, helpers, "README.md")
    (docs / "README.md").write_text("# Changed on disk\n", encoding="utf-8")
    assert helpers.wait_until(
        lambda: helpers.run_js(window.view.page(), "document.querySelector('h1') && document.querySelector('h1').textContent")
        == "Changed on disk"
    )
    assert window.status_label.text() == "reloaded · README.md"


def test_new_file_appears_in_tree(window, docs, helpers):
    window.open_path(docs / "README.md")
    (docs / "sub" / "added.md").write_text("# Added\n", encoding="utf-8")
    assert helpers.wait_until(lambda: "sub/added.md" in window.tree.file_paths())


def test_deleted_current_file_warns(window, docs, helpers):
    window.open_path(docs / "sub" / "other.md")
    wait_loaded(window, helpers, "other.md")
    (docs / "sub" / "other.md").unlink()
    assert helpers.wait_until(lambda: "deleted on disk" in window.status_label.text())
    assert window.status_label.property("state") == "warning"


@pytest.mark.parametrize("doc_theme", DOC_THEMES, ids=lambda t: t.key)
def test_theme_switch_updates_page_and_settings(window, docs, helpers, settings, doc_theme):
    window.open_path(docs / "README.md")
    wait_loaded(window, helpers, "README.md")
    window.set_theme(doc_theme.key)
    assert settings.theme == doc_theme.key
    assert window.theme_actions[doc_theme.key].isChecked()
    assert helpers.wait_until(
        lambda: helpers.run_js(
            window.view.page(), "document.documentElement.getAttribute('data-theme') || ''"
        )
        == doc_theme.attr
    )


def test_jamielab_is_default_and_styles_chrome(window, qapp):
    assert window.doc_theme.key == "jamielab"
    assert "#39ff88" in qapp.styleSheet()
    window.set_theme("paper")
    assert qapp.styleSheet() == ""
    window.set_theme("jamielab")
    assert "#39ff88" in qapp.styleSheet()


def test_restore_session_reopens_last_file(qapp, settings, docs):
    first = MainWindow(qapp, load_theme(), settings)
    first.open_path(docs / "sub" / "other.md")
    close_and_delete(first)
    second = MainWindow(qapp, load_theme(), settings)
    try:
        second.restore_session()
        assert second.base_dir == docs.resolve() / "sub"
        assert second.view.current_path == "other.md"
    finally:
        close_and_delete(second)


def test_cli_checks_paths(docs):
    assert cli.check_paths([docs / "README.md", docs]) is None
    assert "no such file" in cli.check_paths([docs / "nope.md"])
    assert "not a markdown file" in cli.check_paths([docs / "notes.txt"])


def test_cli_rejects_bad_path_before_starting_qt(docs, capsys):
    assert cli.main([str(docs / "nope.md")]) == 2
    assert "no such file" in capsys.readouterr().err


def test_safe_mode_disables_gpu(monkeypatch):
    monkeypatch.setenv("QTWEBENGINE_CHROMIUM_FLAGS", "--foo")
    cli.configure_environment(safe_mode=True)
    cli.configure_environment(safe_mode=True)
    import os

    assert os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] == "--foo --disable-gpu"
    assert cli.parse_args(["--safe-mode", "a.md"]).paths == [Path("a.md")]


@pytest.mark.parametrize("key, light", [("paper", True), ("jamielab", False), ("terminal", False)])
def test_page_background_follows_theme(window, docs, helpers, key, light):
    window.set_theme(key)
    window.open_path(docs / "README.md")
    wait_loaded(window, helpers, "README.md")
    channels = helpers.run_js(
        window.view.page(),
        "getComputedStyle(document.body).backgroundColor.match(/\\d+/g).slice(0, 3).map(Number)",
    )
    assert (sum(channels) / 3 > 128) is light


def test_same_name_in_another_folder_is_loaded(window, tmp_path, helpers):
    for name in ("one", "two"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "README.md").write_text(f"# {name}\n", encoding="utf-8")
    window.open_path(tmp_path / "one" / "README.md")
    wait_loaded(window, helpers, "README.md")
    window.open_path(tmp_path / "two" / "README.md")
    assert window.base_dir == (tmp_path / "two").resolve()
    assert helpers.wait_until(
        lambda: helpers.run_js(window.view.page(), "document.querySelector('h1') && document.querySelector('h1').textContent")
        == "two"
    )

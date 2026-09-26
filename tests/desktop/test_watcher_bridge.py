"""WatcherBridge delivers watchdog events as Qt signals on the GUI thread."""

import pytest
from PyQt6.QtCore import QThread

from md_viewer_desktop.watcher_bridge import WatcherBridge


@pytest.fixture
def bridge(qapp):
    bridge = WatcherBridge()
    received = []
    # A plain slot (not QSignalSpy, which records on the emitting thread)
    # proves the event was queued over to the GUI thread.
    bridge.fileChanged.connect(
        lambda *args: received.append((*args, QThread.currentThread() is qapp.thread()))
    )
    bridge.received = received
    yield bridge
    bridge.stop()


def test_emits_on_file_change_on_gui_thread(bridge, tmp_path, helpers):
    target = tmp_path / "doc.md"
    target.write_text("one", encoding="utf-8")
    bridge.start(tmp_path)
    target.write_text("two", encoding="utf-8")
    # write_text truncates first, so an intermediate size-0 revision may be
    # reported before the final one.
    final = f":{len('two')}"
    assert helpers.wait_until(lambda: any(r[2].endswith(final) for r in bridge.received))
    for rel_path, event_type, _revision, on_gui_thread in bridge.received:
        assert (rel_path, event_type) == ("doc.md", "file_modified")
        assert on_gui_thread


def test_emits_tree_changed_on_create(bridge, tmp_path, helpers):
    bridge.start(tmp_path)
    (tmp_path / "new.md").write_text("# new", encoding="utf-8")
    assert helpers.wait_until(
        lambda: ("new.md", "tree_changed") in [(r[0], r[1]) for r in bridge.received]
    )


def test_restart_switches_directory(bridge, tmp_path, helpers):
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir()
    second.mkdir()
    bridge.start(first)
    bridge.start(second)
    assert bridge.base_dir == second.resolve()
    (first / "ignored.md").write_text("x", encoding="utf-8")
    (second / "doc.md").write_text("x", encoding="utf-8")
    assert helpers.wait_until(lambda: any(r[0] == "doc.md" for r in bridge.received))
    assert not any(r[0] == "ignored.md" for r in bridge.received)

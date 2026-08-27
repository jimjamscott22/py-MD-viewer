"""Tests for Markdown filesystem event classification."""

from watchdog.events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
)

import md_preview_server.watcher as watcher_module
from md_preview_server.storage import get_file_revision
from md_preview_server.watcher import MarkdownFileHandler


def make_handler(base_dir):
    events = []
    handler = MarkdownFileHandler(
        lambda path, event_type, revision: events.append(
            (path, event_type, revision)
        ),
        base_dir,
    )
    return handler, events


def test_modified_markdown_emits_revision(tmp_path):
    target = tmp_path / "doc.md"
    target.write_text("changed", encoding="utf-8")
    handler, events = make_handler(tmp_path)

    handler.on_modified(FileModifiedEvent(str(target)))

    assert events == [
        ("doc.md", "file_modified", get_file_revision(target)),
    ]


def test_created_markdown_refreshes_tree(tmp_path):
    target = tmp_path / "created.md"
    target.write_text("new", encoding="utf-8")
    handler, events = make_handler(tmp_path)

    handler.on_created(FileCreatedEvent(str(target)))

    assert events == [("created.md", "tree_changed", None)]


def test_deleted_markdown_refreshes_tree(tmp_path):
    target = tmp_path / "deleted.md"
    handler, events = make_handler(tmp_path)

    handler.on_deleted(FileDeletedEvent(str(target)))

    assert events == [("deleted.md", "tree_changed", None)]


def test_renamed_markdown_refreshes_tree_with_destination(tmp_path):
    source = tmp_path / "before.md"
    destination = tmp_path / "after.md"
    handler, events = make_handler(tmp_path)

    handler.on_moved(FileMovedEvent(str(source), str(destination)))

    assert events == [("after.md", "tree_changed", None)]


def test_atomic_replace_emits_destination_revision(tmp_path):
    temporary = tmp_path / ".doc.md.tmp"
    destination = tmp_path / "doc.md"
    destination.write_text("replacement", encoding="utf-8")
    handler, events = make_handler(tmp_path)

    handler.on_moved(FileMovedEvent(str(temporary), str(destination)))

    assert events == [
        ("doc.md", "file_modified", get_file_revision(destination)),
    ]


def test_non_markdown_event_is_ignored(tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("ignored", encoding="utf-8")
    handler, events = make_handler(tmp_path)

    handler.on_modified(FileModifiedEvent(str(target)))

    assert events == []


def test_modified_event_without_stat_still_notifies(tmp_path):
    missing = tmp_path / "missing.md"
    handler, events = make_handler(tmp_path)

    handler.on_modified(FileModifiedEvent(str(missing)))

    assert events == [("missing.md", "file_modified", None)]


def test_debounce_keeps_distinct_revisions(tmp_path):
    target = tmp_path / "doc.md"
    target.write_text("first", encoding="utf-8")
    handler, events = make_handler(tmp_path)

    handler.on_modified(FileModifiedEvent(str(target)))
    target.write_text("second revision", encoding="utf-8")
    handler.on_modified(FileModifiedEvent(str(target)))

    assert len(events) == 2
    assert events[0][2] != events[1][2]


def test_debounce_removes_expired_entries(tmp_path, monkeypatch):
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")
    handler, _events = make_handler(tmp_path)
    clock = iter((1.0, 2.0))
    monkeypatch.setattr(watcher_module.time, "monotonic", lambda: next(clock))

    handler.on_created(FileCreatedEvent(str(first)))
    handler.on_created(FileCreatedEvent(str(second)))

    assert len(handler._last_events) == 1
    assert next(iter(handler._last_events))[0] == "second.md"

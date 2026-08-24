"""Tests for stable file revisions and atomic storage."""

from pathlib import Path

import pytest

import md_preview_server.storage as storage


def test_read_text_stable_retries_when_file_changes(tmp_path, monkeypatch):
    doc = tmp_path / "doc.md"
    doc.write_text("old", encoding="utf-8")
    real_read_text = Path.read_text
    changed = False

    def racing_read(path, *args, **kwargs):
        nonlocal changed
        content = real_read_text(path, *args, **kwargs)
        if path == doc and not changed:
            changed = True
            doc.write_text("new external content", encoding="utf-8")
        return content

    monkeypatch.setattr(Path, "read_text", racing_read)

    content, file_stat = storage.read_text_stable(doc)

    assert content == "new external content"
    assert storage.revision_from_stat(file_stat) == storage.get_file_revision(doc)


def test_read_text_stable_rejects_continuously_changing_file(tmp_path, monkeypatch):
    doc = tmp_path / "doc.md"
    doc.write_text("start", encoding="utf-8")
    real_read_text = Path.read_text
    read_count = 0

    def racing_read(path, *args, **kwargs):
        nonlocal read_count
        content = real_read_text(path, *args, **kwargs)
        if path == doc:
            read_count += 1
            doc.write_text("changed-" + ("x" * read_count), encoding="utf-8")
        return content

    monkeypatch.setattr(Path, "read_text", racing_read)

    with pytest.raises(storage.FileChangedDuringRead):
        storage.read_text_stable(doc, max_attempts=2)


def test_atomic_write_text_replaces_complete_file(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("original", encoding="utf-8")
    original_revision = storage.get_file_revision(doc)

    saved_stat = storage.atomic_write_text(
        doc,
        "replacement content",
        expected_revision=original_revision,
    )

    assert doc.read_text(encoding="utf-8") == "replacement content"
    assert storage.revision_from_stat(saved_stat) == storage.get_file_revision(doc)
    assert not list(tmp_path.glob(".doc.md.*.tmp"))


def test_atomic_write_text_preserves_external_edit_on_revision_mismatch(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("original", encoding="utf-8")
    stale_revision = storage.get_file_revision(doc)
    doc.write_text("new external content", encoding="utf-8")

    with pytest.raises(storage.FileRevisionMismatch):
        storage.atomic_write_text(
            doc,
            "browser edit",
            expected_revision=stale_revision,
        )

    assert doc.read_text(encoding="utf-8") == "new external content"
    assert not list(tmp_path.glob(".doc.md.*.tmp"))


def test_atomic_write_text_cleans_up_when_replace_fails(tmp_path, monkeypatch):
    doc = tmp_path / "doc.md"
    doc.write_text("original", encoding="utf-8")

    def fail_replace(source, destination):
        raise OSError("replace failed")

    monkeypatch.setattr(storage.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        storage.atomic_write_text(doc, "replacement")

    assert doc.read_text(encoding="utf-8") == "original"
    assert not list(tmp_path.glob(".doc.md.*.tmp"))

"""Tests for framework-neutral Markdown file discovery helpers."""

import builtins
import importlib
import sys

import pytest

from md_preview_core import files


def test_core_files_does_not_import_flask(monkeypatch):
    sys.modules.pop("md_preview_core.files", None)
    real_import = builtins.__import__

    def import_without_flask(name, *args, **kwargs):
        if name == "flask" or name.startswith("flask."):
            raise AssertionError("the core files module must not import Flask")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_flask)

    module = importlib.import_module("md_preview_core.files")

    assert module.validate_path is not None


def test_validate_path_rejects_escape_without_http_dependency(tmp_path):
    with pytest.raises(files.PathOutsideBaseError):
        files.validate_path(tmp_path, "../outside.md")


def test_scan_files_builds_tree_and_metadata(tmp_path):
    (tmp_path / "guide.md").write_text("# Guide", encoding="utf-8")
    nested = tmp_path / "docs"
    nested.mkdir()
    (nested / "notes.MD").write_text("notes", encoding="utf-8")
    ignored = tmp_path / ".venv"
    ignored.mkdir()
    (ignored / "ignored.md").write_text("ignored", encoding="utf-8")

    files.invalidate_file_cache()
    snapshot = files.scan_files(tmp_path)

    assert snapshot["tree"] == {
        "docs": {"notes.MD": "docs/notes.MD"},
        "guide.md": "guide.md",
    }
    assert {item["path"] for item in snapshot["files"]} == {
        "docs/notes.MD",
        "guide.md",
    }
    assert all(item["modified"].endswith("+00:00") for item in snapshot["files"])


def test_search_markdown_file_returns_context_and_skips_binary(tmp_path):
    (tmp_path / "notes.md").write_text(
        "before\nFind This phrase\nafter\n",
        encoding="utf-8",
    )
    (tmp_path / "binary.md").write_bytes(b"\xff\xfe")

    assert files.search_markdown_file(tmp_path, "notes.md", "find this", 10) == [
        {
            "path": "notes.md",
            "line_number": 2,
            "snippet": "before\nFind This phrase\nafter",
        }
    ]
    assert files.search_markdown_file(tmp_path, "binary.md", "find", 10) == []

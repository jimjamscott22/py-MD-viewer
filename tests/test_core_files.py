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


def test_content_search_limit_exclusions_and_navigation(tmp_path):
    (tmp_path / "one.md").write_text("Needle\n\nNeedle\n\nOther NEEDLE", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "hidden.md").write_text("Needle")
    (tmp_path / "binary.md").write_bytes(b"\xff")
    result = files.search_content(tmp_path, "needle", limit=2)
    assert result["truncated"]
    assert [hit["line_number"] for hit in result["results"]] == [1, 3]
    assert [hit["occurrence"] for hit in result["results"]] == [1, 2]
    assert all(hit["source_line"] == "Needle" for hit in result["results"])
    assert not files.search_content(tmp_path, "needle", limit=3)["truncated"]
    assert files.search_content(tmp_path, "n")["results"] == []
    assert files.search_content(tmp_path, "needle", cancelled=lambda: True)["results"] == []

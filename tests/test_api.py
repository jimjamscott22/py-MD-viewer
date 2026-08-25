"""Tests for the API endpoints (Phases 1-4)."""

import json
from concurrent.futures import Future
from pathlib import Path

import pytest

import md_preview_server.app as app_module
from md_preview_server.app import create_app


@pytest.fixture
def sample_dir(tmp_path):
    """Create a temporary directory with sample markdown files."""
    (tmp_path / "hello.md").write_text("# Hello World\n\nA test file.", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "nested.md").write_text("## Nested\n\nNested content.", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "ignored.md").write_text("# Ignore me", encoding="utf-8")
    return tmp_path


@pytest.fixture
def client(sample_dir):
    """Create a Flask test client with the sample directory."""
    app = create_app(base_dir=sample_dir)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# --- Phase 1: Files & search ---

def test_api_files(client):
    response = client.get("/api/files")
    assert response.status_code == 200
    data = response.get_json()
    assert "tree" in data
    assert "files" in data
    assert len(data["files"]) == 2
    assert ".venv/ignored.md" not in {f["path"] for f in data["files"]}


def test_api_files_metadata(client):
    response = client.get("/api/files")
    data = response.get_json()
    f = data["files"][0]
    assert "path" in f
    assert "name" in f
    assert "size" in f
    assert "modified" in f
    assert f["size"] > 0


def test_api_files_uses_one_shared_snapshot(client, sample_dir, monkeypatch):
    calls = []
    snapshot = {
        "base_dir": sample_dir,
        "tree": {"only.md": "only.md"},
        "files": [{
            "path": "only.md",
            "name": "only.md",
            "size": 7,
            "modified": "2026-08-24T00:00:00+00:00",
        }],
    }

    def fake_scan(base_dir):
        calls.append(base_dir)
        return snapshot

    monkeypatch.setattr(app_module, "_scan_files", fake_scan)

    response = client.get("/api/files")

    assert response.status_code == 200
    assert len(calls) == 1
    assert response.get_json()["tree"] == snapshot["tree"]
    assert response.get_json()["files"] == snapshot["files"]


def test_scan_files_retries_if_invalidated_mid_scan(tmp_path, monkeypatch):
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("first", encoding="utf-8")
    scan_count = 0

    def racing_scan(base_dir):
        nonlocal scan_count
        scan_count += 1
        if scan_count == 1:
            yield first
            second.write_text("second", encoding="utf-8")
            app_module.invalidate_file_cache()
            return
        yield from sorted(base_dir.glob("*.md"))

    monkeypatch.setattr(app_module, "_iter_markdown_files", racing_scan)
    app_module.invalidate_file_cache()

    snapshot = app_module._scan_files(tmp_path)

    assert scan_count == 2
    assert set(snapshot["tree"]) == {"first.md", "second.md"}
    assert {item["path"] for item in snapshot["files"]} == {
        "first.md",
        "second.md",
    }


def test_scan_files_skips_file_that_disappears_before_stat(tmp_path, monkeypatch):
    stable = tmp_path / "stable.md"
    vanished = tmp_path / "vanished.md"
    stable.write_text("stable", encoding="utf-8")

    monkeypatch.setattr(
        app_module,
        "_iter_markdown_files",
        lambda _base_dir: iter((stable, vanished)),
    )
    app_module.invalidate_file_cache()

    snapshot = app_module._scan_files(tmp_path)

    assert snapshot["tree"] == {"stable.md": "stable.md"}
    assert [item["path"] for item in snapshot["files"]] == ["stable.md"]


def test_api_search_found(client):
    response = client.get("/api/search?q=hello")
    data = response.get_json()
    assert len(data["results"]) == 1
    assert data["results"][0]["name"] == "hello.md"


def test_api_search_not_found(client):
    response = client.get("/api/search?q=nonexistent")
    data = response.get_json()
    assert len(data["results"]) == 0


def test_api_search_empty_query(client):
    response = client.get("/api/search?q=")
    data = response.get_json()
    assert data["results"] == []


def test_api_search_by_path(client):
    response = client.get("/api/search?q=sub")
    data = response.get_json()
    assert len(data["results"]) == 1
    assert "nested.md" in data["results"][0]["name"]


# --- Phase 2: Upload & create ---

def test_api_create(client, sample_dir):
    client.get("/api/files")
    response = client.post(
        "/api/create",
        json={"path": "new-doc.md", "content": "# New Document"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert (sample_dir / "new-doc.md").exists()
    assert (sample_dir / "new-doc.md").read_text(encoding="utf-8") == "# New Document"

    files_response = client.get("/api/files")
    files = files_response.get_json()["files"]
    assert {f["path"] for f in files} == {"hello.md", "new-doc.md", "sub/nested.md"}


def test_api_create_auto_extension(client, sample_dir):
    response = client.post(
        "/api/create",
        json={"path": "no-ext", "content": ""},
    )
    data = response.get_json()
    assert data["success"] is True
    assert (sample_dir / "no-ext.md").exists()


def test_api_create_nested(client, sample_dir):
    response = client.post(
        "/api/create",
        json={"path": "deep/nested/file.md", "content": "# Deep"},
    )
    data = response.get_json()
    assert data["success"] is True
    assert (sample_dir / "deep" / "nested" / "file.md").exists()


def test_api_create_duplicate(client):
    response = client.post(
        "/api/create",
        json={"path": "hello.md", "content": "duplicate"},
    )
    assert response.status_code == 409


def test_api_create_no_path(client):
    response = client.post("/api/create", json={"content": "no path"})
    assert response.status_code == 400


def test_api_upload(client, sample_dir):
    from io import BytesIO
    data = {
        "files": (BytesIO(b"# Uploaded"), "upload.md"),
    }
    response = client.post(
        "/api/upload",
        data=data,
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    result = response.get_json()
    assert result["success"] is True
    assert len(result["uploaded"]) == 1
    assert (sample_dir / "upload.md").exists()


def test_api_upload_non_md(client):
    from io import BytesIO
    data = {
        "files": (BytesIO(b"not markdown"), "readme.txt"),
    }
    response = client.post(
        "/api/upload",
        data=data,
        content_type="multipart/form-data",
    )
    result = response.get_json()
    assert len(result["errors"]) == 1
    assert result["errors"][0]["error"] == "Only .md files allowed"


# --- Phase 3: Rename & delete ---

def test_api_rename(client, sample_dir):
    response = client.put(
        "/api/rename",
        json={"old_path": "hello.md", "new_path": "renamed.md"},
    )
    data = response.get_json()
    assert data["success"] is True
    assert not (sample_dir / "hello.md").exists()
    assert (sample_dir / "renamed.md").exists()


def test_api_rename_move(client, sample_dir):
    response = client.put(
        "/api/rename",
        json={"old_path": "hello.md", "new_path": "newdir/moved.md"},
    )
    data = response.get_json()
    assert data["success"] is True
    assert (sample_dir / "newdir" / "moved.md").exists()


def test_api_rename_not_found(client):
    response = client.put(
        "/api/rename",
        json={"old_path": "nope.md", "new_path": "also-nope.md"},
    )
    assert response.status_code == 404


def test_api_rename_conflict(client):
    response = client.put(
        "/api/rename",
        json={"old_path": "hello.md", "new_path": "sub/nested.md"},
    )
    assert response.status_code == 409


def test_api_delete(client, sample_dir):
    response = client.delete(
        "/api/delete",
        json={"paths": ["hello.md"], "confirm": True},
    )
    data = response.get_json()
    assert data["success"] is True
    assert "hello.md" in data["deleted"]
    assert not (sample_dir / "hello.md").exists()


def test_api_delete_no_confirm(client):
    response = client.delete(
        "/api/delete",
        json={"paths": ["hello.md"], "confirm": False},
    )
    assert response.status_code == 400


def test_api_delete_not_found(client):
    response = client.delete(
        "/api/delete",
        json={"paths": ["nope.md"], "confirm": True},
    )
    data = response.get_json()
    assert len(data["errors"]) == 1


def test_api_delete_path_traversal(client):
    response = client.delete(
        "/api/delete",
        json={"paths": ["../../etc/passwd"], "confirm": True},
    )
    assert response.status_code in (403, 404)


# --- Phase 4: Directories ---

def test_api_directories(client, sample_dir):
    response = client.get(f"/api/directories?path={sample_dir}")
    data = response.get_json()
    assert "current" in data
    assert "directories" in data
    assert isinstance(data["directories"], list)
    assert data["md_count"] == 2


def test_api_directories_default(client):
    response = client.get("/api/directories")
    data = response.get_json()
    assert "current" in data


def test_api_set_base_directory(client, sample_dir):
    new_dir = sample_dir / "sub"
    response = client.post(
        "/api/set-base-directory",
        json={"path": str(new_dir)},
    )
    data = response.get_json()
    assert data["success"] is True
    assert data["file_count"] == 1  # only nested.md


def test_api_set_base_directory_invalid(client):
    response = client.post(
        "/api/set-base-directory",
        json={"path": "/nonexistent/path/12345"},
    )
    assert response.status_code == 400


# --- Content search ---

def test_api_search_content_returns_empty_for_short_query(client):
    response = client.get("/api/search/content?q=a")
    assert response.status_code == 200
    data = response.get_json()
    assert data["results"] == []
    assert data["truncated"] == False


def test_api_search_content_finds_match(client):
    response = client.get("/api/search/content?q=test file")
    data = response.get_json()
    assert any(r["path"] == "hello.md" for r in data["results"])


def test_api_search_content_returns_snippet(client):
    response = client.get("/api/search/content?q=test file")
    data = response.get_json()
    result = next(r for r in data["results"] if r["path"] == "hello.md")
    assert "test file" in result["snippet"].lower()
    assert "line_number" in result


def test_api_search_content_no_match_returns_empty(client):
    response = client.get("/api/search/content?q=zzznomatch")
    data = response.get_json()
    assert data["results"] == []


def test_api_search_content_case_insensitive(client):
    response = client.get("/api/search/content?q=HELLO")
    data = response.get_json()
    assert any(r["path"] == "hello.md" for r in data["results"])


def test_api_search_content_skips_excluded_dirs(client):
    response = client.get("/api/search/content?q=ignore")
    data = response.get_json()
    assert not any(".venv" in r["path"] for r in data["results"])


def test_api_search_content_truncates_at_50(tmp_path):
    # Create a file with 60 lines all matching "keyword"
    content = "\n".join(f"line {i} keyword here" for i in range(60))
    (tmp_path / "big.md").write_text(content, encoding="utf-8")
    app = create_app(base_dir=tmp_path)
    app.config["TESTING"] = True
    with app.test_client() as c:
        response = c.get("/api/search/content?q=keyword")
        data = response.get_json()
        assert len(data["results"]) == 50
        assert data["truncated"] is True


def test_api_search_content_bounds_submitted_work(tmp_path, monkeypatch):
    matching = "\n".join(f"line {i} keyword" for i in range(60))
    (tmp_path / "00-first.md").write_text(matching, encoding="utf-8")
    for i in range(20):
        (tmp_path / f"{i + 1:02d}-later.md").write_text(
            "no match",
            encoding="utf-8",
        )

    class RecordingExecutor:
        def __init__(self):
            self.calls = []

        def submit(self, function, *args):
            self.calls.append((function, args))
            future = Future()
            try:
                future.set_result(function(*args))
            except BaseException as exc:
                future.set_exception(exc)
            return future

    executor = RecordingExecutor()
    monkeypatch.setattr(app_module, "_search_executor", executor)
    app_module.invalidate_file_cache()
    app = create_app(base_dir=tmp_path)
    app.config["TESTING"] = True

    with app.test_client() as test_client:
        response = test_client.get("/api/search/content?q=keyword")

    data = response.get_json()
    assert len(data["results"]) == 50
    assert data["truncated"] is True
    assert len(executor.calls) == app_module._MAX_CONTENT_SEARCH_WORKERS
    assert all(
        args[-1] == app_module._MAX_CONTENT_SEARCH_RESULTS + 1
        for _function, args in executor.calls
    )

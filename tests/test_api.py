"""Tests for the API endpoints (Phases 1-4)."""

import json
from pathlib import Path

import pytest

from md_preview_server.app import create_app


@pytest.fixture
def sample_dir(tmp_path):
    """Create a temporary directory with sample markdown files."""
    (tmp_path / "hello.md").write_text("# Hello World\n\nA test file.", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "nested.md").write_text("## Nested\n\nNested content.", encoding="utf-8")
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


def test_api_files_metadata(client):
    response = client.get("/api/files")
    data = response.get_json()
    f = data["files"][0]
    assert "path" in f
    assert "name" in f
    assert "size" in f
    assert "modified" in f
    assert f["size"] > 0


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
    response = client.post(
        "/api/create",
        json={"path": "new-doc.md", "content": "# New Document"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert (sample_dir / "new-doc.md").exists()
    assert (sample_dir / "new-doc.md").read_text(encoding="utf-8") == "# New Document"


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

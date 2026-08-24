"""Tests for the editor API endpoints (Phase 5)."""

from pathlib import Path

import pytest

import md_preview_server.app as app_module
from md_preview_server.app import create_app
from md_preview_server.storage import get_file_revision


@pytest.fixture
def sample_dir(tmp_path):
    (tmp_path / "doc.md").write_text("# Original\n\nContent here.", encoding="utf-8")
    return tmp_path


@pytest.fixture
def client(sample_dir):
    app = create_app(base_dir=sample_dir)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_api_content(client, sample_dir):
    response = client.get("/api/content/doc.md")
    assert response.status_code == 200
    data = response.get_json()
    assert data["content"] == "# Original\n\nContent here."
    assert data["path"] == "doc.md"
    assert "modified" in data
    assert data["revision"] == get_file_revision(sample_dir / "doc.md")


def test_api_content_not_found(client):
    response = client.get("/api/content/nope.md")
    assert response.status_code == 404


def test_api_save(client, sample_dir):
    response = client.put(
        "/api/save",
        json={"path": "doc.md", "content": "# Updated\n\nNew content."},
    )
    data = response.get_json()
    assert data["success"] is True
    assert "modified" in data
    assert (sample_dir / "doc.md").read_text(encoding="utf-8") == "# Updated\n\nNew content."


def test_api_save_not_found(client):
    response = client.put(
        "/api/save",
        json={"path": "nope.md", "content": "x"},
    )
    assert response.status_code == 404


def test_api_save_conflict(client, sample_dir):
    # Get the file's current modified time
    response = client.get("/api/content/doc.md")
    original_modified = response.get_json()["modified"]

    # Modify the file on disk directly
    (sample_dir / "doc.md").write_text("# Changed externally", encoding="utf-8")

    # Try to save with stale last_modified
    response = client.put(
        "/api/save",
        json={
            "path": "doc.md",
            "content": "# My edit",
            "last_modified": original_modified,
        },
    )
    assert response.status_code == 409
    data = response.get_json()
    assert data["error"] == "conflict"
    assert "server_content" in data


def test_api_save_with_revision_returns_new_revision(client, sample_dir):
    loaded = client.get("/api/content/doc.md").get_json()

    response = client.put(
        "/api/save",
        json={
            "path": "doc.md",
            "content": "# Revision save",
            "revision": loaded["revision"],
        },
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["revision"] == get_file_revision(sample_dir / "doc.md")
    assert data["revision"] != loaded["revision"]


def test_api_save_rejects_stale_revision(client, sample_dir):
    loaded = client.get("/api/content/doc.md").get_json()
    target = sample_dir / "doc.md"
    target.write_text("# New external content with another size", encoding="utf-8")

    response = client.put(
        "/api/save",
        json={
            "path": "doc.md",
            "content": "# Browser overwrite",
            "revision": loaded["revision"],
        },
    )

    assert response.status_code == 409
    data = response.get_json()
    assert data["error"] == "conflict"
    assert data["server_revision"] == get_file_revision(target)
    assert target.read_text(encoding="utf-8") == "# New external content with another size"


def test_api_content_retries_to_return_matching_content_and_revision(
    client, sample_dir, monkeypatch
):
    target = sample_dir / "doc.md"
    real_read_text = Path.read_text
    changed = False

    def racing_read(path, *args, **kwargs):
        nonlocal changed
        content = real_read_text(path, *args, **kwargs)
        if path == target and not changed:
            changed = True
            target.write_text("# External edit during load", encoding="utf-8")
        return content

    monkeypatch.setattr(Path, "read_text", racing_read)

    response = client.get("/api/content/doc.md")

    assert response.status_code == 200
    data = response.get_json()
    assert data["content"] == "# External edit during load"
    assert data["revision"] == get_file_revision(target)


def test_api_save_rejects_non_markdown_target(client, sample_dir):
    target = sample_dir / "notes.txt"
    target.write_text("original", encoding="utf-8")

    response = client.put(
        "/api/save",
        json={"path": "notes.txt", "content": "replacement"},
    )

    assert response.status_code == 400
    assert target.read_text(encoding="utf-8") == "original"


def test_api_save_rejects_non_text_content(client):
    response = client.put(
        "/api/save",
        json={"path": "doc.md", "content": {"not": "text"}},
    )

    assert response.status_code == 400


def test_api_save_failure_preserves_original(client, sample_dir, monkeypatch):
    target = sample_dir / "doc.md"

    def fail_write(*args, **kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(app_module, "atomic_write_text", fail_write)

    response = client.put(
        "/api/save",
        json={"path": "doc.md", "content": "replacement"},
    )

    assert response.status_code == 500
    assert target.read_text(encoding="utf-8") == "# Original\n\nContent here."


def test_api_save_no_path(client):
    response = client.put("/api/save", json={"content": "no path"})
    assert response.status_code == 400


def test_api_save_no_content(client):
    response = client.put("/api/save", json={"path": "doc.md"})
    assert response.status_code == 400


def test_api_preview(client):
    response = client.post(
        "/api/preview",
        json={"content": "# Hello\n\n**bold**"},
    )
    data = response.get_json()
    assert "<h1" in data["html"]
    assert "<strong>bold</strong>" in data["html"]


def test_api_preview_empty(client):
    response = client.post("/api/preview", json={"content": ""})
    data = response.get_json()
    assert data["html"] == ""


def test_api_content_path_traversal(client):
    response = client.get("/api/content/../../etc/passwd")
    assert response.status_code in (403, 404)


def test_api_save_path_traversal(client):
    response = client.put(
        "/api/save",
        json={"path": "../../etc/evil.md", "content": "x"},
    )
    assert response.status_code in (403, 404)

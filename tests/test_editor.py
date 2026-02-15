"""Tests for the editor API endpoints (Phase 5)."""

from pathlib import Path

import pytest

from md_preview_server.app import create_app


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


def test_api_content(client):
    response = client.get("/api/content/doc.md")
    assert response.status_code == 200
    data = response.get_json()
    assert data["content"] == "# Original\n\nContent here."
    assert data["path"] == "doc.md"
    assert "modified" in data


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

"""Tests for the HTML export endpoint."""

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


def test_export_html_returns_200(client):
    response = client.get("/api/export/html/hello.md")
    assert response.status_code == 200


def test_export_html_content_disposition(client):
    response = client.get("/api/export/html/hello.md")
    disposition = response.headers.get("Content-Disposition", "")
    assert "attachment" in disposition
    assert "hello.html" in disposition


def test_export_html_contains_rendered_content(client):
    response = client.get("/api/export/html/hello.md")
    data = response.data.decode("utf-8")
    assert "<h1" in data
    assert "Hello World" in data


def test_export_html_is_standalone(client):
    response = client.get("/api/export/html/hello.md")
    data = response.data.decode("utf-8")
    assert "<!DOCTYPE html>" in data
    assert "<style>" in data


def test_export_html_inlines_css(client):
    response = client.get("/api/export/html/hello.md")
    data = response.data.decode("utf-8")
    assert ".codehilite" in data
    assert ".markdown-body" in data


def test_export_html_nested_file(client):
    response = client.get("/api/export/html/sub/nested.md")
    assert response.status_code == 200
    data = response.data.decode("utf-8")
    assert "Nested" in data


def test_export_html_nonexistent_returns_404(client):
    response = client.get("/api/export/html/nope.md")
    assert response.status_code == 404


def test_export_html_path_traversal_returns_403(client):
    response = client.get("/api/export/html/../../etc/passwd")
    assert response.status_code in (403, 404)

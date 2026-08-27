"""Tests for the Flask application."""

import json
import os
import queue
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
    return tmp_path


@pytest.fixture
def client(sample_dir):
    """Create a Flask test client with the sample directory."""
    app = create_app(base_dir=sample_dir)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_index_returns_200(client):
    response = client.get("/")
    assert response.status_code == 200


def test_index_lists_files(client):
    response = client.get("/")
    data = response.data.decode("utf-8")
    assert "hello.md" in data


def test_view_file_returns_200(client):
    response = client.get("/view/hello.md")
    assert response.status_code == 200


def test_view_file_renders_markdown(client):
    response = client.get("/view/hello.md")
    data = response.data.decode("utf-8")
    assert "<h1" in data
    assert "Hello World" in data


def test_view_nested_file(client):
    response = client.get("/view/sub/nested.md")
    assert response.status_code == 200
    data = response.data.decode("utf-8")
    assert "Nested" in data


def test_view_nonexistent_returns_404(client):
    response = client.get("/view/does-not-exist.md")
    assert response.status_code == 404


def test_path_traversal_blocked(client):
    response = client.get("/view/../../etc/passwd")
    assert response.status_code in (403, 404)


def test_events_endpoint(client):
    response = client.get("/events", buffered=False)
    assert response.content_type.startswith("text/event-stream")
    assert next(response.response) == b": connected\n\n"
    response.close()


def test_events_endpoint_removes_closed_subscriber(client):
    initial_subscribers = len(app_module._subscribers)
    response = client.get("/events", buffered=False)

    assert next(response.response) == b": connected\n\n"
    assert len(app_module._subscribers) == initial_subscribers + 1

    response.close()
    assert len(app_module._subscribers) == initial_subscribers


def test_notify_clients_includes_file_revision():
    subscriber = queue.Queue()
    with app_module._subscribers_lock:
        app_module._subscribers.append(subscriber)

    try:
        app_module.notify_clients("notes/doc.md", "file_modified", "123:45")
        payload = json.loads(subscriber.get_nowait())
    finally:
        with app_module._subscribers_lock:
            app_module._subscribers.remove(subscriber)

    assert payload == {
        "type": "file_modified",
        "file": "notes/doc.md",
        "revision": "123:45",
    }

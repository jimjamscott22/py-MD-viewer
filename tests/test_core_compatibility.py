"""Compatibility tests for the pre-extraction server import paths."""

import md_preview_core.renderer as core_renderer
import md_preview_core.storage as core_storage
import md_preview_core.watcher as core_watcher
import md_preview_server.renderer as server_renderer
import md_preview_server.storage as server_storage
import md_preview_server.watcher as server_watcher


def test_server_renderer_reexports_core_api():
    assert server_renderer.render_markdown is core_renderer.render_markdown


def test_server_storage_reexports_core_api():
    assert server_storage.atomic_write_text is core_storage.atomic_write_text
    assert server_storage.FileRevisionMismatch is core_storage.FileRevisionMismatch


def test_server_watcher_reexports_core_api():
    assert server_watcher.MarkdownFileHandler is core_watcher.MarkdownFileHandler
    assert server_watcher.start_watcher is core_watcher.start_watcher

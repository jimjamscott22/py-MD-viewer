"""Tests for the markdown renderer."""

import os

from md_preview_server.renderer import render_markdown, render_markdown_cached_with_meta


def test_heading():
    result = render_markdown("# Hello")
    assert "<h1" in result
    assert "Hello" in result
    assert "headerlink" not in result
    assert "&para;" not in result


def test_bold_and_italic():
    result = render_markdown("**bold** and *italic*")
    assert "<strong>bold</strong>" in result
    assert "<em>italic</em>" in result


def test_fenced_code_block():
    md = '```python\nprint("hello")\n```'
    result = render_markdown(md)
    assert "codehilite" in result
    assert "print" in result


def test_plain_code_block():
    md = "```\nplain text\n```"
    result = render_markdown(md)
    assert "plain text" in result


def test_inline_code():
    result = render_markdown("Use `my_var` here")
    assert "<code>my_var</code>" in result


def test_table():
    md = "| A | B |\n|---|---|\n| 1 | 2 |"
    result = render_markdown(md)
    assert "<table>" in result
    assert "<td>1</td>" in result


def test_blockquote():
    result = render_markdown("> A quote")
    assert "<blockquote>" in result


def test_link():
    result = render_markdown("[click](https://example.com)")
    assert 'href="https://example.com"' in result
    assert "click" in result


def test_toc():
    md = "[TOC]\n\n# Section One\n\n## Section Two"
    result = render_markdown(md)
    assert "toc" in result.lower()


def test_cached_render_refreshes_when_size_changes_with_same_mtime(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("# One\n", encoding="utf-8")
    stat = doc.stat()

    html, _ = render_markdown_cached_with_meta(doc)
    assert "One" in html

    doc.write_text("# Two\n\nextra text\n", encoding="utf-8")
    os.utime(doc, ns=(stat.st_atime_ns, stat.st_mtime_ns))

    html, _ = render_markdown_cached_with_meta(doc)
    assert "Two" in html
    assert "One" not in html

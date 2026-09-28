"""mdview:// request resolution and link routing."""

import pytest
from PyQt6.QtCore import QUrl

from md_preview_core.files import PathOutsideBaseError
from md_viewer_desktop.document_view import (
    NotFound,
    build_page,
    doc_url,
    rel_path_from_url,
    resolve_request,
)


@pytest.fixture
def docs(tmp_path):
    base = tmp_path / "docs"
    (base / "img").mkdir(parents=True)
    (base / "README.md").write_text(
        "---\ntitle: Hello <Doc>\ntags: [a, b]\n---\n# Title\n\n![x](img/pic.png)\n\n"
        "```mermaid\ngraph TD\n  A --> B\n```\n\n$$x^2$$\n\n<script>alert(1)</script>\n",
        encoding="utf-8",
    )
    (base / "img" / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    (tmp_path / "secret.md").write_text("# secret", encoding="utf-8")
    return base


def test_renders_markdown_page(docs):
    response = resolve_request(docs, "doc", "/README.md", "jamielab")
    page = response.body.decode()
    assert response.mime == "text/html"
    assert '<html lang="en" data-theme="jamielab">' in page
    assert "<title>Hello &lt;Doc&gt;</title>" in page
    assert '<h1 id="title">Title</h1>' in page
    assert '<span class="tag-pill">a</span>' in page
    assert "mdview://app/vendor/mermaid/mermaid.min.js" in page
    assert "mdview://app/vendor/katex/katex.min.js" in page
    assert "Content-Security-Policy" in page
    assert "script-src mdview://app;" in page


def test_page_without_diagrams_skips_heavy_scripts():
    page = build_page(title="t", content="<p>plain</p>", doc_theme="")
    assert "mermaid" not in page
    assert "katex" not in page
    assert "mdview://app/js/page.js" in page


def test_serves_sibling_assets(docs):
    response = resolve_request(docs, "doc", "/img/pic.png", "jamielab")
    assert response.mime == "image/png"
    assert response.body.startswith(b"\x89PNG")


@pytest.mark.parametrize(
    "path",
    ["/../secret.md", "/../../etc/passwd", "/img/../../secret.md"],
)
def test_rejects_path_traversal(docs, path):
    with pytest.raises(PathOutsideBaseError):
        resolve_request(docs, "doc", path, "jamielab")


def test_rejects_symlink_escape(docs, tmp_path):
    (docs / "link.md").symlink_to(tmp_path / "secret.md")
    with pytest.raises(PathOutsideBaseError):
        resolve_request(docs, "doc", "/link.md", "jamielab")


@pytest.mark.parametrize(
    "raw",
    [
        "mdview://doc/%2E%2E/secret.md",
        "mdview://doc/..%2Fsecret.md",
        "mdview://doc/img/%2e%2e%2f%2e%2e%2fsecret.md",
    ],
)
def test_encoded_traversal_in_url_is_rejected(docs, raw):
    url = QUrl(raw)
    with pytest.raises(PathOutsideBaseError):
        resolve_request(docs, url.host(), "/" + rel_path_from_url(url), "jamielab")


def test_missing_markdown_renders_error_page(docs):
    response = resolve_request(docs, "doc", "/nope.md", "jamielab")
    assert "not found · nope.md" in response.body.decode()
    assert "doc-message-error" in response.body.decode()


def test_missing_asset_is_not_found(docs):
    with pytest.raises(NotFound):
        resolve_request(docs, "doc", "/img/missing.png", "jamielab")


def test_doc_requests_need_a_base_dir():
    with pytest.raises(NotFound):
        resolve_request(None, "doc", "/README.md", "jamielab")


def test_unknown_host_is_not_found(docs):
    with pytest.raises(NotFound):
        resolve_request(docs, "elsewhere", "/README.md", "jamielab")


def test_app_host_serves_shared_css_without_remote_imports():
    response = resolve_request(None, "app", "/css/style.css", "jamielab")
    assert response.mime == "text/css"
    assert b"--color-bg" in response.body
    assert b"@import" not in response.body
    assert b"fonts.googleapis.com" not in response.body


@pytest.mark.parametrize(
    "path, mime",
    [
        ("/css/codehilite.css", "text/css"),
        ("/css/theme-jamielab.css", "text/css"),
        ("/js/page.js", "text/javascript"),
        ("/vendor/mermaid/mermaid.min.js", "text/javascript"),
        ("/vendor/katex/katex.min.css", "text/css"),
        ("/vendor/katex/auto-render.min.js", "text/javascript"),
        ("/fonts/IBMPlexMono-Regular.woff2", "font/woff2"),
    ],
)
def test_app_host_serves_bundled_assets(path, mime):
    response = resolve_request(None, "app", path, "jamielab")
    assert response.mime == mime
    assert response.body


def test_print_css_is_light_and_print_only():
    response = resolve_request(None, "app", "/css/print.css", "jamielab")
    css = response.body.decode()
    assert response.mime == "text/css"
    assert css.startswith("@media print {")
    assert ".markdown-body .codehilite .k" in css
    page = build_page(title="t", content="<p>x</p>", doc_theme="")
    assert 'href="mdview://app/css/print.css" media="print"' in page


def test_app_host_rejects_traversal():
    with pytest.raises(PathOutsideBaseError):
        resolve_request(None, "app", "/../theme.py", "jamielab")


def test_welcome_page():
    response = resolve_request(None, "app", "/welcome", "light")
    page = response.body.decode()
    assert 'data-theme="light"' in page
    assert "no file open" in page


def test_doc_url_round_trips_unicode_and_spaces():
    rel = "notes/my file é.md"
    url = doc_url(rel, "part")
    assert url.scheme() == "mdview"
    assert url.host() == "doc"
    assert url.fragment() == "part"
    assert rel_path_from_url(url) == rel

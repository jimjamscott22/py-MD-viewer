"""Rendered-document view: ``mdview://`` scheme handler + QWebEngineView.

URL layout (no HTTP server involved):

``mdview://doc/<relpath>``
    ``.md`` files are rendered to a full HTML page; any other file under
    the base directory (images next to the doc) is served as-is. Relative
    links in a document therefore resolve naturally.
``mdview://app/<path>``
    Bundled CSS, fonts, scripts and vendored Mermaid/KaTeX.

Every ``doc`` path goes through :func:`md_preview_core.files.validate_path`.
"""

from __future__ import annotations

import html
import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineUrlRequestJob,
    QWebEngineUrlScheme,
    QWebEngineUrlSchemeHandler,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

from md_preview_core.files import PathOutsideBaseError, validate_path
from md_preview_core.renderer import render_markdown_cached_with_meta

SCHEME = "mdview"
DOC_HOST = "doc"
APP_HOST = "app"

RESOURCES = Path(__file__).resolve().parent / "resources"
# style.css and codehilite.css are shared with the Flask app, not copied.
SERVER_CSS = Path(__file__).resolve().parent.parent / "md_preview_server" / "static" / "css"

_APP_ROOTS = {
    "css/style.css": SERVER_CSS / "style.css",
    "css/codehilite.css": SERVER_CSS / "codehilite.css",
}

WELCOME_PATH = "/welcome"


class NotFound(LookupError):
    """The requested ``mdview://`` resource does not exist."""


@dataclass
class Response:
    body: bytes
    mime: str


def register_scheme() -> None:
    """Register ``mdview://``. Must run before ``QApplication`` exists."""
    if QWebEngineUrlScheme.schemeByName(SCHEME.encode()).name():
        return
    scheme = QWebEngineUrlScheme(SCHEME.encode())
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.Host)
    Flag = QWebEngineUrlScheme.Flag
    scheme.setFlags(Flag.SecureScheme | Flag.LocalScheme | Flag.CorsEnabled)
    QWebEngineUrlScheme.registerScheme(scheme)


def doc_url(rel_path: str, fragment: str = "") -> QUrl:
    url = QUrl()
    url.setScheme(SCHEME)
    url.setHost(DOC_HOST)
    url.setPath("/" + rel_path.lstrip("/"))
    if fragment:
        url.setFragment(fragment)
    return url


def welcome_url() -> QUrl:
    return QUrl(f"{SCHEME}://{APP_HOST}{WELCOME_PATH}")


def rel_path_from_url(url: QUrl) -> str:
    return url.path(QUrl.ComponentFormattingOption.FullyDecoded).lstrip("/")


# ── Page assembly ───────────────────────────────────────────────────

_TEMPLATE: Template | None = None


def _template() -> Template:
    global _TEMPLATE
    if _TEMPLATE is None:
        _TEMPLATE = Template((RESOURCES / "page_template.html").read_text(encoding="utf-8"))
    return _TEMPLATE


def _frontmatter_html(metadata: dict[str, Any]) -> str:
    if not metadata:
        return ""
    rows = []
    for key, value in metadata.items():
        if key == "title":
            continue
        if key == "tags" and isinstance(value, list):
            rendered = "".join(
                f'<span class="tag-pill">{html.escape(str(tag))}</span>' for tag in value
            )
        else:
            rendered = html.escape(str(value))
        rows.append(
            f'<div class="frontmatter-item"><dt>{html.escape(str(key))}</dt>'
            f"<dd>{rendered}</dd></div>"
        )
    if not rows:
        return ""
    return (
        '<div class="frontmatter-card surface-panel">'
        f'<dl class="frontmatter-meta">{"".join(rows)}</dl></div>'
    )


def build_page(
    *,
    title: str,
    content: str,
    doc_theme: str,
    metadata: dict[str, Any] | None = None,
    meta_line: str = "",
) -> str:
    """Wrap rendered Markdown in the desktop page shell."""
    styles = []
    scripts = []
    if "arithmatex" in content:
        styles.append("mdview://app/vendor/katex/katex.min.css")
        scripts += [
            "mdview://app/vendor/katex/katex.min.js",
            "mdview://app/vendor/katex/auto-render.min.js",
        ]
    if 'class="mermaid"' in content:
        scripts.append("mdview://app/vendor/mermaid/mermaid.min.js")
    scripts.append("mdview://app/js/page.js")

    return _template().substitute(
        theme=html.escape(doc_theme, quote=True),
        title=html.escape(title),
        extra_styles="".join(f'<link rel="stylesheet" href="{href}">\n' for href in styles),
        scripts="".join(f'<script src="{src}"></script>\n' for src in scripts),
        meta_line=html.escape(meta_line),
        frontmatter=_frontmatter_html(metadata or {}),
        content=content,
    )


def _message_page(title: str, message: str, doc_theme: str, *, error: bool = False) -> bytes:
    css_class = "doc-message doc-message-error" if error else "doc-message"
    body = f'<p class="{css_class}">{html.escape(message)}</p>'
    return build_page(title=title, content=body, doc_theme=doc_theme).encode()


def resolve_request(
    base_dir: Path | None,
    host: str,
    path: str,
    doc_theme: str,
) -> Response:
    """Map an ``mdview://<host><path>`` request to a response body.

    Raises :class:`PathOutsideBaseError` for traversal attempts and
    :class:`NotFound` for anything missing.
    """
    rel = path.lstrip("/")
    if host == APP_HOST:
        if path == WELCOME_PATH:
            return Response(
                _message_page("MD Viewer", "no file open · File → Open… (Ctrl+O)", doc_theme),
                "text/html",
            )
        target = _APP_ROOTS.get(rel)
        if target is None:
            target = validate_path(RESOURCES, rel)
        if not target.is_file():
            raise NotFound(rel)
        return Response(_read_app_file(rel, target), _mime(target))

    if host != DOC_HOST or base_dir is None:
        raise NotFound(f"{host}{path}")

    target = validate_path(base_dir, rel)
    if target.suffix.lower() == ".md":
        if not target.is_file():
            return Response(
                _message_page(rel, f"not found · {rel}", doc_theme, error=True), "text/html"
            )
        try:
            content, metadata = render_markdown_cached_with_meta(target)
        except (OSError, UnicodeDecodeError) as exc:
            return Response(
                _message_page(rel, f"cannot read {rel}: {exc}", doc_theme, error=True),
                "text/html",
            )
        title = str(metadata.get("title") or target.name)
        page = build_page(
            title=title,
            content=content,
            doc_theme=doc_theme,
            metadata=metadata,
            meta_line=rel,
        )
        return Response(page.encode(), "text/html")

    if not target.is_file():
        raise NotFound(rel)
    return Response(target.read_bytes(), _mime(target))


def _read_app_file(rel: str, target: Path) -> bytes:
    data = target.read_bytes()
    if rel == "css/style.css":
        # The web app pulls JetBrains Mono from Google Fonts; the desktop app
        # is offline-first, so drop remote @imports instead of leaking a request.
        lines = data.decode("utf-8").splitlines(keepends=True)
        data = "".join(line for line in lines if not line.lstrip().startswith("@import")).encode()
    return data


def _mime(path: Path) -> str:
    overrides = {".woff2": "font/woff2", ".woff": "font/woff", ".js": "text/javascript"}
    if path.suffix.lower() in overrides:
        return overrides[path.suffix.lower()]
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


class SchemeHandler(QWebEngineUrlSchemeHandler):
    """Serves ``mdview://`` requests from :func:`resolve_request`."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.base_dir: Path | None = None
        self.doc_theme = "jamielab"

    def requestStarted(self, job: QWebEngineUrlRequestJob) -> None:  # noqa: N802 (Qt API)
        url = job.requestUrl()
        path = url.path(QUrl.ComponentFormattingOption.FullyDecoded)
        try:
            response = resolve_request(self.base_dir, url.host(), path, self.doc_theme)
        except PathOutsideBaseError:
            job.fail(QWebEngineUrlRequestJob.Error.RequestDenied)
            return
        except (NotFound, OSError):
            job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
            return

        buffer = QBuffer(job)
        buffer.setData(response.body)
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        # doc pages load fonts/scripts from the app host; allow that origin hop.
        job.setAdditionalResponseHeaders(
            {QByteArray(b"Access-Control-Allow-Origin"): QByteArray(b"*")}
        )
        job.reply(response.mime.encode(), buffer)


# ── Page + view ─────────────────────────────────────────────────────


class DocumentPage(QWebEnginePage):
    """Routes link clicks: ``.md`` → app, http(s)/mailto → browser, else blocked."""

    openDocument = pyqtSignal(str, str)  # rel_path, fragment
    linkBlocked = pyqtSignal(str)

    EXTERNAL_SCHEMES = {"http", "https", "mailto"}

    def acceptNavigationRequest(  # noqa: N802 (Qt API)
        self, url: QUrl, nav_type: QWebEnginePage.NavigationType, is_main_frame: bool
    ) -> bool:
        scheme = url.scheme()
        if nav_type != QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            # Our own loads, reloads and history: only ever mdview://.
            return scheme == SCHEME

        if scheme in self.EXTERNAL_SCHEMES:
            QDesktopServices.openUrl(url)
            return False

        if scheme == SCHEME and url.host() == DOC_HOST:
            current = self.url()
            if url.matches(current, QUrl.UrlFormattingOption.RemoveFragment):
                return True  # in-page anchor
            rel_path = rel_path_from_url(url)
            if rel_path.lower().endswith(".md"):
                self.openDocument.emit(rel_path, url.fragment())
                return False

        self.linkBlocked.emit(url.toDisplayString())
        return False


class DocumentView(QWebEngineView):
    """A ``QWebEngineView`` that shows one rendered document at a time."""

    def __init__(self, profile: QWebEngineProfile, parent=None):
        super().__init__(parent)
        self._page = DocumentPage(profile, self)
        self.setPage(self._page)
        self._pending_scroll: QPointF | None = None
        self.current_path: str | None = None
        self.loadFinished.connect(self._restore_scroll)

    @property
    def document_page(self) -> DocumentPage:
        return self._page

    def show_welcome(self) -> None:
        self.current_path = None
        self._pending_scroll = None
        self.load(welcome_url())

    def open_document(self, rel_path: str, fragment: str = "") -> None:
        self.current_path = rel_path
        self._pending_scroll = None
        self.load(doc_url(rel_path, fragment))

    def reload_document(self) -> None:
        """Re-render the current document, keeping the scroll position."""
        self._pending_scroll = self._page.scrollPosition()
        self.load(self.url())

    def set_doc_theme(self, doc_theme: str) -> None:
        self._page.runJavaScript(f"window.mdviewSetTheme && window.mdviewSetTheme({json.dumps(doc_theme)})")

    def _restore_scroll(self, ok: bool) -> None:
        position, self._pending_scroll = self._pending_scroll, None
        if ok and position is not None and (position.x() or position.y()):
            self._page.runJavaScript(f"window.scrollTo({position.x():.0f}, {position.y():.0f})")

"""Main window: menus, file tree dock, document view, status bar."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QActionGroup, QCloseEvent, QDragEnterEvent, QDropEvent, QKeySequence
from PyQt6.QtWebEngineCore import QWebEngineProfile
from PyQt6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from md_preview_core.files import PathOutsideBaseError, validate_path

from . import __version__
from . import theme as theme_mod
from .document_view import SCHEME, DocumentView, SchemeHandler
from .file_tree import FileTree
from .settings import Settings
from .theme import Theme
from .watcher_bridge import WatcherBridge

APP_NAME = "MD Viewer"


@dataclass(frozen=True)
class DocTheme:
    key: str  # stored in QSettings
    label: str  # View → Theme menu text
    attr: str  # data-theme value understood by style.css / theme-jamielab.css
    jamielab_chrome: bool  # False → stock light Fusion chrome


DOC_THEMES = (
    DocTheme("jamielab", "jamielab", "jamielab", True),
    DocTheme("terminal", "Terminal", "", True),
    DocTheme("amber", "Amber", "amber", True),
    DocTheme("dracula", "Dracula", "dracula", True),
    DocTheme("nord", "Nord", "nord", True),
    DocTheme("paper", "Paper", "light", False),
)
DOC_THEMES_BY_KEY = {t.key: t for t in DOC_THEMES}


def is_markdown(path: Path) -> bool:
    return path.suffix.lower() == ".md"


class MainWindow(QMainWindow):
    def __init__(self, app: QApplication, theme: Theme, settings: Settings):
        super().__init__()
        self._app = app
        self._theme = theme
        self._settings = settings
        self._doc_theme = DOC_THEMES_BY_KEY.get(settings.theme, DOC_THEMES[0])
        self.base_dir: Path | None = None

        self.setWindowTitle(APP_NAME)
        self.resize(1200, 800)
        self.setAcceptDrops(True)

        # Off-the-record profile: no disk cache, so a reload always re-renders.
        # Parented to the app so it outlives the page (Qt requires the page to
        # be deleted first).
        self._profile = QWebEngineProfile(app)
        self._scheme_handler = SchemeHandler(self)
        self._scheme_handler.doc_theme = self._doc_theme.attr
        self._profile.installUrlSchemeHandler(SCHEME.encode(), self._scheme_handler)

        self.view = DocumentView(self._profile, self)
        self.view.setAcceptDrops(False)  # let file drops reach the window
        # Queued: starting a new load from inside acceptNavigationRequest
        # re-enters Chromium's navigation and aborts the process.
        self.view.document_page.openDocument.connect(
            self._on_link_to_document, Qt.ConnectionType.QueuedConnection
        )
        self.view.document_page.linkBlocked.connect(
            lambda url: self.show_status(f"link blocked · {url}", "warning")
        )
        self.setCentralWidget(self.view)

        self.tree = FileTree(self)
        self.tree.fileActivated.connect(self.open_document)
        dock_body = QWidget(self)
        layout = QVBoxLayout(dock_body)
        margin = theme.space["space-2"]
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(theme.space["space-2"])
        layout.addWidget(self.tree)
        # QSS has no text-transform; label tokens are uppercase in UI.
        self.files_dock = QDockWidget("FILES", self)
        self.files_dock.setObjectName("files-dock")
        self.files_dock.setWidget(dock_body)
        self.files_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.files_dock)
        self.resizeDocks([self.files_dock], [280], Qt.Orientation.Horizontal)

        self.status_label = QLabel(self)
        self.statusBar().addWidget(self.status_label, 1)
        self.statusBar().setSizeGripEnabled(False)

        self.watcher = WatcherBridge(self)
        self.watcher.fileChanged.connect(self._on_file_changed)
        self._tree_refresh = QTimer(self)
        self._tree_refresh.setSingleShot(True)
        self._tree_refresh.setInterval(200)
        self._tree_refresh.timeout.connect(self._refresh_tree)

        self._build_menus()
        self._restore_geometry()
        self._apply_chrome()

    # ── Menus ───────────────────────────────────────────────────────

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        self.open_action = self._action(file_menu, "&Open…", QKeySequence.StandardKey.Open, self.choose_file)
        self.open_folder_action = self._action(
            file_menu, "Open &Folder…", QKeySequence("Ctrl+Shift+O"), self.choose_folder
        )
        file_menu.addSeparator()
        self.reload_action = self._action(file_menu, "&Reload", QKeySequence.StandardKey.Refresh, self.reload)
        file_menu.addSeparator()
        self._action(file_menu, "&Quit", QKeySequence.StandardKey.Quit, self.close)

        view_menu = self.menuBar().addMenu("&View")
        toggle_files = self.files_dock.toggleViewAction()
        toggle_files.setText("&Files Panel")
        toggle_files.setShortcut(QKeySequence("Ctrl+Shift+E"))
        view_menu.addAction(toggle_files)
        theme_menu = view_menu.addMenu("&Theme")
        self.theme_group = QActionGroup(self)
        self.theme_group.setExclusive(True)
        self.theme_actions: dict[str, QAction] = {}
        for doc_theme in DOC_THEMES:
            action = QAction(doc_theme.label, self, checkable=True)
            action.setData(doc_theme.key)
            action.setChecked(doc_theme is self._doc_theme)
            action.triggered.connect(lambda _=False, key=doc_theme.key: self.set_theme(key))
            self.theme_group.addAction(action)
            theme_menu.addAction(action)
            self.theme_actions[doc_theme.key] = action

        help_menu = self.menuBar().addMenu("&Help")
        self._action(help_menu, "&About MD Viewer", None, self.show_about)

    def _action(self, menu, text, shortcut, slot) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(shortcut)
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    # ── Opening things ──────────────────────────────────────────────

    def open_path(self, path: Path) -> bool:
        """Open a file (with its folder in the tree) or a folder."""
        path = path.expanduser().resolve()
        if path.is_dir():
            self.set_base_dir(path)
            self.view.show_welcome()
            self._remember(None)
            self._update_title()
            return True
        if not path.is_file():
            self.show_status(f"not found · {path}", "error")
            return False
        if not is_markdown(path):
            self.show_status(f"not a markdown file · {path.name}", "error")
            return False
        if self.base_dir is None or not path.is_relative_to(self.base_dir):
            self.set_base_dir(path.parent)
        self.open_document(path.relative_to(self.base_dir).as_posix())
        return True

    def set_base_dir(self, base_dir: Path) -> None:
        base_dir = base_dir.resolve()
        if base_dir == self.base_dir:
            return
        self.base_dir = base_dir
        self._scheme_handler.base_dir = base_dir
        # Relative paths from the old folder mean nothing in the new one.
        self.view.current_path = None
        self.tree.set_base_dir(base_dir)
        self.watcher.start(base_dir)
        self._settings.last_folder = base_dir
        self._update_title()
        self.show_status(f"folder · {base_dir}")

    def open_document(self, rel_path: str, fragment: str = "") -> None:
        if self.base_dir is None:
            return
        try:
            validate_path(self.base_dir, rel_path)
        except PathOutsideBaseError:
            self.show_status(f"outside folder · {rel_path}", "error")
            return
        if rel_path == self.view.current_path and not fragment:
            return
        self.view.open_document(rel_path, fragment)
        self.tree.select_path(rel_path)
        self._remember(rel_path)
        self._update_title()
        self.show_status(f"opened · {rel_path}")

    def choose_file(self) -> None:
        start = str(self.base_dir or Path.home())
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open Markdown File", start, "Markdown (*.md);;All files (*)"
        )
        if filename:
            self.open_path(Path(filename))

    def choose_folder(self) -> None:
        start = str(self.base_dir or Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Open Folder", start)
        if folder:
            self.open_path(Path(folder))

    def reload(self) -> None:
        if self.view.current_path:
            self.view.reload_document()
            self.show_status(f"reloaded · {self.view.current_path}")
        self._refresh_tree()

    def restore_session(self) -> None:
        last_file, last_folder = self._settings.last_file, self._settings.last_folder
        if last_folder and last_folder.is_dir():
            self.set_base_dir(last_folder)
        if last_file and last_file.is_file() and self.open_path(last_file):
            return
        self.view.show_welcome()
        if self.base_dir is None:
            self.show_status("no folder open · File → Open Folder… (Ctrl+Shift+O)")

    def _on_link_to_document(self, rel_path: str, fragment: str) -> None:
        if self.base_dir is None:
            return
        try:
            exists = validate_path(self.base_dir, rel_path).is_file()
        except PathOutsideBaseError:
            self.show_status(f"outside folder · {rel_path}", "error")
            return
        if not exists:
            self.show_status(f"not found · {rel_path}", "error")
            return
        self.open_document(rel_path, fragment)

    def _remember(self, rel_path: str | None) -> None:
        self._settings.last_file = (self.base_dir / rel_path) if (rel_path and self.base_dir) else None

    # ── Live reload ─────────────────────────────────────────────────

    def _on_file_changed(self, rel_path: str, event_type: str, _revision: str) -> None:
        if event_type == "tree_changed":
            self._tree_refresh.start()
        if rel_path != self.view.current_path or self.base_dir is None:
            return
        if (self.base_dir / rel_path).is_file():
            self.view.reload_document()
            self.show_status(f"reloaded · {rel_path}")
        else:
            self.show_status(f"deleted on disk · {rel_path}", "warning")

    def _refresh_tree(self) -> None:
        self.tree.rebuild()
        if self.view.current_path:
            self.tree.select_path(self.view.current_path)

    # ── Theme ───────────────────────────────────────────────────────

    def set_theme(self, key: str) -> None:
        doc_theme = DOC_THEMES_BY_KEY.get(key)
        if doc_theme is None:
            return
        self._doc_theme = doc_theme
        self._settings.theme = key
        self._scheme_handler.doc_theme = doc_theme.attr
        self.theme_actions[key].setChecked(True)
        self.view.set_doc_theme(doc_theme.attr)
        self._apply_chrome()
        self.show_status(f"theme · {doc_theme.label}")

    @property
    def doc_theme(self) -> DocTheme:
        return self._doc_theme

    def _apply_chrome(self) -> None:
        if self._doc_theme.jamielab_chrome:
            theme_mod.apply(self._app, self._theme)
        else:
            theme_mod.clear(self._app)

    # ── Status / title / about ──────────────────────────────────────

    def show_status(self, message: str, state: str = "") -> None:
        self.status_label.setText(message)
        if self.status_label.property("state") != state:
            self.status_label.setProperty("state", state)
            self.status_label.style().unpolish(self.status_label)
            self.status_label.style().polish(self.status_label)

    def _update_title(self) -> None:
        if self.view.current_path:
            self.setWindowTitle(f"{Path(self.view.current_path).name} — {APP_NAME}")
        elif self.base_dir:
            self.setWindowTitle(f"{self.base_dir.name or self.base_dir} — {APP_NAME}")
        else:
            self.setWindowTitle(APP_NAME)

    def show_about(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(f"About {APP_NAME}")
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(
            '<p style="font-weight:600">jamielab</p>'
            f'<p style="font-weight:600; font-size:{self._theme.type["h2"].size}px">{APP_NAME}</p>'
            f"<p>version {__version__}</p>"
        )
        box.exec()

    # ── Window lifecycle / drag and drop ────────────────────────────

    def _restore_geometry(self) -> None:
        if (geometry := self._settings.geometry) is not None:
            self.restoreGeometry(geometry)
        if (state := self._settings.window_state) is not None:
            self.restoreState(state)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt API)
        self._settings.geometry = self.saveGeometry()
        self._settings.window_state = self.saveState()
        self._settings.sync()
        self.watcher.stop()
        super().closeEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 (Qt API)
        if self._dropped_path(event) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 (Qt API)
        path = self._dropped_path(event)
        if path is not None:
            event.acceptProposedAction()
            self.open_path(path)

    @staticmethod
    def _dropped_path(event) -> Path | None:
        for url in event.mimeData().urls() if event.mimeData().hasUrls() else []:
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if path.is_dir() or is_markdown(path):
                    return path
        return None

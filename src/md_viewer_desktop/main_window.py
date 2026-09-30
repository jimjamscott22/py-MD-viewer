"""Main window: menus, toolbar, file tree + contents docks, document tabs."""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from pathlib import Path

from PyQt6 import sip
from PyQt6.QtCore import QLocale, QMarginsF, QSize, Qt, QTimer
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QDragEnterEvent,
    QDropEvent,
    QKeySequence,
    QPageLayout,
    QPageSize,
    QTextDocument,
)
from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
from PyQt6.QtWebEngineCore import QWebEngineFindTextResult, QWebEnginePage, QWebEngineProfile
from PyQt6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QTabBar,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from md_preview_core.files import PathOutsideBaseError, invalidate_file_cache, validate_path
from md_preview_core.renderer import render_markdown

from . import __version__
from . import icons
from . import theme as theme_mod
from .document_view import SCHEME, DocumentView, SchemeHandler
from .file_tree import FileTree
from .file_operations import FileOperations
from .find_bar import FindBar
from .settings import SessionTab, Settings
from .search_panel import SearchPanel
from .theme import Theme
from .toc_panel import TocPanel
from .watcher_bridge import WatcherBridge

APP_NAME = "MD Viewer"
ZOOM_STEPS = (0.5, 0.67, 0.75, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)
RECENT_SHOWN = 10


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


def display_path(path: Path) -> str:
    """``~/notes/a.md`` style, for menus and tooltips."""
    try:
        return f"~/{path.relative_to(Path.home()).as_posix()}"
    except ValueError:
        return str(path)


class MainWindow(QMainWindow):
    def __init__(self, app: QApplication, theme: Theme, settings: Settings):
        super().__init__()
        self._app = app
        self._theme = theme
        self._settings = settings
        self._doc_theme = DOC_THEMES_BY_KEY.get(settings.theme, DOC_THEMES[0])
        self._zoom = settings.zoom
        self.base_dir: Path | None = None
        self._watchers: dict[Path, WatcherBridge] = {}
        self._icon_targets: list[tuple[object, str]] = []
        self._close_icon = icons.icon("x", icons.IconColors.from_theme(theme))
        self._printer: QPrinter | None = None
        # Nothing is written to the saved session until something is opened
        # (or restored), so building the window never wipes the last session.
        self._session_active = False
        self._pending_search = None
        self._search_navigation = 0

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icons.app_icon())
        self.resize(1200, 800)
        self.setAcceptDrops(True)

        # Off-the-record profile: no disk cache, so a reload always re-renders.
        # Parented to the app so it outlives the pages (Qt requires the pages
        # to be deleted first).
        self._profile = QWebEngineProfile(app)
        self._scheme_handler = SchemeHandler(self)
        self._scheme_handler.doc_theme = self._doc_theme.attr
        self._profile.installUrlSchemeHandler(SCHEME.encode(), self._scheme_handler)

        # ── Central area: tabs + find bar ──
        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setAccessibleName("Documents")
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_current_tab_changed)
        self.find_bar = FindBar(theme, self)
        self.find_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.find_bar.findRequested.connect(self._find)
        self.find_bar.closed.connect(self._clear_find)
        central = QWidget(self)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.tabs, 1)
        central_layout.addWidget(self.find_bar)
        self.setCentralWidget(central)

        # ── Docks ──
        self.tree = FileTree(self)
        self.tree.fileActivated.connect(self.open_document)
        self.tree.fileActivatedInNewTab.connect(self._open_in_new_tab)
        self.file_operations = FileOperations(self)
        self.tree.createRequested.connect(self._create_file)
        self.tree.renameRequested.connect(self._rename_file)
        self.tree.trashRequested.connect(self._trash_file)
        self.file_operations.created.connect(self._on_file_created)
        self.file_operations.renamed.connect(self._on_file_renamed)
        self.file_operations.trashed.connect(self._on_file_trashed)
        self.file_operations.failed.connect(self._on_file_operation_failed)
        self.file_filter = QLineEdit(self)
        self.file_filter.setPlaceholderText("Filter files…")
        self.file_filter.setAccessibleName("Filter files by name or path")
        self.file_filter.setToolTip("Match part of a filename or relative path")
        self.file_filter.setClearButtonEnabled(True)
        self.file_filter.textChanged.connect(self.tree.set_filter_text)
        files_panel = QWidget(self)
        files_layout = QVBoxLayout(files_panel)
        files_layout.setContentsMargins(0, 0, 0, 0)
        files_layout.setSpacing(theme.space["space-2"])
        files_layout.addWidget(self.file_filter)
        files_layout.addWidget(self.tree, 1)
        self.files_dock = self._dock("FILES", "files-dock", files_panel, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.resizeDocks([self.files_dock], [280], Qt.Orientation.Horizontal)

        self.toc = TocPanel(self)
        self.toc.headingActivated.connect(self._scroll_to_heading)
        self.toc_dock = self._dock("CONTENTS", "toc-dock", self.toc, Qt.DockWidgetArea.RightDockWidgetArea)
        self.resizeDocks([self.toc_dock], [240], Qt.Orientation.Horizontal)

        self.search_panel = SearchPanel(self)
        self.search_panel.resultActivated.connect(self._open_search_result)
        self.search_dock = self._dock("SEARCH", "search-dock", self.search_panel, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.search_dock.hide()

        self.status_label = QLabel(self)
        self.zoom_label = QLabel(self)
        self.statusBar().addWidget(self.status_label, 1)
        self.statusBar().addPermanentWidget(self.zoom_label)
        self.statusBar().setSizeGripEnabled(False)

        self._tree_refresh = QTimer(self)
        self._tree_refresh.setSingleShot(True)
        self._tree_refresh.setInterval(200)
        self._tree_refresh.timeout.connect(self._refresh_tree)

        self._new_tab().show_welcome()
        self._build_menus()
        self._build_toolbar()
        self._restore_geometry()
        self._apply_chrome()
        self._update_zoom_label()

    def _dock(self, title: str, name: str, widget: QWidget, area: Qt.DockWidgetArea) -> QDockWidget:
        body = QWidget(self)
        layout = QVBoxLayout(body)
        margin = self._theme.space["space-2"]
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(self._theme.space["space-2"])
        layout.addWidget(widget)
        # QSS has no text-transform; label tokens are uppercase in UI.
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setWidget(body)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        self.addDockWidget(area, dock)
        return dock

    # ── Menus / toolbar ─────────────────────────────────────────────

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        self.open_action = self._action(
            file_menu, "&Open…", QKeySequence.StandardKey.Open, self.choose_file, icon="file-text"
        )
        self.open_folder_action = self._action(
            file_menu, "Open &Folder…", QKeySequence("Ctrl+Shift+O"), self.choose_folder, icon="folder-open"
        )
        self.recent_menu = file_menu.addMenu("Open &Recent")
        self.recent_menu.aboutToShow.connect(self._populate_recent_menu)
        file_menu.addSeparator()
        self.reload_action = self._action(
            file_menu, "&Reload", QKeySequence.StandardKey.Refresh, self.reload, icon="refresh-cw"
        )
        self.close_tab_action = self._action(
            file_menu, "&Close Tab", QKeySequence.StandardKey.Close, lambda: self.close_tab(self.tabs.currentIndex())
        )
        file_menu.addSeparator()
        self.export_pdf_action = self._action(
            file_menu, "Export &PDF…", None, self.choose_pdf_path, icon="file-down"
        )
        self.print_action = self._action(
            file_menu, "&Print…", QKeySequence.StandardKey.Print, self.print_document, icon="printer"
        )
        file_menu.addSeparator()
        self._action(file_menu, "&Quit", QKeySequence.StandardKey.Quit, self.close)

        edit_menu = self.menuBar().addMenu("&Edit")
        self.find_action = self._action(
            edit_menu, "&Find…", QKeySequence.StandardKey.Find, self.find_bar.open_bar, icon="search"
        )
        self._action(edit_menu, "Find &Next", QKeySequence.StandardKey.FindNext, self.find_bar.find_next)
        self._action(
            edit_menu, "Find Pre&vious", QKeySequence.StandardKey.FindPrevious, self.find_bar.find_previous
        )
        self._action(edit_menu, "Find in &Folder…", QKeySequence("Ctrl+Shift+F"), self.open_content_search, icon="search")

        view_menu = self.menuBar().addMenu("&View")
        toggle_files = self.files_dock.toggleViewAction()
        toggle_files.setText("&Files Panel")
        toggle_files.setShortcut(QKeySequence("Ctrl+Shift+E"))
        view_menu.addAction(toggle_files)
        toggle_search = self.search_dock.toggleViewAction()
        toggle_search.setText("&Search Panel")
        view_menu.addAction(toggle_search)
        self.toggle_toc_action = self.toc_dock.toggleViewAction()
        self.toggle_toc_action.setText("&Contents Panel")
        self.toggle_toc_action.setShortcut(QKeySequence("Ctrl+Shift+T"))
        self._icon_targets.append((self.toggle_toc_action, "list-tree"))
        view_menu.addAction(self.toggle_toc_action)
        view_menu.addSeparator()
        self.zoom_in_action = self._action(
            view_menu, "Zoom &In", QKeySequence.StandardKey.ZoomIn, self.zoom_in, icon="zoom-in"
        )
        self.zoom_in_action.setShortcuts([QKeySequence.StandardKey.ZoomIn, QKeySequence("Ctrl+=")])
        self.zoom_out_action = self._action(
            view_menu, "Zoom &Out", QKeySequence.StandardKey.ZoomOut, self.zoom_out, icon="zoom-out"
        )
        self._action(view_menu, "&Actual Size", QKeySequence("Ctrl+0"), self.zoom_reset)
        view_menu.addSeparator()
        self._action(view_menu, "Ne&xt Tab", QKeySequence("Ctrl+PgDown"), lambda: self._cycle_tab(1)).setShortcuts(
            [QKeySequence("Ctrl+PgDown"), QKeySequence("Ctrl+Tab")]
        )
        self._action(
            view_menu, "Pre&vious Tab", QKeySequence("Ctrl+PgUp"), lambda: self._cycle_tab(-1)
        ).setShortcuts([QKeySequence("Ctrl+PgUp"), QKeySequence("Ctrl+Shift+Tab")])
        view_menu.addSeparator()
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

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Toolbar", self)
        toolbar.setObjectName("main-toolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(QSize(icons.ICON_SIZE, icons.ICON_SIZE))
        for action in (self.open_action, self.open_folder_action, self.reload_action):
            toolbar.addAction(action)
        toolbar.addSeparator()
        toolbar.addAction(self.find_action)
        toolbar.addAction(self.toggle_toc_action)
        toolbar.addSeparator()
        toolbar.addAction(self.zoom_out_action)
        toolbar.addAction(self.zoom_in_action)
        toolbar.addSeparator()
        toolbar.addAction(self.print_action)
        toolbar.addAction(self.export_pdf_action)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        self.toolbar = toolbar

    def _action(self, menu, text, shortcut, slot, *, icon: str | None = None) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(shortcut)
        action.triggered.connect(slot)
        menu.addAction(action)
        if icon:
            self._icon_targets.append((action, icon))
        return action

    def _apply_icons(self) -> None:
        if self._doc_theme.jamielab_chrome:
            colors = icons.IconColors.from_theme(self._theme)
        else:
            colors = icons.IconColors.from_palette(self._app.palette())
        for target, name in self._icon_targets:
            target.setIcon(icons.icon(name, colors))
        self._close_icon = icons.icon("x", colors)
        self.find_bar.set_icons(icons.icon("chevron-up", colors), icons.icon("chevron-down", colors), self._close_icon)
        bar = self.tabs.tabBar()
        for index in range(bar.count()):
            if (button := bar.tabButton(index, QTabBar.ButtonPosition.RightSide)) is not None:
                button.setIcon(self._close_icon)

    def _populate_recent_menu(self) -> None:
        self.recent_menu.clear()
        recent = [p for p in self._settings.recent_files if p.is_file()][:RECENT_SHOWN]
        for path in recent:
            action = self.recent_menu.addAction(f"{path.name}  ·  {display_path(path.parent)}")
            action.setToolTip(str(path))
            action.triggered.connect(lambda _=False, p=path: self.open_path(p))
        if not recent:
            self.recent_menu.addAction("no recent files").setEnabled(False)
            return
        self.recent_menu.addSeparator()
        self.recent_menu.addAction("Clear Recent", self._clear_recent)

    def _clear_recent(self) -> None:
        self._settings.recent_files = []

    # ── Tabs ────────────────────────────────────────────────────────

    @property
    def view(self) -> DocumentView | None:
        """The document view in the current tab (``None`` during teardown)."""
        if sip.isdeleted(self.tabs):
            return None
        return self.tabs.currentWidget()

    def views(self) -> list[DocumentView]:
        return [self.tabs.widget(i) for i in range(self.tabs.count())]

    def _new_tab(self) -> DocumentView:
        view = DocumentView(self._profile, self)
        view.setAcceptDrops(False)  # let file drops reach the window
        view.setZoomFactor(self._zoom)
        page = view.document_page
        # Bound methods, not lambdas: Qt drops these connections when the
        # window dies, so late page/watcher signals can't reach a dead window.
        # The originating view comes from sender().
        # Queued: starting a new load from inside acceptNavigationRequest
        # re-enters Chromium's navigation and aborts the process.
        page.openDocument.connect(self._on_link_to_document, Qt.ConnectionType.QueuedConnection)
        page.linkBlocked.connect(self._on_link_blocked)
        page.findTextFinished.connect(self._on_find_result)
        page.pdfPrintingFinished.connect(self._on_pdf_finished)
        view.printFinished.connect(self._on_print_finished)
        view.loadFinished.connect(self._on_load_finished)
        index = self.tabs.addTab(view, "welcome")
        close = QToolButton(self.tabs)
        close.setObjectName("tab-close")
        close.setAutoRaise(True)
        close.setToolTip("close tab (Ctrl+W)")
        close.setAccessibleName("Close tab")
        close.setIcon(self._close_icon)
        close.clicked.connect(self._on_tab_close_clicked)
        self.tabs.tabBar().setTabButton(index, QTabBar.ButtonPosition.RightSide, close)
        self.tabs.setCurrentIndex(index)
        return view

    def _on_tab_close_clicked(self) -> None:
        bar = self.tabs.tabBar()
        for index in range(bar.count()):
            if bar.tabButton(index, QTabBar.ButtonPosition.RightSide) is self.sender():
                self.close_tab(index)
                return

    def _sender_view(self) -> DocumentView | None:
        obj = self.sender()
        while obj is not None and not isinstance(obj, DocumentView):
            obj = obj.parent()
        return obj if obj is not None and self.tabs.indexOf(obj) >= 0 else None

    def _open_in_new_tab(self, rel_path: str) -> None:
        self.open_document(rel_path, new_tab=True)

    def _scroll_to_heading(self, anchor: str) -> None:
        self.view.scroll_to_anchor(anchor)

    def _on_link_blocked(self, url: str) -> None:
        self.show_status(f"link blocked · {url}", "warning")

    def _tab_for(self, file: Path) -> DocumentView | None:
        for view in self.views():
            if view.abs_path == file:
                return view
        return None

    def close_tab(self, index: int) -> None:
        view = self.tabs.widget(index)
        if view is None:
            return
        if self.tabs.count() == 1:
            view.show_welcome()
            self._update_tab_label(view)
            self._on_current_tab_changed(self.tabs.currentIndex())
        else:
            self.tabs.removeTab(index)
            view.deleteLater()
        self._sync_watchers()
        self._save_session()

    def _cycle_tab(self, step: int) -> None:
        if self.tabs.count() > 1:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() + step) % self.tabs.count())

    def _update_tab_label(self, view: DocumentView) -> None:
        index = self.tabs.indexOf(view)
        if index < 0:
            return
        if view.current_path:
            self.tabs.setTabText(index, Path(view.current_path).name)
            self.tabs.setTabToolTip(index, display_path(view.abs_path))
        else:
            self.tabs.setTabText(index, "welcome")
            self.tabs.setTabToolTip(index, "")

    def _on_current_tab_changed(self, _index: int) -> None:
        if self.view is None:
            return
        self._sync_tree_selection()
        self._update_title()
        self._refresh_toc()
        if not self.find_bar.isHidden():
            for view in self.views():
                if view is not self.view:
                    view.findText("")
            self._find(self.find_bar.text, False)
        self._save_session()

    def _on_load_finished(self, ok: bool) -> None:
        view = self._sender_view()
        if view is None:
            return
        if abs(view.zoomFactor() - self._zoom) > 1e-6:
            view.setZoomFactor(self._zoom)
        if view is self.view:
            self._refresh_toc()
        if ok and self._pending_search is not None and self._pending_search[0] is view:
            _, result, query = self._pending_search
            self._pending_search = None
            self._highlight_search_result(view, result, query)

    # ── Opening things ──────────────────────────────────────────────

    def open_path(self, path: Path, *, new_tab: bool = True) -> bool:
        """Open a file (with its folder in the tree) or a folder.

        Files open in a new tab unless already open (or the current tab is
        empty). A folder only changes the tree; open tabs stay.
        """
        path = path.expanduser().resolve()
        if path.is_dir():
            self.set_base_dir(path)
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
        self.open_document(path.relative_to(self.base_dir).as_posix(), new_tab=new_tab)
        return True

    def open_paths(self, paths: list[Path]) -> None:
        """Open paths handed over by a second launch, then raise the window."""
        for path in paths:
            self.open_path(path)
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def set_base_dir(self, base_dir: Path) -> None:
        base_dir = base_dir.resolve()
        if base_dir == self.base_dir:
            return
        self.base_dir = base_dir
        self.tree.set_base_dir(base_dir)
        self.search_panel.set_root(base_dir)
        self._sync_tree_selection()
        self._sync_watchers()
        self._settings.last_folder = base_dir
        self._update_title()
        self.show_status(f"folder · {base_dir}")

    def open_document(self, rel_path: str, fragment: str = "", *, new_tab: bool = False) -> None:
        """Open ``rel_path`` (relative to the tree's folder)."""
        if self.base_dir is None:
            return
        self._show_document(self.base_dir, rel_path, fragment, new_tab=new_tab)

    def _show_document(
        self, root: Path, rel_path: str, fragment: str = "", *, new_tab: bool = False,
        view: DocumentView | None = None,
    ) -> bool:
        try:
            file = validate_path(root, rel_path)
        except PathOutsideBaseError:
            self.show_status(f"outside folder · {rel_path}", "error")
            return False
        # validate_path resolves symlinks; the tab keeps the path as linked.
        rel_path = posixpath.normpath(rel_path)
        file = root / rel_path
        self._session_active = True

        existing = self._tab_for(file)
        if existing is not None:
            self.tabs.setCurrentWidget(existing)
            if fragment:
                existing.scroll_to_anchor(fragment)
            return True

        if view is None:
            view = self.view
            if new_tab and view.current_path is not None:
                view = self._new_tab()
        view.open_document(rel_path, fragment, root=root, host=self._scheme_handler.add_root(root))
        self.tabs.setCurrentWidget(view)
        self._update_tab_label(view)
        self._sync_tree_selection()
        self._sync_watchers()
        self._settings.add_recent_file(file)
        self._save_session()
        self._update_title()
        self.show_status(f"opened · {rel_path}")
        return True

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
        """Reopen the last folder and tabs."""
        folder = self._settings.last_folder
        tabs = self._settings.tabs
        active = self._settings.active_tab
        if folder and folder.is_dir():
            self.set_base_dir(folder)
        restored = []
        for tab in tabs:
            if tab.root.is_dir() and tab.file.is_file() and is_markdown(tab.file):
                if self.base_dir is None:
                    self.set_base_dir(tab.root)
                if self._show_document(tab.root.resolve(), tab.path, new_tab=True):
                    restored.append(tab)
        self._session_active = True
        if restored:
            self.tabs.setCurrentIndex(min(max(active, 0), self.tabs.count() - 1))
            self._save_session()
            return
        self.view.show_welcome()
        if self.base_dir is None:
            self.show_status("no folder open · File → Open Folder… (Ctrl+Shift+O)")

    def _on_link_to_document(self, rel_path: str, fragment: str) -> None:
        view = self._sender_view()
        if view is None or view.root is None:
            return
        try:
            exists = validate_path(view.root, rel_path).is_file()
        except PathOutsideBaseError:
            self.show_status(f"outside folder · {rel_path}", "error")
            return
        if not exists:
            self.show_status(f"not found · {rel_path}", "error")
            return
        self._show_document(view.root, rel_path, fragment, view=view)

    def _save_session(self) -> None:
        if not self._session_active:
            return
        tabs, active = [], 0
        for view in self.views():
            if view.root is not None and view.current_path:
                if view is self.view:
                    active = len(tabs)
                tabs.append(SessionTab(view.root, view.current_path))
        self._settings.tabs = tabs
        self._settings.active_tab = active

    # ── Live reload ─────────────────────────────────────────────────

    def _sync_watchers(self) -> None:
        """Watch the tree's folder plus every root an open tab lives in."""
        wanted = {v.root for v in self.views() if v.root is not None and v.current_path}
        if self.base_dir is not None:
            wanted.add(self.base_dir)
        for root in list(self._watchers):
            if root not in wanted:
                self._watchers.pop(root).stop()
        for root in wanted - self._watchers.keys():
            bridge = WatcherBridge(self)
            bridge.fileChanged.connect(self._on_watcher_event)
            bridge.start(root)
            self._watchers[root] = bridge

    @property
    def watched_roots(self) -> set[Path]:
        return set(self._watchers)

    def _on_watcher_event(self, rel_path: str, event_type: str, _revision: str) -> None:
        bridge = self.sender()
        if isinstance(bridge, WatcherBridge) and bridge.base_dir is not None:
            self._on_file_changed(bridge.base_dir, rel_path, event_type)

    def _on_file_changed(self, root: Path, rel_path: str, event_type: str) -> None:
        if root == self.base_dir:
            self.search_panel.refresh()
        if event_type == "tree_changed" and root == self.base_dir:
            self._tree_refresh.start()
        for view in self.views():
            if view.root != root or view.current_path != rel_path:
                continue
            if (root / rel_path).is_file():
                view.reload_document()
                self.show_status(f"reloaded · {rel_path}")
            else:
                self.show_status(f"deleted on disk · {rel_path}", "warning")

    def _refresh_tree(self) -> None:
        self.tree.rebuild()
        self._sync_tree_selection()

    def _sync_tree_selection(self) -> None:
        file = self.view.abs_path if self.view is not None else None
        if file is None or self.base_dir is None or not file.is_relative_to(self.base_dir):
            self.tree.select_path(None)
            return
        self.tree.select_path(file.relative_to(self.base_dir).as_posix())

    # ── Sidebar file operations ────────────────────────────────────

    def _create_file(self, root: Path, directory: str) -> None:
        if root is not None:
            self.file_operations.create(root, directory)

    def _rename_file(self, root: Path, rel_path: str) -> None:
        if root is not None:
            self.file_operations.rename(root, rel_path)

    def _trash_file(self, root: Path, rel_path: str) -> None:
        if root is not None:
            self.file_operations.trash(root, rel_path)

    def _on_file_operation_failed(self, message: str) -> None:
        self.show_status(message, "error")

    def _on_file_created(self, root: Path, path: str) -> None:
        invalidate_file_cache()
        self._refresh_tree()
        self.search_panel.refresh()
        self._show_document(root, path, new_tab=True)
        self.show_status(f"created · {path}")

    def _on_file_renamed(self, root: Path, old_path: str, new_path: str) -> None:
        old, new = root / old_path, root / new_path
        for view in self.views():
            if view.abs_path == old:
                view.open_document(new.relative_to(view.root).as_posix())
                self._update_tab_label(view)
        self._settings.recent_files = list(dict.fromkeys(
            new if path == old else path for path in self._settings.recent_files
        ))
        invalidate_file_cache()
        self._refresh_tree()
        self.search_panel.refresh()
        self._sync_watchers()
        self._save_session()
        self._update_title()
        self.show_status(f"renamed · {old_path} → {new_path}")

    def _on_file_trashed(self, root: Path, path: str) -> None:
        target = root / path
        for view in reversed(self.views()):
            if view.abs_path == target:
                self.close_tab(self.tabs.indexOf(view))
        self._settings.recent_files = [p for p in self._settings.recent_files if p != target]
        invalidate_file_cache()
        self._refresh_tree()
        self.search_panel.refresh()
        self.show_status(f"moved to Trash · {path} · recover from your file manager")

    # ── Folder content search ───────────────────────────────────────

    def open_content_search(self) -> None:
        self.search_dock.show()
        self.search_dock.raise_()
        self.search_panel.edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search_panel.edit.selectAll()

    def _open_search_result(self, root: Path, result: dict, query: str) -> None:
        try:
            target = validate_path(root, result["path"])
            if not target.is_file():
                raise ValueError("file no longer exists")
        except (OSError, ValueError) as exc:
            self.show_status(f"search result unavailable: {exc}", "error")
            self.search_panel.refresh()
            return
        self._search_navigation += 1
        if self._show_document(root, result["path"]):
            self._pending_search = (self.view, result, query)
            self.view.reload_document()

    def _highlight_search_result(self, view: DocumentView, result: dict, query: str) -> None:
        # Search the rendered source line, removing Markdown syntax. Its ordinal
        # distinguishes repeated identical lines. Source-only matches retain
        # their exact line/snippet in the dock even when absent from the page.
        plain = QTextDocument()
        plain.setHtml(render_markdown(result["source_line"]))
        text = plain.toPlainText().strip() or query
        generation = self._search_navigation
        remaining = min(result["occurrence"], 50)
        expected = view.abs_path

        def alive() -> bool:
            return (not sip.isdeleted(self) and not sip.isdeleted(view)
                    and generation == self._search_navigation and view is self.view
                    and view.abs_path == expected)

        def found(hit) -> None:
            nonlocal remaining
            if not alive():
                return
            if not hit.numberOfMatches():
                self.show_status(f"source match · {result['path']}:{result['line_number']} · see search snippet")
                return
            remaining -= 1
            if remaining > 0 and hit.activeMatch() < hit.numberOfMatches():
                view.document_page.findText(text, QWebEnginePage.FindFlag(0), found)
            else:
                self.show_status(f"match · {result['path']}:{result['line_number']}")

        def cleared(_hit) -> None:
            if alive():
                view.document_page.findText(text, QWebEnginePage.FindFlag(0), found)

        view.document_page.findText("", QWebEnginePage.FindFlag(0), cleared)

    # ── Contents (TOC) ──────────────────────────────────────────────

    def _refresh_toc(self) -> None:
        view = self.view
        if view is None or not view.current_path:
            self.toc.set_headings([])
            return

        def done(headings, v=view) -> None:
            # JavaScript replies can arrive while the window is being torn down.
            if not sip.isdeleted(self.tabs) and v is self.view:
                self.toc.set_headings(headings)

        view.fetch_headings(done)

    # ── Find in page ────────────────────────────────────────────────

    def _find(self, text: str, backward: bool) -> None:
        flags = QWebEnginePage.FindFlag(0)
        if backward:
            flags |= QWebEnginePage.FindFlag.FindBackward
        self.view.findText(text, flags)
        if not text:
            self.find_bar.set_result(0, 0)

    def _clear_find(self) -> None:
        self.view.findText("")
        self.view.setFocus()

    def _on_find_result(self, result: QWebEngineFindTextResult) -> None:
        view = self._sender_view()
        if view is not None and view is self.view and not self.find_bar.isHidden():
            self.find_bar.set_result(result.activeMatch(), result.numberOfMatches())

    # ── Zoom ────────────────────────────────────────────────────────

    @property
    def zoom(self) -> float:
        return self._zoom

    def set_zoom(self, factor: float) -> None:
        factor = min(max(factor, ZOOM_STEPS[0]), ZOOM_STEPS[-1])
        self._zoom = factor
        self._settings.zoom = factor
        for view in self.views():
            view.setZoomFactor(factor)
        self._update_zoom_label()
        self.show_status(f"zoom · {round(factor * 100)}%")

    def zoom_in(self) -> None:
        self.set_zoom(next((z for z in ZOOM_STEPS if z > self._zoom + 1e-6), ZOOM_STEPS[-1]))

    def zoom_out(self) -> None:
        self.set_zoom(next((z for z in reversed(ZOOM_STEPS) if z < self._zoom - 1e-6), ZOOM_STEPS[0]))

    def zoom_reset(self) -> None:
        self.set_zoom(1.0)

    def _update_zoom_label(self) -> None:
        self.zoom_label.setText("" if abs(self._zoom - 1.0) < 1e-6 else f"{round(self._zoom * 100)}%")

    # ── Print / PDF ─────────────────────────────────────────────────

    @staticmethod
    def page_layout() -> QPageLayout:
        """Letter in the US, A4 elsewhere, 15 mm margins."""
        imperial = QLocale.system().measurementSystem() == QLocale.MeasurementSystem.ImperialUSSystem
        size = QPageSize(QPageSize.PageSizeId.Letter if imperial else QPageSize.PageSizeId.A4)
        return QPageLayout(
            size, QPageLayout.Orientation.Portrait, QMarginsF(15, 15, 15, 15), QPageLayout.Unit.Millimeter
        )

    def _require_document(self) -> DocumentView | None:
        if not self.view.current_path:
            self.show_status("no document open", "warning")
            return None
        return self.view

    def choose_pdf_path(self) -> None:
        view = self._require_document()
        if view is None:
            return
        suggested = view.abs_path.with_suffix(".pdf")
        filename, _ = QFileDialog.getSaveFileName(self, "Export PDF", str(suggested), "PDF (*.pdf)")
        if filename:
            path = Path(filename)
            self.export_pdf(path if path.suffix.lower() == ".pdf" else path.with_suffix(".pdf"))

    def export_pdf(self, path: Path) -> None:
        """Write the current document to ``path`` (printed in the light theme)."""
        view = self._require_document()
        if view is None:
            return
        self.show_status(f"exporting · {path.name}")
        view.prepare_print(lambda: view.document_page.printToPdf(str(path), self.page_layout()))

    def print_document(self) -> None:
        view = self._require_document()
        if view is None:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPageLayout(self.page_layout())
        printer.setDocName(Path(view.current_path).name)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QPrintDialog.DialogCode.Accepted:
            return
        self._printer = printer  # must outlive the asynchronous print
        self.show_status(f"printing · {printer.docName()}")
        view.prepare_print(lambda: view.print(printer))

    def _on_pdf_finished(self, path: str, ok: bool) -> None:
        if (view := self._sender_view()) is not None:
            view.set_doc_theme(self._doc_theme.attr)
        if ok:
            self.show_status(f"exported · {Path(path).name}")
        else:
            self.show_status(f"export failed · {Path(path).name}", "error")

    def _on_print_finished(self, ok: bool) -> None:
        if (view := self._sender_view()) is not None:
            view.set_doc_theme(self._doc_theme.attr)
        self._printer = None
        if ok:
            self.show_status("printed")
        else:
            self.show_status("print failed", "error")

    # ── Theme ───────────────────────────────────────────────────────

    def set_theme(self, key: str) -> None:
        doc_theme = DOC_THEMES_BY_KEY.get(key)
        if doc_theme is None:
            return
        self._doc_theme = doc_theme
        self._settings.theme = key
        self._scheme_handler.doc_theme = doc_theme.attr
        self.theme_actions[key].setChecked(True)
        for view in self.views():
            view.set_doc_theme(doc_theme.attr)
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
        self._apply_icons()

    # ── Status / title / about ──────────────────────────────────────

    def show_status(self, message: str, state: str = "") -> None:
        self.status_label.setText(message)
        if self.status_label.property("state") != state:
            self.status_label.setProperty("state", state)
            self.status_label.style().unpolish(self.status_label)
            self.status_label.style().polish(self.status_label)

    def _update_title(self) -> None:
        if self.view is not None and self.view.current_path:
            self.setWindowTitle(f"{Path(self.view.current_path).name} — {APP_NAME}")
        elif self.base_dir:
            self.setWindowTitle(f"{self.base_dir.name or self.base_dir} — {APP_NAME}")
        else:
            self.setWindowTitle(APP_NAME)

    def show_about(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(f"About {APP_NAME}")
        box.setIconPixmap(icons.app_icon().pixmap(64, 64))
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
        self.search_panel.cancel()
        self._save_session()
        self._settings.geometry = self.saveGeometry()
        self._settings.window_state = self.saveState()
        self._settings.sync()
        for bridge in self._watchers.values():
            bridge.stop()
        self._watchers.clear()
        super().closeEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 (Qt API)
        if self._dropped_paths(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 (Qt API)
        paths = self._dropped_paths(event)
        if paths:
            event.acceptProposedAction()
            for path in paths:
                self.open_path(path)

    @staticmethod
    def _dropped_paths(event) -> list[Path]:
        paths = []
        for url in event.mimeData().urls() if event.mimeData().hasUrls() else []:
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if path.is_dir() or is_markdown(path):
                    paths.append(path)
        return paths

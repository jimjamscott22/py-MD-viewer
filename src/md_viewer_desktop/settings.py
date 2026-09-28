"""Typed wrapper around ``QSettings`` (~/.config/jamielab/md-viewer.conf)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QByteArray, QSettings

DEFAULT_THEME = "jamielab"
MAX_RECENT = 10


@dataclass(frozen=True)
class SessionTab:
    root: Path  # folder the document's links resolve in
    path: str  # posix path relative to root

    @property
    def file(self) -> Path:
        return self.root / self.path


class Settings:
    def __init__(self, backend: QSettings | None = None):
        self._s = backend if backend is not None else QSettings("jamielab", "md-viewer")

    def _path(self, key: str) -> Path | None:
        value = self._s.value(key, "", type=str)
        return Path(value) if value else None

    def _set_path(self, key: str, path: Path | None) -> None:
        self._s.setValue(key, str(path) if path else "")

    @property
    def theme(self) -> str:
        return self._s.value("view/theme", DEFAULT_THEME, type=str) or DEFAULT_THEME

    @theme.setter
    def theme(self, value: str) -> None:
        self._s.setValue("view/theme", value)

    @property
    def last_folder(self) -> Path | None:
        return self._path("session/folder")

    @last_folder.setter
    def last_folder(self, path: Path | None) -> None:
        self._set_path("session/folder", path)

    @property
    def last_file(self) -> Path | None:
        return self._path("session/file")

    @last_file.setter
    def last_file(self, path: Path | None) -> None:
        self._set_path("session/file", path)

    @property
    def tabs(self) -> list[SessionTab]:
        """Open tabs from the last session (falls back to the Phase 2 single file)."""
        raw = self._s.value("session/tabs", "", type=str)
        tabs: list[SessionTab] = []
        try:
            entries = json.loads(raw) if raw else []
        except json.JSONDecodeError:
            entries = []
        for entry in entries if isinstance(entries, list) else []:
            if isinstance(entry, dict) and entry.get("root") and entry.get("path"):
                tabs.append(SessionTab(Path(entry["root"]), str(entry["path"])))
        if not raw and (legacy := self.last_file) is not None:
            tabs.append(SessionTab(legacy.parent, legacy.name))
        return tabs

    @tabs.setter
    def tabs(self, tabs: list[SessionTab]) -> None:
        self._s.setValue(
            "session/tabs", json.dumps([{"root": str(t.root), "path": t.path} for t in tabs])
        )

    @property
    def active_tab(self) -> int:
        return self._s.value("session/active_tab", 0, type=int)

    @active_tab.setter
    def active_tab(self, index: int) -> None:
        self._s.setValue("session/active_tab", index)

    @property
    def recent_files(self) -> list[Path]:
        raw = self._s.value("recent/files", "", type=str)
        try:
            entries = json.loads(raw) if raw else []
        except json.JSONDecodeError:
            return []
        return [Path(p) for p in entries if isinstance(p, str) and p] if isinstance(entries, list) else []

    @recent_files.setter
    def recent_files(self, paths: list[Path]) -> None:
        self._s.setValue("recent/files", json.dumps([str(p) for p in paths[:MAX_RECENT]]))

    def add_recent_file(self, path: Path) -> None:
        paths = [p for p in self.recent_files if p != path]
        self.recent_files = [path, *paths]

    @property
    def zoom(self) -> float:
        value = self._s.value("view/zoom", 1.0, type=float)
        return value if 0.25 <= value <= 5.0 else 1.0

    @zoom.setter
    def zoom(self, value: float) -> None:
        self._s.setValue("view/zoom", float(value))

    @property
    def geometry(self) -> QByteArray | None:
        value = self._s.value("window/geometry")
        return value if isinstance(value, QByteArray) else None

    @geometry.setter
    def geometry(self, value: QByteArray) -> None:
        self._s.setValue("window/geometry", value)

    @property
    def window_state(self) -> QByteArray | None:
        value = self._s.value("window/state")
        return value if isinstance(value, QByteArray) else None

    @window_state.setter
    def window_state(self, value: QByteArray) -> None:
        self._s.setValue("window/state", value)

    def sync(self) -> None:
        self._s.sync()

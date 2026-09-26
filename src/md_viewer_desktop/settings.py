"""Typed wrapper around ``QSettings`` (~/.config/jamielab/md-viewer.conf)."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QByteArray, QSettings

DEFAULT_THEME = "jamielab"


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

"""Native Markdown file dialogs and filesystem operations for the sidebar."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QFile, QObject, pyqtSignal
from PyQt6.QtWidgets import QInputDialog, QMessageBox

from md_preview_core.files import validate_path


def markdown_name(name: str) -> str:
    name = name.strip()
    if not name or name in {".", ".."} or any(c in name for c in "/\\\x00"):
        raise ValueError("enter a filename without folder separators")
    if not Path(name).suffix:
        name += ".md"
    if Path(name).suffix.lower() != ".md":
        raise ValueError("only .md files are supported")
    return name


def _target(root: Path, rel_path: str) -> Path:
    target = validate_path(root, rel_path)
    if (root / rel_path).is_symlink():
        raise ValueError("symbolic links cannot be modified")
    return target


def _existing_file(root: Path, rel_path: str) -> Path:
    target = _target(root, rel_path)
    if target.suffix.lower() != ".md" or not target.is_file():
        raise ValueError("Markdown file not found")
    return target


def create_file(root: Path, directory: str, name: str) -> str:
    target = _target(root, (Path(directory) / markdown_name(name)).as_posix())
    # Exclusive creation also prevents overwrites if another process wins a race.
    with target.open("x", encoding="utf-8"):
        pass
    return target.relative_to(root.resolve()).as_posix()


def rename_file(root: Path, rel_path: str, name: str) -> str:
    source = _existing_file(root, rel_path)
    target = _target(root, (Path(rel_path).parent / markdown_name(name)).as_posix())
    if target != source:
        file = QFile(str(source))
        if not file.rename(str(target)):
            raise OSError(file.errorString())
    return target.relative_to(root.resolve()).as_posix()


def trash_file(root: Path, rel_path: str) -> None:
    file = QFile(str(_existing_file(root, rel_path)))
    if not file.moveToTrash():
        raise OSError(f"could not move file to Trash: {file.errorString()}")


class FileOperations(QObject):
    """Capture the root before opening a modal dialog; emit only after success."""

    created = pyqtSignal(object, str)
    renamed = pyqtSignal(object, str, str)
    trashed = pyqtSignal(object, str)
    failed = pyqtSignal(str)

    def create(self, root: Path, directory: str) -> None:
        name, accepted = QInputDialog.getText(
            self.parent(), "New Markdown File", "Filename (.md):", text="untitled.md"
        )
        if not accepted:
            return
        try:
            path = create_file(root, directory, name)
        except (OSError, ValueError) as exc:
            self.failed.emit(f"create failed: {exc}")
            return
        self.created.emit(root, path)

    def rename(self, root: Path, rel_path: str) -> None:
        name, accepted = QInputDialog.getText(
            self.parent(), "Rename Markdown File", "New filename (.md):", text=Path(rel_path).name
        )
        if not accepted:
            return
        try:
            new_path = rename_file(root, rel_path, name)
        except (OSError, ValueError) as exc:
            self.failed.emit(f"rename failed: {exc}")
            return
        self.renamed.emit(root, rel_path, new_path)

    def trash(self, root: Path, rel_path: str) -> None:
        if QMessageBox.question(
            self.parent(), "Move to Trash",
            f"Move {rel_path} to Trash?\nYou can recover it from your file manager's Trash.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            trash_file(root, rel_path)
        except (OSError, ValueError) as exc:
            self.failed.emit(f"trash failed: {exc}")
            return
        self.trashed.emit(root, rel_path)

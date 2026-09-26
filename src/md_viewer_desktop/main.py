"""``md-viewer`` entry point: argument parsing and QApplication setup."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="md-viewer",
        description=(
            "Offline Markdown viewer. A file opens with its folder in the sidebar; "
            "a folder opens in the sidebar. With no arguments, the last session is restored."
        ),
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        metavar="PATH",
        help="Markdown file or folder to open (only the first is used until tabs land)",
    )
    parser.add_argument(
        "--safe-mode",
        action="store_true",
        help="disable GPU acceleration (fixes a blank view on some VMs / NVIDIA setups)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def check_paths(paths: list[Path]) -> str | None:
    """Return an error message for the first unusable path, else ``None``."""
    for path in paths:
        path = path.expanduser()
        if not path.exists():
            return f"no such file or directory: {path}"
        if path.is_file() and path.suffix.lower() != ".md":
            return f"not a markdown file: {path}"
    return None


def configure_environment(safe_mode: bool) -> None:
    """Set Chromium flags. Must run before QtWebEngine initialises."""
    if safe_mode:
        flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        if "--disable-gpu" not in flags.split():
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{flags} --disable-gpu".strip()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    error = check_paths(args.paths)
    if error:
        print(f"md-viewer: {error}", file=sys.stderr)
        return 2

    configure_environment(args.safe_mode)

    try:
        from PyQt6 import sip
        from PyQt6.QtWidgets import QApplication
    except ImportError as exc:  # pragma: no cover - depends on the environment
        print(
            "md-viewer: PyQt6 is not installed. Install the desktop extra:\n"
            "    uv sync --extra desktop\n"
            f"({exc})",
            file=sys.stderr,
        )
        return 1

    from .document_view import register_scheme
    from .main_window import MainWindow
    from .settings import Settings
    from .theme import load_fonts, load_theme

    # Custom URL schemes must be registered before QApplication exists.
    register_scheme()
    app = QApplication(sys.argv[:1])
    app.setOrganizationName("jamielab")
    app.setApplicationName("md-viewer")
    app.setApplicationDisplayName("MD Viewer")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("md-viewer")

    load_fonts()
    window = MainWindow(app, load_theme(), Settings())
    if args.paths:
        window.open_path(args.paths[0])
    else:
        window.restore_session()
    window.show()
    status = app.exec()
    # Delete the window (and its web page) before the app-owned web profile.
    sip.delete(window)
    return status


if __name__ == "__main__":
    sys.exit(main())

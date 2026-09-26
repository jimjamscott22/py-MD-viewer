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
            "Offline Markdown viewer. A file opens in a tab with its folder in the sidebar; "
            "a folder opens in the sidebar. With no arguments, the last session is restored. "
            "If MD Viewer is already running, the paths open in that window."
        ),
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        metavar="PATH",
        help="Markdown file(s) to open in tabs, or a folder for the sidebar",
    )
    parser.add_argument(
        "--new-instance",
        action="store_true",
        help="start a separate window instead of handing paths to a running one",
    )
    parser.add_argument(
        "--install-desktop",
        action="store_true",
        help="add MD Viewer to the app menu and make it the default for .md files, then exit",
    )
    parser.add_argument(
        "--uninstall-desktop",
        action="store_true",
        help="remove the files --install-desktop wrote, then exit",
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
    if args.install_desktop or args.uninstall_desktop:
        from . import desktop_integration

        if args.install_desktop:
            result = desktop_integration.install()
        else:
            result = desktop_integration.uninstall()
        desktop_integration.report(result)
        return 0

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
    from .icons import app_icon
    from .main_window import MainWindow
    from .settings import Settings
    from .single_instance import InstanceServer, send_to_running
    from .theme import load_fonts, load_theme

    # Custom URL schemes must be registered before QApplication exists.
    register_scheme()
    app = QApplication(sys.argv[:1])
    app.setOrganizationName("jamielab")
    app.setApplicationName("md-viewer")
    app.setApplicationDisplayName("MD Viewer")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("md-viewer")

    server = None
    if not args.new_instance:
        if send_to_running(args.paths):
            return 0
        server = InstanceServer()
        if not server.listen():  # pragma: no cover - socket dir not writable
            print("md-viewer: single-instance socket unavailable", file=sys.stderr)
            server = None

    app.setWindowIcon(app_icon())
    load_fonts()
    window = MainWindow(app, load_theme(), Settings())
    if server is not None:
        server.pathsReceived.connect(window.open_paths)
    if args.paths:
        for path in args.paths:
            window.open_path(path)
    else:
        window.restore_session()
    window.show()
    status = app.exec()
    if server is not None:
        server.close()
    # Delete the window (and its web page) before the app-owned web profile.
    sip.delete(window)
    return status


if __name__ == "__main__":
    sys.exit(main())

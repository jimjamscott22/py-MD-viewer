"""``md-viewer --install-desktop``: register the app with the Linux desktop.

Writes, under ``$XDG_DATA_HOME`` (``~/.local/share``):

* ``applications/md-viewer.desktop``, with ``Exec`` pointing at this install
* ``icons/hicolor/scalable/apps/md-viewer.svg``
* ``mime/packages/md-viewer.xml`` (``*.md`` → ``text/markdown``)

then, when the tools exist, refreshes the desktop/MIME/icon caches and makes
MD Viewer the default for ``text/markdown`` so double-clicking a ``.md`` in
Nautilus opens it. No Qt imports: this runs before the GUI starts.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .theme import APP_ICON_PATH

LINUX_DIR = Path(__file__).resolve().parent / "linux"
DESKTOP_ID = "md-viewer.desktop"
MIME_TYPES = ("text/markdown", "text/x-markdown")


@dataclass
class InstallResult:
    written: list[Path] = field(default_factory=list)
    removed: list[Path] = field(default_factory=list)
    commands: list[list[str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def data_home() -> Path:
    value = os.environ.get("XDG_DATA_HOME")
    return Path(value) if value and os.path.isabs(value) else Path.home() / ".local" / "share"


def targets(base: Path) -> dict[str, Path]:
    return {
        "desktop": base / "applications" / DESKTOP_ID,
        "icon": base / "icons" / "hicolor" / "scalable" / "apps" / "md-viewer.svg",
        "mime": base / "mime" / "packages" / "md-viewer.xml",
    }


def launcher_command(argv0: str | None = None) -> list[str]:
    """How the desktop entry should start this install of md-viewer.

    Prefers the ``md-viewer`` script that is running (``uv tool install`` or
    the project venv); falls back to ``python -m md_viewer_desktop``.
    """
    argv0 = argv0 if argv0 is not None else sys.argv[0]
    script = Path(argv0)
    if script.name.startswith("md-viewer") and script.is_file():
        return [str(script.absolute())]
    found = shutil.which("md-viewer")
    if found:
        return [found]
    return [sys.executable, "-m", "md_viewer_desktop"]


def _desktop_quote(arg: str) -> str:
    """Quote an Exec argument per the Desktop Entry spec."""
    if not any(ch in arg for ch in ' \t\n"\'\\><~|&;$*?#()`'):
        return arg
    escaped = arg.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    return f'"{escaped}"'


def desktop_entry(command: list[str]) -> str:
    """The bundled ``md-viewer.desktop`` with ``Exec``/``TryExec`` for ``command``."""
    exec_line = " ".join(_desktop_quote(arg) for arg in command) + " %F"
    lines = []
    for line in (LINUX_DIR / DESKTOP_ID).read_text(encoding="utf-8").splitlines():
        if line.startswith("Exec="):
            line = f"Exec={exec_line}"
        elif line.startswith("TryExec="):
            line = f"TryExec={command[0]}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def _run(command: list[str], result: InstallResult) -> None:
    if shutil.which(command[0]) is None:
        return
    result.commands.append(command)
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        result.warnings.append(f"{shlex.join(command)} failed: {exc}")


def install(
    base: Path | None = None,
    command: list[str] | None = None,
    *,
    run_tools: bool = True,
    set_default: bool = True,
) -> InstallResult:
    base = base or data_home()
    paths = targets(base)
    result = InstallResult()

    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    paths["desktop"].write_text(desktop_entry(command or launcher_command()), encoding="utf-8")
    shutil.copyfile(APP_ICON_PATH, paths["icon"])
    shutil.copyfile(LINUX_DIR / "md-viewer.xml", paths["mime"])
    result.written += list(paths.values())

    if run_tools:
        _run(["update-mime-database", str(base / "mime")], result)
        _run(["update-desktop-database", str(base / "applications")], result)
        _run(["gtk-update-icon-cache", "-f", "-t", str(base / "icons" / "hicolor")], result)
        if set_default:
            _run(["xdg-mime", "default", DESKTOP_ID, *MIME_TYPES], result)
    return result


def uninstall(base: Path | None = None, *, run_tools: bool = True) -> InstallResult:
    base = base or data_home()
    result = InstallResult()
    for path in targets(base).values():
        if path.is_file():
            path.unlink()
            result.removed.append(path)
    if run_tools:
        _run(["update-mime-database", str(base / "mime")], result)
        _run(["update-desktop-database", str(base / "applications")], result)
    return result


def report(result: InstallResult, out=None) -> None:
    out = out or sys.stdout
    for path in result.written:
        print(f"wrote {path}", file=out)
    for path in result.removed:
        print(f"removed {path}", file=out)
    for command in result.commands:
        print(f"ran {shlex.join(command)}", file=out)
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)

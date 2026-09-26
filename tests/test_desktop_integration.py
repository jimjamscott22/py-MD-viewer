"""``md-viewer --install-desktop``. Pure Python: runs without the desktop extra."""

import configparser

from md_viewer_desktop import desktop_integration as di
from md_viewer_desktop import main as cli
from md_viewer_desktop.theme import APP_ICON_PATH


def read_entry(path):
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(path, encoding="utf-8")
    return parser["Desktop Entry"]


def test_bundled_desktop_entry_is_valid():
    entry = read_entry(di.LINUX_DIR / di.DESKTOP_ID)
    assert entry["Type"] == "Application"
    assert entry["Exec"] == "md-viewer %F"
    assert entry["Icon"] == "md-viewer"
    assert "text/markdown;" in entry["MimeType"]
    assert entry["Terminal"] == "false"
    # Qt sets the Wayland app id / X11 class from setDesktopFileName("md-viewer").
    assert entry["StartupWMClass"] == "md-viewer"


def test_install_writes_entry_icon_and_mime(tmp_path):
    result = di.install(tmp_path, ["/opt/md viewer/bin/md-viewer"], run_tools=False)
    paths = di.targets(tmp_path)
    assert set(result.written) == set(paths.values())
    entry = read_entry(paths["desktop"])
    assert entry["Exec"] == '"/opt/md viewer/bin/md-viewer" %F'
    assert entry["TryExec"] == "/opt/md viewer/bin/md-viewer"
    assert paths["icon"].read_bytes() == APP_ICON_PATH.read_bytes()
    assert '<glob pattern="*.md"/>' in paths["mime"].read_text()
    assert result.commands == []


def test_install_runs_available_tools(tmp_path, monkeypatch):
    ran = []
    monkeypatch.setattr(di.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(di.subprocess, "run", lambda cmd, **kw: ran.append(cmd))
    di.install(tmp_path, ["md-viewer"])
    assert ["xdg-mime", "default", "md-viewer.desktop", "text/markdown", "text/x-markdown"] in ran
    assert ["update-desktop-database", str(tmp_path / "applications")] in ran


def test_missing_tools_are_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(di.shutil, "which", lambda name: None)
    result = di.install(tmp_path, ["md-viewer"])
    assert result.commands == [] and result.warnings == []


def test_uninstall_removes_files(tmp_path):
    di.install(tmp_path, ["md-viewer"], run_tools=False)
    result = di.uninstall(tmp_path, run_tools=False)
    assert len(result.removed) == 3
    assert not any(p.exists() for p in di.targets(tmp_path).values())


def test_launcher_prefers_running_script(tmp_path):
    script = tmp_path / "md-viewer"
    script.write_text("#!/bin/sh\n")
    assert di.launcher_command(str(script)) == [str(script)]
    fallback = di.launcher_command(str(tmp_path / "pytest"))
    assert fallback[-2:] == ["-m", "md_viewer_desktop"] or fallback[0].endswith("md-viewer")


def test_data_home_honours_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert di.data_home() == tmp_path
    monkeypatch.setenv("XDG_DATA_HOME", "relative/ignored")
    assert di.data_home().name == "share"


def test_cli_install_desktop_needs_no_qt(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(di.shutil, "which", lambda name: None)
    assert cli.main(["--install-desktop"]) == 0
    assert (tmp_path / "applications" / "md-viewer.desktop").is_file()
    assert "wrote" in capsys.readouterr().out
    assert cli.main(["--uninstall-desktop"]) == 0
    assert not (tmp_path / "applications" / "md-viewer.desktop").exists()

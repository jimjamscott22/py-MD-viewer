"""Shared fixtures for the PyQt6 desktop app tests.

These tests need the ``desktop`` extra (``uv sync --extra dev --extra desktop``)
and are skipped when PyQt6/QtWebEngine cannot be imported. They run headless.
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if hasattr(os, "geteuid") and os.geteuid() == 0:
    # Chromium refuses to run its sandbox as root (CI containers).
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

import pytest

try:
    from PyQt6.QtCore import QEventLoop, QSettings, QTimer
    from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
except ImportError:  # pragma: no cover - depends on the environment
    collect_ignore_glob = ["test_*.py"]
else:

    @pytest.fixture(scope="session")
    def qapp():
        from PyQt6.QtWidgets import QApplication

        from md_viewer_desktop.document_view import register_scheme

        register_scheme()
        app = QApplication.instance() or QApplication(sys.argv[:1])
        yield app

    @pytest.fixture
    def settings(tmp_path):
        from md_viewer_desktop.settings import Settings

        return Settings(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))

    def wait_until(predicate, timeout_ms=10000):
        """Spin the event loop until ``predicate()`` is truthy or time runs out."""
        loop = QEventLoop()
        timer = QTimer()
        timer.setInterval(20)
        timer.timeout.connect(lambda: predicate() and loop.quit())
        timer.start()
        QTimer.singleShot(timeout_ms, loop.quit)
        if not predicate():
            loop.exec()
        timer.stop()
        return bool(predicate())

    def run_js(page, script, timeout_ms=5000):
        """Evaluate JavaScript in ``page`` and return the result synchronously."""
        loop = QEventLoop()
        result = {}

        def done(value):
            result["value"] = value
            loop.quit()

        page.runJavaScript(script, done)
        QTimer.singleShot(timeout_ms, loop.quit)
        loop.exec()
        return result.get("value")

    @pytest.fixture
    def helpers():
        return type("Helpers", (), {"wait_until": staticmethod(wait_until), "run_js": staticmethod(run_js)})

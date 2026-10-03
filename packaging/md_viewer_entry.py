"""PyInstaller entry point for the desktop app (``md-viewer``).

PyInstaller freezes a script, not a console_scripts entry, so this just calls
``md_viewer_desktop.main.main``. The Flask app has its own ``pyinstaller_entry.py``.
"""
import sys

from md_viewer_desktop.main import main

if __name__ == "__main__":
    sys.exit(main())

"""PyInstaller entry point.

PyInstaller freezes a single script, not a console_scripts entry point, so this
file just imports and calls the app's main(). When frozen, the app serves
markdown from the directory the .exe is launched in (Path.cwd()), same as the
normal `md-preview` command.
"""
from md_preview_server.app import main

if __name__ == "__main__":
    main()

@echo off
REM ============================================================
REM  Build a standalone Windows .exe with PyInstaller.
REM  Run this ONCE on your machine. Output: dist\md-viewer.exe
REM
REM  The .exe needs no Python/uv to run. Double-clicking it
REM  serves markdown from whatever folder the .exe sits in
REM  (it uses the current directory, like `md-preview` does).
REM ============================================================

cd /d "%~dp0"

REM Add pyinstaller to the project's dev deps in an isolated run.
echo Building... this can take a minute on the first run.

uv run --with pyinstaller pyinstaller ^
  --name md-viewer ^
  --onefile ^
  --paths src ^
  --add-data "src/md_preview_server/templates;md_preview_server/templates" ^
  --add-data "src/md_preview_server/static;md_preview_server/static" ^
  --collect-all markdown ^
  --collect-all pymdownx ^
  --collect-all pygments ^
  --hidden-import openai ^
  --noconfirm ^
  pyinstaller_entry.py

echo.
echo Done. Your executable is at: dist\md-viewer.exe
echo Drop it in any folder of .md files and double-click to serve that folder.
pause

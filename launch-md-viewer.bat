@echo off
REM ============================================================
REM  Markdown Viewer launcher
REM  Double-click to start the server and open it in your browser.
REM
REM  By default it serves the SERVE_DIR set below. Change that
REM  path to whichever folder of .md files you want to browse.
REM ============================================================

REM --- Folder whose markdown files you want to view ---
set "SERVE_DIR=D:\Code\Python\PythonApps\py-MD-viewer"

REM --- Location of the project (where uv / the app lives) ---
set "PROJECT_DIR=D:\Code\Python\PythonApps\py-MD-viewer"

REM Open the browser shortly after launch (server boots in ~1-2s)
start "" /min cmd /c "timeout /t 2 >nul & start http://localhost:8000"

REM Run the server from the folder you want to serve.
REM The window stays open and shows logs; close it (or Ctrl+C) to stop.
cd /d "%SERVE_DIR%"
title Markdown Viewer (http://localhost:8000)
uv run --project "%PROJECT_DIR%" md-preview

REM If the server exits/errors, keep the window open so you can read it.
echo.
echo Server stopped. Press any key to close.
pause >nul

#!/usr/bin/env bash
# Build dist/MD_Viewer-<version>-x86_64.AppImage (Linux, x86_64).
#
#   scripts/build-appimage.sh            # build the AppImage
#   scripts/build-appimage.sh --bundle   # stop after the PyInstaller bundle
#
# PyInstaller freezes the app (PyQt6 + QtWebEngine hooks are built in). The
# bundle is wrapped with appimagetool, which is downloaded into build/ if it
# is not already on PATH. Build on the oldest distro you want to support
# (e.g. Ubuntu 22.04), because the AppImage uses the host's glibc.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
ROOT=$PWD
BUILD=$ROOT/build/appimage
APPDIR=$BUILD/MD_Viewer.AppDir
ARCH=${ARCH:-x86_64}
VERSION=$(uv run --extra desktop python -c 'import md_viewer_desktop as m; print(m.__version__)')

rm -rf "$BUILD"
mkdir -p "$BUILD"

echo "==> PyInstaller bundle"
uv run --extra desktop --with pyinstaller pyinstaller \
  --name md-viewer \
  --onedir \
  --noconfirm \
  --distpath "$BUILD/dist" \
  --workpath "$BUILD/work" \
  --specpath "$BUILD" \
  --paths "$ROOT/src" \
  --collect-data md_viewer_desktop \
  --collect-data md_preview_server \
  --collect-all pymdownx \
  --collect-all markdown \
  --collect-submodules pygments \
  --exclude-module flask \
  --exclude-module openai \
  "$ROOT/packaging/md_viewer_entry.py"

[[ ${1:-} == --bundle ]] && { echo "bundle: $BUILD/dist/md-viewer"; exit 0; }

echo "==> AppDir"
mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/share/applications"
cp -a "$BUILD/dist/md-viewer" "$APPDIR/usr/lib/md-viewer"
LINUX=$ROOT/src/md_viewer_desktop/linux
ICON=$ROOT/src/md_viewer_desktop/resources/icons/md-viewer.svg
# The same .desktop file --install-desktop uses; the AppImage tooling needs
# Exec to be the bare command that AppRun provides.
cp "$LINUX/md-viewer.desktop" "$APPDIR/md-viewer.desktop"
cp "$LINUX/md-viewer.desktop" "$APPDIR/usr/share/applications/md-viewer.desktop"
cp "$ICON" "$APPDIR/md-viewer.svg"
cp "$LINUX/md-viewer.xml" "$APPDIR/usr/share/md-viewer.xml"
cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/sh
HERE=$(dirname "$(readlink -f "$0")")
# Chromium's sandbox needs a setuid helper that an AppImage can't ship.
export QTWEBENGINE_DISABLE_SANDBOX=${QTWEBENGINE_DISABLE_SANDBOX:-1}
exec "$HERE/usr/lib/md-viewer/md-viewer" "$@"
RUN
chmod +x "$APPDIR/AppRun"

echo "==> appimagetool"
TOOL=$(command -v appimagetool || true)
if [[ -z $TOOL ]]; then
  TOOL=$BUILD/appimagetool
  curl -fsSL -o "$TOOL" \
    "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
  chmod +x "$TOOL"
fi
OUT=$ROOT/dist/MD_Viewer-${VERSION}-${ARCH}.AppImage
mkdir -p "$ROOT/dist"
# --appimage-extract-and-run lets this work where FUSE is unavailable (CI, containers).
ARCH=$ARCH "$TOOL" --appimage-extract-and-run "$APPDIR" "$OUT"
echo "built: $OUT"

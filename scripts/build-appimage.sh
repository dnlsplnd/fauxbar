#!/usr/bin/env bash
# Builds fauxbar-x86_64.AppImage from the current source tree.
#
# Uses a dedicated venv (with --system-site-packages so it picks up the
# dnf-installed PySide6/mutagen) rather than the system Python directly,
# because numpy needs special handling: Fedora's python3-numpy links against
# FlexiBLAS, which resolves its actual BLAS backend via a runtime dlopen
# using a system config file - that indirection isn't traceable by
# PyInstaller's dependency scanner, so the backend never gets bundled and
# the frozen app aborts on startup. A plain PyPI numpy wheel bundles its
# own BLAS statically instead, so we force-install one into the venv,
# shadowing the system one for the build only.
set -euo pipefail
cd "$(dirname "$0")/.."

APP_NAME=fauxbar
BUILD_VENV=.build-venv
APPDIR=AppDir
APPIMAGETOOL=appimagetool-x86_64.AppImage

if [ ! -d "$BUILD_VENV" ]; then
  python3 -m venv --system-site-packages "$BUILD_VENV"
fi
"$BUILD_VENV/bin/pip" install --quiet --upgrade pip
"$BUILD_VENV/bin/pip" install --quiet pyinstaller
"$BUILD_VENV/bin/pip" install --quiet --ignore-installed --no-deps numpy

rm -rf build dist "$APP_NAME.spec"
"$BUILD_VENV/bin/pyinstaller" --name "$APP_NAME" --onedir --windowed \
  --add-data "app/style.qss:app" \
  --add-data "assets/fauxbar.png:assets" \
  --icon "assets/fauxbar.png" \
  main.py

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib/$APP_NAME"
cp -r "dist/$APP_NAME"/* "$APPDIR/usr/lib/$APP_NAME/"

cat > "$APPDIR/AppRun" <<EOF
#!/bin/bash
HERE="\$(dirname "\$(readlink -f "\${0}")")"
exec "\${HERE}/usr/lib/$APP_NAME/$APP_NAME" "\$@"
EOF
chmod +x "$APPDIR/AppRun"

cat > "$APPDIR/$APP_NAME.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$APP_NAME
Comment=A foobar2000-styled media player
Exec=$APP_NAME
Icon=$APP_NAME
Categories=AudioVideo;Audio;Player;Qt;
Terminal=false
EOF

cp assets/fauxbar.png "$APPDIR/$APP_NAME.png"

if [ ! -x "$APPIMAGETOOL" ]; then
  curl -L -o "$APPIMAGETOOL" \
    https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
  chmod +x "$APPIMAGETOOL"
fi

ARCH=x86_64 "./$APPIMAGETOOL" "$APPDIR" "${APP_NAME}-x86_64.AppImage"

echo "Built: $(pwd)/${APP_NAME}-x86_64.AppImage"

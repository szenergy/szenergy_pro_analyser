#!/usr/bin/env bash
# =========================================================================
#  SZenergy Pro Analyser - Linux Build Script
#  Builds the application and generates a standalone Linux AppImage in dist/
# =========================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "[1/3] Installing dependencies..."
pip install -r requirements.txt
pip install pyinstaller

echo "[2/3] Building with PyInstaller (Fast Startup onedir mode)..."
pyinstaller SZenergyPro-Analyser.spec --noconfirm --clean

echo "[3/3] Generating AppImage in dist/..."
APPDIR="$SCRIPT_DIR/build/AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"

# Move PyInstaller binary directory into AppDir
mv -r "$SCRIPT_DIR/dist/SZenergy_Pro_Analyser/" "$APPDIR/usr/bin"

# Create Desktop Entry
cat << 'EOF' > "$APPDIR/szenergypro.desktop"
[Desktop Entry]
Type=Application
Name=SZenergy Pro Analyser
Exec=SZenergy_Pro_Analyser %F
Icon=szenergypro
Categories=Development;Engineering;Science;
Terminal=false
EOF

# Create AppRun launcher
cat << 'EOF' > "$APPDIR/AppRun"
#!/bin/sh
HERE="$(dirname "$(readlink -f "${0}")")"
exec "${HERE}/usr/bin/SZenergy_Pro_Analyser" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# Download appimagetool if not present
TOOL="$SCRIPT_DIR/build/appimagetool-x86_64.AppImage"
if [ ! -f "$TOOL" ]; then
    echo "Downloading appimagetool..."
    curl -Lo "$TOOL" "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x "$TOOL"
fi

mkdir -p "$SCRIPT_DIR/dist"
ARCH=x86_64 "$TOOL" --appimage-extract-and-run "$APPDIR" "$SCRIPT_DIR/dist/SZenergyPro-Analyser.AppImage"
chmod +x "$SCRIPT_DIR/dist/SZenergyPro-Analyser.AppImage"

echo ""
echo "========================================================================="
echo " Build Complete! Output AppImage: dist/SZenergyPro-Analyser.AppImage"
echo "========================================================================="

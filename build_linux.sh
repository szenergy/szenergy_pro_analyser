#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "================================================="
echo "   SZenergy Pro Analyser - Linux Build Script    "
echo "================================================="

# Detect Python / Virtualenv
if [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
    PIP=".venv/bin/pip"
    PYINSTALLER=".venv/bin/pyinstaller"
else
    PYTHON="python3"
    PIP="pip3"
    PYINSTALLER="pyinstaller"
fi

echo "[1/3] Checking PyInstaller installation..."
if ! command -v "$PYINSTALLER" &> /dev/null; then
    echo "Installing PyInstaller..."
    "$PIP" install pyinstaller
fi

echo "[2/3] Building single executable for Linux..."
"$PYINSTALLER" \
    --noconfirm \
    --clean \
    --onefile \
    --windowed \
    --name "SZenergyProAnalyzer" \
    --splash "splash.png" \
    --add-data "szenergy_logo.png:." \
    --hidden-import "PySide6" \
    --hidden-import "PySide6.QtCore" \
    --hidden-import "PySide6.QtGui" \
    --hidden-import "PySide6.QtWidgets" \
    --hidden-import "pyqtgraph" \
    --hidden-import "pandas" \
    --hidden-import "numpy" \
    --hidden-import "openpyxl" \
    --hidden-import "nptdms" \
    main.py

echo "[3/3] Setting executable permissions..."
chmod +x dist/SZenergyProAnalyzer

echo ""
echo "================================================="
echo "Build complete! Linux single executable created:"
echo "  $(pwd)/dist/SZenergyProAnalyzer"
echo "================================================="

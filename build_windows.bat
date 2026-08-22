@echo off
setlocal enabledelayedexpansion

echo =================================================
echo   SZenergy Pro Analyser - Windows Build Script
echo =================================================

cd /d "%~dp0"

:: Detect Python / Virtualenv
if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
    set "PIP=.venv\Scripts\pip.exe"
    set "PYINSTALLER=.venv\Scripts\pyinstaller.exe"
) else (
    set "PYTHON=python"
    set "PIP=pip"
    set "PYINSTALLER=pyinstaller"
)

echo [1/2] Checking PyInstaller installation...
where !PYINSTALLER! >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing PyInstaller...
    !PIP! install pyinstaller
)

echo [2/2] Building single executable for Windows...
!PYINSTALLER! ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name "SZenergyProAnalyzer" ^
    --splash "szenergy_logo.png" ^
    --add-data "szenergy_logo.png;." ^
    --hidden-import "PySide6" ^
    --hidden-import "PySide6.QtCore" ^
    --hidden-import "PySide6.QtGui" ^
    --hidden-import "PySide6.QtWidgets" ^
    --hidden-import "pyqtgraph" ^
    --hidden-import "pandas" ^
    --hidden-import "numpy" ^
    --hidden-import "openpyxl" ^
    --hidden-import "nptdms" ^
    main.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Build failed! Check the output above.
    pause
    exit /b %errorlevel%
)

echo.
echo =================================================
echo Build complete! Windows executable created:
echo   %~dp0dist\SZenergyProAnalyzer.exe
echo =================================================
pause

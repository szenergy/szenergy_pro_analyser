@echo off
REM =========================================================================
REM  SZenergy Pro Analyser - Windows Build Script
REM  Builds the application with PyInstaller and compiles the Windows Installer
REM =========================================================================

echo [1/3] Installing requirements...
pip install -r requirements.txt
pip install pyinstaller

echo [2/3] Building application with PyInstaller (Fast Startup onedir mode)...
pyinstaller SZenergyPro-Analyser.spec --noconfirm --clean
if %ERRORLEVEL% NEQ 0 (
    echo PyInstaller build failed!
    exit /b %ERRORLEVEL%
)

echo [3/3] Creating Windows Installer...
set ISCC_PATH=""
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set ISCC_PATH="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set ISCC_PATH="C:\Program Files\Inno Setup 6\ISCC.exe"
where iscc >nul 2>&1 && set ISCC_PATH="iscc"

if not %ISCC_PATH%=="" (
    echo Compiling Installer with Inno Setup...
    %ISCC_PATH% installer.iss
    echo Installer successfully created: dist\SZenergyPro-Analyser-Setup.exe
) else (
    echo Inno Setup not found in standard paths.
    echo Creating zip archive in dist folder as fallback...
    powershell -Command "Compress-Archive -Force -Path 'dist\SZenergy_Pro_Analyser\*' -DestinationPath 'dist\SZenergyPro-Analyser-windows-x64.zip'"
    echo To generate the Setup.exe installer, install Inno Setup and run: iscc installer.iss
)

echo.
echo =========================================================================
echo  Build finished! Check the 'dist' folder for output.
echo =========================================================================
pause

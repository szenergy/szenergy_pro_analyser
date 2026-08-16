# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller specification file for SZenergy Pro Analyser.
Optimized for fast startup times (< 0.5s) using directory mode (onedir).
"""

import sys
import os

block_cipher = None

datas = []
if os.path.exists('szenergy_logo.jpg'):
    datas.append(('szenergy_logo.jpg', '.'))

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'core',
        'core.data_models',
        'core.file_parser',
        'core.state_manager',
        'core.migrations',
        'ui',
        'ui.main_window',
        'ui.sidebar',
        'ui.graph_view',
        'ui.import_wizard',
        'ui.edit_dialogs',
        'ui.loading_dialog',
        'utils',
        'utils.constants',
        'numpy',
        'pandas',
        'pyqtgraph',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'scipy',
        'matplotlib',
        'tkinter',
        'IPython',
        'pytest',
        'unittest',
        'lib2to3',
        'test',
        'distutils',
        'PySide6.QtWebEngine',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtQuick',
        'PySide6.QtQml',
        'PySide6.Qt3DCore',
        'PySide6.Qt3DRender',
        'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets',
        'PySide6.QtDesigner',
        'PySide6.QtPdf',
        'PySide6.QtPdfWidgets',
        'PySide6.QtSpatialAudio',
        'PySide6.QtSensors',
        'PySide6.QtSerialPort',
        'PySide6.QtBluetooth',
        'PySide6.QtNfc',
        'PySide6.QtPositioning',
        'PySide6.QtLocation',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SZenergy_Pro_Analyser',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SZenergy_Pro_Analyser',
)

"""
Startup Splash & Loading Screen.
Provides a native, professional loading screen with progress feedback
matching the application's exact theme stylesheet.
"""

import os
import sys
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QSplashScreen, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QApplication, QFrame
)
from PySide6.QtGui import QPixmap, QFont

from utils.constants import APP_NAME, APP_VERSION, APP_LOGO_FILENAME


def get_resource_path(relative_path: str) -> str:
    """Gets absolute path to resource, supporting PyInstaller onefile bundles and development."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, relative_path)


class SplashScreen(QSplashScreen):
    """
    Branded startup splash screen matching the application's exact desktop theme.
    Displays live progress during initialization and workspace restoration.
    """

    def __init__(self, is_dark: bool = True):
        self.is_dark = is_dark
        width = 520
        height = 260

        # Base solid pixmap
        bg_hex = "#1E2125" if self.is_dark else "#F8F9FA"
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.transparent)

        super().__init__(pixmap, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(width, height)

        self._init_ui(width, height)
        self.set_progress(0, "Starting application...")

    def _init_ui(self, width: int, height: int):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.root_frame = QFrame(self)
        self.root_frame.setObjectName("SplashRoot")

        # Color palette directly from utils/theme.py
        bg_main = "#1E2125" if self.is_dark else "#F8F9FA"
        bg_header = "#191B1F" if self.is_dark else "#E9ECEF"
        bg_panel = "#16181B" if self.is_dark else "#FFFFFF"
        border_col = "#2C3036" if self.is_dark else "#DEE2E6"
        text_primary = "#FFFFFF" if self.is_dark else "#212529"
        text_secondary = "#A0A0A0" if self.is_dark else "#6C757D"
        accent_color = "#00E676" if self.is_dark else "#00C853"
        prog_bg = "#282C31" if self.is_dark else "#E9ECEF"
        prog_border = "#3A3F47" if self.is_dark else "#CED4DA"

        self.root_frame.setStyleSheet(f"""
            QFrame#SplashRoot {{
                background-color: {bg_main};
                border: 1px solid {border_col};
                border-radius: 4px;
            }}
            QLabel {{
                color: {text_primary};
                font-family: 'Segoe UI', Arial, sans-serif;
                background: transparent;
            }}
            QProgressBar {{
                background-color: {prog_bg};
                border: 1px solid {prog_border};
                border-radius: 3px;
                text-align: center;
                height: 6px;
                max-height: 6px;
            }}
            QProgressBar::chunk {{
                background-color: {accent_color};
                border-radius: 2px;
            }}
        """)

        root_layout = QVBoxLayout(self.root_frame)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Header Bar (matching application menubar)
        header_bar = QWidget()
        header_bar.setStyleSheet(f"""
            background-color: {bg_header};
            border-bottom: 1px solid {border_col};
            border-top-left-radius: 3px;
            border-top-right-radius: 3px;
        """)
        header_layout = QHBoxLayout(header_bar)
        header_layout.setContentsMargins(14, 6, 14, 6)

        header_title = QLabel(APP_NAME)
        header_title.setStyleSheet(f"color: {text_secondary}; font-size: 11px; font-weight: bold;")
        header_layout.addWidget(header_title)

        header_layout.addStretch()

        version_label = QLabel(f"v{APP_VERSION}")
        version_label.setStyleSheet(f"color: {accent_color}; font-size: 11px; font-weight: bold;")
        header_layout.addWidget(version_label)

        root_layout.addWidget(header_bar)

        # 2. Main Content Body
        body_widget = QWidget()
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(20, 18, 20, 14)
        body_layout.setSpacing(18)

        # Logo badge in framed box
        logo_box = QFrame()
        logo_box.setStyleSheet(f"""
            background-color: {bg_panel};
            border: 1px solid {border_col};
            border-radius: 4px;
        """)
        logo_box_layout = QVBoxLayout(logo_box)
        logo_box_layout.setContentsMargins(8, 8, 8, 8)

        self.logo_label = QLabel()
        self.logo_label.setFixedSize(56, 56)
        self.logo_label.setScaledContents(True)
        logo_path = get_resource_path(APP_LOGO_FILENAME)
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path)
            self.logo_label.setPixmap(pix.scaled(56, 56, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo_box_layout.addWidget(self.logo_label)
        body_layout.addWidget(logo_box)

        # App Info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)
        info_layout.setAlignment(Qt.AlignVCenter)

        title_label = QLabel(APP_NAME)
        title_font = QFont("Segoe UI", 15, QFont.Bold)
        title_label.setFont(title_font)
        info_layout.addWidget(title_label)

        subtitle_label = QLabel("Telemetry & Data Analysis Platform")
        subtitle_label.setStyleSheet(f"color: {text_secondary}; font-size: 12px;")
        info_layout.addWidget(subtitle_label)

        sub_desc = QLabel("SZEnergy Team - Shell Eco-marathon")
        sub_desc.setStyleSheet(f"color: {accent_color}; font-size: 11px;")
        info_layout.addWidget(sub_desc)

        body_layout.addLayout(info_layout)
        body_layout.addStretch()

        root_layout.addWidget(body_widget)
        root_layout.addStretch()

        # 3. Bottom Status & Progress Area
        bottom_area = QWidget()
        bottom_area.setStyleSheet(f"""
            background-color: {bg_panel};
            border-top: 1px solid {border_col};
            border-bottom-left-radius: 3px;
            border-bottom-right-radius: 3px;
        """)
        bottom_layout = QVBoxLayout(bottom_area)
        bottom_layout.setContentsMargins(16, 10, 16, 12)
        bottom_layout.setSpacing(6)

        # Status text
        self.status_label = QLabel("Starting...")
        self.status_label.setStyleSheet(f"color: {text_primary}; font-size: 11px;")
        bottom_layout.addWidget(self.status_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        bottom_layout.addWidget(self.progress_bar)

        root_layout.addWidget(bottom_area)

        main_layout.addWidget(self.root_frame)

    def set_progress(self, percent: int, status_text: Optional[str] = None):
        """
        Updates the progress bar value (0-100) and status label,
        processing pending Qt events to ensure smooth rendering.
        """
        clamped_val = max(0, min(100, int(percent)))
        self.progress_bar.setValue(clamped_val)
        if status_text:
            self.status_label.setText(status_text)

        app = QApplication.instance()
        if app:
            app.processEvents()

    def set_status(self, status_text: str):
        """Updates the status message text and processes events."""
        self.status_label.setText(status_text)
        app = QApplication.instance()
        if app:
            app.processEvents()

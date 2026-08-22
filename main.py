"""
Entry point for SZenergy Pro Analyser desktop application.
Includes modern stylesheet with smooth, thin scrollbars, startup splash screen,
and system OS theme adaptation.
"""

import argparse
import os
import sys
import logging
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon

from ui.main_window import MainWindow, is_dark_theme
from ui.splash_screen import SplashScreen
from utils.theme import get_theme_stylesheet
from utils.constants import APP_NAME, ORGANIZATION_NAME, APP_LOGO_FILENAME, APP_VERSION
from utils.logger import setup_logging

# Attempt to import PyInstaller bootloader splash module (available in PyInstaller bundles built with --splash)
try:
    import pyi_splash
except ImportError:
    pyi_splash = None


def parse_args(argv=None):
    """Parses command line arguments including verbose debugging flag."""
    parser = argparse.ArgumentParser(description=f"{APP_NAME} - Telemetry Log Analyser")
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose debug logging in terminal"
    )
    return parser.parse_args(argv)


def get_resource_path(relative_path: str) -> str:
    """Gets absolute path to resource, supporting PyInstaller onefile bundles and development."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(__file__), relative_path)


def main():
    args = parse_args()
    logger = setup_logging(verbose=args.verbose)
    logger.info("Starting %s v%s...", APP_NAME, APP_VERSION)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORGANIZATION_NAME)
    app.setStyle("Fusion")

    logo_path = get_resource_path(APP_LOGO_FILENAME)
    if os.path.exists(logo_path):
        app.setWindowIcon(QIcon(logo_path))

    # Detect OS Theme (Light / Dark)
    is_dark = is_dark_theme()
    logger.debug("Detected desktop theme mode: %s", "Dark" if is_dark else "Light")
    app.setStyleSheet(get_theme_stylesheet(is_dark))

    # Initialize and show Qt Splash Screen
    splash = SplashScreen(is_dark=is_dark)
    splash.show()
    splash.set_progress(15, "Initializing application environment...")

    # Close PyInstaller bootloader splash to hand off smoothly to Qt splash screen
    if pyi_splash is not None:
        try:
            if hasattr(pyi_splash, "is_alive") and pyi_splash.is_alive():
                pyi_splash.close()
            elif hasattr(pyi_splash, "close"):
                pyi_splash.close()
        except Exception:
            pass

    window = MainWindow(splash=splash)

    splash.set_progress(100, "Ready")
    if getattr(window, "_restore_is_maximized", False):
        window.showMaximized()
    else:
        window.show()
    splash.finish(window)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

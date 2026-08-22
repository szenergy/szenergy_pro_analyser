"""
Entry point for SZenergy Pro Analyser desktop application.
Includes modern stylesheet with smooth, thin scrollbars and system OS theme adaptation.
"""

import argparse
import os
import sys
import logging
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon

from ui.main_window import MainWindow, is_dark_theme
from utils.constants import APP_NAME, ORGANIZATION_NAME, APP_LOGO_FILENAME, APP_VERSION
from utils.logger import setup_logging


def parse_args(argv=None):
    """Parses command line arguments including verbose debugging flag."""
    parser = argparse.ArgumentParser(description=f"{APP_NAME} - Telemetry Log Analyser")
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose debug logging in terminal"
    )
    return parser.parse_args(argv)


def main():
    args = parse_args()
    logger = setup_logging(verbose=args.verbose)
    logger.info("Starting %s v%s...", APP_NAME, APP_VERSION)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORGANIZATION_NAME)
    app.setStyle("Fusion")

    logo_path = os.path.join(os.path.dirname(__file__), APP_LOGO_FILENAME)
    if os.path.exists(logo_path):
        app.setWindowIcon(QIcon(logo_path))

    # Detect OS Theme (Light / Dark)
    is_dark = is_dark_theme()
    logger.debug("Detected desktop theme mode: %s", "Dark" if is_dark else "Light")

    if is_dark:
        stylesheet = """
            QMainWindow, QDialog { background-color: #1E2125; color: #E0E0E0; }
            QWidget { background-color: #1E2125; color: #E0E0E0; font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px; }
            QTreeWidget, QTableWidget { background-color: #16181B; border: 1px solid #2C3036; gridline-color: #2C3036; }
            QHeaderView::section { background-color: #25282D; color: #A0A0A0; padding: 4px; border: 1px solid #2C3036; font-weight: bold; }
            QComboBox, QLineEdit { background-color: #282C31; border: 1px solid #3A3F47; padding: 4px; color: #FFFFFF; border-radius: 3px; }
            QPushButton { background-color: #2A2E33; border: 1px solid #3A3F47; color: #FFFFFF; padding: 5px 12px; border-radius: 3px; }
            QPushButton:hover { background-color: #353A40; }
            QPushButton:checked { background-color: #00E676; color: #121212; border: 1px solid #00C853; font-weight: bold; }
            QMenuBar { background-color: #191B1F; color: #D0D0D0; }
            QMenuBar::item:selected { background-color: #2A2E33; }
            QMenu { background-color: #22252A; border: 1px solid #3A3F47; }
            QMenu::item:selected { background-color: #353A40; }
            QSplitter::handle { background-color: #2C3036; }

            /* Modern Thin Scrollbars (Dark Theme) */
            QScrollBar:vertical {
                background: #16181B;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #3A3F47;
                min-height: 25px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: #00E676;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
                height: 0px;
            }

            QScrollBar:horizontal {
                background: #16181B;
                height: 10px;
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background: #3A3F47;
                min-width: 25px;
                border-radius: 5px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #00E676;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
                width: 0px;
            }
        """
    else:
        stylesheet = """
            QMainWindow, QDialog { background-color: #F8F9FA; color: #212529; }
            QWidget { background-color: #F8F9FA; color: #212529; font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px; }
            QTreeWidget, QTableWidget { background-color: #FFFFFF; border: 1px solid #DEE2E6; gridline-color: #E9ECEF; }
            QHeaderView::section { background-color: #E9ECEF; color: #495057; padding: 4px; border: 1px solid #DEE2E6; font-weight: bold; }
            QComboBox, QLineEdit { background-color: #FFFFFF; border: 1px solid #CED4DA; padding: 4px; color: #212529; border-radius: 3px; }
            QPushButton { background-color: #E9ECEF; border: 1px solid #CED4DA; color: #212529; padding: 5px 12px; border-radius: 3px; }
            QPushButton:hover { background-color: #DEE2E6; }
            QPushButton:checked { background-color: #00C853; color: #FFFFFF; border: 1px solid #009624; font-weight: bold; }
            QMenuBar { background-color: #E9ECEF; color: #212529; }
            QMenuBar::item:selected { background-color: #DEE2E6; }
            QMenu { background-color: #FFFFFF; border: 1px solid #CED4DA; }
            QMenu::item:selected { background-color: #E9ECEF; }
            QSplitter::handle { background-color: #DEE2E6; }

            /* Modern Thin Scrollbars (Light Theme) */
            QScrollBar:vertical {
                background: #F8F9FA;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #CED4DA;
                min-height: 25px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: #00C853;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
                height: 0px;
            }

            QScrollBar:horizontal {
                background: #F8F9FA;
                height: 10px;
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background: #CED4DA;
                min-width: 25px;
                border-radius: 5px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #00C853;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
                width: 0px;
            }
        """

    app.setStyleSheet(stylesheet)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

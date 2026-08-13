"""
Entry point for SZenergy Pro Analyser desktop application.
"""

import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Dark theme stylesheet matching modern telemetry tools
    dark_stylesheet = """
        QMainWindow, QDialog {
            background-color: #1E2125;
            color: #E0E0E0;
        }
        QWidget {
            background-color: #1E2125;
            color: #E0E0E0;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 13px;
        }
        QTreeWidget, QTableWidget {
            background-color: #16181B;
            border: 1px solid #2C3036;
            gridline-color: #2C3036;
        }
        QHeaderView::section {
            background-color: #25282D;
            color: #A0A0A0;
            padding: 4px;
            border: 1px solid #2C3036;
            font-weight: bold;
        }
        QComboBox, QLineEdit {
            background-color: #282C31;
            border: 1px solid #3A3F47;
            padding: 4px;
            color: #FFFFFF;
            border-radius: 3px;
        }
        QPushButton {
            background-color: #2A2E33;
            border: 1px solid #3A3F47;
            color: #FFFFFF;
            padding: 5px 12px;
            border-radius: 3px;
        }
        QPushButton:hover {
            background-color: #353A40;
        }
        QMenuBar {
            background-color: #191B1F;
            color: #D0D0D0;
        }
        QMenuBar::item:selected {
            background-color: #2A2E33;
        }
        QMenu {
            background-color: #22252A;
            border: 1px solid #3A3F47;
        }
        QMenu::item:selected {
            background-color: #353A40;
        }
        QSplitter::handle {
            background-color: #2C3036;
        }
    """
    app.setStyleSheet(dark_stylesheet)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

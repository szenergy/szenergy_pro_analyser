"""
Compact popup displaying a palette grid of colors from LAP_COLORS, and icon utilities for laps.
"""

from PySide6.QtWidgets import QFrame, QVBoxLayout, QGridLayout, QPushButton, QLabel
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor, QPixmap, QIcon

from utils.constants import LAP_COLORS


def create_color_icon(hex_color: str, size: int = 14) -> QIcon:
    """Utility to create a small colored square icon for selected laps."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(hex_color))
    return QIcon(pixmap)


def create_empty_icon(size: int = 14) -> QIcon:
    """Utility to create a subtle gray square icon for unselected laps."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor("#4A4E57"))
    return QIcon(pixmap)


def format_lap_time(seconds: float) -> str:
    """Format duration in seconds to M:SS.ms format."""
    if seconds <= 0:
        return "--:--.--"
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins}:{secs:05.2f}"


class LapColorPickerPopup(QFrame):
    """
    Compact popup displaying a grid of color swatches from LAP_COLORS.
    Clicking a swatch emits color_selected(str) and closes the popup.
    """
    color_selected = Signal(str)

    def __init__(self, current_color: str = "", parent=None, is_dark: bool = True):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.current_color = current_color
        self.is_dark = is_dark

        bg_color = "#1E2125" if is_dark else "#FFFFFF"
        border_color = "#3A3F47" if is_dark else "#CED4DA"
        text_color = "#E0E0E0" if is_dark else "#212529"

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 6px;
            }}
            QLabel {{
                color: {text_color};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 11px;
                font-weight: bold;
                border: none;
                background: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(8)

        title_lbl = QLabel("Select Lap Color")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        grid = QGridLayout()
        grid.setSpacing(6)

        columns = 4
        for idx, hex_color in enumerate(LAP_COLORS):
            row = idx // columns
            col = idx % columns

            btn = QPushButton()
            btn.setFixedSize(26, 26)
            btn.setCursor(Qt.PointingHandCursor)
            is_current = (hex_color.upper() == current_color.upper())
            border_style = "2px solid #FFFFFF" if (is_current and is_dark) else ("2px solid #000000" if is_current else f"1px solid {border_color}")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {hex_color};
                    border: {border_style};
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    border: 2px solid {"#00E676" if is_dark else "#00C853"};
                }}
            """)
            btn.setToolTip(hex_color)
            btn.clicked.connect(lambda _, c=hex_color: self._on_color_clicked(c))
            grid.addWidget(btn, row, col)

        layout.addLayout(grid)

    def _on_color_clicked(self, color: str):
        self.color_selected.emit(color)
        self.close()

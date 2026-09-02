import math

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QPixmap, QPainter, QIcon, QPen, QPolygonF, QPainterPath


def create_icon_x_grid(is_dark: bool) -> QIcon:
    """Draws a crisp vector icon representing vertical X-axis grid lines."""
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    fg = QColor("#E0E0E0" if is_dark else "#2A2E33")
    pen = QPen(fg, 1.4)
    painter.setPen(pen)
    painter.drawRoundedRect(3, 3, 18, 18, 2, 2)
    # Vertical grid lines
    pen.setStyle(Qt.DotLine)
    painter.setPen(pen)
    painter.drawLine(9, 4, 9, 20)
    painter.drawLine(15, 4, 15, 20)
    painter.end()
    return QIcon(pixmap)


def create_icon_y_grid(is_dark: bool) -> QIcon:
    """Draws a crisp vector icon representing horizontal Y-axis grid lines."""
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    fg = QColor("#E0E0E0" if is_dark else "#2A2E33")
    pen = QPen(fg, 1.4)
    painter.setPen(pen)
    painter.drawRoundedRect(3, 3, 18, 18, 2, 2)
    # Horizontal grid lines
    pen.setStyle(Qt.DotLine)
    painter.setPen(pen)
    painter.drawLine(4, 9, 20, 9)
    painter.drawLine(4, 15, 20, 15)
    painter.end()
    return QIcon(pixmap)


def create_icon_cursor(is_dark: bool) -> QIcon:
    """Draws a vector crosshair icon for cursor tracking and value displays."""
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    fg = QColor("#E0E0E0" if is_dark else "#2A2E33")
    pen = QPen(fg, 1.4)
    painter.setPen(pen)
    painter.drawEllipse(5, 5, 14, 14)
    painter.drawLine(12, 1, 12, 6)
    painter.drawLine(12, 18, 12, 23)
    painter.drawLine(1, 12, 6, 12)
    painter.drawLine(18, 12, 23, 12)
    painter.setBrush(fg)
    painter.drawEllipse(11, 11, 2, 2)
    painter.end()
    return QIcon(pixmap)


def create_icon_legend(is_dark: bool) -> QIcon:
    """Draws a vector legend list/label icon."""
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    fg = QColor("#E0E0E0" if is_dark else "#2A2E33")
    pen = QPen(fg, 1.5)
    painter.setPen(pen)
    painter.setBrush(fg)
    # 3 lines with bullet dots
    painter.drawEllipse(3, 4, 3, 3)
    painter.drawLine(9, 5, 21, 5)
    painter.drawEllipse(3, 11, 3, 3)
    painter.drawLine(9, 12, 21, 12)
    painter.drawEllipse(3, 18, 3, 3)
    painter.drawLine(9, 19, 21, 19)
    painter.end()
    return QIcon(pixmap)


def create_icon_rename_legend(is_dark: bool) -> QIcon:
    """Draws a vector tag icon for renaming curve/legend labels."""
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    fg = QColor("#E0E0E0" if is_dark else "#2A2E33")
    pen = QPen(fg, 1.5)
    painter.setPen(pen)
    tag = QPolygonF([
        QPointF(3, 12),
        QPointF(9, 4),
        QPointF(20, 4),
        QPointF(20, 20),
        QPointF(9, 20),
    ])
    painter.drawPolygon(tag)
    painter.drawEllipse(14, 10, 3, 3)
    painter.drawLine(6, 12, 10, 12)
    painter.end()
    return QIcon(pixmap)


def create_icon_autorange(is_dark: bool) -> QIcon:
    """Draws a vector expand/auto-range icon with 4 corner brackets."""
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    fg = QColor("#E0E0E0" if is_dark else "#2A2E33")
    pen = QPen(fg, 1.6)
    painter.setPen(pen)
    painter.drawLine(3, 8, 3, 3)
    painter.drawLine(3, 3, 8, 3)
    painter.drawLine(16, 3, 21, 3)
    painter.drawLine(21, 3, 21, 8)
    painter.drawLine(3, 16, 3, 21)
    painter.drawLine(3, 21, 8, 21)
    painter.drawLine(16, 21, 21, 21)
    painter.drawLine(21, 21, 21, 16)
    painter.end()
    return QIcon(pixmap)


def create_icon_export(is_dark: bool) -> QIcon:
    """Draws a vector export/share icon (tray with upward arrow)."""
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    fg = QColor("#E0E0E0" if is_dark else "#2A2E33")
    pen = QPen(fg, 1.6)
    painter.setPen(pen)
    # Bottom tray/box
    painter.drawLine(4, 13, 4, 20)
    painter.drawLine(4, 20, 20, 20)
    painter.drawLine(20, 20, 20, 13)
    # Upward arrow stem
    painter.drawLine(12, 15, 12, 3)
    # Upward arrow head
    painter.drawLine(7, 8, 12, 3)
    painter.drawLine(17, 8, 12, 3)
    painter.end()
    return QIcon(pixmap)


def create_icon_settings(is_dark: bool) -> QIcon:
    """Draws a vector gear / settings icon for map management and configuration."""
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    fg = QColor("#E0E0E0" if is_dark else "#2A2E33")
    pen = QPen(fg, 1.5)
    painter.setPen(pen)

    cx, cy = 12.0, 12.0
    painter.drawEllipse(QPointF(cx, cy), 6.0, 6.0)
    painter.setBrush(fg)
    painter.drawEllipse(QPointF(cx, cy), 2.2, 2.2)

    # 8 radial teeth
    for i in range(8):
        angle_rad = i * (math.pi / 4.0)
        x1 = cx + 5.0 * math.cos(angle_rad)
        y1 = cy + 5.0 * math.sin(angle_rad)
        x2 = cx + 9.5 * math.cos(angle_rad)
        y2 = cy + 9.5 * math.sin(angle_rad)
        pen.setWidthF(2.2)
        painter.setPen(pen)
        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    painter.end()
    return QIcon(pixmap)


def create_icon_antialias(is_dark: bool) -> QIcon:
    """Draws a vector smooth S-curve icon representing anti-aliasing / curve smoothing."""
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    fg = QColor("#E0E0E0" if is_dark else "#2A2E33")
    pen = QPen(fg, 1.8)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)

    path = QPainterPath()
    path.moveTo(3, 16)
    path.cubicTo(8, 16, 8, 8, 12, 8)
    path.cubicTo(16, 8, 16, 16, 21, 16)
    painter.drawPath(path)
    painter.end()
    return QIcon(pixmap)

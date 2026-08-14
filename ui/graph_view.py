"""
PyQtGraph-based main view displaying vertically stacked, synchronized plots for selected channels.
Normalizes lap X-axis data for accurate lap overlay comparisons.
Features toolbar icon toggle buttons for X/Y grids, cursor values, legend labels, custom legend renaming, and auto-ranging.
Displays tracking dots on each curve at the cursor crosshair position.
Ensures equal viewbox heights across all stacked plots and full X-axis grid support on every plot.
"""

from typing import Dict, List, Set, Tuple, Optional
import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QFrame, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt, QSize, QPointF
from PySide6.QtGui import QColor, QPixmap, QPainter, QIcon, QPen, QPolygonF

from core.data_models import Session, Lap
from utils.constants import STD_CHANNEL_TIME, STD_CHANNEL_DISTANCE


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


class GraphViewWidget(QWidget):
    """Main plotting area with vertically stacked charts, toolbar toggles, and on-graph value readouts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sessions: Dict[str, Session] = {}
        self.selected_channels: List[str] = []
        self.selected_laps_info: List[Tuple[str, int, str]] = []
        self.custom_lap_labels: Dict[Tuple[str, int], str] = {}
        self.x_axis_channel: str = STD_CHANNEL_TIME
        self.time_label: str = STD_CHANNEL_TIME
        self.dist_label: str = STD_CHANNEL_DISTANCE
        self.is_dark: bool = True

        # View and Display toggles
        self.show_x_grid: bool = True
        self.show_y_grid: bool = True
        self.show_cursor_values: bool = True
        self.show_legend: bool = True

        self.plot_widgets: Dict[str, pg.PlotItem] = {}
        self.v_lines: List[pg.InfiniteLine] = []
        self.tracking_dots: List[Tuple[pg.ScatterPlotItem, str, int, str]] = []
        self.legend: Optional[pg.LegendItem] = None

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Top Control Bar for X-Axis selection and interactive tool buttons
        self.control_bar = QFrame()
        c_layout = QHBoxLayout(self.control_bar)
        c_layout.setContentsMargins(10, 4, 10, 4)
        c_layout.setSpacing(6)

        # 1. Auto Range All Graphs Button
        self.btn_autorange = QPushButton()
        self.btn_autorange.setToolTip("Auto Range All Graphs")
        self.btn_autorange.setFixedSize(32, 28)
        self.btn_autorange.setIconSize(QSize(18, 18))
        self.btn_autorange.clicked.connect(self._on_autorange)
        c_layout.addWidget(self.btn_autorange)

        # 2. Toggle X-Axis Grid Button
        self.btn_x_grid = QPushButton()
        self.btn_x_grid.setCheckable(True)
        self.btn_x_grid.setChecked(True)
        self.btn_x_grid.setToolTip("Toggle X-Axis Grid Lines")
        self.btn_x_grid.setFixedSize(32, 28)
        self.btn_x_grid.setIconSize(QSize(18, 18))
        self.btn_x_grid.toggled.connect(self._toggle_x_grid)
        c_layout.addWidget(self.btn_x_grid)

        # 3. Toggle Y-Axis Grid Button
        self.btn_y_grid = QPushButton()
        self.btn_y_grid.setCheckable(True)
        self.btn_y_grid.setChecked(True)
        self.btn_y_grid.setToolTip("Toggle Y-Axis Grid Lines")
        self.btn_y_grid.setFixedSize(32, 28)
        self.btn_y_grid.setIconSize(QSize(18, 18))
        self.btn_y_grid.toggled.connect(self._toggle_y_grid)
        c_layout.addWidget(self.btn_y_grid)

        # 4. Toggle Cursor Values Display Button
        self.btn_cursor = QPushButton()
        self.btn_cursor.setCheckable(True)
        self.btn_cursor.setChecked(True)
        self.btn_cursor.setToolTip("Toggle Cursor Crosshair & Value Display")
        self.btn_cursor.setFixedSize(32, 28)
        self.btn_cursor.setIconSize(QSize(18, 18))
        self.btn_cursor.toggled.connect(self._toggle_cursor_values)
        c_layout.addWidget(self.btn_cursor)

        # 5. Toggle Legend / Label Button
        self.btn_legend = QPushButton()
        self.btn_legend.setCheckable(True)
        self.btn_legend.setChecked(True)
        self.btn_legend.setToolTip("Toggle Curve Legend")
        self.btn_legend.setFixedSize(32, 28)
        self.btn_legend.setIconSize(QSize(18, 18))
        self.btn_legend.toggled.connect(self._toggle_legend)
        c_layout.addWidget(self.btn_legend)

        # 6. Rename Legend / Curve Labels Button
        self.btn_rename_legend = QPushButton()
        self.btn_rename_legend.setToolTip("Rename Legend / Curve Labels...")
        self.btn_rename_legend.setFixedSize(32, 28)
        self.btn_rename_legend.setIconSize(QSize(18, 18))
        self.btn_rename_legend.clicked.connect(self._on_rename_legend)
        c_layout.addWidget(self.btn_rename_legend)

        c_layout.addStretch()

        # 7. X-Axis Selector
        c_layout.addWidget(QLabel("<b>X-Axis:</b>"))
        self.x_axis_combo = QComboBox()
        self.x_axis_combo.addItems([self.dist_label, self.time_label])
        self.x_axis_combo.currentTextChanged.connect(self._on_x_axis_changed)
        c_layout.addWidget(self.x_axis_combo)

        layout.addWidget(self.control_bar)

        # PyQtGraph Layout Container
        self.glw = pg.GraphicsLayoutWidget()
        layout.addWidget(self.glw)

        # Connect scene mouse-move signal ONCE globally on initialization
        self.glw.scene().sigMouseMoved.connect(self._on_mouse_moved)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_row_heights()

    def _update_row_heights(self):
        """Ensures all stacked plot ViewBoxes have identical height."""
        n = len(self.selected_channels)
        if n == 0 or not self.plot_widgets:
            return

        h_axis = 40
        margin = 18
        spacing = 6 * (n - 1)
        total_h = self.glw.height() - margin - spacing
        if total_h <= 0:
            return

        h_plot = (total_h - (h_axis if n > 1 else 0)) / n
        for i in range(n):
            if i == n - 1 and n > 1:
                self.glw.ci.layout.setRowFixedHeight(i, h_plot + h_axis)
            else:
                self.glw.ci.layout.setRowFixedHeight(i, h_plot)

    def set_x_axis_labels(self, time_label: str, dist_label: str):
        """Updates X-Axis options based on configured standard labels."""
        self.time_label = time_label
        self.dist_label = dist_label

        self.x_axis_combo.blockSignals(True)
        self.x_axis_combo.clear()
        self.x_axis_combo.addItems([self.time_label, self.dist_label])
        self.x_axis_combo.blockSignals(False)

        self.x_axis_channel = self.x_axis_combo.currentText()
        self.rebuild_plots()

    def apply_theme(self, is_dark: bool):
        self.is_dark = is_dark
        bg_color = "#191B1F" if is_dark else "#FFFFFF"
        fg_color = "#E0E0E0" if is_dark else "#202020"
        bar_style = (
            "background-color: #24272C; color: #E0E0E0; border-bottom: 1px solid #2C3036;"
            if is_dark else
            "background-color: #E8ECEF; color: #212529; border-bottom: 1px solid #DEE2E6;"
        )

        pg.setConfigOptions(background=bg_color, foreground=fg_color, antialias=True)
        self.glw.setBackground(bg_color)
        self.control_bar.setStyleSheet(bar_style)

        # Refresh icons with current theme colors
        self.btn_x_grid.setIcon(create_icon_x_grid(is_dark))
        self.btn_y_grid.setIcon(create_icon_y_grid(is_dark))
        self.btn_cursor.setIcon(create_icon_cursor(is_dark))
        self.btn_legend.setIcon(create_icon_legend(is_dark))
        self.btn_rename_legend.setIcon(create_icon_rename_legend(is_dark))
        self.btn_autorange.setIcon(create_icon_autorange(is_dark))

        self.rebuild_plots()

    def set_sessions(self, sessions: Dict[str, Session]):
        self.sessions = sessions
        self.rebuild_plots()

    def set_selected_channels(self, channels: Set[str]):
        self.selected_channels = sorted(list(channels))
        self.rebuild_plots()

    def set_selected_laps(self, laps_info: List[Tuple[str, int, str]]):
        self.selected_laps_info = laps_info
        self.rebuild_plots()

    def _on_x_axis_changed(self, new_x_axis: str):
        if new_x_axis:
            self.x_axis_channel = new_x_axis
            self.rebuild_plots()

    def _toggle_x_grid(self, checked: bool):
        self.show_x_grid = checked
        for plot in self.plot_widgets.values():
            plot.showGrid(x=self.show_x_grid, y=self.show_y_grid, alpha=0.3)

    def _toggle_y_grid(self, checked: bool):
        self.show_y_grid = checked
        for plot in self.plot_widgets.values():
            plot.showGrid(x=self.show_x_grid, y=self.show_y_grid, alpha=0.3)

    def _toggle_cursor_values(self, checked: bool):
        self.show_cursor_values = checked
        for v_line in self.v_lines:
            v_line.setVisible(self.show_cursor_values)
        for dot, _, _, _ in self.tracking_dots:
            dot.setVisible(self.show_cursor_values)
        if not self.show_cursor_values:
            title_color = "#E0E0E0" if self.is_dark else "#202020"
            for channel_name, plot in self.plot_widgets.items():
                plot.setTitle(f"<span style='color:{title_color}; font-weight:bold; font-size:10pt;'>{channel_name}</span>", justify='left')

    def _toggle_legend(self, checked: bool):
        self.show_legend = checked
        if self.legend:
            self.legend.setVisible(self.show_legend)

    def _on_autorange(self):
        for plot in self.plot_widgets.values():
            plot.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
            plot.autoRange()

    def _on_rename_legend(self):
        """Opens dialog to customize legend labels specifying what the curve colors mean."""
        if not self.selected_laps_info:
            QMessageBox.information(
                self, "No Laps Selected",
                "Please select at least one lap from the left sidebar to customize its legend label."
            )
            return

        from ui.edit_dialogs import RenameLegendLabelsDialog
        dialog = RenameLegendLabelsDialog(
            self.selected_laps_info, self.sessions, self.custom_lap_labels, parent=self
        )
        if dialog.exec() == RenameLegendLabelsDialog.Accepted:
            self.custom_lap_labels.update(dialog.renamed_labels)
            self.rebuild_plots()

    def rebuild_plots(self):
        self.glw.clear()
        self.plot_widgets.clear()
        self.v_lines.clear()
        self.tracking_dots.clear()
        self.legend = None

        if not self.selected_channels or not self.selected_laps_info:
            label = pg.LabelItem(
                text="Select laps and channels from the left sidebar to display graphs.",
                size="12pt", color="#808080"
            )
            self.glw.addItem(label, row=0, col=0)
            return

        first_plot: Optional[pg.PlotItem] = None
        title_color = "#E0E0E0" if self.is_dark else "#202020"

        for row, channel_name in enumerate(self.selected_channels):
            plot = self.glw.addPlot(row=row, col=0)

            title_html = f"<span style='color:{title_color}; font-weight:bold; font-size:10pt;'>{channel_name}</span>"
            plot.setTitle(title_html, justify='left')
            plot.setLabel("left", "")
            plot.showGrid(x=self.show_x_grid, y=self.show_y_grid, alpha=0.3)
            plot.getAxis('left').setWidth(65)

            if first_plot is None:
                first_plot = plot
                self.legend = pg.LegendItem(offset=(-10, 10))
                self.legend.setParentItem(first_plot)
                self.legend.setVisible(self.show_legend)
                if self.is_dark:
                    self.legend.setBrush(pg.mkBrush(30, 33, 38, 220))
                    self.legend.setPen(pg.mkPen(80, 80, 80))
                else:
                    self.legend.setBrush(pg.mkBrush(245, 245, 245, 220))
                    self.legend.setPen(pg.mkPen(200, 200, 200))
            else:
                plot.setXLink(first_plot)

            if row == len(self.selected_channels) - 1:
                plot.getAxis("bottom").setStyle(showValues=True)
                plot.getAxis("bottom").setHeight(40)
                plot.setLabel("bottom", f"{self.x_axis_channel}")
            else:
                # Keep bottom axis active to render X grid lines, but without text numbers
                plot.getAxis("bottom").setStyle(showValues=False, tickLength=0)
                plot.getAxis("bottom").setHeight(0)

            # Synchronized vertical crosshair
            v_line = pg.InfiniteLine(
                angle=90, movable=False,
                pen=pg.mkPen("#FFD740", width=1, style=Qt.DashLine)
            )
            v_line.setVisible(self.show_cursor_values)
            plot.addItem(v_line, ignoreBounds=True)
            self.v_lines.append(v_line)

            self.plot_widgets[channel_name] = plot

            # Plot curves and create tracking dots for each selected lap
            for session_id, lap_num, color in self.selected_laps_info:
                if session_id not in self.sessions:
                    continue
                session = self.sessions[session_id]
                lap = session.get_lap(lap_num)
                if not lap:
                    continue

                raw_x = lap.get_channel(self.x_axis_channel)
                raw_y = lap.get_channel(channel_name)

                if raw_x is not None and raw_y is not None and len(raw_x) > 0 and len(raw_y) > 0:
                    x_normalized = raw_x - raw_x[0]
                    pen = pg.mkPen(color=color, width=1.8)

                    curve = plot.plot(x_normalized, raw_y, pen=pen)

                    # Create tracking dot for this curve
                    dot_pen = pg.mkPen("#FFFFFF" if self.is_dark else "#000000", width=1.2)
                    dot = pg.ScatterPlotItem(
                        size=8,
                        brush=pg.mkBrush(color),
                        pen=dot_pen,
                        symbol='o'
                    )
                    dot.setZValue(10)
                    dot.setVisible(self.show_cursor_values)
                    plot.addItem(dot, ignoreBounds=True)
                    self.tracking_dots.append((dot, session_id, lap_num, channel_name))

                    # Populate the single shared legend using the first row curves
                    if row == 0 and self.legend is not None:
                        default_name = f"{session.name} L{lap.lap_number}"
                        curve_name = self.custom_lap_labels.get((session_id, lap.lap_number), default_name)
                        self.legend.addItem(curve, curve_name)

            plot.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
            plot.autoRange()

        self._update_row_heights()

    def _on_mouse_moved(self, evt):
        if not self.plot_widgets or not self.show_cursor_values:
            return

        first_plot = list(self.plot_widgets.values())[0]
        mouse_point = first_plot.vb.mapSceneToView(evt)
        x_val = mouse_point.x()

        # Update crosshair position on all stacked plots
        for v_line in self.v_lines:
            v_line.setPos(x_val)

        title_color = "#E0E0E0" if self.is_dark else "#202020"

        # Update tracking dots position on every curve
        for dot, session_id, lap_num, channel_name in self.tracking_dots:
            session = self.sessions.get(session_id)
            if not session:
                dot.setData(x=[], y=[])
                continue
            lap = session.get_lap(lap_num)
            if not lap:
                dot.setData(x=[], y=[])
                continue

            raw_x = lap.get_channel(self.x_axis_channel)
            raw_y = lap.get_channel(channel_name)

            if raw_x is not None and raw_y is not None and len(raw_x) > 1:
                norm_x = raw_x - raw_x[0]
                if norm_x[0] <= x_val <= norm_x[-1]:
                    y_val = float(np.interp(x_val, norm_x, raw_y))
                    dot.setData(x=[x_val], y=[y_val])
                    dot.setVisible(True)
                else:
                    dot.setData(x=[], y=[])
            else:
                dot.setData(x=[], y=[])

        # Update each plot's header directly with its current channel values
        for channel_name, plot in self.plot_widgets.items():
            title_parts = [f"<span style='color:{title_color}; font-weight:bold; font-size:10pt;'>{channel_name}</span>"]

            for session_id, lap_num, color in self.selected_laps_info:
                session = self.sessions.get(session_id)
                if not session:
                    continue
                lap = session.get_lap(lap_num)
                if not lap:
                    continue

                raw_x = lap.get_channel(self.x_axis_channel)
                raw_y = lap.get_channel(channel_name)

                if raw_x is not None and raw_y is not None and len(raw_x) > 1:
                    norm_x = raw_x - raw_x[0]
                    if norm_x[0] <= x_val <= norm_x[-1]:
                        y_val = float(np.interp(x_val, norm_x, raw_y))
                        title_parts.append(f"<span style='color:{color}; font-weight:bold; font-size:10pt;'>{y_val:.2f}</span>")

            plot.setTitle(" &nbsp;&nbsp;&nbsp; ".join(title_parts), justify='left')

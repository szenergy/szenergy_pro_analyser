"""
PyQtGraph-based main view displaying vertically stacked, synchronized plots for selected channels.
Normalizes lap X-axis data for accurate lap overlay comparisons.
Displays current telemetry values directly on each individual channel graph.
"""

from typing import Dict, List, Set, Tuple, Optional
import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QFrame
from PySide6.QtCore import Qt

from core.data_models import Session, Lap
from utils.constants import STD_CHANNEL_TIME, STD_CHANNEL_DISTANCE


class GraphViewWidget(QWidget):
    """Main plotting area with vertically stacked charts, synchronized cursor, and on-graph value readouts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sessions: Dict[str, Session] = {}
        self.selected_channels: List[str] = []
        self.selected_laps_info: List[Tuple[str, int, str]] = []
        self.x_axis_channel: str = STD_CHANNEL_TIME
        self.time_label: str = STD_CHANNEL_TIME
        self.dist_label: str = STD_CHANNEL_DISTANCE
        self.is_dark: bool = True

        self.plot_widgets: Dict[str, pg.PlotItem] = {}
        self.v_lines: List[pg.InfiniteLine] = []
        self.legend: Optional[pg.LegendItem] = None

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Top Control Bar for X-Axis selection
        self.control_bar = QFrame()
        c_layout = QHBoxLayout(self.control_bar)
        c_layout.setContentsMargins(10, 4, 10, 4)

        c_layout.addWidget(QLabel("<b>X-Axis Mode:</b>"))
        self.x_axis_combo = QComboBox()
        self.x_axis_combo.addItems([self.time_label, self.dist_label])
        self.x_axis_combo.currentTextChanged.connect(self._on_x_axis_changed)
        c_layout.addWidget(self.x_axis_combo)

        c_layout.addStretch()
        layout.addWidget(self.control_bar)

        # PyQtGraph Layout Container
        self.glw = pg.GraphicsLayoutWidget()
        layout.addWidget(self.glw)

        # Connect scene mouse-move signal ONCE globally on initialization
        self.glw.scene().sigMouseMoved.connect(self._on_mouse_moved)

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

    def rebuild_plots(self):
        self.glw.clear()
        self.plot_widgets.clear()
        self.v_lines.clear()
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
            plot.showGrid(x=True, y=True, alpha=0.3)
            plot.getAxis('left').setWidth(65)

            if first_plot is None:
                first_plot = plot
                self.legend = pg.LegendItem(offset=(-10, 10))
                self.legend.setParentItem(first_plot)
                if self.is_dark:
                    self.legend.setBrush(pg.mkBrush(30, 33, 38, 220))
                    self.legend.setPen(pg.mkPen(80, 80, 80))
                else:
                    self.legend.setBrush(pg.mkBrush(245, 245, 245, 220))
                    self.legend.setPen(pg.mkPen(200, 200, 200))
            else:
                plot.setXLink(first_plot)

            if row == len(self.selected_channels) - 1:
                plot.setLabel("bottom", f"{self.x_axis_channel}")
            else:
                plot.hideAxis("bottom")

            # Synchronized vertical crosshair
            v_line = pg.InfiniteLine(
                angle=90, movable=False,
                pen=pg.mkPen("#FFD740", width=1, style=Qt.DashLine)
            )
            plot.addItem(v_line, ignoreBounds=True)
            self.v_lines.append(v_line)

            self.plot_widgets[channel_name] = plot

            # Plot curves for each selected lap
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

                    # Populate the single shared legend using the first row curves
                    if row == 0 and self.legend is not None:
                        short_session = session.name[:12] + "..." if len(session.name) > 15 else session.name
                        curve_name = f"{short_session} L{lap.lap_number}"
                        self.legend.addItem(curve, curve_name)

            plot.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
            plot.autoRange()

    def _on_mouse_moved(self, evt):
        if not self.plot_widgets:
            return

        first_plot = list(self.plot_widgets.values())[0]
        mouse_point = first_plot.vb.mapSceneToView(evt)
        x_val = mouse_point.x()

        # Update crosshair position on all stacked plots
        for v_line in self.v_lines:
            v_line.setPos(x_val)

        title_color = "#E0E0E0" if self.is_dark else "#202020"

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

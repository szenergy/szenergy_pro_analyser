"""
PyQtGraph-based main view displaying vertically stacked, synchronized plots for selected channels.
Normalizes lap X-axis data for accurate lap overlay comparisons.
Features aligned left axes and automatic auto-ranging on view updates.
"""

from typing import Dict, List, Set, Tuple, Optional
import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QFrame
from PySide6.QtCore import Qt

from core.data_models import Session, Lap
from utils.constants import STD_CHANNEL_TIME, STD_CHANNEL_DISTANCE


class GraphViewWidget(QWidget):
    """Main plotting area with vertically stacked charts and synchronized cursor."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sessions: Dict[str, Session] = {}
        self.selected_channels: List[str] = []
        self.selected_laps_info: List[Tuple[str, int, str]] = []
        self.x_axis_channel: str = STD_CHANNEL_TIME

        self.plot_widgets: Dict[str, pg.PlotItem] = {}
        self.v_lines: List[pg.InfiniteLine] = []

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Control Bar for X-Axis selection and Current Values display
        self.control_bar = QFrame()
        c_layout = QHBoxLayout(self.control_bar)
        c_layout.setContentsMargins(10, 4, 10, 4)

        c_layout.addWidget(QLabel("<b>X-Axis Mode:</b>"))
        self.x_axis_combo = QComboBox()
        self.x_axis_combo.addItems([STD_CHANNEL_TIME, STD_CHANNEL_DISTANCE])
        self.x_axis_combo.currentTextChanged.connect(self._on_x_axis_changed)
        c_layout.addWidget(self.x_axis_combo)

        c_layout.addSpacing(20)
        self.cursor_info_label = QLabel("Cursor: --")
        self.cursor_info_label.setStyleSheet("font-weight: bold;")
        c_layout.addWidget(self.cursor_info_label)

        c_layout.addStretch()
        layout.addWidget(self.control_bar)

        # PyQtGraph Layout Container
        self.glw = pg.GraphicsLayoutWidget()
        layout.addWidget(self.glw)

    def apply_theme(self, is_dark: bool):
        """Updates PyQtGraph background/foreground based on system light/dark theme."""
        bg_color = "#191B1F" if is_dark else "#FFFFFF"
        fg_color = "#E0E0E0" if is_dark else "#202020"
        bar_style = "background-color: #24272C; color: white;" if is_dark else "background-color: #E8ECEF; color: black;"

        pg.setConfigOptions(background=bg_color, foreground=fg_color)
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
        self.x_axis_channel = new_x_axis
        self.rebuild_plots()

    def rebuild_plots(self):
        """Clears and rebuilds stacked plot items with lap X-axis overlay normalization and auto-ranging."""
        self.glw.clear()
        self.plot_widgets.clear()
        self.v_lines.clear()

        # Display helpful placeholder if no selection
        if not self.selected_channels or not self.selected_laps_info:
            label = pg.LabelItem(
                text="Select laps and channels from the left sidebar to display graphs.",
                size="13pt", color="#808080"
            )
            self.glw.addItem(label, row=0, col=0)
            return

        first_plot: Optional[pg.PlotItem] = None

        for row, channel_name in enumerate(self.selected_channels):
            plot = self.glw.addPlot(row=row, col=0)
            plot.setLabel("left", channel_name)
            plot.showGrid(x=True, y=True, alpha=0.3)

            # FIX 1: Set fixed width for left axis to align all plot canvases perfectly on the left
            plot.getAxis('left').setWidth(75)

            # Synchronize X-axis across stacked plots
            if first_plot is None:
                first_plot = plot
            else:
                plot.setXLink(first_plot)

            if row == len(self.selected_channels) - 1:
                plot.setLabel("bottom", f"Relative {self.x_axis_channel}")
            else:
                plot.hideAxis("bottom")

            # Add vertical crosshair line
            v_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#FFD740", width=1, style=Qt.DashLine))
            plot.addItem(v_line, ignoreBounds=True)
            self.v_lines.append(v_line)

            plot.scene().sigMouseMoved.connect(self._on_mouse_moved)
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

                if raw_x is not None and raw_y is not None and len(raw_x) > 0:
                    x_normalized = raw_x - raw_x[0]
                    pen = pg.mkPen(color=color, width=1.8)
                    plot.plot(x_normalized, raw_y, pen=pen, name=f"{session.name} - Lap {lap.lap_number}")

            # FIX 2: Auto-range every plot on update
            plot.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
            plot.autoRange()

    def _on_mouse_moved(self, evt):
        if not self.plot_widgets:
            return

        first_plot = list(self.plot_widgets.values())[0]
        mouse_point = first_plot.vb.mapSceneToView(evt)
        x_val = mouse_point.x()

        for v_line in self.v_lines:
            v_line.setPos(x_val)

        unit = "s" if self.x_axis_channel == STD_CHANNEL_TIME else "m"
        info_text = f"Relative {self.x_axis_channel}: {x_val:.2f} {unit}"
        self.cursor_info_label.setText(info_text)

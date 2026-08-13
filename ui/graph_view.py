"""
PyQtGraph-based main view displaying vertically stacked, synchronized plots for selected channels.
"""

from typing import Dict, List, Set, Optional
import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QFrame
from PySide6.QtCore import Qt, Signal

from core.data_models import Session, Lap
from utils.constants import STD_CHANNEL_TIME, STD_CHANNEL_DISTANCE

# Enable anti-aliasing for smooth lines
pg.setConfigOptions(antialias=True, background="#191B1F", foreground="#E0E0E0")


class GraphViewWidget(QWidget):
    """Main plotting area with vertically stacked charts and synchronized cursor."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sessions: Dict[str, Session] = {}
        self.selected_channels: List[str] = []
        self.x_axis_channel: str = STD_CHANNEL_TIME

        self.plot_widgets: Dict[str, pg.PlotItem] = {}
        self.curve_items: Dict[Tuple[str, str, int], pg.PlotDataItem] = {}  # (channel, session_id, lap_num) -> Curve
        self.v_lines: List[pg.InfiniteLine] = []

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Control Bar for X-Axis selection and Current Values display
        control_bar = QFrame()
        control_bar.setStyleSheet("background-color: #24272C; color: white;")
        c_layout = QHBoxLayout(control_bar)
        c_layout.setContentsMargins(10, 4, 10, 4)

        c_layout.addWidget(QLabel("<b>X-Axis Mode:</b>"))
        self.x_axis_combo = QComboBox()
        self.x_axis_combo.addItems([STD_CHANNEL_TIME, STD_CHANNEL_DISTANCE])
        self.x_axis_combo.currentTextChanged.connect(self._on_x_axis_changed)
        c_layout.addWidget(self.x_axis_combo)

        c_layout.addSpacing(20)
        self.cursor_info_label = QLabel("Cursor: --")
        self.cursor_info_label.setStyleSheet("color: #00E676; font_weight: bold;")
        c_layout.addWidget(self.cursor_info_label)

        c_layout.addStretch()
        layout.addWidget(control_bar)

        # PyQtGraph Layout Container
        self.glw = pg.GraphicsLayoutWidget()
        layout.addWidget(self.glw)

    def set_sessions(self, sessions: Dict[str, Session]):
        """Sets active sessions reference."""
        self.sessions = sessions
        self.rebuild_plots()

    def set_selected_channels(self, channels: Set[str]):
        """Updates list of channels to plot vertically."""
        # Preserve user selection order as much as possible
        self.selected_channels = sorted(list(channels))
        self.rebuild_plots()

    def update_lap_visibility(self, session_id: str, lap_number: int, is_visible: bool):
        """Toggles visibility of curves for a specific lap without rebuilding everything."""
        for channel in self.selected_channels:
            key = (channel, session_id, lap_number)
            if key in self.curve_items:
                self.curve_items[key].setVisible(is_visible)

    def _on_x_axis_changed(self, new_x_axis: str):
        self.x_axis_channel = new_x_axis
        self.rebuild_plots()

    def rebuild_plots(self):
        """Clears and rebuilds all stacked plot items and curves."""
        self.glw.clear()
        self.plot_widgets.clear()
        self.curve_items.clear()
        self.v_lines.clear()

        if not self.selected_channels:
            return

        first_plot: Optional[pg.PlotItem] = None

        for row, channel_name in enumerate(self.selected_channels):
            # Create PlotItem
            plot = self.glw.addPlot(row=row, col=0)
            plot.setLabel("left", channel_name)
            plot.showGrid(x=True, y=True, alpha=0.3)

            # Synchronize X-axis across all stacked plots
            if first_plot is None:
                first_plot = plot
            else:
                plot.setXLink(first_plot)

            # Label X axis on bottom plot only
            if row == len(self.selected_channels) - 1:
                plot.setLabel("bottom", self.x_axis_channel)
            else:
                plot.hideAxis("bottom")

            # Add vertical crosshair line
            v_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#FFD740", width=1, style=Qt.DashLine))
            plot.addItem(v_line, ignoreBounds=True)
            self.v_lines.append(v_line)

            # Connect mouse move event for crosshairs
            plot.scene().sigMouseMoved.connect(self._on_mouse_moved)

            self.plot_widgets[channel_name] = plot

            # Plot curves for each visible lap across sessions
            for session in self.sessions.values():
                for lap in session.laps:
                    if not lap.is_visible:
                        continue

                    x_data = lap.get_channel(self.x_axis_channel)
                    y_data = lap.get_channel(channel_name)

                    if x_data is not None and y_data is not None:
                        pen = pg.mkPen(color=lap.color, width=1.5)
                        curve = plot.plot(x_data, y_data, pen=pen, name=f"S:{session.name} L:{lap.lap_number}")
                        self.curve_items[(channel_name, session.id, lap.lap_number)] = curve

    def _on_mouse_moved(self, evt):
        """Updates synchronized vertical crosshairs and status label on mouse hover."""
        if not self.plot_widgets:
            return

        first_plot = list(self.plot_widgets.values())[0]
        mouse_point = first_plot.vb.mapSceneToView(evt)
        x_val = mouse_point.x()

        # Move all vertical crosshairs
        for v_line in self.v_lines:
            v_line.setPos(x_val)

        # Update cursor readout label
        unit = "s" if self.x_axis_channel == STD_CHANNEL_TIME else "m"
        info_text = f"{self.x_axis_channel}: {x_val:.2f} {unit}"
        self.cursor_info_label.setText(info_text)

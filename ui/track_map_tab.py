"""
Track Map tab widget component for sidebar bottom tabs.
Provides UI controls for selecting and rotating track maps with a central canvas area.
"""

import math
from typing import Optional, Dict, Any, List, Tuple
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QSlider, QLabel, QFrame, QPushButton
)
from PySide6.QtCore import Qt, QTimer
import pyqtgraph as pg
import numpy as np

from utils.theme import is_system_dark_theme
from utils.constants import LAP_COLORS
from core.state_manager import StateManager
from core.map_parser import compute_start_line_coords
from ui.graph_icons import create_icon_settings


class TrackMapTabWidget(QWidget):
    """Widget embedded in the sidebar tab containing track map selection and rotation controls."""

    def __init__(self, state_manager: Optional[StateManager] = None, parent=None):
        super().__init__(parent)
        self.state_manager = state_manager or StateManager()

        self._current_map_name: str = ""
        self._raw_x: Optional[np.ndarray] = None
        self._raw_y: Optional[np.ndarray] = None
        self._raw_dist: Optional[np.ndarray] = None
        self._cached_cursor_positions: List[Tuple[float, str]] = []
        self._current_angle_deg: float = 0.0
        self._current_color: str = LAP_COLORS[1]
        self.is_dark: bool = is_system_dark_theme()

        self._rotation_save_timer = QTimer(self)
        self._rotation_save_timer.setSingleShot(True)
        self._rotation_save_timer.setInterval(500)
        self._rotation_save_timer.timeout.connect(self._flush_rotation_save)

        self._init_ui()
        self.refresh_map_list()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # 1. Top Controls Bar: Map selector dropdown & Rotation slider
        controls_layout = QVBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(4)

        # Map dropdown row with Manage Maps button
        map_row = QHBoxLayout()
        map_row.setContentsMargins(0, 0, 0, 0)
        map_row.setSpacing(4)
        map_row.addWidget(QLabel("Map:"))
        self.map_combo = QComboBox()
        self.map_combo.currentTextChanged.connect(self._on_map_selection_changed)
        map_row.addWidget(self.map_combo, 1)

        self.btn_manage_maps = QPushButton()
        self.btn_manage_maps.setToolTip("Manage Track Maps")
        self.btn_manage_maps.setFixedSize(28, 24)
        self.btn_manage_maps.setCursor(Qt.PointingHandCursor)
        self.btn_manage_maps.clicked.connect(self._on_open_map_manager)
        map_row.addWidget(self.btn_manage_maps)
        controls_layout.addLayout(map_row)

        # Rotation slider row
        rot_row = QHBoxLayout()
        rot_row.setContentsMargins(0, 0, 0, 0)
        rot_row.setSpacing(6)
        rot_row.addWidget(QLabel("Rotation:"))

        self.rotation_slider = QSlider(Qt.Horizontal)
        self.rotation_slider.setRange(-180, 180)
        self.rotation_slider.setValue(0)
        self.rotation_slider.setSingleStep(1)
        self.rotation_slider.setPageStep(15)
        rot_row.addWidget(self.rotation_slider, 1)

        self.rotation_value_label = QLabel("0°")
        self.rotation_value_label.setMinimumWidth(36)
        rot_row.addWidget(self.rotation_value_label)

        self.rotation_slider.valueChanged.connect(self._on_rotation_changed)
        controls_layout.addLayout(rot_row)

        layout.addLayout(controls_layout)

        # 2. Track Map Viewport / Plot Canvas
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setContextMenuPolicy(Qt.NoContextMenu)
        self.plot_widget.showAxis("left", False)
        self.plot_widget.showAxis("bottom", False)
        self.plot_widget.setAspectLocked(True)
        self.plot_item = self.plot_widget.getPlotItem()
        self.plot_item.hideButtons()
        self.plot_item.setMenuEnabled(False)
        if hasattr(self.plot_item, "vb") and hasattr(self.plot_item.vb, "setMenuEnabled"):
            self.plot_item.vb.setMenuEnabled(False)
        self.map_curve = self.plot_widget.plot([], [], pen=pg.mkPen(color="#00E676", width=4))
        self.start_line_curve = self.plot_widget.plot([], [], pen=pg.mkPen(color="#FF1744" if self.is_dark else "#D50000", width=4))

        # Tracking dots scatter item for active cursor distance position(s)
        self.tracking_dots_scatter = pg.ScatterPlotItem(size=14, pxMode=True)
        self.plot_widget.addItem(self.tracking_dots_scatter)

        # Placeholder text when no maps are available
        self.placeholder_text_item = pg.TextItem(
            html="<div style='text-align: center; color: #888888; font-size: 9.5pt; font-family: Segoe UI, sans-serif;'>"
                 "No maps available.<br><br>Import maps by clicking on the settings icon above.</div>",
            anchor=(0.5, 0.5)
        )
        self.placeholder_text_item.setPos(0, 0)
        self.placeholder_text_item.setZValue(10)
        self.placeholder_text_item.setVisible(False)
        self.plot_widget.addItem(self.placeholder_text_item)

        # Compatibility aliases
        self.map_canvas = self.plot_widget
        self.placeholder_canvas_label = QLabel("Import maps by clicking on the settings icon above")

        layout.addWidget(self.plot_widget, 1)
        self.apply_theme(self.is_dark)

    def _on_open_map_manager(self):
        """Opens the MapManagerDialog to manage and import track maps."""
        from ui.map_manager_dialog import MapManagerDialog
        dialog = MapManagerDialog(state_manager=self.state_manager, parent=self)
        dialog.exec()
        self.refresh_map_list(select_name=dialog.current_map_name or self._current_map_name)

    def apply_theme(self, is_dark: bool):
        """Updates the map canvas background and track pen color to match the theme."""
        self.is_dark = is_dark
        if hasattr(self, "btn_manage_maps"):
            self.btn_manage_maps.setIcon(create_icon_settings(is_dark))
        bg_color = "#191B1F" if is_dark else "#FFFFFF"
        self.plot_widget.setBackground(bg_color)
        pen_color = self._current_color if self._current_color else ("#00E676" if is_dark else "#00A844")
        self.map_curve.setPen(pg.mkPen(color=pen_color, width=4))
        start_line_color = "#FF1744" if is_dark else "#D50000"
        self.start_line_curve.setPen(pg.mkPen(color=start_line_color, width=4))
        self._update_tracking_dots()

    def refresh_map_list(self, select_name: Optional[str] = None):
        """Reloads available maps from state manager into the map dropdown."""
        self.map_combo.blockSignals(True)
        self.map_combo.clear()

        maps = self.state_manager.load_maps()
        if maps:
            for m in maps:
                name = m.get("name", "")
                self.map_combo.addItem(name, userData=name)
            
            if select_name:
                idx = self.map_combo.findText(select_name)
                if idx >= 0:
                    self.map_combo.setCurrentIndex(idx)
        else:
            self.map_combo.addItem("-- No Maps Available --", userData=None)

        self.map_combo.blockSignals(False)

        current_text = self.map_combo.currentText()
        if current_text and current_text != "-- No Maps Available --":
            self.placeholder_text_item.setVisible(False)
            self._load_and_render_map(current_text)
        else:
            self._raw_x = None
            self._raw_y = None
            self._raw_dist = None
            self.map_curve.setData([], [])
            self.start_line_curve.setData([], [])
            self.tracking_dots_scatter.setData([])
            self.placeholder_text_item.setVisible(True)
            self.plot_widget.setXRange(-10, 10, padding=0)
            self.plot_widget.setYRange(-10, 10, padding=0)

    def get_selected_map(self) -> Optional[str]:
        """Returns the currently selected track map name, or None."""
        txt = self.map_combo.currentText()
        if txt and txt != "-- No Maps Available --":
            return txt
        return None

    def set_selected_map(self, map_name: Optional[str]):
        """Selects the given track map name if it exists in the dropdown."""
        if not map_name:
            return
        idx = self.map_combo.findText(map_name)
        if idx >= 0:
            self.map_combo.setCurrentIndex(idx)

    def _on_map_selection_changed(self, map_name: str):
        """Loads and displays track map geometry when selected from dropdown."""
        if self._rotation_save_timer.isActive():
            self._rotation_save_timer.stop()
            self._flush_rotation_save()

        if not map_name or map_name == "-- No Maps Available --":
            self._current_map_name = ""
            self._raw_x = None
            self._raw_y = None
            self._raw_dist = None
            self.map_curve.setData([], [])
            self.start_line_curve.setData([], [])
            self.tracking_dots_scatter.setData([])
            self.placeholder_text_item.setVisible(True)
            self.plot_widget.setXRange(-10, 10, padding=0)
            self.plot_widget.setYRange(-10, 10, padding=0)
            return

        self._load_and_render_map(map_name)

    def _load_and_render_map(self, map_name: str):
        """Loads coordinates, saved rotation, color, and distance for the given map name and renders."""
        self.placeholder_text_item.setVisible(False)
        self._current_map_name = map_name
        map_data = self.state_manager.get_map(map_name)
        if map_data and "x" in map_data and "y" in map_data:
            self._raw_x = np.asarray(map_data["x"], dtype=np.float64)
            self._raw_y = np.asarray(map_data["y"], dtype=np.float64)
            dist_data = map_data.get("distance")
            if dist_data is not None and len(dist_data) == len(self._raw_x):
                self._raw_dist = np.asarray(dist_data, dtype=np.float64)
            else:
                # Calculate cumulative Euclidean path distance if explicit distance column is missing
                diffs = np.sqrt(np.diff(self._raw_x, prepend=self._raw_x[0])**2 + np.diff(self._raw_y, prepend=self._raw_y[0])**2)
                self._raw_dist = np.cumsum(diffs)

            rot = float(map_data.get("rotation", 0.0))
            self._current_angle_deg = rot
            self.rotation_slider.blockSignals(True)
            self.rotation_slider.setValue(int(round(rot)))
            self.rotation_value_label.setText(f"{int(round(rot))}°")
            self.rotation_slider.blockSignals(False)

            self._current_color = map_data.get("color", LAP_COLORS[1])
            self.map_curve.setPen(pg.mkPen(color=self._current_color, width=4))
        else:
            self._raw_x = None
            self._raw_y = None
            self._raw_dist = None

        self._apply_rotation_and_render()

    def set_cursor_positions(self, points: List[Tuple[float, str]]):
        """Receives active cursor positions as (distance, color) tuples and updates tracking dots."""
        self._cached_cursor_positions = points or []
        self._update_tracking_dots()

    def _update_tracking_dots(self):
        """Positions and renders tracking dots on the rotated track map canvas."""
        if not self._cached_cursor_positions or self._raw_x is None or self._raw_y is None or self._raw_dist is None or len(self._raw_x) == 0:
            self.tracking_dots_scatter.setData([])
            return

        rad = math.radians(self._current_angle_deg)
        cos_theta = math.cos(rad)
        sin_theta = math.sin(rad)

        cx = float(np.mean(self._raw_x))
        cy = float(np.mean(self._raw_y))

        dist_min = float(self._raw_dist.min())
        dist_max = float(self._raw_dist.max())
        dist_span = dist_max - dist_min

        spots = []
        border_color = "#FFFFFF" if self.is_dark else "#000000"

        for dist_val, hex_color in self._cached_cursor_positions:
            if dist_span <= 0:
                target_d = dist_min
            else:
                if dist_val < dist_min:
                    target_d = dist_min
                elif dist_val > dist_max:
                    target_d = dist_min + ((dist_val - dist_min) % dist_span)
                else:
                    target_d = dist_val

            # Interpolate coordinates along the polyline path
            interp_x = float(np.interp(target_d, self._raw_dist, self._raw_x))
            interp_y = float(np.interp(target_d, self._raw_dist, self._raw_y))

            # Apply rotation around centroid
            dx = interp_x - cx
            dy = interp_y - cy
            rot_x = (dx * cos_theta) - (dy * sin_theta) + cx
            rot_y = (dx * sin_theta) + (dy * cos_theta) + cy

            spots.append({
                "pos": (rot_x, rot_y),
                "size": 14,
                "brush": pg.mkBrush(hex_color),
                "pen": pg.mkPen(color=border_color, width=2)
            })

        self.tracking_dots_scatter.setData(spots)

    def _on_rotation_changed(self, val: int):
        """Updates rotation angle, renders transformed coordinates, and starts debounce save timer."""
        self._current_angle_deg = float(val)
        self.rotation_value_label.setText(f"{val}°")
        self._apply_rotation_and_render()

        if self._current_map_name and self._current_map_name != "-- No Maps Available --":
            self._rotation_save_timer.start()

    def _flush_rotation_save(self):
        """Persists rotation angle to disk after debounce delay."""
        if self._current_map_name and self._current_map_name != "-- No Maps Available --":
            self.state_manager.save_map_rotation(self._current_map_name, self._current_angle_deg)

    def _apply_rotation_and_render(self):
        """Rotates raw coordinates around their centroid and updates the plot curve and start line."""
        if self._raw_x is None or self._raw_y is None or len(self._raw_x) == 0:
            self.map_curve.setData([], [])
            self.start_line_curve.setData([], [])
            self.tracking_dots_scatter.setData([])
            return

        rad = math.radians(self._current_angle_deg)
        cos_theta = math.cos(rad)
        sin_theta = math.sin(rad)

        cx = float(np.mean(self._raw_x))
        cy = float(np.mean(self._raw_y))

        dx = self._raw_x - cx
        dy = self._raw_y - cy

        x_rot = (dx * cos_theta) - (dy * sin_theta) + cx
        y_rot = (dx * sin_theta) + (dy * cos_theta) + cy

        self.map_curve.setData(x_rot, y_rot)
        sl_x, sl_y = compute_start_line_coords(self._raw_x, self._raw_y, self._current_angle_deg)
        self.start_line_curve.setData(sl_x, sl_y)
        self._update_tracking_dots()
        self.plot_widget.autoRange()

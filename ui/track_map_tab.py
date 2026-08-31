"""
Track Map tab widget component for sidebar bottom tabs.
Provides UI controls for selecting and rotating track maps with a central canvas area.
"""

import math
from typing import Optional, Dict, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QSlider, QLabel, QFrame
)
from PySide6.QtCore import Qt
import pyqtgraph as pg
import numpy as np

from utils.theme import is_system_dark_theme
from utils.constants import LAP_COLORS
from core.state_manager import StateManager


class TrackMapTabWidget(QWidget):
    """Widget embedded in the sidebar tab containing track map selection and rotation controls."""

    def __init__(self, state_manager: Optional[StateManager] = None, parent=None):
        super().__init__(parent)
        self.state_manager = state_manager or StateManager()

        self._raw_x: Optional[np.ndarray] = None
        self._raw_y: Optional[np.ndarray] = None
        self._current_angle_deg: float = 0.0
        self._current_color: str = LAP_COLORS[1]
        self.is_dark: bool = is_system_dark_theme()

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

        # Map dropdown row
        map_row = QHBoxLayout()
        map_row.setContentsMargins(0, 0, 0, 0)
        map_row.setSpacing(6)
        map_row.addWidget(QLabel("Map:"))
        self.map_combo = QComboBox()
        self.map_combo.currentTextChanged.connect(self._on_map_selection_changed)
        map_row.addWidget(self.map_combo, 1)
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

        # Compatibility aliases
        self.map_canvas = self.plot_widget
        self.placeholder_canvas_label = QLabel()

        layout.addWidget(self.plot_widget, 1)
        self.apply_theme(self.is_dark)

    def apply_theme(self, is_dark: bool):
        """Updates the map canvas background and track pen color to match the theme."""
        self.is_dark = is_dark
        bg_color = "#191B1F" if is_dark else "#FFFFFF"
        self.plot_widget.setBackground(bg_color)
        pen_color = self._current_color if self._current_color else ("#00E676" if is_dark else "#00A844")
        self.map_curve.setPen(pg.mkPen(color=pen_color, width=4))

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
            self._load_and_render_map(current_text)
        else:
            self._raw_x = None
            self._raw_y = None
            self.map_curve.setData([], [])

    def _on_map_selection_changed(self, map_name: str):
        """Loads and displays track map geometry when selected from dropdown."""
        if not map_name or map_name == "-- No Maps Available --":
            self._raw_x = None
            self._raw_y = None
            self.map_curve.setData([], [])
            return

        self._load_and_render_map(map_name)

    def _load_and_render_map(self, map_name: str):
        """Loads coordinates, saved rotation, and color for the given map name and renders."""
        map_data = self.state_manager.get_map(map_name)
        if map_data and "x" in map_data and "y" in map_data:
            self._raw_x = np.asarray(map_data["x"], dtype=np.float64)
            self._raw_y = np.asarray(map_data["y"], dtype=np.float64)
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

        self._apply_rotation_and_render()

    def _on_rotation_changed(self, val: int):
        """Updates rotation angle, saves it for the current map, and re-renders."""
        self._current_angle_deg = float(val)
        self.rotation_value_label.setText(f"{val}°")
        self._apply_rotation_and_render()

        current_map = self.map_combo.currentText()
        if current_map and current_map != "-- No Maps Available --":
            self.state_manager.save_map_rotation(current_map, float(val))

    def _apply_rotation_and_render(self):
        """Rotates raw coordinates around their centroid and updates the plot curve."""
        if self._raw_x is None or self._raw_y is None or len(self._raw_x) == 0:
            self.map_curve.setData([], [])
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
        self.plot_widget.autoRange()

"""
Dialog for managing and editing track maps.
Supports importing maps from .xlsx and .mat files with column mapping,
viewing 2D track geometries, renaming, and deleting maps.
"""

import math
import os
from typing import Optional, Dict, Any
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QLineEdit, QSplitter, QAbstractItemView, QWidget,
    QFileDialog, QMessageBox, QSlider
)
from PySide6.QtCore import Qt
import pyqtgraph as pg
import numpy as np

from core.state_manager import StateManager
from core.map_parser import get_map_file_columns, load_map_file_data, compute_start_line_coords
from ui.import_map_dialog import ImportMapDialog
from ui.color_picker_popup import LapColorPickerPopup
from utils.constants import LAP_COLORS
from utils.theme import is_system_dark_theme


class MapManagerDialog(QDialog):
    """Dialog for managing track maps with a master list on the left and detail preview on the right."""

    def __init__(self, state_manager: Optional[StateManager] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Maps")
        self.setMinimumSize(780, 520)
        self.state_manager = state_manager or StateManager()
        self.current_map_name: str = ""
        self.is_dark: bool = is_system_dark_theme()
        self._raw_x: Optional[np.ndarray] = None
        self._raw_y: Optional[np.ndarray] = None
        self._current_angle_deg: float = 0.0
        self._current_color: str = LAP_COLORS[1]
        self._init_ui()
        self._load_map_list()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        splitter = QSplitter(Qt.Horizontal)

        # Left Panel: Map List & Add / Remove Buttons
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 5, 0)
        left_layout.setSpacing(6)

        left_layout.addWidget(QLabel("<b>Available Maps:</b>"))
        self.map_list = QListWidget()
        self.map_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.map_list.currentItemChanged.connect(self._on_map_selection_changed)
        left_layout.addWidget(self.map_list)

        # Buttons below map list: Add & Remove
        list_btn_layout = QHBoxLayout()
        list_btn_layout.setContentsMargins(0, 0, 0, 0)
        list_btn_layout.setSpacing(6)

        self.add_btn = QPushButton("Add")
        self.add_btn.clicked.connect(self._on_add_map)
        list_btn_layout.addWidget(self.add_btn)

        self.remove_btn = QPushButton("Remove")
        self.remove_btn.setStyleSheet("color: #FF5252;")
        self.remove_btn.clicked.connect(self._on_remove_map)
        list_btn_layout.addWidget(self.remove_btn)

        left_layout.addLayout(list_btn_layout)
        splitter.addWidget(left_widget)

        # Right Panel: Map Name & Map Canvas
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 0, 0, 0)
        right_layout.setSpacing(6)

        # Map Name Field
        name_layout = QHBoxLayout()
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_layout.setSpacing(6)
        name_layout.addWidget(QLabel("<b>Map Name:</b>"))
        self.map_name_input = QLineEdit()
        name_layout.addWidget(self.map_name_input)
        right_layout.addLayout(name_layout)

        # Rotation Slider & Track Color Row
        rot_color_layout = QHBoxLayout()
        rot_color_layout.setContentsMargins(0, 0, 0, 0)
        rot_color_layout.setSpacing(8)
        rot_color_layout.addWidget(QLabel("<b>Rotation:</b>"))

        self.rotation_slider = QSlider(Qt.Horizontal)
        self.rotation_slider.setRange(-180, 180)
        self.rotation_slider.setValue(0)
        self.rotation_slider.setSingleStep(1)
        self.rotation_slider.setPageStep(15)
        rot_color_layout.addWidget(self.rotation_slider, 1)

        self.rotation_value_label = QLabel("0°")
        self.rotation_value_label.setMinimumWidth(36)
        rot_color_layout.addWidget(self.rotation_value_label)

        rot_color_layout.addSpacing(8)
        rot_color_layout.addWidget(QLabel("<b>Color:</b>"))

        self.color_btn = QPushButton()
        self.color_btn.setFixedSize(36, 24)
        self.color_btn.setCursor(Qt.PointingHandCursor)
        self.color_btn.clicked.connect(self._on_open_color_picker)
        rot_color_layout.addWidget(self.color_btn)

        self.rotation_slider.valueChanged.connect(self._on_rotation_changed)
        right_layout.addLayout(rot_color_layout)

        # Map Display / Preview Canvas using PyQtGraph
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
        self.map_curve = self.plot_widget.plot([], [], pen=pg.mkPen(color=self._current_color, width=4))
        self.start_line_curve = self.plot_widget.plot([], [], pen=pg.mkPen(color="#FF1744" if self.is_dark else "#D50000", width=4))
        self.map_canvas = self.plot_widget  # Backwards compatibility alias

        right_layout.addWidget(self.plot_widget, 1)

        # Right bottom action row: Save Button
        save_btn_layout = QHBoxLayout()
        save_btn_layout.setContentsMargins(0, 0, 0, 0)
        save_btn_layout.addStretch()

        self.save_btn = QPushButton("Save")
        self.save_btn.setStyleSheet("background-color: #00E676; color: black; font-weight: bold;")
        self.save_btn.clicked.connect(self._on_save_map)
        save_btn_layout.addWidget(self.save_btn)
        right_layout.addLayout(save_btn_layout)

        splitter.addWidget(right_widget)
        splitter.setSizes([240, 540])
        layout.addWidget(splitter, 1)

        self.apply_theme(self.is_dark)

    def apply_theme(self, is_dark: bool):
        """Updates the map canvas background and track pen color to match the theme."""
        self.is_dark = is_dark
        bg_color = "#191B1F" if is_dark else "#FFFFFF"
        self.plot_widget.setBackground(bg_color)
        pen_color = self._current_color if self._current_color else ("#00E676" if is_dark else "#00A844")
        self.map_curve.setPen(pg.mkPen(color=pen_color, width=4))
        start_line_color = "#FF1744" if is_dark else "#D50000"
        self.start_line_curve.setPen(pg.mkPen(color=start_line_color, width=4))
        self._update_color_button()

    def _update_color_button(self):
        """Updates the color button swatch to reflect the current map color."""
        color = self._current_color or LAP_COLORS[1]
        border_color = "#FFFFFF" if self.is_dark else "#333333"
        self.color_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                border: 2px solid {border_color};
                border-radius: 4px;
            }}
            QPushButton:hover {{
                border: 2px solid {"#00E676" if self.is_dark else "#00C853"};
            }}
        """)
        self.color_btn.setToolTip(f"Track Color: {color}")

    def _on_open_color_picker(self):
        """Opens the color picker popup anchored below the color button."""
        popup = LapColorPickerPopup(
            current_color=self._current_color,
            parent=self,
            is_dark=self.is_dark
        )
        popup.color_selected.connect(self._on_color_selected)
        btn_pos = self.color_btn.mapToGlobal(self.color_btn.rect().bottomLeft())
        popup.move(btn_pos)
        popup.show()

    def _on_color_selected(self, hex_color: str):
        """Handles color selection from the palette popup."""
        self._current_color = hex_color
        self._update_color_button()
        self.map_curve.setPen(pg.mkPen(color=self._current_color, width=4))

    def _load_map_list(self, select_name: Optional[str] = None):
        """Populates the map list with saved maps from the maps directory."""
        self.map_list.blockSignals(True)
        self.map_list.clear()

        saved_maps = self.state_manager.load_maps()
        target_row = 0

        for idx, m in enumerate(saved_maps):
            name = m.get("name", "")
            item = QListWidgetItem(name)
            self.map_list.addItem(item)
            if select_name and name.lower() == select_name.lower():
                target_row = idx

        self.map_list.blockSignals(False)

        if self.map_list.count() > 0:
            self.map_list.setCurrentRow(target_row)
            self._render_selected_map(self.map_list.item(target_row).text())
        else:
            self.current_map_name = ""
            self.map_name_input.clear()
            self._raw_x = None
            self._raw_y = None
            self.map_curve.setData([], [])

    def _on_rotation_changed(self, val: int):
        """Updates preview rotation angle and re-renders transformed coordinates."""
        self._current_angle_deg = float(val)
        self.rotation_value_label.setText(f"{val}°")
        self._apply_rotation_and_render()

    def _apply_rotation_and_render(self):
        """Rotates raw coordinates around their centroid and updates the plot curve and start line."""
        if self._raw_x is None or self._raw_y is None or len(self._raw_x) == 0:
            self.map_curve.setData([], [])
            self.start_line_curve.setData([], [])
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
        self.plot_widget.autoRange()

    def _render_selected_map(self, map_name: str):
        """Renders the 2D track map geometry on the preview canvas with its saved rotation and color."""
        self.current_map_name = map_name
        self.map_name_input.setText(map_name)

        map_data = self.state_manager.get_map(map_name)
        if map_data is not None and "x" in map_data and "y" in map_data:
            self._raw_x = np.asarray(map_data["x"], dtype=np.float64)
            self._raw_y = np.asarray(map_data["y"], dtype=np.float64)
            rot = float(map_data.get("rotation", 0.0))
            self._current_angle_deg = rot
            self.rotation_slider.blockSignals(True)
            self.rotation_slider.setValue(int(round(rot)))
            self.rotation_value_label.setText(f"{int(round(rot))}°")
            self.rotation_slider.blockSignals(False)

            self._current_color = map_data.get("color", LAP_COLORS[1])
            self._update_color_button()
            self.map_curve.setPen(pg.mkPen(color=self._current_color, width=4))

            self._apply_rotation_and_render()
        else:
            self._raw_x = None
            self._raw_y = None
            self._current_color = LAP_COLORS[1]
            self._update_color_button()
            self.map_curve.setData([], [])
            self.start_line_curve.setData([], [])

    def _on_map_selection_changed(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem] = None):
        """Updates the name input and preview when a map item is selected."""
        if current:
            self._render_selected_map(current.text())
        else:
            self.current_map_name = ""
            self.map_name_input.clear()
            self._raw_x = None
            self._raw_y = None
            self._current_color = LAP_COLORS[1]
            self._update_color_button()
            self.map_curve.setData([], [])
            self.start_line_curve.setData([], [])

    def _on_add_map(self):
        """Prompts user to select an .xlsx or .csv track file and import it."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Track Map File",
            "",
            "Track Map Files (*.xlsx *.xls *.csv);;Excel Files (*.xlsx *.xls);;CSV Files (*.csv);;All Files (*)"
        )
        if not file_path:
            return

        try:
            columns = get_map_file_columns(file_path)
            if not columns:
                QMessageBox.warning(self, "No Columns Found", "Could not find any data columns or variables in the selected file.")
                return
        except Exception as e:
            QMessageBox.critical(self, "File Read Error", f"Failed to read file:\n{str(e)}")
            return

        dialog = ImportMapDialog(file_path, columns, parent=self)
        if dialog.exec() == QDialog.Accepted:
            try:
                x_arr, y_arr, dist_arr = load_map_file_data(
                    file_path,
                    dialog.selected_x_col,
                    dialog.selected_y_col,
                    dialog.selected_dist_col
                )
                self.state_manager.save_map(
                    name=dialog.selected_map_name,
                    x=x_arr,
                    y=y_arr,
                    distance=dist_arr,
                    color=LAP_COLORS[1]
                )
                self._load_map_list(select_name=dialog.selected_map_name)
            except Exception as e:
                QMessageBox.critical(self, "Import Error", f"Failed to import track map data:\n{str(e)}")

    def _on_remove_map(self):
        """Deletes the currently selected track map."""
        if not self.current_map_name:
            return

        reply = QMessageBox.question(
            self,
            "Delete Track Map",
            f"Are you sure you want to delete track map '{self.current_map_name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.state_manager.delete_map(self.current_map_name)
            self._load_map_list()

    def _on_save_map(self):
        """Saves name, rotation, and color modifications to the current track map."""
        if not self.current_map_name:
            return

        new_name = self.map_name_input.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Invalid Name", "Map name cannot be empty.")
            return

        map_data = self.state_manager.get_map(self.current_map_name)
        if map_data:
            self.state_manager.save_map(
                name=new_name,
                x=map_data["x"],
                y=map_data["y"],
                distance=map_data.get("distance"),
                rotation=self._current_angle_deg,
                color=self._current_color,
                old_name=self.current_map_name
            )
            self._load_map_list(select_name=new_name)

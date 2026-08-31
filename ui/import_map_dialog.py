"""
Dialog for importing a track map from an .xlsx or .mat file and mapping X, Y, and Distance columns.
"""

import os
import re
from typing import List, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox,
    QLineEdit, QPushButton, QLabel, QMessageBox, QGroupBox
)
from PySide6.QtCore import Qt


class ImportMapDialog(QDialog):
    """Modal dialog to configure track map name and select X, Y, and Distance columns from an imported file."""

    def __init__(self, file_path: str, columns: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Track Map")
        self.setMinimumWidth(440)
        self.file_path = file_path
        self.columns = list(columns)

        self.selected_map_name: str = ""
        self.selected_x_col: str = ""
        self.selected_y_col: str = ""
        self.selected_dist_col: Optional[str] = None

        self._init_ui()
        self._auto_detect_columns()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # File info banner
        filename = os.path.basename(self.file_path)
        info_label = QLabel(f"<b>Source File:</b> {filename}")
        info_label.setStyleSheet("color: #AAAAAA;")
        layout.addWidget(info_label)

        # Form group
        group = QGroupBox("Map Configuration")
        form = QFormLayout(group)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(10)

        # Map Name
        default_name = os.path.splitext(filename)[0].replace("_", " ").title()
        self.map_name_input = QLineEdit(default_name)
        self.map_name_input.setPlaceholderText("e.g. Hungaroring, Track 1")
        form.addRow("<b>Map Name:</b>", self.map_name_input)

        # X Column ComboBox
        self.x_combo = QComboBox()
        self.x_combo.addItems(self.columns)
        form.addRow("<b>X Column:</b>", self.x_combo)

        # Y Column ComboBox
        self.y_combo = QComboBox()
        self.y_combo.addItems(self.columns)
        form.addRow("<b>Y Column:</b>", self.y_combo)

        # Distance Column ComboBox (Optional)
        self.dist_combo = QComboBox()
        self.dist_combo.addItem("-- None / Skip --", userData=None)
        for col in self.columns:
            self.dist_combo.addItem(col, userData=col)
        form.addRow("<b>Distance Column:</b>", self.dist_combo)

        layout.addWidget(group)

        # Dialog Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(8)
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        import_btn = QPushButton("Import Map")
        import_btn.setStyleSheet("background-color: #00E676; color: black; font-weight: bold;")
        import_btn.clicked.connect(self._on_import_clicked)
        btn_layout.addWidget(import_btn)

        layout.addLayout(btn_layout)

    def _auto_detect_columns(self):
        """Auto-detects best matches for X, Y, and Distance based on column names."""
        x_patterns = [r"^x$", r"pos_?x", r"coord_?x", r"east", r"longitude", r"^x_m$"]
        y_patterns = [r"^y$", r"pos_?y", r"coord_?y", r"north", r"latitude", r"^y_m$"]
        dist_patterns = [r"dist", r"distance", r"lap_?dist", r"^s$", r"meter"]

        # Detect X
        for idx, col in enumerate(self.columns):
            cl = col.lower().strip()
            if any(re.search(p, cl) for p in x_patterns):
                self.x_combo.setCurrentIndex(idx)
                break

        # Detect Y
        for idx, col in enumerate(self.columns):
            cl = col.lower().strip()
            if any(re.search(p, cl) for p in y_patterns):
                self.y_combo.setCurrentIndex(idx)
                break
        # Detect Distance
        for idx, col in enumerate(self.columns):
            cl = col.lower().strip()
            if any(re.search(p, cl) for p in dist_patterns):
                # Account for index 0 being "-- None / Skip --"
                self.dist_combo.setCurrentIndex(idx + 1)
                break

        # Fallback for generic / headerless columns
        if len(self.columns) > 1 and self.y_combo.currentIndex() == self.x_combo.currentIndex():
            self.y_combo.setCurrentIndex(1)
        if self.dist_combo.currentIndex() == 0 and len(self.columns) >= 3:
            if self.columns[0].lower().startswith("column") or self.columns[0].lower().startswith("col"):
                self.dist_combo.setCurrentIndex(3)

    def _on_import_clicked(self):
        """Validates inputs and accepts dialog."""
        map_name = self.map_name_input.text().strip()
        if not map_name:
            QMessageBox.warning(self, "Invalid Name", "Please enter a name for the map.")
            self.map_name_input.setFocus()
            return

        x_col = self.x_combo.currentText()
        y_col = self.y_combo.currentText()

        if not x_col or not y_col:
            QMessageBox.warning(self, "Incomplete Selection", "Please select both X and Y columns.")
            return

        self.selected_map_name = map_name
        self.selected_x_col = x_col
        self.selected_y_col = y_col
        self.selected_dist_col = self.dist_combo.currentData()

        self.accept()

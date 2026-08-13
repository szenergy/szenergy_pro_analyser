"""
Dialog wizard for mapping raw log file channels to standard internal channel names and saving presets.
"""

from typing import Dict, List, Optional
import pandas as pd
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QComboBox, QPushButton, QLabel, QLineEdit, QMessageBox, QHeaderView
)
from PySide6.QtCore import Qt

from core.state_manager import StateManager
from utils.constants import STD_CHANNEL_LAP, STD_CHANNEL_TIME, STD_CHANNEL_DISTANCE


SUGGESTED_TARGETS = [
    "-- Skip --",
    STD_CHANNEL_LAP,
    STD_CHANNEL_TIME,
    STD_CHANNEL_DISTANCE,
    "Speed",
    "RPM",
    "Current",
    "Voltage",
    "Power",
    "Energy",
    "Throttle",
    "SteeringAngle",
    "Temperature",
    "GPS_Lat",
    "GPS_Lon"
]


class ImportWizardDialog(QDialog):
    """Wizard dialog for mapping raw channels to internal standard names."""

    def __init__(self, file_path: str, raw_columns: List[str], preview_df: pd.DataFrame,
                 state_manager: StateManager, initial_preset: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Import Log Wizard - {file_path}")
        self.setMinimumSize(700, 500)

        self.file_path = file_path
        self.raw_columns = raw_columns
        self.preview_df = preview_df
        self.state_manager = state_manager
        self.result_mapping: Dict[str, str] = {}

        self._init_ui(initial_preset)

    def _init_ui(self, initial_preset: Optional[str]):
        layout = QVBoxLayout(self)

        # Header instructions
        instruction = QLabel(
            "<b>Map channels for import:</b><br>"
            "Assign raw channels to standard internal names. "
            "<b>Must map at least 'Lap' and 'Time' or 'Distance'.</b>"
        )
        instruction.setTextFormat(Qt.RichText)
        layout.addWidget(instruction)

        # Mapping Table
        self.table = QTableWidget(len(self.raw_columns), 3)
        self.table.setHorizontalHeaderLabels(["Raw Channel (File)", "Mapped Channel Name", "Preview Data"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)

        # Load existing preset if provided
        presets = self.state_manager.load_presets()
        preset_map = presets.get(initial_preset, {}) if initial_preset else {}

        self.combos: Dict[str, QComboBox] = {}

        for row, raw_col in enumerate(self.raw_columns):
            # Raw name item
            raw_item = QTableWidgetItem(raw_col)
            raw_item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 0, raw_item)

            # Editable combo box for mapped channel
            combo = QComboBox()
            combo.setEditable(True)
            combo.addItems(SUGGESTED_TARGETS)

            # Try auto-matching or using preset
            mapped_val = preset_map.get(raw_col)
            if not mapped_val:
                mapped_val = self._auto_guess_mapping(raw_col)

            if mapped_val:
                idx = combo.findText(mapped_val)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                else:
                    combo.setEditText(mapped_val)
            else:
                combo.setCurrentIndex(0)  # Default to Skip

            self.combos[raw_col] = combo
            self.table.setCellWidget(row, 1, combo)

            # Preview string
            preview_str = ""
            if raw_col in self.preview_df.columns:
                vals = self.preview_df[raw_col].dropna().tolist()[:4]
                preview_str = ", ".join(str(v) for v in vals)
            prev_item = QTableWidgetItem(preview_str)
            prev_item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 2, prev_item)

        layout.addWidget(self.table)

        # Save Preset Row
        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("Save as Preset Name:"))
        self.preset_input = QLineEdit()
        if initial_preset:
            self.preset_input.setText(initial_preset)
        preset_layout.addWidget(self.preset_input)

        self.save_preset_btn = QPushButton("Save Preset")
        self.save_preset_btn.clicked.connect(self._on_save_preset)
        preset_layout.addWidget(self.save_preset_btn)
        layout.addLayout(preset_layout)

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.import_btn = QPushButton("Import Data")
        self.import_btn.setStyleSheet("font-weight: bold; background-color: #00E676; color: black;")
        self.import_btn.clicked.connect(self._on_import)
        btn_layout.addWidget(self.import_btn)

        layout.addLayout(btn_layout)

    def _auto_guess_mapping(self, raw_col: str) -> Optional[str]:
        """Guesses mapping based on common column name substrings."""
        name = raw_col.lower().replace("_", "").replace(" ", "")
        if "lap" in name:
            return STD_CHANNEL_LAP
        elif "time" in name or name == "t":
            return STD_CHANNEL_TIME
        elif "dist" in name or name == "d" or "pos" in name:
            return STD_CHANNEL_DISTANCE
        elif "speed" in name or "velocity" in name or "spd" in name:
            return "Speed"
        elif "rpm" in name:
            return "RPM"
        return None

    def _get_current_mapping(self) -> Dict[str, str]:
        mapping = {}
        for raw_col, combo in self.combos.items():
            text = combo.currentText().strip()
            if text and text != "-- Skip --":
                mapping[raw_col] = text
        return mapping

    def _on_save_preset(self):
        preset_name = self.preset_input.text().strip()
        if not preset_name:
            QMessageBox.warning(self, "Warning", "Please enter a preset name.")
            return
        mapping = self._get_current_mapping()
        if not mapping:
            QMessageBox.warning(self, "Warning", "No mapped channels to save in preset.")
            return

        self.state_manager.save_preset(preset_name, mapping)
        QMessageBox.information(self, "Preset Saved", f"Preset '{preset_name}' saved successfully!")

    def _on_import(self):
        mapping = self._get_current_mapping()
        mapped_targets = list(mapping.values())

        if STD_CHANNEL_LAP not in mapped_targets:
            QMessageBox.critical(self, "Validation Error", f"You must map at least one channel to '{STD_CHANNEL_LAP}'.")
            return

        if STD_CHANNEL_TIME not in mapped_targets and STD_CHANNEL_DISTANCE not in mapped_targets:
            QMessageBox.critical(
                self, "Validation Error",
                f"You must map an X-Axis channel (either '{STD_CHANNEL_TIME}' or '{STD_CHANNEL_DISTANCE}')."
            )
            return

        self.result_mapping = mapping
        self.accept()

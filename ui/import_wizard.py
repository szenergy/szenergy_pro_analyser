"""
Dialog wizard for mapping raw log file channels to standard internal channel names and saving presets.
Also includes PresetPreviewDialog for inspecting detected presets before importing.
"""

from typing import Dict, List, Optional, Set
import pandas as pd
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QComboBox, QPushButton, QLabel, QLineEdit, QMessageBox, QHeaderView,
    QAbstractItemView
)
from PySide6.QtCore import Qt

from core.state_manager import StateManager
from utils.constants import STD_CHANNEL_LAP, STD_CHANNEL_TIME, STD_CHANNEL_DISTANCE


class PresetPreviewDialog(QDialog):
    """Preview dialog showing how a detected preset maps channels before applying."""

    ACTION_APPLY = 1
    ACTION_EDIT = 2

    def __init__(self, file_path: str, preset_name: str, mapping: Dict[str, str],
                 preview_df: pd.DataFrame, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Preset Detected - {preset_name}")
        self.setMinimumSize(600, 400)
        self.selected_action = QDialog.Rejected

        self.file_path = file_path
        self.preset_name = preset_name
        self.mapping = mapping
        self.preview_df = preview_df

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        instruction = QLabel(
            f"<b>Preset '{self.preset_name}' matched file:</b><br>"
            f"<i>{self.file_path}</i><br><br>"
            "Review channel mappings below:"
        )
        instruction.setTextFormat(Qt.RichText)
        layout.addWidget(instruction)

        # Mapping Table
        table = QTableWidget(len(self.mapping), 3)
        table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        table.setHorizontalHeaderLabels(["Raw Channel (File)", "Mapped Channel Name", "Preview Data"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)

        for row, (raw_col, mapped_col) in enumerate(self.mapping.items()):
            table.setItem(row, 0, QTableWidgetItem(raw_col))
            table.setItem(row, 1, QTableWidgetItem(mapped_col))

            preview_str = ""
            if raw_col in self.preview_df.columns:
                vals = self.preview_df[raw_col].dropna().tolist()[:4]
                preview_str = ", ".join(str(v) for v in vals)
            table.setItem(row, 2, QTableWidgetItem(preview_str))

        layout.addWidget(table)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        edit_btn = QPushButton("Edit Mapping in Wizard")
        edit_btn.clicked.connect(self._on_edit)
        btn_layout.addWidget(edit_btn)

        apply_btn = QPushButton("Apply Preset & Import")
        apply_btn.setStyleSheet("font-weight: bold; background-color: #00E676; color: black;")
        apply_btn.clicked.connect(self._on_apply)
        btn_layout.addWidget(apply_btn)

        layout.addLayout(btn_layout)

    def _on_apply(self):
        self.selected_action = self.ACTION_APPLY
        self.accept()

    def _on_edit(self):
        self.selected_action = self.ACTION_EDIT
        self.done(self.ACTION_EDIT)


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

        self.suggested_targets = ["-- Skip --"] + self.state_manager.get_channel_labels()
        self._init_ui(initial_preset)

    def _init_ui(self, initial_preset: Optional[str]):
        layout = QVBoxLayout(self)

        instruction = QLabel(
            "<b>Map channels for import:</b><br>"
            "Assign raw channels to standard internal names. "
            "<b>Must map 'Lap' and 'Time' or 'Distance'. Duplicate channel assignments are not allowed.</b>"
        )
        instruction.setTextFormat(Qt.RichText)
        layout.addWidget(instruction)

        # Mapping Table
        self.table = QTableWidget(len(self.raw_columns), 3)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalHeaderLabels(["Raw Channel (File)", "Mapped Channel Name", "Preview Data"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)

        presets = self.state_manager.load_presets()
        preset_map = presets.get(initial_preset, {}) if initial_preset else {}

        self.combos: Dict[str, QComboBox] = {}
        suggested_used: Set[str] = set()

        for row, raw_col in enumerate(self.raw_columns):
            raw_item = QTableWidgetItem(raw_col)
            raw_item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 0, raw_item)

            combo = QComboBox()
            combo.setEditable(True)
            combo.addItems(self.suggested_targets)

            mapped_val = preset_map.get(raw_col)
            if not mapped_val:
                mapped_val = self._auto_guess_mapping(raw_col, suggested_used)

            if mapped_val:
                suggested_used.add(mapped_val)
                idx = combo.findText(mapped_val)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                else:
                    combo.setEditText(mapped_val)
            else:
                combo.setCurrentIndex(0)

            self.combos[raw_col] = combo
            self.table.setCellWidget(row, 1, combo)

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

    def _auto_guess_mapping(self, raw_col: str, already_used: Set[str]) -> Optional[str]:
        name = raw_col.lower().replace("_", "").replace(" ", "")
        
        candidates = []
        if "lap" in name:
            candidates.append(STD_CHANNEL_LAP)
        if "time" in name or name == "t":
            candidates.append(STD_CHANNEL_TIME)
        if "dist" in name or name == "d" or "pos" in name:
            candidates.append(STD_CHANNEL_DISTANCE)
        if "speed" in name or "velocity" in name or "spd" in name:
            candidates.append("Speed")
        if "rpm" in name:
            candidates.append("RPM")
        if "volt" in name or "v" in name:
            candidates.append("Voltage")
        if "curr" in name or "amp" in name or "a" in name:
            candidates.append("Current")

        for cand in candidates:
            if cand not in already_used and cand in self.suggested_targets:
                return cand
        return None

    def _get_current_mapping(self) -> Dict[str, str]:
        mapping = {}
        for raw_col, combo in self.combos.items():
            text = combo.currentText().strip()
            if text and text != "-- Skip --":
                mapping[raw_col] = text
        return mapping

    def _validate_no_duplicates(self, mapping: Dict[str, str]) -> bool:
        targets = list(mapping.values())
        duplicates = set([t for t in targets if targets.count(t) > 1])
        if duplicates:
            dup_str = ", ".join(duplicates)
            QMessageBox.critical(
                self, "Duplicate Channels Error",
                f"The following channel names are mapped multiple times: {dup_str}.\n"
                "Each target channel name must be unique."
            )
            return False
        return True

    def _on_save_preset(self):
        preset_name = self.preset_input.text().strip()
        if not preset_name:
            QMessageBox.warning(self, "Warning", "Please enter a preset name.")
            return
        mapping = self._get_current_mapping()
        if not mapping:
            QMessageBox.warning(self, "Warning", "No mapped channels to save in preset.")
            return
        if not self._validate_no_duplicates(mapping):
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

        if not self._validate_no_duplicates(mapping):
            return

        self.result_mapping = mapping
        self.accept()

"""
Dialog wizard for mapping raw log file channels to standard internal channel names and saving presets.
Also includes PresetPreviewDialog for inspecting detected presets before importing.
"""

import os
import re
import unicodedata
from typing import Dict, List, Optional, Set
import pandas as pd
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QComboBox, QPushButton, QLabel, QLineEdit, QMessageBox, QHeaderView,
    QAbstractItemView
)
from PySide6.QtCore import Qt

from core.state_manager import StateManager, generate_slug
from utils.constants import SLUG_LAP, SLUG_TIME, SLUG_DISTANCE


class PresetPreviewDialog(QDialog):
    """Preview dialog showing how a detected preset maps channels before applying."""

    ACTION_APPLY = 1
    ACTION_EDIT = 2

    def __init__(self, file_path: str, preset_name: str, mapping: Dict[str, str],
                 raw_columns: Optional[List[str]] = None,
                 state_manager=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preset Matching & Preview")
        self.setMinimumSize(580, 480)
        self.selected_action = QDialog.Rejected

        self.file_path = file_path
        self.preset_name = preset_name
        self.selected_preset_name = preset_name
        self.mapping = mapping
        self.raw_columns = list(raw_columns) if raw_columns is not None else list(mapping.keys())
        self.state_manager = state_manager

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        filename = os.path.basename(self.file_path)
        header_label = QLabel(
            f"<b>Matching telemetry log:</b> <code>{filename}</code>"
        )
        header_label.setTextFormat(Qt.RichText)
        layout.addWidget(header_label)

        # Preset selection row
        preset_select_layout = QHBoxLayout()
        preset_select_layout.addWidget(QLabel("<b>Selected Preset:</b>"))
        self.preset_combo = QComboBox()
        presets = self.state_manager.load_presets() if self.state_manager else {}
        preset_names = sorted(list(presets.keys()))
        if self.preset_name and self.preset_name not in preset_names:
            preset_names.insert(0, self.preset_name)
        self.preset_combo.addItems(preset_names)
        idx = self.preset_combo.findText(self.preset_name)
        if idx >= 0:
            self.preset_combo.setCurrentIndex(idx)
        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)
        preset_select_layout.addWidget(self.preset_combo, stretch=1)
        layout.addLayout(preset_select_layout)

        # Stats summary badge
        self.stats_label = QLabel()
        self.stats_label.setStyleSheet(
            "background-color: rgba(255, 255, 255, 0.06); border: 1px solid rgba(255, 255, 255, 0.12); "
            "border-radius: 4px; padding: 6px 10px; font-weight: bold;"
        )
        layout.addWidget(self.stats_label)

        # Mapping Table (3 Columns: Raw Channel, Mapped Target Name, Status)
        self.table = QTableWidget(0, 3)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalHeaderLabels(["Channel in File / Preset", "Mapped Target Name", "Match Status"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        layout.addWidget(self.table)

        self._refresh_table()

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
        apply_btn.setStyleSheet("background-color: #00E676; color: black; font-weight: bold;")
        apply_btn.clicked.connect(self._on_apply)
        btn_layout.addWidget(apply_btn)

        layout.addLayout(btn_layout)

    def _on_preset_changed(self, new_preset_name: str):
        if not new_preset_name:
            return
        self.selected_preset_name = new_preset_name
        presets = self.state_manager.load_presets() if self.state_manager else {}
        self.mapping = presets.get(new_preset_name, {})
        self._refresh_table()

    def _refresh_table(self):
        raw_set = set(self.raw_columns)
        preset_cols = list(self.mapping.keys())

        matched_cols = [c for c in preset_cols if c in raw_set]
        missing_in_file_cols = [c for c in preset_cols if c not in raw_set]
        unmapped_in_file_cols = [c for c in self.raw_columns if c not in self.mapping]

        total_rows = len(matched_cols) + len(missing_in_file_cols) + len(unmapped_in_file_cols)
        self.table.setRowCount(total_rows)

        # Update stats label
        self.stats_label.setText(
            f"✓ {len(matched_cols)} Mapped in File &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"⚠ {len(missing_in_file_cols)} in Preset but Missing in File &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"⊘ {len(unmapped_in_file_cols)} Skipped (Not in Preset)"
        )

        row = 0
        # 1. Matched Channels
        for raw_col in matched_cols:
            slug_val = self.mapping[raw_col]
            display_label = slug_val
            if self.state_manager:
                display_label = self.state_manager.get_label_by_slug(slug_val, slug_val)

            item0 = QTableWidgetItem(raw_col)
            item1 = QTableWidgetItem(display_label)
            item2 = QTableWidgetItem("✓ Mapped")
            item2.setForeground(Qt.green)

            self.table.setItem(row, 0, item0)
            self.table.setItem(row, 1, item1)
            self.table.setItem(row, 2, item2)
            row += 1

        # 2. Missing in File Channels (present in preset, absent in file)
        for raw_col in missing_in_file_cols:
            slug_val = self.mapping[raw_col]
            display_label = slug_val
            if self.state_manager:
                display_label = self.state_manager.get_label_by_slug(slug_val, slug_val)

            item0 = QTableWidgetItem(f"{raw_col} (not in file)")
            item0.setForeground(Qt.gray)
            item1 = QTableWidgetItem(display_label)
            item1.setForeground(Qt.gray)
            item2 = QTableWidgetItem("⚠ Missing in file (skipped)")
            item2.setForeground(Qt.yellow)

            self.table.setItem(row, 0, item0)
            self.table.setItem(row, 1, item1)
            self.table.setItem(row, 2, item2)
            row += 1

        # 3. Unmapped File Channels (present in file, absent in preset)
        for raw_col in unmapped_in_file_cols:
            item0 = QTableWidgetItem(raw_col)
            item1 = QTableWidgetItem("-- Skip --")
            item1.setForeground(Qt.gray)
            item2 = QTableWidgetItem("⊘ Skipped (unmapped)")
            item2.setForeground(Qt.gray)

            self.table.setItem(row, 0, item0)
            self.table.setItem(row, 1, item1)
            self.table.setItem(row, 2, item2)
            row += 1

    def get_filtered_mapping(self) -> Dict[str, str]:
        """Returns the mapping dictionary containing only channels present in the actual file."""
        return {raw_col: slug for raw_col, slug in self.mapping.items() if raw_col in self.raw_columns}

    def _on_apply(self):
        self.selected_action = self.ACTION_APPLY
        self.accept()

    def _on_edit(self):
        self.selected_action = self.ACTION_EDIT
        self.done(self.ACTION_EDIT)


class ImportWizardDialog(QDialog):
    """Wizard dialog for mapping raw channels to internal standard names (2 columns layout)."""

    def __init__(self, file_path: str, raw_columns: List[str], preview_df: pd.DataFrame,
                 state_manager: StateManager, initial_preset: Optional[str] = None,
                 initial_mapping: Optional[Dict[str, str]] = None, is_remapping: bool = False,
                 parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.raw_columns = raw_columns
        self.preview_df = preview_df
        self.state_manager = state_manager
        self.is_remapping = is_remapping
        self.result_mapping: Dict[str, str] = {}
        self.result_preset_name: Optional[str] = initial_preset

        if is_remapping:
            self.setWindowTitle(f"Edit Channel Mapping - {os.path.basename(file_path)}")
        else:
            self.setWindowTitle(f"Import Log Wizard - {file_path}")
        self.setMinimumSize(600, 500)

        self.suggested_targets = ["-- Skip --"] + self.state_manager.get_channel_labels()
        self._init_ui(initial_preset, initial_mapping)

    def _init_ui(self, initial_preset: Optional[str], initial_mapping: Optional[Dict[str, str]]):
        layout = QVBoxLayout(self)

        lap_label = self.state_manager.get_lap_label()
        time_label = self.state_manager.get_time_label()
        dist_label = self.state_manager.get_distance_label()

        instr_title = "Edit channel mappings:" if self.is_remapping else "Map channels for import:"
        instruction = QLabel(
            f"<b>{instr_title}</b><br>"
            "Assign raw channels to standard internal names.<br>"
            f"<b>Must map '{lap_label}' and '{time_label}' or '{dist_label}'. Duplicate channel assignments are not allowed.</b>"
        )
        instruction.setTextFormat(Qt.RichText)
        layout.addWidget(instruction)

        # Load Existing Preset Row (above table)
        load_preset_layout = QHBoxLayout()
        load_preset_layout.addWidget(QLabel("<b>Apply Saved Preset:</b>"))
        self.load_preset_combo = QComboBox()
        presets = self.state_manager.load_presets()
        preset_list = ["-- Select a Preset --"] + sorted(list(presets.keys()))
        self.load_preset_combo.addItems(preset_list)
        if initial_preset and initial_preset in preset_list:
            self.load_preset_combo.setCurrentText(initial_preset)
        self.load_preset_combo.currentTextChanged.connect(self._on_load_preset_selected)
        load_preset_layout.addWidget(self.load_preset_combo, stretch=1)

        self.load_preset_btn = QPushButton("Apply Preset")
        self.load_preset_btn.clicked.connect(self._on_apply_preset_button_clicked)
        load_preset_layout.addWidget(self.load_preset_btn)
        layout.addLayout(load_preset_layout)

        # Preset status banner
        self.preset_status_label = QLabel()
        self.preset_status_label.setVisible(False)
        self.preset_status_label.setStyleSheet("color: #00E676; font-size: 12px; padding: 2px;")
        layout.addWidget(self.preset_status_label)

        # Mapping Table (2 columns: raw channel, combo box)
        self.table = QTableWidget(len(self.raw_columns), 2)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalHeaderLabels(["Raw Channel (File)", "Mapped Channel Name"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        preset_map = presets.get(initial_preset, {}) if initial_preset else {}
        mapping_source = initial_mapping if initial_mapping is not None else preset_map

        self.combos: Dict[str, QComboBox] = {}
        suggested_used: Set[str] = set()

        for row, raw_col in enumerate(self.raw_columns):
            raw_item = QTableWidgetItem(raw_col)
            raw_item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 0, raw_item)

            combo = QComboBox()
            combo.setEditable(True)
            combo.addItems(self.suggested_targets)

            mapped_val = mapping_source.get(raw_col)
            if mapped_val:
                mapped_val = self.state_manager.get_label_by_slug(mapped_val, mapped_val)

            # Do not auto-guess/suggest unmapped raw channels if editing existing mapping or preset
            if not mapped_val and not initial_preset and not initial_mapping:
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

        action_text = "Apply Changes" if self.is_remapping else "Import Data"
        self.import_btn = QPushButton(action_text)
        self.import_btn.setStyleSheet("background-color: #00E676; color: black;")
        self.import_btn.clicked.connect(self._on_import)
        btn_layout.addWidget(self.import_btn)

        layout.addLayout(btn_layout)

    def _apply_preset_to_table(self, preset_name: str):
        if not preset_name or preset_name == "-- Select a Preset --":
            return
        presets = self.state_manager.load_presets()
        preset_map = presets.get(preset_name, {})
        if not preset_map:
            return

        mapped_count = 0
        unmapped_count = 0

        for raw_col, combo in self.combos.items():
            if raw_col in preset_map:
                slug_val = preset_map[raw_col]
                display_label = self.state_manager.get_label_by_slug(slug_val, slug_val)
                idx = combo.findText(display_label)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                else:
                    combo.setEditText(display_label)
                mapped_count += 1
            else:
                combo.setCurrentIndex(0)  # -- Skip --
                unmapped_count += 1

        self.preset_input.setText(preset_name)
        self.result_preset_name = preset_name
        self.preset_status_label.setText(
            f"✓ Applied preset '{preset_name}': {mapped_count} channels mapped, {unmapped_count} unmapped in file."
        )
        self.preset_status_label.setVisible(True)

    def _on_load_preset_selected(self, preset_name: str):
        if preset_name and preset_name != "-- Select a Preset --":
            self._apply_preset_to_table(preset_name)

    def _on_apply_preset_button_clicked(self):
        preset_name = self.load_preset_combo.currentText()
        self._apply_preset_to_table(preset_name)

    def _auto_guess_mapping(self, raw_col: str, already_used: Set[str]) -> Optional[str]:
        # Normalize accents and convert to lowercase
        nfkd = unicodedata.normalize('NFKD', raw_col.strip())
        norm = "".join(c for c in nfkd if not unicodedata.combining(c)).lower()
        tokens = set(re.split(r'[^a-z0-9]+', norm))
        clean = re.sub(r'[^a-z0-9]', '', norm)

        # Dynamic label lookups from state_manager by slug
        lap_label = self.state_manager.get_lap_label()
        time_label = self.state_manager.get_time_label()
        dist_label = self.state_manager.get_distance_label()
        speed_label = self.state_manager.get_label_by_slug("speed", "Speed")
        rpm_label = self.state_manager.get_label_by_slug("rpm", "RPM")
        volt_label = self.state_manager.get_label_by_slug("voltage", "Voltage")
        curr_label = self.state_manager.get_label_by_slug("current", "Current")
        throttle_label = self.state_manager.get_label_by_slug("throttle", "Throttle")
        temp_label = self.state_manager.get_label_by_slug("temperature", "Temperature")
        steer_label = self.state_manager.get_label_by_slug("steering_angle", "SteeringAngle")
        power_label = self.state_manager.get_label_by_slug("power", "Power")
        energy_label = self.state_manager.get_label_by_slug("energy", "Energy")
        lat_label = self.state_manager.get_label_by_slug("gps_lat", "GPS_Lat")
        lon_label = self.state_manager.get_label_by_slug("gps_lon", "GPS_Lon")

        candidates = []

        # 1. Lap: "lap", "lap_no", "kor", "round"
        if bool(tokens & {"lap", "lapno", "round", "kor", "korszam"}) or "lap" in clean or "round" in clean or clean in ("kor", "korszam", "lapno"):
            candidates.append(lap_label)

        # 2. Time: "time", "timestamp", "ido", "sec", exact "t"
        if clean == "t" or bool(tokens & {"time", "timestamp", "ido", "sec", "seconds"}) or "timestamp" in clean or "time" in clean:
            candidates.append(time_label)

        # 3. Distance: "distance", "dist", "tavolsag", "pos", "position", "odo", exact "d"
        if clean == "d" or bool(tokens & {"distance", "dist", "tavolsag", "pos", "position", "odo"}) or "distance" in clean or "dist" in clean or "tavolsag" in clean or "position" in clean or "odo" in clean:
            candidates.append(dist_label)

        # 4. Speed: "speed", "spd", "velocity", "vel", "sebesseg", "kmh", "kph", "mph"
        if bool(tokens & {"speed", "spd", "velocity", "vel", "sebesseg", "kmh", "kph", "mph"}) or "speed" in clean or "velocity" in clean or "sebesseg" in clean or "kmh" in clean or "kph" in clean or "mph" in clean:
            candidates.append(speed_label)

        # 5. RPM: "rpm", "engine_rpm", "motor_rpm", "fordulat"
        if bool(tokens & {"rpm", "enginerpm", "motorrpm", "fordulat"}) or "rpm" in clean or "fordulat" in clean:
            candidates.append(rpm_label)

        # 6. Voltage: "voltage", "volt", "batt_volt", "v_bat", exact "v"
        if clean == "v" or bool(tokens & {"voltage", "volt", "battvolt", "vbat"}) or "voltage" in clean or "volt" in clean or "vbat" in clean or "battvolt" in clean or bool(re.search(r'\bv[_\s]?bat\b', norm)):
            candidates.append(volt_label)

        # 7. Current: "current", "curr", "amp", "batt_curr", "i_bat", exact "a", exact "i"
        if clean in ("a", "i") or bool(tokens & {"current", "curr", "amp", "amps", "battcurr", "ibat"}) or "current" in clean or "curr" in clean or "ibat" in clean or "battcurr" in clean or bool(re.search(r'\bi[_\s]?bat\b', norm)):
            candidates.append(curr_label)

        # 8. Throttle: "throttle", "tps", "pedal", "accel_pedal", "gaz"
        if bool(tokens & {"throttle", "tps", "pedal", "accelpedal", "gaz"}) or "throttle" in clean or "tps" in clean or "pedal" in clean or "gaz" in clean:
            candidates.append(throttle_label)

        # 9. Temperature: "temperature", "temp", "homerséklet", "degc"
        if bool(tokens & {"temperature", "temp", "homerseklet", "degc"}) or "temperature" in clean or "temp" in clean or "homerseklet" in clean or "degc" in clean:
            candidates.append(temp_label)

        # 10. SteeringAngle: "steering", "steer", "kormanyszog"
        if bool(tokens & {"steering", "steer", "kormanyszog"}) or "steering" in clean or "steer" in clean or "kormanyszog" in clean:
            candidates.append(steer_label)

        # 11. Power: "power", "watt", "kw"
        if bool(tokens & {"power", "watt", "kw"}) or "power" in clean or "watt" in clean or "kw" in tokens:
            candidates.append(power_label)

        # 12. Energy: "energy", "wh", "kwh", "joule"
        if bool(tokens & {"energy", "wh", "kwh", "joule"}) or "energy" in clean or "joule" in clean or "kwh" in tokens or "wh" in tokens:
            candidates.append(energy_label)

        # 13. GPS_Lat: "latitude", "gps_lat", "lat"
        if bool(tokens & {"latitude", "gpslat", "lat"}) or "latitude" in clean or "gpslat" in clean or "lat" in tokens:
            candidates.append(lat_label)

        # 14. GPS_Lon: "longitude", "gps_lon", "lon", "long"
        if bool(tokens & {"longitude", "gpslon", "lon", "long"}) or "longitude" in clean or "gpslon" in clean or "lon" in tokens:
            candidates.append(lon_label)

        for cand in candidates:
            if cand not in already_used and cand in self.suggested_targets:
                return cand
        return None

    def _get_current_mapping(self) -> Dict[str, str]:
        mapping = {}
        for raw_col, combo in self.combos.items():
            text = combo.currentText().strip()
            if text and text != "-- Skip --":
                slug = self.state_manager.get_slug_by_label(text) or generate_slug(text)
                mapping[raw_col] = slug
        return mapping

    def _get_current_label_mapping(self) -> Dict[str, str]:
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

    def _save_new_custom_channels(self, mapping: Dict[str, str]):
        """Detects newly entered mapping target labels, adds them to standard channel defs, and saves them."""
        existing_labels = self.state_manager.get_channel_labels()
        existing_defs = self.state_manager.get_channel_defs()
        
        updated = False
        for raw, target in mapping.items():
            if target not in existing_labels:
                base_slug = generate_slug(target)
                slug = base_slug
                counter = 1
                existing_slugs = [ch["slug"] for ch in existing_defs]
                while slug in existing_slugs:
                    slug = f"{base_slug}_{counter}"
                    counter += 1
                
                existing_defs.append({"label": target, "slug": slug})
                existing_labels.append(target)
                updated = True
                
        if updated:
            self.state_manager.save_channel_defs(existing_defs)

    def _on_save_preset(self):
        preset_name = self.preset_input.text().strip()
        if not preset_name:
            QMessageBox.warning(self, "Warning", "Please enter a preset name.")
            return
        label_mapping = self._get_current_label_mapping()
        if not label_mapping:
            QMessageBox.warning(self, "Warning", "No mapped channels to save in preset.")
            return
        if not self._validate_no_duplicates(label_mapping):
            return

        self._save_new_custom_channels(label_mapping)
        mapping = self._get_current_mapping()
        self.state_manager.save_preset(preset_name, mapping)
        self.result_preset_name = preset_name
        QMessageBox.information(self, "Preset Saved", f"Preset '{preset_name}' saved successfully!")

    def _on_import(self):
        label_mapping = self._get_current_label_mapping()
        if not self._validate_no_duplicates(label_mapping):
            return

        self._save_new_custom_channels(label_mapping)
        mapping = self._get_current_mapping()
        mapped_slugs = set(mapping.values())

        lap_label = self.state_manager.get_lap_label()
        time_label = self.state_manager.get_time_label()
        dist_label = self.state_manager.get_distance_label()

        if SLUG_LAP not in mapped_slugs:
            QMessageBox.critical(self, "Validation Error", f"You must map at least one channel to '{lap_label}'.")
            return

        if SLUG_TIME not in mapped_slugs and SLUG_DISTANCE not in mapped_slugs:
            QMessageBox.critical(
                self, "Validation Error",
                f"You must map an X-Axis channel (either '{time_label}' or '{dist_label}')."
            )
            return

        self.result_mapping = mapping
        entered_preset = self.preset_input.text().strip()
        if entered_preset:
            self.result_preset_name = entered_preset
        self.accept()

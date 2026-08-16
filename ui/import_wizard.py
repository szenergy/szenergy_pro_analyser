"""
Dialog wizard for mapping raw log file channels to standard internal channel names and managing presets.
Unified interface for initial file import, preset matching, and session channel remapping.
"""

import os
import re
import unicodedata
from typing import Dict, List, Optional, Set
import pandas as pd
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QComboBox, QPushButton, QLabel, QMessageBox, QHeaderView,
    QAbstractItemView
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from core.state_manager import StateManager, generate_slug
from utils.constants import SLUG_LAP, SLUG_TIME, SLUG_DISTANCE


class ImportWizardDialog(QDialog):
    """
    Unified Wizard dialog for mapping raw log file channels to standard internal channel names.
    Provides preset selection, loading, saving, live matching statistics, and interactive channel mapping.
    """

    def __init__(self, file_path: str, raw_columns: List[str],
                 state_manager: StateManager, preview_df: Optional[pd.DataFrame] = None,
                 initial_preset: Optional[str] = None,
                 initial_mapping: Optional[Dict[str, str]] = None,
                 is_remapping: bool = False,
                 parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.raw_columns = list(raw_columns)
        self.preview_df = preview_df
        self.state_manager = state_manager
        self.is_remapping = is_remapping
        self.result_mapping: Dict[str, str] = {}
        self.loaded_preset_name: Optional[str] = initial_preset
        self.result_preset_name: Optional[str] = initial_preset

        self.combos: Dict[str, QComboBox] = {}
        self.status_items: Dict[str, QTableWidgetItem] = {}

        filename = os.path.basename(file_path)
        if is_remapping:
            self.setWindowTitle(f"Edit Channel Mapping - {filename}")
        else:
            self.setWindowTitle(f"Import Log Wizard - {filename}")
        self.setMinimumSize(660, 560)

        self.suggested_targets = ["-- Skip --"] + self.state_manager.get_channel_labels()
        self._init_ui(initial_preset, initial_mapping)

    def _init_ui(self, initial_preset: Optional[str], initial_mapping: Optional[Dict[str, str]]):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 1. Top File Name Display
        filename = os.path.basename(self.file_path)
        header_label = QLabel(f"<b>File:</b> <code>{filename}</code>")
        header_label.setTextFormat(Qt.RichText)
        header_label.setStyleSheet("font-size: 13px; padding-bottom: 2px;")
        layout.addWidget(header_label)

        # 2. Preset Selection Row (Combo Box + Save & Load Buttons)
        preset_layout = QHBoxLayout()
        preset_label = QLabel("<b>Preset:</b>")
        preset_label.setStyleSheet("font-size: 13px;")
        preset_layout.addWidget(preset_label)

        self.preset_combo = QComboBox()
        self.preset_combo.setEditable(True)
        presets = self.state_manager.load_presets()
        preset_names = sorted(list(presets.keys()))

        # If an initial preset was passed but isn't in preset_names, add it
        if initial_preset and initial_preset not in preset_names:
            preset_names.insert(0, initial_preset)

        self.preset_combo.addItems([""] + preset_names)

        if initial_preset:
            idx = self.preset_combo.findText(initial_preset)
            if idx >= 0:
                self.preset_combo.setCurrentIndex(idx)
            else:
                self.preset_combo.setEditText(initial_preset)
        else:
            self.preset_combo.setCurrentIndex(0)

        preset_layout.addWidget(self.preset_combo, stretch=1)

        self.save_btn = QPushButton("Save Preset")
        self.save_btn.setToolTip("Save the current channel mapping below to the preset name above")
        self.save_btn.clicked.connect(self._on_save_preset)
        preset_layout.addWidget(self.save_btn)

        self.load_btn = QPushButton("Load Preset")
        self.load_btn.setToolTip("Apply the selected preset mapping to the table below")
        self.load_btn.clicked.connect(self._on_load_preset)
        preset_layout.addWidget(self.load_btn)

        layout.addLayout(preset_layout)

        # 3. Live 3-Stat Summary Badges
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(10)

        self.stat_matched = QLabel("✓ 0 Matched")
        self.stat_missing = QLabel("⚠ 0 In Preset (Not in File)")
        self.stat_skipped = QLabel("⊘ 0 Skipped")

        stats_layout.addWidget(self.stat_matched)
        stats_layout.addWidget(self.stat_missing)
        stats_layout.addWidget(self.stat_skipped)
        stats_layout.addStretch()

        layout.addLayout(stats_layout)

        # 4. Mapping Table (3 Columns: Status Icon, File Channel, Mapped Channel)
        self.table = QTableWidget(len(self.raw_columns), 3)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalHeaderLabels(["Status", "Channel in File", "Mapped Target Channel"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)

        preset_map = presets.get(initial_preset, {}) if initial_preset else {}
        mapping_source = initial_mapping if initial_mapping is not None else preset_map

        suggested_used: Set[str] = set()

        for row, raw_col in enumerate(self.raw_columns):
            # Col 0: Status Icon
            status_item = QTableWidgetItem()
            status_item.setTextAlignment(Qt.AlignCenter)
            font = status_item.font()
            font.setBold(True)
            status_item.setFont(font)
            status_item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 0, status_item)
            self.status_items[raw_col] = status_item

            # Col 1: Raw File Channel Name
            raw_item = QTableWidgetItem(raw_col)
            raw_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table.setItem(row, 1, raw_item)

            # Col 2: Mapped Channel Combobox
            combo = QComboBox()
            combo.setEditable(True)
            combo.addItems(self.suggested_targets)

            mapped_val = mapping_source.get(raw_col)
            if mapped_val:
                mapped_val = self.state_manager.get_label_by_slug(mapped_val, mapped_val)

            # Auto-guess if no preset or mapping source provided
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
                combo.setCurrentIndex(0)  # -- Skip --

            combo.currentTextChanged.connect(lambda _, c=raw_col: self._on_channel_mapping_changed(c))
            self.combos[raw_col] = combo
            self.table.setCellWidget(row, 2, combo)

        layout.addWidget(self.table)
        self._refresh_icons_and_stats()

        # 5. Bottom Action Buttons (Cancel and Submit)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        action_text = "Apply Changes" if self.is_remapping else "Import Data"
        self.submit_btn = QPushButton(action_text)
        self.submit_btn.setStyleSheet("background-color: #00E676; color: black; font-weight: bold; padding: 6px 16px;")
        self.submit_btn.clicked.connect(self._on_submit)
        btn_layout.addWidget(self.submit_btn)

        layout.addLayout(btn_layout)

    def _on_channel_mapping_changed(self, raw_col: str):
        """Called when a single channel's dropdown changes."""
        self._refresh_icons_and_stats()

    def _refresh_icons_and_stats(self):
        """Updates row status icons, missing preset rows, and live stats counters based on the loaded preset."""
        matched_count = 0
        skipped_count = 0

        # Update file channels
        for row, raw_col in enumerate(self.raw_columns):
            combo = self.combos.get(raw_col)
            status_item = self.status_items.get(raw_col)
            text = combo.currentText().strip() if combo else ""
            if text and text != "-- Skip --":
                matched_count += 1
                if status_item:
                    status_item.setText("✓")
                    status_item.setForeground(QColor("#00E676"))
            else:
                skipped_count += 1
                if status_item:
                    status_item.setText("⊘")
                    status_item.setForeground(QColor("#808080"))

        current_preset = self.loaded_preset_name
        presets = self.state_manager.load_presets() if self.state_manager else {}
        missing_in_file_cols = []
        if current_preset and current_preset in presets:
            preset_cols = presets[current_preset].keys()
            raw_set = set(self.raw_columns)
            missing_in_file_cols = [c for c in preset_cols if c not in raw_set]

        # Dynamically append/remove 'in preset but not in file' rows at the end of the table
        total_rows = len(self.raw_columns) + len(missing_in_file_cols)
        self.table.setRowCount(total_rows)

        preset_map = presets.get(current_preset, {})
        for i, missing_col in enumerate(missing_in_file_cols):
            row = len(self.raw_columns) + i

            # Col 0: ⚠ warning icon
            status_item = QTableWidgetItem("⚠")
            status_item.setTextAlignment(Qt.AlignCenter)
            font = status_item.font()
            font.setBold(True)
            status_item.setFont(font)
            status_item.setForeground(QColor("#FFD740"))
            status_item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 0, status_item)

            # Col 1: File Channel name item (not in file)
            raw_item = QTableWidgetItem(f"{missing_col} (not in file)")
            raw_item.setForeground(QColor("#808080"))
            raw_item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 1, raw_item)

            # Col 2: Target channel name (non-editable text, not a combobox)
            self.table.setCellWidget(row, 2, None)
            slug_val = preset_map.get(missing_col, "")
            display_label = slug_val
            if self.state_manager and slug_val:
                display_label = self.state_manager.get_label_by_slug(slug_val, slug_val)
            target_item = QTableWidgetItem(display_label)
            target_item.setForeground(QColor("#808080"))
            target_item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 2, target_item)

        # 1. Matched Stat: only color, background, and border if count > 0
        self.stat_matched.setText(f"✓ {matched_count} Matched")
        if matched_count > 0:
            self.stat_matched.setStyleSheet(
                "background-color: rgba(0, 230, 118, 0.12); color: #00E676; "
                "border: 1px solid rgba(0, 230, 118, 0.35); border-radius: 4px; "
                "padding: 5px 12px; font-weight: bold;"
            )
        else:
            self.stat_matched.setStyleSheet(
                "background-color: transparent; color: #808080; "
                "border: none; padding: 5px 12px; font-weight: bold;"
            )

        # 2. In Preset (Not in File) Stat: only color, background, and border if count > 0
        missing_count = len(missing_in_file_cols)
        self.stat_missing.setText(f"⚠ {missing_count} In Preset (Not in File)")
        if missing_count > 0:
            self.stat_missing.setStyleSheet(
                "background-color: rgba(255, 215, 64, 0.12); color: #FFD740; "
                "border: 1px solid rgba(255, 215, 64, 0.35); border-radius: 4px; "
                "padding: 5px 12px; font-weight: bold;"
            )
        else:
            self.stat_missing.setStyleSheet(
                "background-color: transparent; color: #808080; "
                "border: none; padding: 5px 12px; font-weight: bold;"
            )

        # 3. Skipped Stat: never has background or border
        self.stat_skipped.setText(f"⊘ {skipped_count} Skipped")
        if skipped_count > 0:
            self.stat_skipped.setStyleSheet(
                "background-color: transparent; color: #9E9E9E; "
                "border: none; padding: 5px 12px; font-weight: bold;"
            )
        else:
            self.stat_skipped.setStyleSheet(
                "background-color: transparent; color: #808080; "
                "border: none; padding: 5px 12px; font-weight: bold;"
            )

    def _on_load_preset(self):
        """Loads and applies the currently selected preset to the table."""
        preset_name = self.preset_combo.currentText().strip()
        if not preset_name:
            QMessageBox.warning(self, "Warning", "Please select or type a preset name to load.")
            return

        presets = self.state_manager.load_presets() if self.state_manager else {}
        preset_map = presets.get(preset_name)
        if not preset_map:
            QMessageBox.warning(self, "Warning", f"Preset '{preset_name}' was not found in saved presets.")
            return

        for raw_col, combo in self.combos.items():
            combo.blockSignals(True)
            if raw_col in preset_map:
                slug_val = preset_map[raw_col]
                display_label = self.state_manager.get_label_by_slug(slug_val, slug_val)
                idx = combo.findText(display_label)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                else:
                    combo.setEditText(display_label)
            else:
                combo.setCurrentIndex(0)  # -- Skip --
            combo.blockSignals(False)

        self.loaded_preset_name = preset_name
        self.result_preset_name = preset_name
        self._refresh_icons_and_stats()

    def _on_save_preset(self):
        """Saves the table's current configuration to the preset name specified in the combobox."""
        preset_name = self.preset_combo.currentText().strip()
        if not preset_name:
            QMessageBox.warning(self, "Warning", "Please enter a preset name to save.")
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
        self.loaded_preset_name = preset_name
        self.result_preset_name = preset_name

        # Ensure preset is in the combobox items
        if self.preset_combo.findText(preset_name) < 0:
            self.preset_combo.addItem(preset_name)

        self._refresh_icons_and_stats()
        QMessageBox.information(self, "Preset Saved", f"Preset '{preset_name}' saved successfully!")

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

    def _on_submit(self):
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
        entered_preset = self.preset_combo.currentText().strip()
        self.result_preset_name = entered_preset if entered_preset else None
        self.accept()


class PresetPreviewDialog(ImportWizardDialog):
    """Backward-compatible wrapper for legacy references to PresetPreviewDialog."""
    ACTION_APPLY = 1
    ACTION_EDIT = 2

    def __init__(self, file_path: str, preset_name: str, mapping: Dict[str, str],
                 raw_columns: Optional[List[str]] = None,
                 state_manager=None, parent=None):
        raw_cols = list(raw_columns) if raw_columns is not None else list(mapping.keys())
        super().__init__(
            file_path=file_path,
            raw_columns=raw_cols,
            state_manager=state_manager,
            initial_preset=preset_name,
            initial_mapping=mapping,
            parent=parent
        )
        self.selected_action = self.ACTION_APPLY

    @property
    def selected_preset_name(self) -> Optional[str]:
        return self.result_preset_name

    def get_filtered_mapping(self) -> Dict[str, str]:
        return self.result_mapping

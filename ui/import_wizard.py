"""
Dialog wizard for mapping raw log file channels to standard internal channel names and managing presets.
Unified interface for initial file import, preset matching, and session channel remapping.
"""

import logging
import os
from typing import Dict, List, Optional
import pandas as pd
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QComboBox, QPushButton, QLabel, QMessageBox, QHeaderView,
    QAbstractItemView, QCheckBox, QFrame, QGridLayout
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from core.state_manager import StateManager, generate_slug
from utils.constants import STD_CH_LAP_NUM_SLUG, STD_CH_LAP_TIME_SLUG, STD_CH_LAP_DIST_SLUG

from ui.save_preset_dialog import SavePresetChoiceDialog

logger = logging.getLogger(__name__)


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

        self.loaded_preset_slug: Optional[str] = None
        self.loaded_preset_name: Optional[str] = None
        self.result_preset_slug: Optional[str] = None
        self.result_preset_name: Optional[str] = None

        self.channel_targets = ["-- Skip --"] + self.state_manager.get_channel_labels()
        logger.debug("ImportWizardDialog opened for '%s' (initial_preset: %s, is_remapping: %s, raw_cols: %d)",
                     filename, initial_preset, is_remapping, len(self.raw_columns))
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
        presets = self.state_manager.load_presets() if self.state_manager else []

        self.preset_combo.addItem("None", None)
        for p in presets:
            self.preset_combo.addItem(p.get("name", ""), p.get("slug", ""))

        target_slug = None
        if initial_preset and initial_preset != "None" and self.state_manager:
            p = self.state_manager.get_preset_by_slug(initial_preset) or self.state_manager.get_preset_by_name(initial_preset)
            if p:
                target_slug = p["slug"]
            else:
                self.preset_combo.addItem(initial_preset, None)
                idx = self.preset_combo.findText(initial_preset)
                if idx >= 0:
                    self.preset_combo.setCurrentIndex(idx)

        if target_slug:
            for i in range(self.preset_combo.count()):
                if self.preset_combo.itemData(i) == target_slug:
                    self.preset_combo.setCurrentIndex(i)
                    break
            self.loaded_preset_slug = target_slug
            self.loaded_preset_name = self.state_manager.get_preset_name_by_slug(target_slug)
        elif not initial_preset or initial_preset == "None":
            self.preset_combo.setCurrentIndex(0)
            self.loaded_preset_slug = None
            self.loaded_preset_name = None
        else:
            self.loaded_preset_slug = None
            self.loaded_preset_name = initial_preset

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

        initial_p = self.state_manager.get_preset_by_slug(target_slug) if (self.state_manager and target_slug) else None
        preset_map = initial_p.get("mapping", {}) if initial_p else {}
        mapping_source = initial_mapping if initial_mapping is not None else preset_map

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
            combo.addItems(self.channel_targets)

            mapped_val = mapping_source.get(raw_col)
            if mapped_val:
                mapped_val = self.state_manager.get_label_by_slug(mapped_val, mapped_val)
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

        # 5. Bottom Action Buttons (Remember Checkbox, Cancel and Submit)
        btn_layout = QHBoxLayout()

        self.remember_checkbox = QCheckBox("Remember for this file")
        is_remembered = False
        if self.state_manager:
            is_remembered = self.state_manager.get_file_preset(self.file_path) is not None
        self.remember_checkbox.setChecked(is_remembered)
        btn_layout.addWidget(self.remember_checkbox)

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

        current_preset = self.state_manager.get_preset_by_slug(self.loaded_preset_slug) if (self.state_manager and self.loaded_preset_slug) else None
        missing_in_file_cols = []
        if current_preset:
            preset_cols = list(current_preset.get("mapping", {}).keys())
            raw_set = set(self.raw_columns)
            missing_in_file_cols = [c for c in preset_cols if c not in raw_set]

        # Dynamically append/remove 'in preset but not in file' rows at the end of the table
        total_rows = len(self.raw_columns) + len(missing_in_file_cols)
        self.table.setRowCount(total_rows)

        preset_map = current_preset.get("mapping", {}) if current_preset else {}
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
        """Loads and applies the currently selected preset to the table. If 'None' or empty, resets all channels to skip."""
        idx = self.preset_combo.currentIndex()
        preset_slug = self.preset_combo.itemData(idx) if idx >= 0 else None
        preset_text = self.preset_combo.currentText().strip()

        if preset_text == "None" or not preset_text:
            # Set all channels to skip
            for raw_col, combo in self.combos.items():
                combo.blockSignals(True)
                combo.setCurrentIndex(0)  # -- Skip --
                combo.blockSignals(False)
            self.loaded_preset_slug = None
            self.loaded_preset_name = None
            self.result_preset_slug = None
            self.result_preset_name = None
            self._refresh_icons_and_stats()
            return

        preset = None
        if self.state_manager:
            preset = self.state_manager.get_preset_by_name(preset_text) or self.state_manager.get_preset_by_slug(preset_text)
        if not preset and preset_slug and self.state_manager:
            preset = self.state_manager.get_preset_by_slug(preset_slug)

        if not preset:
            QMessageBox.warning(self, "Warning", f"Preset '{preset_text}' was not found in saved presets.")
            return

        preset_map = preset.get("mapping", {})
        for raw_col, combo in self.combos.items():
            combo.blockSignals(True)
            if raw_col in preset_map:
                slug_val = preset_map[raw_col]
                display_label = self.state_manager.get_label_by_slug(slug_val, slug_val)
                c_idx = combo.findText(display_label)
                if c_idx >= 0:
                    combo.setCurrentIndex(c_idx)
                else:
                    combo.setEditText(display_label)
            else:
                combo.setCurrentIndex(0)  # -- Skip --
            combo.blockSignals(False)

        self.loaded_preset_slug = preset.get("slug")
        self.loaded_preset_name = preset.get("name")
        self.result_preset_slug = preset.get("slug")
        self.result_preset_name = preset.get("name")
        self._refresh_icons_and_stats()

    def _on_save_preset(self):
        """Saves the table's current configuration to the preset name specified in the combobox."""
        preset_name = self.preset_combo.currentText().strip()
        if not preset_name or preset_name == "None":
            QMessageBox.warning(self, "Warning", "Please enter a valid preset name to save.")
            return

        label_mapping = self._get_current_label_mapping()
        if not label_mapping:
            QMessageBox.warning(self, "Warning", "No mapped channels to save in preset.")
            return

        if not self._validate_no_duplicates(label_mapping):
            return

        self._save_new_custom_channels(label_mapping)
        mapping = self._get_current_mapping()

        target_slug = None
        action_text = "created"

        # If a preset is loaded and its name is being changed, prompt the user
        if self.loaded_preset_name and self.loaded_preset_name != "None" and preset_name != self.loaded_preset_name:
            loaded_preset = (
                self.state_manager.get_preset_by_slug(self.loaded_preset_slug)
                if self.loaded_preset_slug and self.state_manager else None
            )
            if not loaded_preset and self.state_manager:
                loaded_preset = self.state_manager.get_preset_by_name(self.loaded_preset_name)

            original_mapping = loaded_preset.get("mapping", {}) if loaded_preset else {}
            all_keys = set(original_mapping.keys()) | set(mapping.keys())
            channels_changed = sum(1 for k in all_keys if original_mapping.get(k) != mapping.get(k))

            dialog = SavePresetChoiceDialog(
                old_name=self.loaded_preset_name,
                new_name=preset_name,
                channels_changed=channels_changed,
                parent=self
            )
            if dialog.exec() != QDialog.Accepted:
                return

            if dialog.selected_action == SavePresetChoiceDialog.ACTION_UPDATE:
                target_slug = self.loaded_preset_slug
                action_text = "updated"
            elif dialog.selected_action == SavePresetChoiceDialog.ACTION_CREATE_NEW:
                target_slug = None
                action_text = "created"
            else:
                return
        elif self.loaded_preset_slug and preset_name == self.loaded_preset_name:
            target_slug = self.loaded_preset_slug
            action_text = "updated"
        else:
            target_slug = None
            action_text = "created"

        saved_slug = self.state_manager.save_preset(preset_name, mapping, slug=target_slug)
        self.loaded_preset_slug = saved_slug
        self.loaded_preset_name = preset_name
        self.result_preset_slug = saved_slug
        self.result_preset_name = preset_name

        # Refresh preset_combo items
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem("None", None)
        presets = self.state_manager.load_presets()
        target_idx = 0
        for i, p in enumerate(presets, start=1):
            self.preset_combo.addItem(p["name"], p["slug"])
            if p["slug"] == saved_slug:
                target_idx = i
        self.preset_combo.setCurrentIndex(target_idx)
        self.preset_combo.blockSignals(False)

        self._refresh_icons_and_stats()
        QMessageBox.information(self, "Preset Saved", f"Preset '{preset_name}' {action_text} successfully!")

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
        self.state_manager.save_new_custom_channels(list(mapping.values()))

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

        if STD_CH_LAP_NUM_SLUG not in mapped_slugs:
            QMessageBox.critical(self, "Validation Error", f"You must map at least one channel to '{lap_label}'.")
            return

        if STD_CH_LAP_TIME_SLUG not in mapped_slugs and STD_CH_LAP_DIST_SLUG not in mapped_slugs:
            QMessageBox.critical(
                self, "Validation Error",
                f"You must map an X-Axis channel (either '{time_label}' or '{dist_label}')."
            )
            return

        self.result_mapping = mapping
        idx = self.preset_combo.currentIndex()
        preset_slug = self.preset_combo.itemData(idx) if idx >= 0 else None
        entered_preset = self.preset_combo.currentText().strip()

        if entered_preset and entered_preset != "None":
            self.result_preset_name = entered_preset
            self.result_preset_slug = preset_slug or (self.state_manager.get_preset_slug_by_name(entered_preset) if self.state_manager else None)
        else:
            self.result_preset_name = None
            self.result_preset_slug = None

        if self.state_manager:
            if self.remember_checkbox.isChecked() and self.loaded_preset_slug:
                preset = self.state_manager.get_preset_by_slug(self.loaded_preset_slug)
                # Only save the preset if it was not modified
                if preset and preset.get("mapping") == mapping:
                    self.state_manager.save_file_preset(self.file_path, self.loaded_preset_slug)
                else:
                    self.state_manager.remove_file_preset(self.file_path)
            else:
                self.state_manager.remove_file_preset(self.file_path)

        logger.info("ImportWizardDialog submitted: %d channels mapped, preset '%s' (slug: '%s')",
                    len(self.result_mapping), self.result_preset_name, self.result_preset_slug)
        self.accept()

    def exec(self) -> int:
        """Executes the dialog modally."""
        return super().exec()


from ui.preset_preview_dialog import PresetPreviewDialog

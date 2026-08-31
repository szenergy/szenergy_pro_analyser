"""
Dialog for managing and editing saved channel map presets.
"""

from typing import Dict, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QTableWidget, QTableWidgetItem, QComboBox, QPushButton, QLabel, QLineEdit,
    QMessageBox, QHeaderView, QSplitter, QAbstractItemView, QWidget
)
from PySide6.QtCore import Qt

from core.state_manager import StateManager


class PresetManagerDialog(QDialog):
    """Dialog for managing and editing saved channel map presets with Import Wizard-style ComboBoxes."""

    def __init__(self, state_manager: StateManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Channel Map Presets")
        self.setMinimumSize(720, 480)
        self.state_manager = state_manager

        self.current_preset_slug: Optional[str] = None
        self.current_preset_name: str = ""

        self._init_ui()
        self.load_preset_list()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        splitter = QSplitter(Qt.Horizontal)

        # Left Panel: Preset List & Delete Button
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 5, 0)
        left_layout.setSpacing(6)

        left_layout.addWidget(QLabel("<b>Saved Presets:</b>"))
        self.preset_list = QListWidget()
        self.preset_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.preset_list.currentItemChanged.connect(lambda cur, prev: self._on_preset_selected())
        left_layout.addWidget(self.preset_list)

        self.delete_btn = QPushButton("Delete Selected Preset")
        self.delete_btn.setStyleSheet("color: #FF5252;")
        self.delete_btn.clicked.connect(self._on_delete_preset)
        left_layout.addWidget(self.delete_btn)

        splitter.addWidget(left_widget)

        # Right Panel: Preset Editor
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 0, 0, 0)
        right_layout.setSpacing(6)

        # Name field
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("<b>Preset Name:</b>"))
        self.preset_name_input = QLineEdit()
        name_layout.addWidget(self.preset_name_input)
        right_layout.addLayout(name_layout)

        # Mapping Table
        self.table = QTableWidget(0, 2)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalHeaderLabels(["Raw Channel (File)", "Mapped Target Channel"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        right_layout.addWidget(self.table)

        # Row controls & Save Button
        row_btn_layout = QHBoxLayout()
        add_row_btn = QPushButton("Add Row")
        add_row_btn.clicked.connect(self._on_add_row)
        row_btn_layout.addWidget(add_row_btn)

        remove_row_btn = QPushButton("Remove Selected Rows")
        remove_row_btn.clicked.connect(self._on_remove_row)
        row_btn_layout.addWidget(remove_row_btn)

        row_btn_layout.addStretch()

        save_preset_btn = QPushButton("Save Changes")
        save_preset_btn.setStyleSheet("background-color: #00E676; color: black;")
        save_preset_btn.clicked.connect(self._on_save_preset)
        row_btn_layout.addWidget(save_preset_btn)

        right_layout.addLayout(row_btn_layout)
        splitter.addWidget(right_widget)

        splitter.setSizes([220, 500])
        layout.addWidget(splitter, 1)

        # Bottom Dialog Close Button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Close Manager")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _clear_table(self):
        """Safely clears table items and all cell widgets to prevent floating orphaned widgets."""
        self.table.clearContents()
        self.table.setRowCount(0)

    def load_preset_list(self):
        self.preset_list.blockSignals(True)
        self.preset_list.clear()
        presets = self.state_manager.load_presets()
        for preset in presets:
            item = QListWidgetItem(preset.get("name", ""))
            item.setData(Qt.UserRole, preset.get("slug", ""))
            self.preset_list.addItem(item)
        self.preset_list.blockSignals(False)

        if self.preset_list.count() > 0:
            self.preset_list.setCurrentRow(0)
            self._on_preset_selected()
        else:
            self.current_preset_slug = None
            self.current_preset_name = ""
            self.preset_name_input.clear()
            self._clear_table()

    def _on_preset_selected(self):
        self._clear_table()
        current_item = self.preset_list.currentItem()
        if not current_item:
            self.current_preset_slug = None
            self.current_preset_name = ""
            self.preset_name_input.clear()
            return

        slug = current_item.data(Qt.UserRole)
        preset = self.state_manager.get_preset_by_slug(slug)
        if not preset:
            preset = self.state_manager.get_preset_by_name(current_item.text())

        if not preset:
            return

        self.current_preset_slug = preset["slug"]
        self.current_preset_name = preset["name"]
        self.preset_name_input.setText(preset["name"])
        mapping = preset.get("mapping", {})

        target_options = ["-- Skip --"] + self.state_manager.get_channel_labels()
        self.table.setRowCount(len(mapping))

        for row, (raw_col, slug_val) in enumerate(mapping.items()):
            raw_item = QTableWidgetItem(raw_col)
            self.table.setItem(row, 0, raw_item)

            combo = QComboBox()
            combo.setEditable(True)
            combo.addItems(target_options)

            # Resolve slug to display label for combo display
            display_label = self.state_manager.get_label_by_slug(slug_val, slug_val)
            idx = combo.findText(display_label)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.setEditText(display_label)

            self.table.setCellWidget(row, 1, combo)

    def _on_add_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)

        raw_item = QTableWidgetItem(f"NewChannel_{row + 1}")
        self.table.setItem(row, 0, raw_item)

        target_options = ["-- Skip --"] + self.state_manager.get_channel_labels()
        combo = QComboBox()
        combo.setEditable(True)
        combo.addItems(target_options)
        self.table.setCellWidget(row, 1, combo)

    def _on_remove_row(self):
        current_row = self.table.currentRow()
        if current_row >= 0:
            self.table.removeRow(current_row)

    def _get_table_mapping(self) -> Dict[str, str]:
        mapping = {}
        for row in range(self.table.rowCount()):
            raw_item = self.table.item(row, 0)
            combo = self.table.cellWidget(row, 1)
            if raw_item and isinstance(combo, QComboBox):
                raw_col = raw_item.text().strip()
                mapped_label = combo.currentText().strip()
                if raw_col and mapped_label and mapped_label != "-- Skip --":
                    slug = self.state_manager.get_slug_by_label(mapped_label)
                    if slug is None:
                        from core.state_manager import generate_slug
                        slug = generate_slug(mapped_label)
                    mapping[raw_col] = slug
        return mapping

    def _save_new_custom_channels_from_table(self):
        targets = []
        for row in range(self.table.rowCount()):
            combo = self.table.cellWidget(row, 1)
            if isinstance(combo, QComboBox):
                label = combo.currentText().strip()
                if label:
                    targets.append(label)
        self.state_manager.save_new_custom_channels(targets)

    def _on_save_preset(self):
        new_preset_name = self.preset_name_input.text().strip()
        if not new_preset_name:
            QMessageBox.warning(self, "Warning", "Please enter a valid preset name.")
            return

        self._save_new_custom_channels_from_table()

        mapping = self._get_table_mapping()
        if not mapping:
            QMessageBox.warning(self, "Warning", "Cannot save preset with empty channel mappings.")
            return

        targets = list(mapping.values())
        duplicates = set([t for t in targets if targets.count(t) > 1])
        if duplicates:
            dup_str = ", ".join(duplicates)
            QMessageBox.critical(
                self, "Duplicate Mapping Error",
                f"The following target channels are assigned multiple times: {dup_str}.\n"
                "Each target channel name must be unique within a preset."
            )
            return

        saved_slug = self.state_manager.save_preset(
            new_preset_name, mapping, slug=self.current_preset_slug
        )
        self.current_preset_slug = saved_slug
        self.current_preset_name = new_preset_name
        QMessageBox.information(self, "Saved", f"Preset '{new_preset_name}' saved successfully!")

        self.load_preset_list()
        for i in range(self.preset_list.count()):
            item = self.preset_list.item(i)
            if item.data(Qt.UserRole) == saved_slug:
                self.preset_list.setCurrentItem(item)
                break

    def _on_delete_preset(self):
        current_item = self.preset_list.currentItem()
        if not current_item:
            return

        preset_slug = current_item.data(Qt.UserRole)
        preset_name = current_item.text()
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete preset '{preset_name}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.state_manager.delete_preset(preset_slug or preset_name)
            self.load_preset_list()

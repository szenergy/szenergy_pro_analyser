"""
Dialog for managing standard internal channels with in-table editing, labels, units, types, and calculated configuration.
"""

from typing import Dict, List, Optional, Tuple, Any
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLineEdit, QMessageBox, QHeaderView, QAbstractItemView, QWidget
)
from PySide6.QtCore import Qt

from core.state_manager import StateManager, generate_slug
from utils.constants import (
    STD_CH_LAP_NUM_SLUG, STD_CH_LAP_TIME_SLUG, STD_CH_LAP_DIST_SLUG
)
from utils.theme import is_system_dark_theme
from ui.graph_icons import create_icon_settings

SYSTEM_REQUIRED_SLUGS = [STD_CH_LAP_NUM_SLUG, STD_CH_LAP_TIME_SLUG, STD_CH_LAP_DIST_SLUG]


class ChannelManagerDialog(QDialog):
    """Dialog for managing standard internal channels with Type, Label, Unit, and Calculated configuration."""

    def __init__(self, state_manager: StateManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Standard Channel List")
        self.setMinimumSize(620, 500)
        self.state_manager = state_manager
        self.is_dark: bool = getattr(parent, "is_dark", is_system_dark_theme())

        self.channels: List[Dict[str, Any]] = []
        self._is_populating: bool = False
        self._init_ui()
        self.load_channels()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # Table Widget displaying Type, Label, Unit, (Configure icon)
        self.table = QTableWidget(0, 4)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalHeaderLabels(["Type", "Label", "Unit", ""])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 110)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 40)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.itemChanged.connect(self._on_table_item_changed)
        layout.addWidget(self.table, 1)

        # Add Controls Row (Label, Unit, Add Channel, Add Calculated)
        add_layout = QHBoxLayout()
        add_layout.setSpacing(6)

        self.label_input = QLineEdit()
        self.label_input.setPlaceholderText("Enter channel label (e.g. Brake Pressure)...")
        self.label_input.returnPressed.connect(self._on_add_channel)
        add_layout.addWidget(self.label_input, 2)

        self.unit_input = QLineEdit()
        self.unit_input.setPlaceholderText("Unit (e.g. bar)...")
        self.unit_input.setMaximumWidth(120)
        self.unit_input.returnPressed.connect(self._on_add_channel)
        add_layout.addWidget(self.unit_input, 1)

        self.btn_add_channel = QPushButton("Add Channel")
        self.btn_add_channel.clicked.connect(self._on_add_channel)
        add_layout.addWidget(self.btn_add_channel)

        self.btn_add_calculated = QPushButton("Add Calculated")
        self.btn_add_calculated.setToolTip("Add calculated channel (coming soon)")
        self.btn_add_calculated.clicked.connect(self._on_add_calculated)
        add_layout.addWidget(self.btn_add_calculated)

        layout.addLayout(add_layout)

        # Action Controls Row (Remove Selected, Save & Apply)
        action_layout = QHBoxLayout()
        action_layout.setSpacing(6)

        self.btn_remove = QPushButton("Remove Selected")
        self.btn_remove.clicked.connect(self._on_remove_channel)
        action_layout.addWidget(self.btn_remove)

        action_layout.addStretch()

        self.btn_save = QPushButton("Save & Apply")
        self.btn_save.setStyleSheet("background-color: #00E676; color: black; font-weight: bold;")
        self.btn_save.clicked.connect(self._on_save)
        action_layout.addWidget(self.btn_save)

        layout.addLayout(action_layout)

    def load_channels(self):
        raw_defs = self.state_manager.get_channel_defs()
        self.channels = []
        for c in raw_defs:
            if isinstance(c, dict):
                d = dict(c)
                if "type" not in d:
                    d["type"] = "system" if d.get("slug") in SYSTEM_REQUIRED_SLUGS else "normal"
                if "unit" not in d:
                    d["unit"] = ""
                self.channels.append(d)
            elif isinstance(c, str):
                slug = generate_slug(c)
                ch_type = "system" if slug in SYSTEM_REQUIRED_SLUGS else "normal"
                self.channels.append({"label": c, "slug": slug, "type": ch_type, "unit": ""})
            elif isinstance(c, tuple) and len(c) >= 2:
                slug = str(c[1])
                ch_type = "system" if slug in SYSTEM_REQUIRED_SLUGS else "normal"
                unit = str(c[2]) if len(c) >= 3 else ""
                self.channels.append({"label": str(c[0]), "slug": slug, "type": ch_type, "unit": unit})
        self.refresh_table()

    def refresh_table(self):
        self._is_populating = True
        self.table.setRowCount(len(self.channels))
        for row, ch in enumerate(self.channels):
            ch_type = ch.get("type", "normal")
            if ch.get("slug") in SYSTEM_REQUIRED_SLUGS:
                ch_type = "system"
            label = ch.get("label", "")
            unit = ch.get("unit", "")

            # 0. Type Column (Non-editable)
            type_display = ch_type.capitalize()
            type_item = QTableWidgetItem(type_display)
            type_item.setTextAlignment(Qt.AlignCenter)
            type_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table.setItem(row, 0, type_item)

            # 1. Label Column (Directly editable in table)
            label_item = QTableWidgetItem(label)
            label_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            self.table.setItem(row, 1, label_item)

            # 2. Unit Column (Directly editable in table)
            unit_item = QTableWidgetItem(unit)
            unit_item.setTextAlignment(Qt.AlignCenter)
            unit_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            self.table.setItem(row, 2, unit_item)

            # 3. Configure Column (Icon button only for calculated channels)
            if ch_type == "calculated":
                btn_cfg = QPushButton()
                btn_cfg.setIcon(create_icon_settings(self.is_dark))
                btn_cfg.setToolTip("Configure Calculated Channel")
                btn_cfg.setFixedSize(28, 24)
                btn_cfg.setCursor(Qt.PointingHandCursor)
                btn_cfg.clicked.connect(lambda _, r=row: self._on_configure_calculated(r))

                cfg_container = QWidget()
                c_layout = QHBoxLayout(cfg_container)
                c_layout.setContentsMargins(0, 0, 0, 0)
                c_layout.setAlignment(Qt.AlignCenter)
                c_layout.addWidget(btn_cfg)
                self.table.setCellWidget(row, 3, cfg_container)
            else:
                self.table.setCellWidget(row, 3, None)
                empty_item = QTableWidgetItem("")
                empty_item.setFlags(Qt.NoItemFlags)
                self.table.setItem(row, 3, empty_item)

        self._is_populating = False

    def _is_label_exists(self, label: str, exclude_index: int = -1) -> bool:
        norm = label.strip().lower()
        for idx, ch in enumerate(self.channels):
            if idx == exclude_index:
                continue
            if ch["label"].strip().lower() == norm:
                return True
        return False

    def _on_table_item_changed(self, item: QTableWidgetItem):
        """Handles direct in-table cell edits for channel label and unit."""
        if self._is_populating or item is None:
            return

        row = item.row()
        col = item.column()
        if row < 0 or row >= len(self.channels):
            return

        ch = self.channels[row]
        ch_type = ch.get("type", "normal")
        if ch.get("slug") in SYSTEM_REQUIRED_SLUGS:
            ch_type = "system"

        if col == 1:  # Display Name / Label
            new_label = item.text().strip()
            if not new_label:
                self._is_populating = True
                item.setText(ch["label"])
                self._is_populating = False
                QMessageBox.warning(self, "Invalid Label", "Channel label cannot be empty.")
                return

            if self._is_label_exists(new_label, exclude_index=row):
                self._is_populating = True
                item.setText(ch["label"])
                self._is_populating = False
                QMessageBox.warning(self, "Duplicate Label", f"A channel with label '{new_label}' already exists.")
                return

            ch["label"] = new_label
            if ch["slug"] not in SYSTEM_REQUIRED_SLUGS and ch_type != "system":
                existing_slugs = [
                    other["slug"] for idx, other in enumerate(self.channels) if idx != row
                ]
                ch["slug"] = self.state_manager.generate_unique_slug(new_label, existing_slugs)

        elif col == 2:  # Engineering Unit
            new_unit = item.text().strip()
            ch["unit"] = new_unit

    def _on_add_channel(self):
        new_label = self.label_input.text().strip()
        new_unit = self.unit_input.text().strip()
        if not new_label:
            return

        if self._is_label_exists(new_label):
            QMessageBox.warning(self, "Duplicate Label", f"A channel with label '{new_label}' already exists.")
            return

        existing_slugs = [ch["slug"] for ch in self.channels]
        slug = self.state_manager.generate_unique_slug(new_label, existing_slugs)

        self.channels.append({
            "label": new_label,
            "slug": slug,
            "type": "normal",
            "unit": new_unit
        })
        self.label_input.clear()
        self.unit_input.clear()
        self.refresh_table()
        self.table.selectRow(len(self.channels) - 1)

    def _on_add_calculated(self):
        """Opens dialog to configure and add a new calculated channel."""
        from ui.calculated_channel_dialog import CalculatedChannelDialog

        initial_data = {}
        entered_label = self.label_input.text().strip()
        entered_unit = self.unit_input.text().strip()
        if entered_label:
            initial_data["label"] = entered_label
        if entered_unit:
            initial_data["unit"] = entered_unit

        dialog = CalculatedChannelDialog(
            parent=self,
            channel_data=initial_data if initial_data else None,
            state_manager=self.state_manager,
            is_dark=self.is_dark
        )
        if dialog.exec() == QDialog.Accepted and dialog.result_channel_data:
            new_label = dialog.result_channel_data["label"]
            if self._is_label_exists(new_label):
                QMessageBox.warning(self, "Duplicate Label", f"A channel with label '{new_label}' already exists.")
                return
            self.channels.append(dialog.result_channel_data)
            self.label_input.clear()
            self.unit_input.clear()
            self.refresh_table()
            self.table.selectRow(len(self.channels) - 1)

    def _on_configure_calculated(self, row: int):
        """Opens dialog to edit an existing calculated channel."""
        if row < 0 or row >= len(self.channels):
            return
        ch = self.channels[row]
        if ch.get("type") != "calculated":
            return
        from ui.calculated_channel_dialog import CalculatedChannelDialog
        dialog = CalculatedChannelDialog(
            parent=self,
            channel_data=ch,
            state_manager=self.state_manager,
            is_dark=self.is_dark
        )
        if dialog.exec() == QDialog.Accepted and dialog.result_channel_data:
            new_data = dialog.result_channel_data
            if new_data["label"] != ch.get("label") and self._is_label_exists(new_data["label"]):
                QMessageBox.warning(self, "Duplicate Label", f"A channel with label '{new_data['label']}' already exists.")
                return
            self.channels[row] = new_data
            self.refresh_table()
            self.table.selectRow(row)

    def _on_remove_channel(self):
        current_row = self.table.currentRow()
        if current_row < 0 or current_row >= len(self.channels):
            QMessageBox.warning(self, "Selection Required", "Please select a channel to remove.")
            return

        ch = self.channels[current_row]
        if ch["slug"] in SYSTEM_REQUIRED_SLUGS or ch.get("type") == "system":
            QMessageBox.warning(
                self, "Protected System Channel",
                f"Cannot remove required system channel '{ch['label']}' (slug: '{ch['slug']}').\n"
                "You may rename or change its unit, but the system requires a Lap, Time, and Distance channel."
            )
            return

        del self.channels[current_row]
        self.refresh_table()

    def _on_save(self):
        self.state_manager.save_channel_defs(self.channels)
        QMessageBox.information(self, "Saved", "Standard channel list saved successfully.")
        self.accept()

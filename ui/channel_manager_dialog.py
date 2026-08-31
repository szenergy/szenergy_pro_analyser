"""
Dialog for managing standard internal channels with labels, slug generation, and renaming.
"""

from typing import Dict, List
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLineEdit, QMessageBox, QHeaderView, QAbstractItemView, QInputDialog
)
from PySide6.QtCore import Qt

from core.state_manager import StateManager, generate_slug
from utils.constants import (
    STD_CH_LAP_NUM_SLUG, STD_CH_LAP_TIME_SLUG, STD_CH_LAP_DIST_SLUG
)

SYSTEM_REQUIRED_SLUGS = [STD_CH_LAP_NUM_SLUG, STD_CH_LAP_TIME_SLUG, STD_CH_LAP_DIST_SLUG]


class ChannelManagerDialog(QDialog):
    """Dialog for managing standard internal channels with labels, slug generation, and renaming."""

    def __init__(self, state_manager: StateManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Standard Channel List")
        self.setMinimumSize(550, 480)
        self.state_manager = state_manager

        self.channels: List[Dict[str, str]] = []
        self._init_ui()
        self.load_channels()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # Table Widget displaying Label & Slug
        self.table = QTableWidget(0, 2)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalHeaderLabels(["Display Label", "Internal Slug (Key)"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self.table, 1)

        # Add Controls Row
        add_layout = QHBoxLayout()
        self.label_input = QLineEdit()
        self.label_input.setPlaceholderText("Enter new channel label (e.g. Brake Pressure [bar])...")
        self.label_input.returnPressed.connect(self._on_add_channel)
        add_layout.addWidget(self.label_input)

        add_btn = QPushButton("Add Channel")
        add_btn.clicked.connect(self._on_add_channel)
        add_layout.addWidget(add_btn)

        layout.addLayout(add_layout)

        # Edit Action Controls Row
        action_layout = QHBoxLayout()

        rename_btn = QPushButton("Rename Selected")
        rename_btn.clicked.connect(self._on_rename_channel)
        action_layout.addWidget(rename_btn)

        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._on_remove_channel)
        action_layout.addWidget(remove_btn)

        action_layout.addStretch()

        save_btn = QPushButton("Save & Apply")
        save_btn.setStyleSheet("background-color: #00E676; color: black;")
        save_btn.clicked.connect(self._on_save)
        action_layout.addWidget(save_btn)

        layout.addLayout(action_layout)

    def load_channels(self):
        raw_defs = self.state_manager.get_channel_defs()
        self.channels = []
        for c in raw_defs:
            if isinstance(c, dict):
                self.channels.append(dict(c))
            elif isinstance(c, str):
                self.channels.append({"label": c, "slug": generate_slug(c)})
            elif isinstance(c, tuple) and len(c) >= 2:
                self.channels.append({"label": c[0], "slug": c[1]})
        self.refresh_table()

    def refresh_table(self):
        self.table.setRowCount(len(self.channels))
        for row, ch in enumerate(self.channels):
            label = ch["label"]
            slug = ch["slug"]

            label_text = label
            if slug in SYSTEM_REQUIRED_SLUGS:
                label_text = f"{label}  (System Required)"

            label_item = QTableWidgetItem(label_text)
            slug_item = QTableWidgetItem(slug)

            label_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            slug_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

            self.table.setItem(row, 0, label_item)
            self.table.setItem(row, 1, slug_item)

    def _is_label_exists(self, label: str, exclude_index: int = -1) -> bool:
        norm = label.strip().lower()
        for idx, ch in enumerate(self.channels):
            if idx == exclude_index:
                continue
            if ch["label"].strip().lower() == norm:
                return True
        return False

    def _on_add_channel(self):
        new_label = self.label_input.text().strip()
        if not new_label:
            return

        if self._is_label_exists(new_label):
            QMessageBox.warning(self, "Duplicate Label", f"A channel with label '{new_label}' already exists.")
            return

        existing_slugs = [ch["slug"] for ch in self.channels]
        slug = self.state_manager.generate_unique_slug(new_label, existing_slugs)

        self.channels.append({"label": new_label, "slug": slug})
        self.label_input.clear()
        self.refresh_table()
        self.table.selectRow(len(self.channels) - 1)

    def _on_rename_channel(self):
        current_row = self.table.currentRow()
        if current_row < 0 or current_row >= len(self.channels):
            QMessageBox.warning(self, "Selection Required", "Please select a channel to rename.")
            return

        ch = self.channels[current_row]
        new_label, ok = QInputDialog.getText(
            self, "Rename Channel",
            f"Enter new label for channel '{ch['label']}':",
            QLineEdit.Normal, ch["label"]
        )

        if ok and new_label.strip():
            new_label = new_label.strip()
            if self._is_label_exists(new_label, exclude_index=current_row):
                QMessageBox.warning(self, "Duplicate Label", f"A channel with label '{new_label}' already exists.")
                return

            if ch["slug"] not in SYSTEM_REQUIRED_SLUGS:
                existing_slugs = [
                    other["slug"] for idx, other in enumerate(self.channels) if idx != current_row
                ]
                slug = self.state_manager.generate_unique_slug(new_label, existing_slugs)
                ch["slug"] = slug

            ch["label"] = new_label
            self.refresh_table()
            self.table.selectRow(current_row)

    def _on_remove_channel(self):
        current_row = self.table.currentRow()
        if current_row < 0 or current_row >= len(self.channels):
            QMessageBox.warning(self, "Selection Required", "Please select a channel to remove.")
            return

        ch = self.channels[current_row]
        if ch["slug"] in SYSTEM_REQUIRED_SLUGS:
            QMessageBox.warning(
                self, "Protected System Channel",
                f"Cannot remove required system channel '{ch['label']}' (slug: '{ch['slug']}').\n"
                "You may rename it, but the system requires a Lap, Time, and Distance channel."
            )
            return

        del self.channels[current_row]
        self.refresh_table()

    def _on_save(self):
        self.state_manager.save_channel_defs(self.channels)
        QMessageBox.information(self, "Saved", "Standard channel list saved successfully.")
        self.accept()

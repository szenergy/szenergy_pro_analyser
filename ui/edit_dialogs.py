"""
Dialogs for the Edit Menu: Preset Manager and Channel Manager.
Clean layout without header labels, maximizing space for splitters and tables.
Fixes orphaned QComboBox cell widget accumulation in QTableWidget.
"""

from typing import Dict, List, Tuple
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QTableWidget, QTableWidgetItem, QComboBox, QPushButton, QLabel, QLineEdit,
    QMessageBox, QHeaderView, QSplitter, QAbstractItemView, QWidget, QInputDialog
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap, QIcon

from core.data_models import Session
from core.state_manager import StateManager, generate_slug


SYSTEM_REQUIRED_SLUGS = ["lap", "time", "distance"]


class PresetManagerDialog(QDialog):
    """Dialog for managing and editing saved channel map presets with Import Wizard-style ComboBoxes."""

    def __init__(self, state_manager: StateManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Channel Map Presets")
        self.setMinimumSize(720, 480)
        self.state_manager = state_manager

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
        self.preset_list.currentTextChanged.connect(self._on_preset_selected)
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
        for name in sorted(presets.keys()):
            self.preset_list.addItem(name)
        self.preset_list.blockSignals(False)

        if self.preset_list.count() > 0:
            self.preset_list.setCurrentRow(0)
            self._on_preset_selected(self.preset_list.currentItem().text())
        else:
            self.current_preset_name = ""
            self.preset_name_input.clear()
            self._clear_table()

    def _on_preset_selected(self, preset_name: str):
        self._clear_table()

        if not preset_name:
            self.current_preset_name = ""
            self.preset_name_input.clear()
            return

        self.current_preset_name = preset_name
        self.preset_name_input.setText(preset_name)

        presets = self.state_manager.load_presets()
        mapping = presets.get(preset_name, {})

        target_options = ["-- Skip --"] + self.state_manager.get_channel_labels()
        self.table.setRowCount(len(mapping))

        for row, (raw_col, mapped_col) in enumerate(mapping.items()):
            raw_item = QTableWidgetItem(raw_col)
            self.table.setItem(row, 0, raw_item)

            combo = QComboBox()
            combo.setEditable(True)
            combo.addItems(target_options)

            idx = combo.findText(mapped_col)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.setEditText(mapped_col)

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
                mapped_target = combo.currentText().strip()
                if raw_col and mapped_target and mapped_target != "-- Skip --":
                    mapping[raw_col] = mapped_target
        return mapping

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
        new_preset_name = self.preset_name_input.text().strip()
        if not new_preset_name:
            QMessageBox.warning(self, "Warning", "Please enter a valid preset name.")
            return

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

        if self.current_preset_name and self.current_preset_name != new_preset_name:
            self.state_manager.delete_preset(self.current_preset_name)

        self._save_new_custom_channels(mapping)
        self.state_manager.save_preset(new_preset_name, mapping)
        QMessageBox.information(self, "Saved", f"Preset '{new_preset_name}' saved successfully!")

        self.load_preset_list()
        items = self.preset_list.findItems(new_preset_name, Qt.MatchExactly)
        if items:
            self.preset_list.setCurrentItem(items[0])

    def _on_delete_preset(self):
        current_item = self.preset_list.currentItem()
        if not current_item:
            return

        preset_name = current_item.text()
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete preset '{preset_name}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.state_manager.delete_preset(preset_name)
            self.load_preset_list()


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

        base_slug = generate_slug(new_label)
        slug = base_slug
        counter = 1
        existing_slugs = [ch["slug"] for ch in self.channels]
        while slug in existing_slugs:
            slug = f"{base_slug}_{counter}"
            counter += 1

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
                base_slug = generate_slug(new_label)
                slug = base_slug
                counter = 1
                existing_slugs = [
                    other["slug"] for idx, other in enumerate(self.channels) if idx != current_row
                ]
                while slug in existing_slugs:
                    slug = f"{base_slug}_{counter}"
                    counter += 1
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


class RenameLegendLabelsDialog(QDialog):
    """
    Dialog allowing the user to rename the legend / curve labels that specify what the colors mean.
    """

    def __init__(
        self,
        selected_laps_info: List[Tuple[str, int, str]],
        sessions: Dict[str, Session],
        current_custom_labels: Dict[Tuple[str, int], str],
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("Rename Legend & Curve Labels")
        self.setMinimumSize(540, 360)
        self.selected_laps_info = selected_laps_info
        self.sessions = sessions
        self.current_custom_labels = current_custom_labels
        self.renamed_labels: Dict[Tuple[str, int], str] = {}
        self.inputs: Dict[Tuple[str, int], QLineEdit] = {}

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        info_label = QLabel(
            "<b>Rename Curve / Color Legend Labels:</b><br>"
            "Customize the legend labels that specify what each curve color represents on the graphs."
        )
        info_label.setTextFormat(Qt.RichText)
        layout.addWidget(info_label)

        # Table: Color & Session/Lap | Custom Legend Label
        self.table = QTableWidget(len(self.selected_laps_info), 2)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalHeaderLabels(["Curve / Session Lap", "Custom Legend Label"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        for row, (session_id, lap_num, color) in enumerate(self.selected_laps_info):
            session = self.sessions.get(session_id)
            session_name = session.name if session else session_id
            default_name = f"{session_name} L{lap_num}"

            # Color swatch icon + session lap info
            item_info = QTableWidgetItem(f"  {session_name} — Lap {lap_num}")
            item_info.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

            pixmap = QPixmap(16, 16)
            pixmap.fill(QColor(color))
            item_info.setIcon(QIcon(pixmap))
            self.table.setItem(row, 0, item_info)

            # Editable custom name
            current_val = self.current_custom_labels.get((session_id, lap_num), default_name)
            edit = QLineEdit(current_val)
            edit.setPlaceholderText(default_name)
            self.inputs[(session_id, lap_num)] = edit
            self.table.setCellWidget(row, 1, edit)

        layout.addWidget(self.table)

        # Action Buttons
        btn_layout = QHBoxLayout()

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self._on_reset_defaults)
        btn_layout.addWidget(reset_btn)

        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        apply_btn = QPushButton("Apply & Save")
        apply_btn.setStyleSheet("background-color: #00E676; color: black; font-weight: bold;")
        apply_btn.clicked.connect(self._on_apply)
        btn_layout.addWidget(apply_btn)

        layout.addLayout(btn_layout)

    def _on_reset_defaults(self):
        for (session_id, lap_num), edit in self.inputs.items():
            session = self.sessions.get(session_id)
            session_name = session.name if session else session_id
            edit.setText(f"{session_name} L{lap_num}")

    def _on_apply(self):
        for (session_id, lap_num), edit in self.inputs.items():
            txt = edit.text().strip()
            if not txt:
                session = self.sessions.get(session_id)
                session_name = session.name if session else session_id
                txt = f"{session_name} L{lap_num}"
            self.renamed_labels[(session_id, lap_num)] = txt

        self.accept()

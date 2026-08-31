"""
Dialog for managing remembered file-to-preset mappings with multi-selection removal.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QMessageBox, QHeaderView, QAbstractItemView,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle, QApplication
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette

from core.state_manager import StateManager


class PathElideLeftDelegate(QStyledItemDelegate):
    """Item delegate that explicitly elides text on the left (e.g. '.../folder/filename.csv') so file names stay visible."""

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        style = opt.widget.style() if opt.widget else QApplication.style()

        # 1. Draw item background / hover / selection highlights using current widget style
        style.drawPrimitive(QStyle.PE_PanelItemViewItem, opt, painter, opt.widget)

        # 2. Draw explicitly left-elided text aligned to the right
        full_text = index.data(Qt.DisplayRole) or ""
        if full_text:
            text_rect = style.subElementRect(QStyle.SE_ItemViewItemText, opt, opt.widget)
            text_rect.adjust(4, 0, -4, 0)

            fm = opt.fontMetrics
            elided = fm.elidedText(full_text, Qt.ElideLeft, text_rect.width())

            painter.save()
            painter.setFont(opt.font)

            if opt.state & QStyle.State_Selected:
                text_color = opt.palette.color(QPalette.HighlightedText)
            elif not (opt.state & QStyle.State_Enabled):
                text_color = opt.palette.color(QPalette.Disabled, QPalette.Text)
            else:
                text_color = opt.palette.color(QPalette.Text)

            painter.setPen(text_color)
            painter.drawText(text_rect, Qt.AlignRight | Qt.AlignVCenter, elided)
            painter.restore()


class FileMappingManagerDialog(QDialog):
    """Dialog for managing remembered file-to-preset mappings with multi-selection removal."""

    def __init__(self, state_manager: StateManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage File Mappings")
        self.setMinimumSize(680, 420)
        self.state_manager = state_manager

        self._init_ui()
        self.load_file_mappings()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Table Widget: 2 columns (File Path, Mapped Preset)
        self.table = QTableWidget(0, 2)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalHeaderLabels(["File Path", "Mapped Preset"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setTextElideMode(Qt.ElideLeft)
        self.table.setItemDelegateForColumn(0, PathElideLeftDelegate(self.table))
        layout.addWidget(self.table, 1)

        # Action Buttons Row
        btn_layout = QHBoxLayout()

        self.remove_btn = QPushButton("Remove Selected")
        self.remove_btn.setToolTip("Remove selected file mappings so the import wizard will prompt on next open")
        self.remove_btn.clicked.connect(self._on_remove_selected)
        btn_layout.addWidget(self.remove_btn)

        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def load_file_mappings(self):
        """Loads remembered file presets and populates the table."""
        file_mappings = self.state_manager.load_file_presets()
        self.table.setRowCount(len(file_mappings))

        for row, (file_path, preset_slug) in enumerate(sorted(file_mappings.items())):
            # Column 0: File Path (Right-aligned so file name is visible when path is long)
            path_item = QTableWidgetItem(file_path)
            path_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            path_item.setData(Qt.UserRole, file_path)
            path_item.setToolTip(file_path)
            path_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table.setItem(row, 0, path_item)

            # Column 1: Mapped Preset (Display Name, fallback to slug)
            preset_name = self.state_manager.get_preset_name_by_slug(preset_slug) or preset_slug
            preset_item = QTableWidgetItem(preset_name)
            preset_item.setToolTip(f"Preset Slug: {preset_slug}")
            preset_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table.setItem(row, 1, preset_item)

    def _on_remove_selected(self):
        """Removes selected file mappings."""
        selected_indexes = self.table.selectionModel().selectedRows()
        if not selected_indexes:
            QMessageBox.information(self, "No Selection", "Please select one or more file mappings to remove.")
            return

        count = len(selected_indexes)
        reply = QMessageBox.question(
            self, "Confirm Remove",
            f"Are you sure you want to remove the {count} selected file mapping(s)?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        paths_to_remove = []
        for index in selected_indexes:
            row = index.row()
            path_item = self.table.item(row, 0)
            if path_item:
                file_path = path_item.data(Qt.UserRole) or path_item.text()
                paths_to_remove.append(file_path)

        for file_path in paths_to_remove:
            self.state_manager.remove_file_preset(file_path)

        self.load_file_mappings()

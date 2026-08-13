"""
Left Sidebar widget containing Session/Lap tree and Channels selection list.
"""

from typing import Dict, List, Set, Tuple
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QLabel,
    QHeaderView, QAbstractItemView, QPushButton, QHBoxLayout
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor, QPixmap, QIcon

from core.data_models import Session, Lap


def create_color_icon(hex_color: str, size: int = 14) -> QIcon:
    """Utility to create a small colored square icon for lap trees."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(hex_color))
    return QIcon(pixmap)


def format_lap_time(seconds: float) -> str:
    """Format duration in seconds to M:SS.ms format."""
    if seconds <= 0:
        return "--:--.--"
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins}:{secs:05.2f}"


class SidebarWidget(QWidget):
    """Left sidebar managing sessions, laps selection, and channel visibility."""

    # Signal (session_id, lap_number, is_selected)
    lap_visibility_changed = Signal(str, int, bool)
    # Signal (set of selected channel names)
    channels_selection_changed = Signal(set)
    # Signal (session_id)
    session_remove_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sessions: Dict[str, Session] = {}
        self.selected_channels: Set[str] = set()

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # 1. Sessions & Laps Section
        layout.addWidget(QLabel("<b>Sessions & Laps</b>"))

        self.session_tree = QTreeWidget()
        self.session_tree.setHeaderLabels(["Session / Lap", "Time"])
        self.session_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.session_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.session_tree.itemChanged.connect(self._on_tree_item_changed)
        layout.addWidget(self.session_tree)

        # 2. Channels Section
        layout.addWidget(QLabel("<b>Available Channels</b>"))

        self.channel_tree = QTreeWidget()
        self.channel_tree.setHeaderLabels(["Channel Name"])
        self.channel_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.channel_tree.itemChanged.connect(self._on_channel_item_changed)
        layout.addWidget(self.channel_tree)

    def add_session(self, session: Session):
        """Adds a session to the sidebar tree."""
        self.sessions[session.id] = session

        # Add top-level Session item
        session_item = QTreeWidgetItem(self.session_tree)
        session_item.setText(0, session.name)
        session_item.setData(0, Qt.UserRole, ("session", session.id))
        session_item.setExpanded(True)

        # Add Laps as children
        for lap in session.laps:
            lap_item = QTreeWidgetItem(session_item)
            lap_item.setText(0, f"Lap {lap.lap_number}")
            lap_item.setText(1, format_lap_time(lap.duration))
            lap_item.setIcon(0, create_color_icon(lap.color))
            lap_item.setCheckState(0, Qt.Checked if lap.is_visible else Qt.Unchecked)
            lap_item.setData(0, Qt.UserRole, ("lap", session.id, lap.lap_number))

        self.update_available_channels()

    def remove_session(self, session_id: str):
        """Removes a session from the sidebar."""
        if session_id in self.sessions:
            del self.sessions[session_id]

        for i in range(self.session_tree.topLevelItemCount()):
            item = self.session_tree.topLevelItem(i)
            if item and item.data(0, Qt.UserRole) == ("session", session_id):
                self.session_tree.takeTopLevelItem(i)
                break

        self.update_available_channels()

    def update_available_channels(self):
        """Rebuilds the list of available channels across all loaded sessions."""
        self.channel_tree.blockSignals(True)
        self.channel_tree.clear()

        all_channels: Set[str] = set()
        for session in self.sessions.values():
            all_channels.update(session.channels)

        for channel_name in sorted(all_channels):
            item = QTreeWidgetItem(self.channel_tree)
            item.setText(0, channel_name)
            # Default check first 3 common channels like Speed, RPM
            is_checked = channel_name in self.selected_channels
            item.setCheckState(0, Qt.Checked if is_checked else Qt.Unchecked)

        self.channel_tree.blockSignals(False)

    def _on_tree_item_changed(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.UserRole)
        if not data or data[0] != "lap":
            return

        session_id, lap_number = data[1], data[2]
        is_checked = (item.checkState(0) == Qt.Checked)

        if session_id in self.sessions:
            lap = self.sessions[session_id].get_lap(lap_number)
            if lap:
                lap.is_visible = is_checked
                self.lap_visibility_changed.emit(session_id, lap_number, is_checked)

    def _on_channel_item_changed(self, item: QTreeWidgetItem, column: int):
        channel_name = item.text(0)
        is_checked = (item.checkState(0) == Qt.Checked)

        if is_checked:
            self.selected_channels.add(channel_name)
        else:
            self.selected_channels.discard(channel_name)

        self.channels_selection_changed.emit(set(self.selected_channels))

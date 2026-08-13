"""
Left Sidebar widget containing Session/Lap tree and Channels selection list.
Supports drag multi-selection, row highlighting (no checkboxes), smooth scrolling, and dynamic color allocation.
"""

from typing import Dict, List, Set, Tuple
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QLabel,
    QHeaderView, QAbstractItemView
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor, QPixmap, QIcon

from core.data_models import Session, Lap
from utils.constants import LAP_COLORS


def create_color_icon(hex_color: str, size: int = 14) -> QIcon:
    """Utility to create a small colored square icon for selected laps."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(hex_color))
    return QIcon(pixmap)


def create_empty_icon(size: int = 14) -> QIcon:
    """Utility to create a subtle gray square icon for unselected laps."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor("#4A4E57"))
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

    # Signal (list of tuples: [(session_id, lap_number, color_hex)])
    laps_selection_changed = Signal(list)
    # Signal (set of selected channel names)
    channels_selection_changed = Signal(set)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sessions: Dict[str, Session] = {}

        # Dynamic color pool tracking
        self.available_colors: List[str] = list(LAP_COLORS)
        self.allocated_colors: Dict[Tuple[str, int], str] = {}

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # 1. Sessions & Laps Section
        layout.addWidget(QLabel("<b>Sessions & Laps</b>"))

        self.session_tree = QTreeWidget()
        self.session_tree.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.session_tree.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.session_tree.setHeaderLabels(["Session / Lap", "Time"])
        self.session_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.session_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        
        self.session_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.session_tree.itemSelectionChanged.connect(self._on_lap_selection_changed)
        layout.addWidget(self.session_tree)

        # 2. Channels Section
        layout.addWidget(QLabel("<b>Available Channels</b>"))

        self.channel_tree = QTreeWidget()
        self.channel_tree.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.channel_tree.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.channel_tree.setHeaderLabels(["Channel Name"])
        self.channel_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        
        self.channel_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.channel_tree.itemSelectionChanged.connect(self._on_channel_selection_changed)
        layout.addWidget(self.channel_tree)

    def add_session(self, session: Session):
        """Adds a session to the sidebar tree without selecting any laps by default."""
        self.sessions[session.id] = session

        session_item = QTreeWidgetItem(self.session_tree)
        session_item.setText(0, session.name)
        session_item.setData(0, Qt.UserRole, ("session", session.id))
        session_item.setExpanded(True)

        for lap in session.laps:
            lap_item = QTreeWidgetItem(session_item)
            lap_item.setText(0, f"Lap {lap.lap_number}")
            lap_item.setText(1, format_lap_time(lap.duration))
            lap_item.setIcon(0, create_empty_icon())
            lap_item.setData(0, Qt.UserRole, ("lap", session.id, lap.lap_number))

        self.session_tree.clearSelection()
        self.update_available_channels()

    def remove_session(self, session_id: str):
        to_release = [key for key in self.allocated_colors if key[0] == session_id]
        for key in to_release:
            color = self.allocated_colors.pop(key)
            self.available_colors.append(color)

        if session_id in self.sessions:
            del self.sessions[session_id]

        for i in range(self.session_tree.topLevelItemCount()):
            item = self.session_tree.topLevelItem(i)
            if item and item.data(0, Qt.UserRole) == ("session", session_id):
                self.session_tree.takeTopLevelItem(i)
                break

        self.update_available_channels()
        self._on_lap_selection_changed()

    def update_available_channels(self):
        self.channel_tree.blockSignals(True)
        self.channel_tree.clear()

        all_channels: Set[str] = set()
        for session in self.sessions.values():
            all_channels.update(session.channels)

        for channel_name in sorted(all_channels):
            item = QTreeWidgetItem(self.channel_tree)
            item.setText(0, channel_name)

        self.channel_tree.clearSelection()
        self.channel_tree.blockSignals(False)

    def _on_lap_selection_changed(self):
        selected_items = self.session_tree.selectedItems()
        currently_selected_laps: Set[Tuple[str, int]] = set()

        for item in selected_items:
            data = item.data(0, Qt.UserRole)
            if data and data[0] == "lap":
                session_id, lap_num = data[1], data[2]
                currently_selected_laps.add((session_id, lap_num))

        deselected = set(self.allocated_colors.keys()) - currently_selected_laps
        for key in deselected:
            color = self.allocated_colors.pop(key)
            self.available_colors.insert(0, color)

        newly_selected = currently_selected_laps - set(self.allocated_colors.keys())
        for key in sorted(list(newly_selected)):
            if self.available_colors:
                color = self.available_colors.pop(0)
            else:
                color = "#%06x" % (hash(key) & 0xFFFFFF)
            self.allocated_colors[key] = color

        root_count = self.session_tree.topLevelItemCount()
        for r in range(root_count):
            session_item = self.session_tree.topLevelItem(r)
            for c in range(session_item.childCount()):
                child = session_item.child(c)
                data = child.data(0, Qt.UserRole)
                if data and data[0] == "lap":
                    key = (data[1], data[2])
                    if key in self.allocated_colors:
                        child.setIcon(0, create_color_icon(self.allocated_colors[key]))
                    else:
                        child.setIcon(0, create_empty_icon())

        result = [
            (session_id, lap_num, color)
            for (session_id, lap_num), color in self.allocated_colors.items()
        ]
        self.laps_selection_changed.emit(result)

    def _on_channel_selection_changed(self):
        selected_items = self.channel_tree.selectedItems()
        selected_channels = set(item.text(0) for item in selected_items)
        self.channels_selection_changed.emit(selected_channels)

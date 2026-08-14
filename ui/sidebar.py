"""
Left Sidebar widget containing Session/Lap tree and Channels selection list.
Supports drag multi-selection, row highlighting, dynamic color allocation,
channel search filtering, and context menu session management.
"""

from typing import Dict, List, Set, Tuple, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem, QLabel,
    QHeaderView, QAbstractItemView, QMessageBox, QLineEdit, QMenu
)
from PySide6.QtCore import Signal, Qt, QPoint
from PySide6.QtGui import QColor, QPixmap, QIcon, QAction

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
    # Signal (session_id string)
    session_removed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sessions: Dict[str, Session] = {}
        self.selected_channels: Set[str] = set()

        # Dynamic color pool tracking
        self.available_colors: List[str] = list(LAP_COLORS)
        self.allocated_colors: Dict[Tuple[str, int], str] = {}

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(6)

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
        self.session_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.session_tree.customContextMenuRequested.connect(self._show_session_context_menu)
        layout.addWidget(self.session_tree)

        # 2. Channels Section with Search Filter
        layout.addWidget(QLabel("<b>Available Channels</b>"))

        self.channel_search_input = QLineEdit()
        self.channel_search_input.setPlaceholderText("Filter channels...")
        self.channel_search_input.setClearButtonEnabled(True)
        self.channel_search_input.textChanged.connect(self._filter_channels)
        layout.addWidget(self.channel_search_input)

        self.channel_tree = QTreeWidget()
        self.channel_tree.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.channel_tree.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.channel_tree.setHeaderLabels(["Channel Name"])
        self.channel_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)

        self.channel_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.channel_tree.itemSelectionChanged.connect(self._on_channel_selection_changed)
        layout.addWidget(self.channel_tree)

    def _show_session_context_menu(self, pos: QPoint):
        item = self.session_tree.itemAt(pos)
        if not item:
            return

        data = item.data(0, Qt.UserRole)
        if not data:
            return

        menu = QMenu(self)

        if data[0] == "session":
            session_id = data[1]
            select_all_action = QAction("Select All Laps in Session", self)
            select_all_action.triggered.connect(lambda: self._select_all_session_laps(item, True))
            menu.addAction(select_all_action)

            deselect_all_action = QAction("Deselect All Laps in Session", self)
            deselect_all_action.triggered.connect(lambda: self._select_all_session_laps(item, False))
            menu.addAction(deselect_all_action)

            menu.addSeparator()

            remove_action = QAction("Remove Session", self)
            remove_action.triggered.connect(lambda: self.remove_session(session_id))
            menu.addAction(remove_action)

        elif data[0] == "lap":
            is_selected = item.isSelected()
            toggle_action = QAction("Deselect Lap" if is_selected else "Select Lap", self)
            toggle_action.triggered.connect(lambda: item.setSelected(not is_selected))
            menu.addAction(toggle_action)

        menu.exec(self.session_tree.viewport().mapToGlobal(pos))

    def _select_all_session_laps(self, session_item: QTreeWidgetItem, select: bool):
        max_laps = len(LAP_COLORS)
        for i in range(session_item.childCount()):
            child = session_item.child(i)
            if select and len(self.session_tree.selectedItems()) >= max_laps:
                QMessageBox.warning(
                    self, "Limit Reached",
                    f"You can select a maximum of {max_laps} laps simultaneously."
                )
                break
            child.setSelected(select)

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
        """Removes a session, frees its allocated colors, and notifies the application."""
        to_release = [key for key in self.allocated_colors if key[0] == session_id]
        for key in to_release:
            color = self.allocated_colors.pop(key)
            if color in LAP_COLORS and color not in self.available_colors:
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
        self.session_removed.emit(session_id)

    def clear_all_sessions(self):
        """Clears all sessions from the sidebar."""
        self.sessions.clear()
        self.allocated_colors.clear()
        self.available_colors = list(LAP_COLORS)
        self.session_tree.clear()
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
        self._filter_channels(self.channel_search_input.text())

    def _filter_channels(self, query: str):
        query = query.strip().lower()
        root_count = self.channel_tree.topLevelItemCount()
        for i in range(root_count):
            item = self.channel_tree.topLevelItem(i)
            if item:
                text = item.text(0).lower()
                item.setHidden(query != "" and query not in text)

    def _on_lap_selection_changed(self):
        selected_items = self.session_tree.selectedItems()
        currently_selected_laps: Set[Tuple[str, int]] = set()

        for item in selected_items:
            data = item.data(0, Qt.UserRole)
            if data and data[0] == "lap":
                session_id, lap_num = data[1], data[2]
                currently_selected_laps.add((session_id, lap_num))

        # Enforce maximum laps limit
        max_laps = len(LAP_COLORS)
        if len(currently_selected_laps) > max_laps:
            self.session_tree.blockSignals(True)
            for item in selected_items:
                data = item.data(0, Qt.UserRole)
                if data and data[0] == "lap":
                    key = (data[1], data[2])
                    if key not in self.allocated_colors:
                        item.setSelected(False)
                        break
            self.session_tree.blockSignals(False)
            QMessageBox.warning(
                self, "Limit Reached",
                f"You can select a maximum of {max_laps} laps simultaneously for comparison."
            )
            return

        # Reclaim deselected colors
        deselected = set(self.allocated_colors.keys()) - currently_selected_laps
        for key in deselected:
            color = self.allocated_colors.pop(key)
            if color in LAP_COLORS and color not in self.available_colors:
                # Maintain color palette order
                insert_idx = LAP_COLORS.index(color)
                self.available_colors.append(color)
                self.available_colors.sort(key=lambda c: LAP_COLORS.index(c) if c in LAP_COLORS else 999)

        # Allocate new colors
        newly_selected = currently_selected_laps - set(self.allocated_colors.keys())
        for key in sorted(list(newly_selected)):
            if self.available_colors:
                color = self.available_colors.pop(0)
            else:
                color = "#%06x" % (hash(key) & 0xFFFFFF)
            self.allocated_colors[key] = color

        # Update lap icon indicators
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

        # Limit maximum channels selectable to 6
        if len(selected_items) > 6:
            self.channel_tree.blockSignals(True)
            for item in selected_items:
                if item.text(0) not in self.selected_channels:
                    item.setSelected(False)
                    break
            self.channel_tree.blockSignals(False)
            QMessageBox.warning(self, "Limit Reached", "You can select a maximum of 6 channels simultaneously.")
            return

        self.selected_channels = set(item.text(0) for item in selected_items)
        self.channels_selection_changed.emit(self.selected_channels)

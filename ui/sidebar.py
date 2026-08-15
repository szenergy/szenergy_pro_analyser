"""
Left Sidebar widget containing Session/Lap tree and Channels selection list.
Supports embedded top menu bar, drag multi-selection, row highlighting,
dynamic color allocation, channel search filtering, and context menu session management.
"""

from typing import Dict, List, Set, Tuple, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem, QLabel,
    QHeaderView, QAbstractItemView, QMessageBox, QLineEdit, QMenu, QMenuBar, QFrame
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
    """Left sidebar managing sessions, laps selection, and channel visibility with integrated menu bar."""

    # Signal (list of tuples: [(session_id, lap_number, color_hex)])
    laps_selection_changed = Signal(list)
    # Signal (set of selected channel names)
    channels_selection_changed = Signal(set)
    # Signal (session_id string)
    session_removed = Signal(str)
    # Signal (session_id string)
    session_edit_mapping_requested = Signal(str)

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
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 0. Integrated Menu Bar Container at the top of the sidebar
        self.menu_container = QFrame()
        m_layout = QHBoxLayout(self.menu_container)
        m_layout.setContentsMargins(6, 4, 6, 4)
        m_layout.setSpacing(4)

        self.menu_bar = QMenuBar()
        m_layout.addWidget(self.menu_bar)
        m_layout.addStretch()
        layout.addWidget(self.menu_container)

        # Content Area
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(5, 5, 5, 5)
        content_layout.setSpacing(6)

        # 1. Sessions & Laps Section
        content_layout.addWidget(QLabel("<b>Sessions & Laps</b>"))

        self.session_tree = QTreeWidget()
        self.session_tree.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.session_tree.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.session_tree.setHeaderLabels(["Session / Lap", "Time"])
        self.session_tree.header().setStretchLastSection(False)
        self.session_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.session_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.session_tree.setIndentation(10)

        self.session_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.session_tree.itemSelectionChanged.connect(self._on_lap_selection_changed)
        self.session_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.session_tree.customContextMenuRequested.connect(self._show_session_context_menu)
        content_layout.addWidget(self.session_tree)

        # 2. Channels Section with Search Filter
        content_layout.addWidget(QLabel("<b>Available Channels</b>"))

        self.channel_search_input = QLineEdit()
        self.channel_search_input.setPlaceholderText("Filter channels...")
        self.channel_search_input.setClearButtonEnabled(True)
        self.channel_search_input.textChanged.connect(self._filter_channels)
        content_layout.addWidget(self.channel_search_input)

        self.channel_tree = QTreeWidget()
        self.channel_tree.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.channel_tree.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.channel_tree.setHeaderHidden(True)
        self.channel_tree.setIndentation(10)

        self.channel_tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.channel_tree.itemSelectionChanged.connect(self._on_channel_selection_changed)
        content_layout.addWidget(self.channel_tree)

        layout.addWidget(content_widget, 1)

    def apply_theme(self, is_dark: bool):
        bar_style = (
            "background-color: #24272C; border-bottom: 1px solid #2C3036;"
            if is_dark else
            "background-color: #E8ECEF; border-bottom: 1px solid #DEE2E6;"
        )
        self.menu_container.setStyleSheet(bar_style)

    def _create_session_context_menu(self, item: QTreeWidgetItem) -> Optional[QMenu]:
        """Creates the context menu for a session or lap tree item."""
        data = item.data(0, Qt.UserRole)
        if not data:
            return None

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

            edit_mapping_action = QAction("Edit Channel Mapping...", self)
            edit_mapping_action.triggered.connect(lambda: self.session_edit_mapping_requested.emit(session_id))
            menu.addAction(edit_mapping_action)

            menu.addSeparator()

            remove_action = QAction("Remove Session", self)
            remove_action.triggered.connect(lambda: self.remove_session(session_id))
            menu.addAction(remove_action)

        elif data[0] == "lap":
            is_selected = item.isSelected()
            toggle_action = QAction("Deselect Lap" if is_selected else "Select Lap", self)
            toggle_action.triggered.connect(lambda: item.setSelected(not is_selected))
            menu.addAction(toggle_action)

        return menu

    def _show_session_context_menu(self, pos: QPoint):
        item = self.session_tree.itemAt(pos)
        if not item:
            return
        menu = self._create_session_context_menu(item)
        if menu:
            menu.exec(self.session_tree.viewport().mapToGlobal(pos))

    def _select_all_session_laps(self, session_item: QTreeWidgetItem, select: bool):
        max_laps = len(LAP_COLORS)
        self.session_tree.blockSignals(True)
        for i in range(session_item.childCount()):
            child = session_item.child(i)
            if select and len(self.session_tree.selectedItems()) >= max_laps:
                break
            child.setSelected(select)
        self.session_tree.blockSignals(False)
        self._on_lap_selection_changed()

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
        self.update_available_channels()

    def update_session(self, updated_session: Session):
        """Updates an existing session in the sidebar tree, preserving lap selections and colors."""
        session_id = updated_session.id
        self.sessions[session_id] = updated_session

        target_session_item = None
        for i in range(self.session_tree.topLevelItemCount()):
            item = self.session_tree.topLevelItem(i)
            if item and item.data(0, Qt.UserRole) == ("session", session_id):
                target_session_item = item
                break

        if not target_session_item:
            self.add_session(updated_session)
            return

        target_session_item.setText(0, updated_session.name)

        # Remember currently selected lap numbers and their colors for this session
        selected_lap_info = {}
        for i in range(target_session_item.childCount()):
            child = target_session_item.child(i)
            if child.isSelected():
                lap_data = child.data(0, Qt.UserRole)
                if lap_data and len(lap_data) >= 3:
                    lap_num = lap_data[2]
                    selected_lap_info[lap_num] = self.allocated_colors.get((session_id, lap_num))

        self.session_tree.blockSignals(True)
        # Clear existing lap items and rebuild
        target_session_item.takeChildren()

        for lap in updated_session.laps:
            lap_item = QTreeWidgetItem(target_session_item)
            lap_item.setText(0, f"Lap {lap.lap_number}")
            lap_item.setText(1, format_lap_time(lap.duration))
            lap_item.setData(0, Qt.UserRole, ("lap", session_id, lap.lap_number))

            if lap.lap_number in selected_lap_info:
                color = selected_lap_info[lap.lap_number]
                if not color:
                    color = self._allocate_color((session_id, lap.lap_number))
                else:
                    self.allocated_colors[(session_id, lap.lap_number)] = color
                lap_item.setIcon(0, create_color_icon(color))
                lap_item.setSelected(True)
            else:
                lap_item.setIcon(0, create_empty_icon())

        self.session_tree.blockSignals(False)
        self.update_available_channels()
        self._on_lap_selection_changed()

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

        # Retain valid previously selected channels
        self.selected_channels = self.selected_channels.intersection(all_channels)

        for channel_name in sorted(all_channels):
            item = QTreeWidgetItem(self.channel_tree)
            item.setText(0, channel_name)
            if channel_name in self.selected_channels:
                item.setSelected(True)

        self.channel_tree.blockSignals(False)
        self._filter_channels(self.channel_search_input.text())
        self.channels_selection_changed.emit(self.selected_channels)

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
        lap_items: List[QTreeWidgetItem] = []
        currently_selected_laps: Set[Tuple[str, int]] = set()

        for item in selected_items:
            data = item.data(0, Qt.UserRole)
            if data and data[0] == "lap":
                lap_items.append(item)
                session_id, lap_num = data[1], data[2]
                currently_selected_laps.add((session_id, lap_num))

        # Enforce maximum laps limit
        max_laps = len(LAP_COLORS)
        if len(currently_selected_laps) > max_laps:
            self.session_tree.blockSignals(True)
            # Prioritize laps that already have allocated colors
            kept_items = []
            for item in lap_items:
                data = item.data(0, Qt.UserRole)
                key = (data[1], data[2])
                if key in self.allocated_colors and len(kept_items) < max_laps:
                    kept_items.append(item)

            for item in lap_items:
                if len(kept_items) >= max_laps:
                    break
                if item not in kept_items:
                    kept_items.append(item)

            for item in lap_items:
                if item not in kept_items:
                    item.setSelected(False)
            self.session_tree.blockSignals(False)

            QMessageBox.warning(
                self, "Limit Reached",
                f"You can select a maximum of {max_laps} laps simultaneously for comparison."
            )
            currently_selected_laps = set(
                (item.data(0, Qt.UserRole)[1], item.data(0, Qt.UserRole)[2])
                for item in kept_items
            )

        # Reclaim deselected colors
        deselected = set(self.allocated_colors.keys()) - currently_selected_laps
        for key in deselected:
            color = self.allocated_colors.pop(key)
            if color in LAP_COLORS and color not in self.available_colors:
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

        result = sorted([
            (session_id, lap_num, color)
            for (session_id, lap_num), color in self.allocated_colors.items()
        ], key=lambda x: (x[0], x[1]))
        self.laps_selection_changed.emit(result)

    def _on_channel_selection_changed(self):
        selected_items = self.channel_tree.selectedItems()

        # Limit maximum channels selectable to 6
        if len(selected_items) > 6:
            self.channel_tree.blockSignals(True)
            # Prioritize already selected channels
            kept_items = [item for item in selected_items if item.text(0) in self.selected_channels]
            for item in selected_items:
                if len(kept_items) >= 6:
                    break
                if item not in kept_items:
                    kept_items.append(item)

            for item in selected_items:
                if item not in kept_items:
                    item.setSelected(False)
            self.channel_tree.blockSignals(False)
            QMessageBox.warning(self, "Limit Reached", "You can select a maximum of 6 channels simultaneously.")
            selected_items = kept_items

        self.selected_channels = set(item.text(0) for item in selected_items)
        self.channels_selection_changed.emit(self.selected_channels)

"""
Left Sidebar widget containing Session/Lap tree and Channels selection list.
Supports embedded top menu bar, drag multi-selection, row highlighting,
dynamic color allocation, channel search filtering, and context menu session management.
"""

from typing import Dict, List, Set, Tuple, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem, QLabel,
    QHeaderView, QAbstractItemView, QMessageBox, QLineEdit, QMenu, QMenuBar, QFrame,
    QGridLayout, QPushButton
)
from PySide6.QtCore import Signal, Qt, QPoint, QTimer, QEvent
from PySide6.QtGui import QColor, QPixmap, QIcon, QAction

from core.data_models import Session, Lap
from utils.constants import LAP_COLORS, MAX_SELECTED_CHANNELS


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


class LapColorPickerPopup(QFrame):
    """
    Compact popup displaying a grid of color swatches from LAP_COLORS.
    Clicking a swatch emits color_selected(str) and closes the popup.
    """
    color_selected = Signal(str)

    def __init__(self, current_color: str = "", parent=None, is_dark: bool = True):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.current_color = current_color
        self.is_dark = is_dark

        bg_color = "#1E2125" if is_dark else "#FFFFFF"
        border_color = "#3A3F47" if is_dark else "#CED4DA"
        text_color = "#E0E0E0" if is_dark else "#212529"

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 6px;
            }}
            QLabel {{
                color: {text_color};
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 11px;
                font-weight: bold;
                border: none;
                background: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(8)

        title_lbl = QLabel("Select Lap Color")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        grid = QGridLayout()
        grid.setSpacing(6)

        columns = 4
        for idx, hex_color in enumerate(LAP_COLORS):
            row = idx // columns
            col = idx % columns

            btn = QPushButton()
            btn.setFixedSize(26, 26)
            btn.setCursor(Qt.PointingHandCursor)
            is_current = (hex_color.upper() == current_color.upper())
            border_style = "2px solid #FFFFFF" if (is_current and is_dark) else ("2px solid #000000" if is_current else f"1px solid {border_color}")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {hex_color};
                    border: {border_style};
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    border: 2px solid {"#00E676" if is_dark else "#00C853"};
                }}
            """)
            btn.setToolTip(hex_color)
            btn.clicked.connect(lambda _, c=hex_color: self._on_color_clicked(c))
            grid.addWidget(btn, row, col)

        layout.addLayout(grid)

    def _on_color_clicked(self, color: str):
        self.color_selected.emit(color)
        self.close()


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

    def __init__(self, parent=None, state_manager=None):
        super().__init__(parent)
        self.state_manager = state_manager
        self.sessions: Dict[str, Session] = {}
        self.selected_channels: Set[str] = set()
        self.is_dark: bool = True

        # Dynamic color pool tracking
        self.available_colors: List[str] = list(LAP_COLORS)
        self.allocated_colors: Dict[Tuple[str, int], str] = {}

        # Defer updates while user is interacting (mouse drag / rapid keyboard selection)
        self._is_mouse_selecting: bool = False
        self._pending_lap_selection: bool = False
        self._pending_channel_selection: bool = False

        self._selection_debounce_timer = QTimer(self)
        self._selection_debounce_timer.setSingleShot(True)
        self._selection_debounce_timer.setInterval(75)
        self._selection_debounce_timer.timeout.connect(self._flush_pending_selections)

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

        # Install event filters after all widgets are initialized
        self.session_tree.viewport().installEventFilter(self)
        self.channel_tree.viewport().installEventFilter(self)

    def eventFilter(self, watched, event):
        session_vp = getattr(self, "session_tree", None)
        channel_vp = getattr(self, "channel_tree", None)
        session_vp = session_vp.viewport() if session_vp is not None else None
        channel_vp = channel_vp.viewport() if channel_vp is not None else None

        if watched is not None and watched == session_vp:
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                item = self.session_tree.itemAt(pos)
                if item:
                    data = item.data(0, Qt.UserRole)
                    if data and data[0] == "lap":
                        session_id, lap_num = data[1], data[2]
                        key = (session_id, lap_num)
                        if key in self.allocated_colors:
                            item_rect = self.session_tree.visualItemRect(item)
                            # Check if click is on the color icon (within 28px of item_rect.left())
                            if item_rect.left() <= pos.x() <= item_rect.left() + 28:
                                self._show_color_picker_for_lap(session_id, lap_num, item_rect)
                                return True

        if watched is not None and watched in (session_vp, channel_vp):
            if event.type() == QEvent.MouseButtonPress:
                self._is_mouse_selecting = True
            elif event.type() == QEvent.MouseButtonRelease:
                self._is_mouse_selecting = False
                self._flush_pending_selections()
        return super().eventFilter(watched, event)

    def _show_color_picker_for_lap(self, session_id: str, lap_num: int, item_rect):
        """Displays the LapColorPickerPopup next to the lap's color icon."""
        current_color = self.allocated_colors.get((session_id, lap_num), "")
        popup = LapColorPickerPopup(
            current_color=current_color,
            parent=self.session_tree.viewport(),
            is_dark=getattr(self, "is_dark", True)
        )
        popup.color_selected.connect(lambda c: self.set_lap_color(session_id, lap_num, c))

        # Position popup directly below the icon
        global_pos = self.session_tree.viewport().mapToGlobal(QPoint(item_rect.left(), item_rect.bottom() + 2))
        popup.move(global_pos)
        popup.show()

    def set_lap_color(self, session_id: str, lap_num: int, new_color: str):
        """Changes the assigned color for a specific lap without modifying selection."""
        key = (session_id, lap_num)
        self.allocated_colors[key] = new_color

        # Update the tree item icon
        root_count = self.session_tree.topLevelItemCount()
        for r in range(root_count):
            session_item = self.session_tree.topLevelItem(r)
            s_data = session_item.data(0, Qt.UserRole)
            if s_data and s_data[0] == "session" and s_data[1] == session_id:
                for c in range(session_item.childCount()):
                    child = session_item.child(c)
                    c_data = child.data(0, Qt.UserRole)
                    if c_data and c_data[0] == "lap" and c_data[2] == lap_num:
                        child.setIcon(0, create_color_icon(new_color))
                        break
                break

        # Flush selection changed signal immediately
        self._pending_lap_selection = True
        self._flush_pending_selections()

    def _flush_pending_selections(self):
        """Flushes any pending lap or channel selection signals to update graphs once user finished selecting."""
        self._selection_debounce_timer.stop()
        if self._pending_lap_selection:
            self._pending_lap_selection = False
            result = sorted([
                (session_id, lap_num, color)
                for (session_id, lap_num), color in self.allocated_colors.items()
            ], key=lambda x: (x[0], x[1]))
            self.laps_selection_changed.emit(result)

        if self._pending_channel_selection:
            self._pending_channel_selection = False
            self.channels_selection_changed.emit(self.selected_channels)

    def apply_theme(self, is_dark: bool):
        self.is_dark = is_dark
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
            session_id, lap_num = data[1], data[2]
            key = (session_id, lap_num)
            is_selected = item.isSelected()
            toggle_action = QAction("Deselect Lap" if is_selected else "Select Lap", self)
            toggle_action.triggered.connect(lambda: item.setSelected(not is_selected))
            menu.addAction(toggle_action)

            if key in self.allocated_colors:
                menu.addSeparator()
                color_menu = menu.addMenu("Change Color")
                for color_hex in LAP_COLORS:
                    c_act = QAction(create_color_icon(color_hex), color_hex, self)
                    c_act.triggered.connect(lambda _, c=color_hex, s=session_id, l=lap_num: self.set_lap_color(s, l, c))
                    color_menu.addAction(c_act)

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
        self._on_lap_selection_changed(immediate=True)

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
        self._on_lap_selection_changed(immediate=True)

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
        self._on_lap_selection_changed(immediate=True)
        self.session_removed.emit(session_id)

    def clear_all_sessions(self):
        """Clears all sessions from the sidebar."""
        self.sessions.clear()
        self.allocated_colors.clear()
        self.available_colors = list(LAP_COLORS)
        self.session_tree.clear()
        self.update_available_channels()
        self._on_lap_selection_changed(immediate=True)

    def update_available_channels(self):
        self.channel_tree.blockSignals(True)
        self.channel_tree.clear()

        all_channels: Set[str] = set()
        for session in self.sessions.values():
            all_channels.update(session.channels)

        # Retain valid previously selected channels
        self.selected_channels = self.selected_channels.intersection(all_channels)

        for channel_slug in sorted(all_channels):
            item = QTreeWidgetItem(self.channel_tree)
            display_label = channel_slug
            if self.state_manager:
                display_label = self.state_manager.get_label_by_slug(channel_slug, channel_slug)
            item.setText(0, display_label)
            item.setData(0, Qt.UserRole, channel_slug)
            if channel_slug in self.selected_channels:
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

    def _on_lap_selection_changed(self, immediate: bool = False):
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
            self.allocated_colors.pop(key, None)

        # Allocate new colors
        newly_selected = currently_selected_laps - set(self.allocated_colors.keys())
        for key in sorted(list(newly_selected)):
            used_colors = set(self.allocated_colors.values())
            unused = [c for c in LAP_COLORS if c not in used_colors]
            if unused:
                color = unused[0]
            else:
                color = LAP_COLORS[len(self.allocated_colors) % len(LAP_COLORS)]
            self.allocated_colors[key] = color

        self.available_colors = [c for c in LAP_COLORS if c not in self.allocated_colors.values()]

        # Update lap icon indicators immediately so tree UI is responsive
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

        self._pending_lap_selection = True
        if immediate:
            self._flush_pending_selections()
        elif self._is_mouse_selecting:
            # User is actively dragging mouse; defer emission until mouse release (with fallback timer)
            self._selection_debounce_timer.start(150)
        else:
            # User clicked or navigates with keys; debounce to avoid spamming graph rebuilds
            self._selection_debounce_timer.start(50)

    def _on_channel_selection_changed(self, immediate: bool = False):
        selected_items = self.channel_tree.selectedItems()

        # Limit maximum channels selectable
        if len(selected_items) > MAX_SELECTED_CHANNELS:
            self.channel_tree.blockSignals(True)
            # Prioritize already selected channels
            kept_items = [item for item in selected_items if item.data(0, Qt.UserRole) in self.selected_channels]
            for item in selected_items:
                if len(kept_items) >= MAX_SELECTED_CHANNELS:
                    break
                if item not in kept_items:
                    kept_items.append(item)

            for item in selected_items:
                if item not in kept_items:
                    item.setSelected(False)
            self.channel_tree.blockSignals(False)
            QMessageBox.warning(self, "Limit Reached", f"You can select a maximum of {MAX_SELECTED_CHANNELS} channels simultaneously.")
            selected_items = kept_items

        self.selected_channels = set()
        for item in selected_items:
            slug = item.data(0, Qt.UserRole)
            if slug:
                self.selected_channels.add(slug)

        self._pending_channel_selection = True
        if immediate:
            self._flush_pending_selections()
        elif self._is_mouse_selecting:
            self._selection_debounce_timer.start(150)
        else:
            self._selection_debounce_timer.start(50)

    def get_selected_laps(self) -> Dict[str, List[int]]:
        """Returns a mapping of session_id to list of selected lap numbers."""
        result: Dict[str, List[int]] = {}
        for (session_id, lap_num) in self.allocated_colors.keys():
            if session_id not in result:
                result[session_id] = []
            result[session_id].append(lap_num)
        return result

    def select_laps_for_session(self, session_id: str, lap_numbers: List[int]):
        """Programmatically selects specific lap numbers for a given session."""
        target_session_item = None
        for i in range(self.session_tree.topLevelItemCount()):
            item = self.session_tree.topLevelItem(i)
            if item and item.data(0, Qt.UserRole) == ("session", session_id):
                target_session_item = item
                break

        if not target_session_item:
            return

        self.session_tree.blockSignals(True)
        for i in range(target_session_item.childCount()):
            child = target_session_item.child(i)
            data = child.data(0, Qt.UserRole)
            if data and len(data) >= 3:
                lap_num = data[2]
                if lap_num in lap_numbers:
                    child.setSelected(True)
                else:
                    child.setSelected(False)
        self.session_tree.blockSignals(False)
        self._on_lap_selection_changed(immediate=True)

    def restore_selected_laps(self, lap_entries: List[Tuple[str, int, Optional[str]]]):
        """
        Restores exact lap selections and their allocated colors across all sessions in exact order.
        lap_entries: List of (session_id, lap_number, color_hex)
        """
        self.session_tree.blockSignals(True)

        # Clear existing allocations and reset available colors
        self.allocated_colors.clear()
        self.available_colors = list(LAP_COLORS)

        # Deselect all items in session tree
        root_count = self.session_tree.topLevelItemCount()
        for r in range(root_count):
            session_item = self.session_tree.topLevelItem(r)
            for c in range(session_item.childCount()):
                child = session_item.child(c)
                child.setSelected(False)
                child.setIcon(0, create_empty_icon())

        # Map (session_id, lap_num) -> tree item
        item_map = {}
        for r in range(root_count):
            session_item = self.session_tree.topLevelItem(r)
            s_data = session_item.data(0, Qt.UserRole)
            if s_data and s_data[0] == "session":
                s_id = s_data[1]
                for c in range(session_item.childCount()):
                    child = session_item.child(c)
                    c_data = child.data(0, Qt.UserRole)
                    if c_data and c_data[0] == "lap":
                        item_map[(s_id, c_data[2])] = child

        # Apply selections in the exact order with their exact colors
        for session_id, lap_num, color in lap_entries:
            key = (session_id, lap_num)
            if key in item_map:
                assigned_color = color
                if not assigned_color:
                    used_colors = set(self.allocated_colors.values())
                    unused = [c for c in LAP_COLORS if c not in used_colors]
                    assigned_color = unused[0] if unused else LAP_COLORS[len(self.allocated_colors) % len(LAP_COLORS)]

                self.allocated_colors[key] = assigned_color
                child_item = item_map[key]
                child_item.setSelected(True)
                child_item.setIcon(0, create_color_icon(assigned_color))

        self.available_colors = [c for c in LAP_COLORS if c not in self.allocated_colors.values()]
        self.session_tree.blockSignals(False)

        self._pending_lap_selection = True
        self._flush_pending_selections()

    def get_selected_channels(self) -> List[str]:
        """Returns the list of currently selected channel slugs."""
        return sorted(list(self.selected_channels))

    def set_selected_channels(self, channel_slugs: List[str]):
        """Sets the selected channels in the channel tree and triggers selection change."""
        self.channel_tree.blockSignals(True)
        target_slugs = set(channel_slugs)
        self.selected_channels = set()

        root_count = self.channel_tree.topLevelItemCount()
        for i in range(root_count):
            item = self.channel_tree.topLevelItem(i)
            if item:
                slug = item.data(0, Qt.UserRole)
                if slug in target_slugs:
                    item.setSelected(True)
                    self.selected_channels.add(slug)
                else:
                    item.setSelected(False)

        self.channel_tree.blockSignals(False)
        self._pending_channel_selection = True
        self._flush_pending_selections()

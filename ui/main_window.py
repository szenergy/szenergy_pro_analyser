"""
Main application window organizing the menu bar, left sidebar, and stacked graph views.
"""

import uuid
from typing import Dict
from PySide6.QtWidgets import (
    QMainWindow, QSplitter, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QGuiApplication, QAction, QDesktopServices

from core.state_manager import StateManager
from core.file_parser import get_file_columns_and_preview, parse_session
from core.data_models import Session
from ui.sidebar import SidebarWidget
from ui.graph_view import GraphViewWidget
from ui.import_wizard import ImportWizardDialog, PresetPreviewDialog
from ui.edit_dialogs import PresetManagerDialog, ChannelManagerDialog
from utils.constants import APP_NAME, APP_VERSION


class MainWindow(QMainWindow):
    """Main window of the SZenergy Pro Analyser desktop application."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(1200, 750)

        self.state_manager = StateManager()
        self.sessions: Dict[str, Session] = {}

        self._init_menu()
        self._init_ui()
        self.update_system_theme()
        self._sync_x_axis_labels()

    def _init_menu(self):
        menu_bar = self.menuBar()

        # 1. File Menu
        file_menu = menu_bar.addMenu("&File")

        open_action = QAction("&Open Log File...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._on_open_file)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        open_config_action = QAction("Open &Config Folder", self)
        open_config_action.triggered.connect(self._on_open_config_folder)
        file_menu.addAction(open_config_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 2. Edit Menu
        edit_menu = menu_bar.addMenu("&Edit")

        manage_presets_action = QAction("Manage Saved &Presets...", self)
        manage_presets_action.triggered.connect(self._on_manage_presets)
        edit_menu.addAction(manage_presets_action)

        manage_channels_action = QAction("Manage Standard &Channel List...", self)
        manage_channels_action.triggered.connect(self._on_manage_channels)
        edit_menu.addAction(manage_channels_action)

    def _init_ui(self):
        main_splitter = QSplitter(Qt.Horizontal)

        # Left Sidebar
        self.sidebar = SidebarWidget()
        self.sidebar.laps_selection_changed.connect(self._on_laps_selection_changed)
        self.sidebar.channels_selection_changed.connect(self._on_channels_selection_changed)
        main_splitter.addWidget(self.sidebar)

        # Right Graph View
        self.graph_view = GraphViewWidget()
        main_splitter.addWidget(self.graph_view)

        main_splitter.setSizes([300, 900])
        self.setCentralWidget(main_splitter)

    def _sync_x_axis_labels(self):
        time_label = self.state_manager.get_time_label()
        dist_label = self.state_manager.get_distance_label()
        self.graph_view.set_x_axis_labels(time_label, dist_label)

    def update_system_theme(self):
        hints = QGuiApplication.styleHints()
        is_dark = True
        if hasattr(hints, "colorScheme"):
            is_dark = (hints.colorScheme() == Qt.ColorScheme.Dark)
        
        self.graph_view.apply_theme(is_dark)

    def _on_open_config_folder(self):
        """Opens the application config directory in the OS native file manager."""
        config_dir = self.state_manager.config_dir
        QDesktopServices.openUrl(QUrl.fromLocalFile(config_dir))

    def _on_manage_presets(self):
        dialog = PresetManagerDialog(self.state_manager, parent=self)
        dialog.exec()

    def _on_manage_channels(self):
        dialog = ChannelManagerDialog(self.state_manager, parent=self)
        if dialog.exec():
            self._sync_x_axis_labels()

    def _on_open_file(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Telemetry Log Files",
            "",
            "Supported Log Files (*.csv *.xlsx *.xls *.tdms);;CSV Files (*.csv);;Excel Files (*.xlsx *.xls);;TDMS Files (*.tdms);;All Files (*)"
        )

        for path in file_paths:
            self._import_file(path)

    def _import_file(self, file_path: str):
        try:
            raw_columns, preview_df = get_file_columns_and_preview(file_path)
        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"Failed to read file '{file_path}':\n{str(e)}")
            return

        matching_preset = self.state_manager.find_matching_preset(raw_columns)
        chosen_mapping = None

        if matching_preset:
            presets = self.state_manager.load_presets()
            preset_map = presets.get(matching_preset, {})

            preview_dialog = PresetPreviewDialog(
                file_path=file_path,
                preset_name=matching_preset,
                mapping=preset_map,
                preview_df=preview_df,
                parent=self
            )

            res = preview_dialog.exec()
            if preview_dialog.selected_action == PresetPreviewDialog.ACTION_APPLY:
                chosen_mapping = preset_map
            elif preview_dialog.selected_action == PresetPreviewDialog.ACTION_EDIT:
                chosen_mapping = None
            else:
                return

        if not chosen_mapping:
            wizard = ImportWizardDialog(
                file_path=file_path,
                raw_columns=raw_columns,
                preview_df=preview_df,
                state_manager=self.state_manager,
                initial_preset=matching_preset,
                parent=self
            )
            if wizard.exec() == ImportWizardDialog.Accepted:
                chosen_mapping = wizard.result_mapping
            else:
                return

        if not chosen_mapping:
            return

        session_id = str(uuid.uuid4())
        try:
            session = parse_session(
                file_path=file_path,
                mapping=chosen_mapping,
                session_id=session_id,
                lap_label=self.state_manager.get_lap_label(),
                time_label=self.state_manager.get_time_label(),
                dist_label=self.state_manager.get_distance_label()
            )
        except Exception as e:
            QMessageBox.critical(self, "Parse Error", f"Failed to parse log file:\n{str(e)}")
            return

        self.sessions[session_id] = session
        self.sidebar.add_session(session)
        self.graph_view.set_sessions(self.sessions)

    def _on_laps_selection_changed(self, selected_laps_info: list):
        self.graph_view.set_selected_laps(selected_laps_info)

    def _on_channels_selection_changed(self, selected_channels: set):
        self.graph_view.set_selected_channels(selected_channels)

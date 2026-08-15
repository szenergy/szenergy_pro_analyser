"""
Main application window organizing the menu bar, left sidebar, and stacked graph views.
Includes robust background worker lifecycle management and centralized session handling.
"""

import os
import uuid
from typing import Dict, List
from PySide6.QtWidgets import (
    QMainWindow, QSplitter, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt, QUrl, QThread
from PySide6.QtGui import QGuiApplication, QAction, QDesktopServices

from core.state_manager import StateManager
from core.file_parser import get_file_columns_and_preview, parse_session, parse_session_from_dataframe
from core.data_models import Session
from ui.sidebar import SidebarWidget
from ui.graph_view import GraphViewWidget
from ui.import_wizard import ImportWizardDialog, PresetPreviewDialog
from ui.edit_dialogs import PresetManagerDialog, ChannelManagerDialog
from ui.loading_dialog import LoadingDialog, FilePreviewWorker, FileParseWorker
from utils.constants import APP_NAME, APP_VERSION


class MainWindow(QMainWindow):
    """Main window of the SZenergy Pro Analyser desktop application."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(1200, 750)

        self.state_manager = StateManager()
        
        from core.migrations import run_migrations
        run_migrations(self.state_manager)
        
        self.sessions: Dict[str, Session] = {}

        self._init_ui()
        self._init_menu()
        self.update_system_theme()
        self._sync_x_axis_labels()

    def _init_menu(self):
        menu_bar = self.sidebar.menu_bar

        # 1. File Menu
        file_menu = menu_bar.addMenu("&File")

        open_action = QAction("&Open Log File...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._on_open_file)
        file_menu.addAction(open_action)
        self.addAction(open_action)

        clear_action = QAction("&Clear Workspace", self)
        clear_action.triggered.connect(self._on_clear_workspace)
        file_menu.addAction(clear_action)
        self.addAction(clear_action)

        file_menu.addSeparator()

        open_config_action = QAction("Open &Config Folder", self)
        open_config_action.triggered.connect(self._on_open_config_folder)
        file_menu.addAction(open_config_action)
        self.addAction(open_config_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        self.addAction(exit_action)

        # 2. Edit Menu
        edit_menu = menu_bar.addMenu("&Edit")

        manage_presets_action = QAction("Manage Saved &Presets...", self)
        manage_presets_action.triggered.connect(self._on_manage_presets)
        edit_menu.addAction(manage_presets_action)
        self.addAction(manage_presets_action)

        manage_channels_action = QAction("Manage Standard &Channel List...", self)
        manage_channels_action.triggered.connect(self._on_manage_channels)
        edit_menu.addAction(manage_channels_action)
        self.addAction(manage_channels_action)

    def _init_ui(self):
        main_splitter = QSplitter(Qt.Horizontal)

        # Left Sidebar
        self.sidebar = SidebarWidget(state_manager=self.state_manager)
        self.sidebar.laps_selection_changed.connect(self._on_laps_selection_changed)
        self.sidebar.channels_selection_changed.connect(self._on_channels_selection_changed)
        self.sidebar.session_removed.connect(self._on_session_removed)
        self.sidebar.session_edit_mapping_requested.connect(self._on_edit_session_mapping)
        main_splitter.addWidget(self.sidebar)

        # Right Graph View
        self.graph_view = GraphViewWidget(state_manager=self.state_manager)
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

        self.sidebar.apply_theme(is_dark)
        self.graph_view.apply_theme(is_dark)

    def _on_open_config_folder(self):
        config_dir = self.state_manager.config_dir
        QDesktopServices.openUrl(QUrl.fromLocalFile(config_dir))

    def _on_manage_presets(self):
        dialog = PresetManagerDialog(self.state_manager, parent=self)
        dialog.exec()

    def _on_manage_channels(self):
        dialog = ChannelManagerDialog(self.state_manager, parent=self)
        if dialog.exec():
            self._sync_x_axis_labels()

    def _on_clear_workspace(self):
        if not self.sessions:
            return
        reply = QMessageBox.question(
            self, "Clear Workspace",
            "Are you sure you want to unload all telemetry sessions?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.sessions.clear()
            self.sidebar.clear_all_sessions()
            self.graph_view.custom_lap_labels.clear()
            self.graph_view.set_sessions(self.sessions)

    def _on_session_removed(self, session_id: str):
        if session_id in self.sessions:
            del self.sessions[session_id]
        stale_keys = [k for k in self.graph_view.custom_lap_labels if k[0] == session_id]
        for k in stale_keys:
            del self.graph_view.custom_lap_labels[k]
        self.graph_view.set_sessions(self.sessions)

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
        """Processes file import using background QThread workers and loading dialogs."""
        filename = os.path.basename(file_path)

        # Do not let the user import the same file multiple times
        for session in self.sessions.values():
            if os.path.abspath(session.file_path) == os.path.abspath(file_path):
                QMessageBox.warning(
                    self, "Already Loaded",
                    f"The file '{filename}' is already loaded in the workspace."
                )
                return

        # 1. Background Header Reading
        preview_worker = FilePreviewWorker(file_path)
        preview_dialog = LoadingDialog(
            f"Inspecting headers for '{filename}'...\nPlease wait.",
            worker=preview_worker,
            parent=self
        )

        if not preview_dialog.exec_worker():
            if preview_dialog.error_message:
                QMessageBox.critical(self, "Import Error", f"Failed to read file '{file_path}':\n{preview_dialog.error_message}")
            return

        if not preview_dialog.result_data:
            return

        raw_columns, preview_df = preview_dialog.result_data

        matching_preset = self.state_manager.find_matching_preset(raw_columns)
        chosen_mapping = None
        applied_preset_name = matching_preset

        if matching_preset:
            presets = self.state_manager.load_presets()
            preset_map = presets.get(matching_preset, {})

            preview_dlg = PresetPreviewDialog(
                file_path=file_path,
                preset_name=matching_preset,
                mapping=preset_map,
                raw_columns=raw_columns,
                state_manager=self.state_manager,
                parent=self
            )

            res = preview_dlg.exec()
            if preview_dlg.selected_action == PresetPreviewDialog.ACTION_APPLY:
                chosen_mapping = preview_dlg.get_filtered_mapping()
                applied_preset_name = preview_dlg.selected_preset_name
            elif preview_dlg.selected_action == PresetPreviewDialog.ACTION_EDIT:
                chosen_mapping = None
                applied_preset_name = preview_dlg.selected_preset_name
            else:
                return

        if not chosen_mapping:
            wizard = ImportWizardDialog(
                file_path=file_path,
                raw_columns=raw_columns,
                preview_df=preview_df,
                state_manager=self.state_manager,
                initial_preset=applied_preset_name,
                parent=self
            )
            if wizard.exec() == ImportWizardDialog.Accepted:
                chosen_mapping = wizard.result_mapping
                applied_preset_name = wizard.result_preset_name or applied_preset_name
            else:
                return

        if not chosen_mapping:
            return

        # 2. Background Log Data Parsing (initial load from disk)
        session_id = str(uuid.uuid4())
        parse_worker = FileParseWorker(
            file_path=file_path,
            mapping=chosen_mapping,
            session_id=session_id,
            lap_label=self.state_manager.get_lap_label(),
            time_label=self.state_manager.get_time_label(),
            dist_label=self.state_manager.get_distance_label(),
        )

        parse_dialog = LoadingDialog(
            f"Parsing log data for '{filename}'...\nPlease wait.",
            worker=parse_worker,
            parent=self
        )

        if not parse_dialog.exec_worker():
            if parse_dialog.error_message:
                QMessageBox.critical(self, "Parse Error", f"Failed to parse log file:\n{parse_dialog.error_message}")
            return

        session = parse_dialog.result_data
        if not session:
            return

        session.preset_name = applied_preset_name
        self.sessions[session_id] = session
        self.sidebar.add_session(session)
        self.graph_view.set_sessions(self.sessions)

    def _on_edit_session_mapping(self, session_id: str):
        """Allows editing channel mappings for an existing loaded session/file instantaneously in memory."""
        session = self.sessions.get(session_id)
        if not session:
            return

        # 1. Retrieve raw columns and preview DataFrame directly from memory (0 ms, NO loading bar)
        if session.raw_df is not None and not session.raw_df.empty:
            raw_columns = list(session.raw_df.columns)
            preview_df = session.raw_df.head(10)
        else:
            if not os.path.exists(session.file_path):
                QMessageBox.warning(self, "File Not Found", "The log file for this session could not be found.")
                return
            raw_columns, preview_df = get_file_columns_and_preview(session.file_path)

        # Pre-fill preset name from session.preset_name or find best matching preset
        initial_preset = session.preset_name or self.state_manager.find_matching_preset(raw_columns)

        # 2. Open Wizard instantly
        wizard = ImportWizardDialog(
            file_path=session.file_path,
            raw_columns=raw_columns,
            preview_df=preview_df,
            state_manager=self.state_manager,
            initial_preset=initial_preset,
            initial_mapping=session.mapping,
            is_remapping=True,
            parent=self
        )

        if wizard.exec() != ImportWizardDialog.Accepted:
            return

        new_mapping = wizard.result_mapping
        if not new_mapping:
            return

        new_preset_name = wizard.result_preset_name or initial_preset

        # 3. Re-parse session in memory (instantaneous, NO loading bar)
        if session.raw_df is not None and not session.raw_df.empty:
            new_session = parse_session_from_dataframe(
                raw_df=session.raw_df,
                file_path=session.file_path,
                mapping=new_mapping,
                session_id=session_id,
                lap_label=self.state_manager.get_lap_label(),
                time_label=self.state_manager.get_time_label(),
                dist_label=self.state_manager.get_distance_label(),
                preset_name=new_preset_name
            )
        else:
            new_session = parse_session(
                file_path=session.file_path,
                mapping=new_mapping,
                session_id=session_id,
                lap_label=self.state_manager.get_lap_label(),
                time_label=self.state_manager.get_time_label(),
                dist_label=self.state_manager.get_distance_label(),
                preset_name=new_preset_name
            )

        new_session.preset_name = new_preset_name
        self.sessions[session_id] = new_session
        self.sidebar.update_session(new_session)
        self.graph_view.set_sessions(self.sessions)

    def _on_laps_selection_changed(self, selected_laps_info: list):
        self.graph_view.set_selected_laps(selected_laps_info)

    def _on_channels_selection_changed(self, selected_channels: set):
        self.graph_view.set_selected_channels(selected_channels)

    def closeEvent(self, event):
        """Cleanly terminate any background worker threads on application exit."""
        super().closeEvent(event)

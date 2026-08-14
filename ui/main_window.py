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
from core.file_parser import get_file_columns_and_preview, parse_session
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
        self.sessions: Dict[str, Session] = {}
        self._active_workers: List[QThread] = []

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
        self.sidebar = SidebarWidget()
        self.sidebar.laps_selection_changed.connect(self._on_laps_selection_changed)
        self.sidebar.channels_selection_changed.connect(self._on_channels_selection_changed)
        self.sidebar.session_removed.connect(self._on_session_removed)
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

    def _track_worker(self, worker: QThread):
        self._active_workers.append(worker)
        worker.finished.connect(lambda: self._untrack_worker(worker))

    def _untrack_worker(self, worker: QThread):
        if worker in self._active_workers:
            self._active_workers.remove(worker)
        worker.deleteLater()

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
        preview_worker = FilePreviewWorker(file_path, parent=self)
        self._track_worker(preview_worker)

        preview_dialog = LoadingDialog(
            f"Inspecting headers for '{filename}'...\nPlease wait.",
            worker=preview_worker,
            parent=self
        )

        preview_data = {}

        def on_preview_success(raw_cols, preview_df):
            preview_data["raw_columns"] = raw_cols
            preview_data["preview_df"] = preview_df
            preview_dialog.accept()

        def on_preview_error(err_msg):
            preview_data["error"] = err_msg
            preview_dialog.reject()

        preview_worker.success.connect(on_preview_success)
        preview_worker.error.connect(on_preview_error)

        preview_worker.start()
        preview_dialog.exec()

        if "error" in preview_data:
            QMessageBox.critical(self, "Import Error", f"Failed to read file '{file_path}':\n{preview_data['error']}")
            return
        if "raw_columns" not in preview_data:
            return

        raw_columns = preview_data["raw_columns"]
        preview_df = preview_data["preview_df"]

        matching_preset = self.state_manager.find_matching_preset(raw_columns)
        chosen_mapping = None

        if matching_preset:
            presets = self.state_manager.load_presets()
            preset_map = presets.get(matching_preset, {})

            preview_dlg = PresetPreviewDialog(
                file_path=file_path,
                preset_name=matching_preset,
                mapping=preset_map,
                parent=self
            )

            res = preview_dlg.exec()
            if preview_dlg.selected_action == PresetPreviewDialog.ACTION_APPLY:
                chosen_mapping = preset_map
            elif preview_dlg.selected_action == PresetPreviewDialog.ACTION_EDIT:
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

        # 2. Background Log Data Parsing
        session_id = str(uuid.uuid4())
        parse_worker = FileParseWorker(
            file_path=file_path,
            mapping=chosen_mapping,
            session_id=session_id,
            lap_label=self.state_manager.get_lap_label(),
            time_label=self.state_manager.get_time_label(),
            dist_label=self.state_manager.get_distance_label(),
            parent=self
        )
        self._track_worker(parse_worker)

        parse_dialog = LoadingDialog(
            f"Parsing log data for '{filename}'...\nPlease wait.",
            worker=parse_worker,
            parent=self
        )

        parse_result = {}

        def on_parse_success(session):
            parse_result["session"] = session
            parse_dialog.accept()

        def on_parse_error(err_msg):
            parse_result["error"] = err_msg
            parse_dialog.reject()

        parse_worker.success.connect(on_parse_success)
        parse_worker.error.connect(on_parse_error)

        parse_worker.start()
        parse_dialog.exec()

        if "error" in parse_result:
            QMessageBox.critical(self, "Parse Error", f"Failed to parse log file:\n{parse_result['error']}")
            return
        if "session" not in parse_result:
            return

        session = parse_result["session"]
        self.sessions[session_id] = session
        self.sidebar.add_session(session)
        self.graph_view.set_sessions(self.sessions)

    def _on_laps_selection_changed(self, selected_laps_info: list):
        self.graph_view.set_selected_laps(selected_laps_info)

    def _on_channels_selection_changed(self, selected_channels: set):
        self.graph_view.set_selected_channels(selected_channels)

    def closeEvent(self, event):
        """Cleanly terminate any background worker threads on application exit."""
        for worker in list(self._active_workers):
            if worker.isRunning():
                worker.requestInterruption()
                worker.wait(1000)
        super().closeEvent(event)

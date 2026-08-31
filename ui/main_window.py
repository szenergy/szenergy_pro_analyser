"""
Main application window organizing the menu bar, left sidebar, and stacked graph views.
Includes robust background worker lifecycle management and centralized session handling.
"""

import logging
import os
import uuid
from typing import Dict, List
from PySide6.QtWidgets import (
    QMainWindow, QSplitter, QFileDialog, QMessageBox, QApplication
)
from PySide6.QtCore import Qt, QUrl, QThread, QByteArray, QEventLoop
from PySide6.QtGui import QGuiApplication, QAction, QActionGroup, QDesktopServices

from core.state_manager import StateManager
from core.file_parser import get_file_columns_and_preview, parse_session, parse_session_from_dataframe
from core.data_models import Session
from ui.sidebar import SidebarWidget
from ui.graph_view import GraphViewWidget
from ui.import_wizard import ImportWizardDialog, PresetPreviewDialog
from ui.edit_dialogs import (
    PresetManagerDialog, ChannelManagerDialog, FileMappingManagerDialog, MapManagerDialog
)
from ui.loading_dialog import LoadingDialog, FilePreviewWorker, FileParseWorker, WorkspaceRestoreWorker
from utils.constants import (
    APP_NAME, APP_VERSION,
    STD_CH_LAP_NUM_SLUG, STD_CH_LAP_TIME_SLUG, STD_CH_LAP_DIST_SLUG
)
from utils.theme import is_system_dark_theme, get_theme_stylesheet

logger = logging.getLogger(__name__)


def is_dark_theme() -> bool:
    """Detects whether the system environment is currently in Dark Mode."""
    return is_system_dark_theme()


class MainWindow(QMainWindow):
    """Main window of the application."""

    def __init__(self, state_manager: Optional[StateManager] = None, splash=None):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(1200, 750)

        self.theme_mode: str = "auto"  # "auto", "dark", or "light"
        self.state_manager = state_manager if state_manager is not None else StateManager()
        
        if splash is not None:
            splash.set_progress(25, "Running configuration checks...")

        from core.migrations import run_migrations
        run_migrations(self.state_manager)
        
        self.sessions: Dict[str, Session] = {}

        if splash is not None:
            splash.set_progress(45, "Initializing workspace & graph engine...")

        self._init_ui()
        self._init_menu()
        self.apply_theme()
        self._sync_x_axis_labels()
        self._restore_ui_state(splash=splash)

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

        import_config_action = QAction("&Import Configuration...", self)
        import_config_action.triggered.connect(self._on_import_config)
        file_menu.addAction(import_config_action)
        self.addAction(import_config_action)

        export_config_action = QAction("&Export Configuration...", self)
        export_config_action.triggered.connect(self._on_export_config)
        file_menu.addAction(export_config_action)
        self.addAction(export_config_action)

        open_config_action = QAction("Open Config Folder", self)
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

        manage_presets_action = QAction("Manage &Presets...", self)
        manage_presets_action.triggered.connect(self._on_manage_presets)
        edit_menu.addAction(manage_presets_action)
        self.addAction(manage_presets_action)

        manage_channels_action = QAction("Manage &Channels...", self)
        manage_channels_action.triggered.connect(self._on_manage_channels)
        edit_menu.addAction(manage_channels_action)
        self.addAction(manage_channels_action)

        manage_file_mappings_action = QAction("Manage File &Mappings...", self)
        manage_file_mappings_action.triggered.connect(self._on_manage_file_mappings)
        edit_menu.addAction(manage_file_mappings_action)
        self.addAction(manage_file_mappings_action)

        manage_maps_action = QAction("Manage &Maps...", self)
        manage_maps_action.triggered.connect(self._on_manage_maps)
        edit_menu.addAction(manage_maps_action)
        self.addAction(manage_maps_action)

        # 3. View Menu
        view_menu = menu_bar.addMenu("&View")

        # Theme Submenu
        theme_menu = view_menu.addMenu("Theme")
        self.theme_group = QActionGroup(self)
        self.theme_group.setExclusive(True)

        self.theme_auto_action = QAction("Auto (System)", self, checkable=True)
        self.theme_group.addAction(self.theme_auto_action)
        theme_menu.addAction(self.theme_auto_action)
        self.theme_auto_action.triggered.connect(lambda: self.set_theme_mode("auto"))

        self.theme_dark_action = QAction("Dark", self, checkable=True)
        self.theme_group.addAction(self.theme_dark_action)
        theme_menu.addAction(self.theme_dark_action)
        self.theme_dark_action.triggered.connect(lambda: self.set_theme_mode("dark"))

        self.theme_light_action = QAction("Light", self, checkable=True)
        self.theme_group.addAction(self.theme_light_action)
        theme_menu.addAction(self.theme_light_action)
        self.theme_light_action.triggered.connect(lambda: self.set_theme_mode("light"))

        self._sync_theme_menu_checks()

        # Cursor Values Submenu
        cursor_values_menu = view_menu.addMenu("Cursor Values")
        self.cursor_on_graph_action = QAction("On Graph", self, checkable=True)
        self.cursor_on_graph_action.setChecked(self.graph_view.show_cursor_values_on_graph if hasattr(self, "graph_view") else True)
        self.cursor_on_graph_action.toggled.connect(self._on_toggle_cursor_on_graph)
        cursor_values_menu.addAction(self.cursor_on_graph_action)

        self.cursor_above_graph_action = QAction("Above Graph", self, checkable=True)
        self.cursor_above_graph_action.setChecked(self.graph_view.show_cursor_values_above_graph if hasattr(self, "graph_view") else True)
        self.cursor_above_graph_action.toggled.connect(self._on_toggle_cursor_above_graph)
        cursor_values_menu.addAction(self.cursor_above_graph_action)

    def set_theme_mode(self, mode: str):
        """Sets active theme mode ('auto', 'dark', 'light') and applies stylesheets and widget themes."""
        if mode not in ("auto", "dark", "light"):
            mode = "auto"
        self.theme_mode = mode
        self.apply_theme()
        self._sync_theme_menu_checks()

    def is_currently_dark(self) -> bool:
        """Determines if the active view is dark mode based on theme_mode setting."""
        if self.theme_mode == "dark":
            return True
        elif self.theme_mode == "light":
            return False
        return is_system_dark_theme()

    def apply_theme(self):
        """Applies current theme stylesheet to QApplication, sidebar, and graph view."""
        is_dark = self.is_currently_dark()
        app = QApplication.instance()
        if app:
            app.setStyleSheet(get_theme_stylesheet(is_dark))
        if hasattr(self, "sidebar"):
            self.sidebar.apply_theme(is_dark)
        if hasattr(self, "graph_view"):
            self.graph_view.apply_theme(is_dark)

    def update_system_theme(self):
        """Compatibility alias for apply_theme."""
        self.apply_theme()

    def _sync_theme_menu_checks(self):
        if hasattr(self, "theme_auto_action"):
            self.theme_auto_action.setChecked(self.theme_mode == "auto")
        if hasattr(self, "theme_dark_action"):
            self.theme_dark_action.setChecked(self.theme_mode == "dark")
        if hasattr(self, "theme_light_action"):
            self.theme_light_action.setChecked(self.theme_mode == "light")

    def _on_toggle_cursor_on_graph(self, checked: bool):
        """Handles toggling of on-graph cursor numerical value labels."""
        if hasattr(self, "graph_view"):
            self.graph_view.set_cursor_values_on_graph(checked)
        self._save_settings()

    def _on_toggle_cursor_above_graph(self, checked: bool):
        """Handles toggling of above-graph header title cursor numerical values."""
        if hasattr(self, "graph_view"):
            self.graph_view.set_cursor_values_above_graph(checked)
        self._save_settings()

    def _init_ui(self):
        self.main_splitter = QSplitter(Qt.Horizontal)

        # Left Sidebar
        self.sidebar = SidebarWidget(state_manager=self.state_manager)
        self.sidebar.laps_selection_changed.connect(self._on_laps_selection_changed)
        self.sidebar.channels_selection_changed.connect(self._on_channels_selection_changed)
        self.sidebar.session_removed.connect(self._on_session_removed)
        self.sidebar.session_edit_mapping_requested.connect(self._on_edit_session_mapping)
        self.main_splitter.addWidget(self.sidebar)

        # Right Graph View
        self.graph_view = GraphViewWidget(state_manager=self.state_manager)
        if hasattr(self.sidebar, "track_map_tab") and self.sidebar.track_map_tab is not None:
            self.graph_view.cursor_positions_changed.connect(self.sidebar.track_map_tab.set_cursor_positions)
        self.main_splitter.addWidget(self.graph_view)

        self.main_splitter.setSizes([300, 900])
        self.setCentralWidget(self.main_splitter)

    def _sync_x_axis_labels(self):
        time_label = self.state_manager.get_time_label()
        dist_label = self.state_manager.get_distance_label()
        self.graph_view.set_x_axis_labels(time_label, dist_label)
        if hasattr(self, "x_axis_dist_action"):
            self.x_axis_dist_action.setText(dist_label)
        if hasattr(self, "x_axis_time_action"):
            self.x_axis_time_action.setText(time_label)

    def _on_open_config_folder(self):
        config_dir = self.state_manager.config_dir
        logger.debug("Opening configuration folder: %s", config_dir)
        QDesktopServices.openUrl(QUrl.fromLocalFile(config_dir))

    def _on_export_config(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Configuration",
            "szenergy_config.json",
            "JSON Files (*.json);;All Files (*)"
        )
        if not file_path:
            return

        try:
            self.state_manager.export_config_to_file(file_path)
            QMessageBox.information(
                self,
                "Export Successful",
                f"Configuration exported successfully to:\n{file_path}"
            )
        except Exception as e:
            logger.error("Failed to export configuration to %s: %s", file_path, e, exc_info=True)
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Failed to export configuration:\n{str(e)}"
            )

    def _on_import_config(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Configuration",
            "",
            "JSON Files (*.json);;All Files (*)"
        )
        if not file_path:
            return

        try:
            num_presets, num_channels = self.state_manager.import_config_from_file(file_path)
            self._sync_x_axis_labels()
            self.sidebar.update_available_channels()
            self.graph_view.rebuild_plots()

            QMessageBox.information(
                self,
                "Import Successful",
                f"Configuration imported successfully from:\n{os.path.basename(file_path)}\n\n"
                f"• Presets updated/added: {num_presets}\n"
                f"• Channels updated/added: {num_channels}"
            )
        except Exception as e:
            logger.error("Failed to import configuration from %s: %s", file_path, e, exc_info=True)
            QMessageBox.critical(
                self,
                "Import Failed",
                f"Failed to import configuration:\n{str(e)}"
            )

    def _on_manage_presets(self):
        dialog = PresetManagerDialog(self.state_manager, parent=self)
        dialog.exec()

    def _on_manage_channels(self):
        dialog = ChannelManagerDialog(self.state_manager, parent=self)
        if dialog.exec():
            self._sync_x_axis_labels()

    def _on_manage_file_mappings(self):
        dialog = FileMappingManagerDialog(self.state_manager, parent=self)
        dialog.exec()

    def _on_manage_maps(self):
        dialog = MapManagerDialog(self.state_manager, parent=self)
        dialog.exec()
        if hasattr(self, "sidebar") and hasattr(self.sidebar, "track_map_tab"):
            self.sidebar.track_map_tab.refresh_map_list()

    def _on_clear_workspace(self):
        if not self.sessions:
            return
        reply = QMessageBox.question(
            self, "Clear Workspace",
            "Are you sure you want to unload all telemetry sessions?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            logger.info("Clearing %d workspace telemetry session(s)", len(self.sessions))
            self.sessions.clear()
            self.sidebar.clear_all_sessions()
            self.graph_view.custom_lap_labels.clear()
            self.graph_view.set_sessions(self.sessions)
            self.state_manager.clear_workspace_state()
            self._save_settings()

    def _on_session_removed(self, session_id: str):
        if session_id in self.sessions:
            removed_name = self.sessions[session_id].name
            logger.info("Removing session '%s' (id: %s)", removed_name, session_id)
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

        remembered_slug = self.state_manager.get_file_preset(file_path)
        chosen_mapping = None
        applied_preset_slug = None
        applied_preset_name = None

        if remembered_slug:
            preset = self.state_manager.get_preset_by_slug(remembered_slug)
            if not preset:
                preset = self.state_manager.get_preset_by_name(remembered_slug)

            if not preset:
                QMessageBox.warning(
                    self, "Preset Not Found",
                    f"The remembered preset '{remembered_slug}' for this file was not found.\n"
                    "Please configure the channel mapping in the wizard."
                )
                matching_slug = self.state_manager.find_matching_preset(raw_columns)
                wizard = ImportWizardDialog(
                    file_path=file_path,
                    raw_columns=raw_columns,
                    preview_df=preview_df,
                    state_manager=self.state_manager,
                    initial_preset=matching_slug,
                    parent=self
                )
                if wizard.exec() != ImportWizardDialog.Accepted:
                    return
                chosen_mapping = wizard.result_mapping
                applied_preset_slug = wizard.result_preset_slug
                applied_preset_name = wizard.result_preset_name
            else:
                preset_mapping = preset.get("mapping", {})
                file_cols_set = set(raw_columns)
                mapped_channels = {col: slug for col, slug in preset_mapping.items() if col in file_cols_set}
                mapped_slugs = set(mapped_channels.values())

                if (STD_CH_LAP_NUM_SLUG not in mapped_slugs or
                        (STD_CH_LAP_TIME_SLUG not in mapped_slugs and STD_CH_LAP_DIST_SLUG not in mapped_slugs)):
                    QMessageBox.warning(
                        self, "Mapping Error",
                        f"The remembered preset '{preset.get('name')}' is missing required channels for this file.\n"
                        "Please configure the channel mapping in the wizard."
                    )
                    wizard = ImportWizardDialog(
                        file_path=file_path,
                        raw_columns=raw_columns,
                        preview_df=preview_df,
                        state_manager=self.state_manager,
                        initial_preset=preset.get("slug"),
                        parent=self
                    )
                    if wizard.exec() != ImportWizardDialog.Accepted:
                        return
                    chosen_mapping = wizard.result_mapping
                    applied_preset_slug = wizard.result_preset_slug
                    applied_preset_name = wizard.result_preset_name
                else:
                    # Valid remembered preset - skip the wizard!
                    chosen_mapping = mapped_channels
                    applied_preset_slug = preset.get("slug")
                    applied_preset_name = preset.get("name")
        else:
            matching_slug = self.state_manager.find_matching_preset(raw_columns)
            wizard = ImportWizardDialog(
                file_path=file_path,
                raw_columns=raw_columns,
                preview_df=preview_df,
                state_manager=self.state_manager,
                initial_preset=matching_slug,
                parent=self
            )
            if wizard.exec() != ImportWizardDialog.Accepted:
                return
            chosen_mapping = wizard.result_mapping
            applied_preset_slug = wizard.result_preset_slug
            applied_preset_name = wizard.result_preset_name

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
            dist_label=self.state_manager.get_distance_label()
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

        session.preset_slug = applied_preset_slug
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

        # Pre-fill preset name from session.preset_slug / session.preset_name or find best matching preset
        initial_preset = session.preset_slug or session.preset_name or self.state_manager.find_matching_preset(raw_columns)

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

        new_preset_slug = wizard.result_preset_slug
        new_preset_name = wizard.result_preset_name or (self.state_manager.get_preset_name_by_slug(new_preset_slug) if new_preset_slug else None)

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
                preset_slug=new_preset_slug,
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
                preset_slug=new_preset_slug,
                preset_name=new_preset_name
            )

        new_session.preset_slug = new_preset_slug
        new_session.preset_name = new_preset_name
        self.sessions[session_id] = new_session
        self.sidebar.update_session(new_session)
        self.graph_view.set_sessions(self.sessions)

    def _on_laps_selection_changed(self, selected_laps_info: list):
        self.graph_view.set_selected_laps(selected_laps_info)

    def _on_channels_selection_changed(self, selected_channels: set):
        self.graph_view.set_selected_channels(selected_channels)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if hasattr(self, "graph_view") and self.graph_view.cancel_drag_selection():
                event.accept()
                return
        super().keyPressEvent(event)

    def _save_settings(self):
        """Saves application settings (theme, window geometry, graph grid lines, x-axis, cursor toggle) to settings.json."""
        try:
            geometry_hex = self.saveGeometry().toHex().data().decode("ascii")
            window_state = {
                "geometry": geometry_hex,
                "is_maximized": self.isMaximized(),
                "main_splitter": self.main_splitter.sizes() if hasattr(self, "main_splitter") else [300, 900]
            }

            graph_state = {}
            if hasattr(self, "graph_view"):
                graph_state = {
                    "show_x_grid": self.graph_view.show_x_grid,
                    "show_y_grid": self.graph_view.show_y_grid,
                    "show_cursor_values": self.graph_view.show_cursor_values,
                    "show_cursor_values_on_graph": self.graph_view.show_cursor_values_on_graph,
                    "show_cursor_values_above_graph": self.graph_view.show_cursor_values_above_graph,
                    "show_legend": self.graph_view.show_legend,
                    "x_axis_slug": self.graph_view.x_axis_slug,
                }

            sidebar_settings = {}
            if hasattr(self, "sidebar"):
                sidebar_settings = {
                    "bottom_tab_index": self.sidebar.get_bottom_tab_index(),
                    "selected_map": self.sidebar.get_selected_map(),
                }

            settings_data = {
                "theme_mode": self.theme_mode,
                "window": window_state,
                "graph": graph_state,
                "sidebar": sidebar_settings,
            }
            self.state_manager.save_settings(settings_data)
            logger.debug("Application settings successfully saved to settings.json")
        except Exception as e:
            logger.error("Failed to save application settings: %s", e, exc_info=True)

    def _save_workspace_state(self):
        """Saves currently loaded sessions, selected laps, custom labels, and sidebar channels to workspace_state.json."""
        try:
            if not self.sessions:
                self.state_manager.clear_workspace_state()
                return

            # 1. Sidebar State
            sidebar_state = {
                "selected_channels": self.sidebar.get_selected_channels() if hasattr(self, "sidebar") else []
            }

            # 2. Workspace Sessions & Custom Lap Labels
            sessions_data = []
            for session in self.sessions.values():
                session_laps = []
                for lap in session.laps:
                    key = (session.id, lap.lap_number)
                    if key in self.sidebar.allocated_colors:
                        session_laps.append({
                            "lap_number": lap.lap_number,
                            "color": self.sidebar.allocated_colors[key]
                        })

                sessions_data.append({
                    "file_path": session.file_path,
                    "mapping": session.mapping,
                    "preset_slug": session.preset_slug,
                    "preset_name": session.preset_name,
                    "selected_laps": session_laps
                })

            selected_laps_order = []
            if hasattr(self, "sidebar") and self.sidebar.allocated_colors:
                for (s_id, lap_num), color in self.sidebar.allocated_colors.items():
                    if s_id in self.sessions and self.sessions[s_id].file_path:
                        norm_path = os.path.abspath(self.sessions[s_id].file_path)
                        selected_laps_order.append({
                            "file_path": norm_path,
                            "lap_number": lap_num,
                            "color": color
                        })

            custom_labels_data = {}
            if hasattr(self, "graph_view") and self.graph_view.custom_lap_labels:
                for (session_id, lap_num), label in self.graph_view.custom_lap_labels.items():
                    session = self.sessions.get(session_id)
                    if session and session.file_path:
                        norm_path = os.path.abspath(session.file_path)
                        custom_labels_data[f"{norm_path}::{lap_num}"] = str(label)

            zoom_state = {}
            if hasattr(self, "graph_view"):
                if self.graph_view.has_manual_zoom_or_pan and self.graph_view.plot_widgets:
                    self.graph_view._record_current_view_ranges()
                zoom_state = {
                    "has_manual_zoom_or_pan": self.graph_view.has_manual_zoom_or_pan,
                    "saved_x_range": self.graph_view.saved_x_range,
                    "saved_y_ranges": self.graph_view.saved_y_ranges,
                }

            workspace_data = {
                "sessions": sessions_data,
                "selected_laps_order": selected_laps_order,
                "custom_lap_labels": custom_labels_data,
                "sidebar": sidebar_state,
                "zoom": zoom_state,
            }
            self.state_manager.save_workspace_state(workspace_data)
            logger.debug("Workspace state successfully saved (%d sessions, %d custom labels)",
                         len(sessions_data), len(custom_labels_data))
        except Exception as e:
            logger.error("Failed to save workspace state: %s", e, exc_info=True)

    def _save_ui_state(self):
        """Saves current application settings to settings.json and workspace to workspace_state.json."""
        self._save_settings()
        self._save_workspace_state()

    def _restore_ui_state(self, splash=None):
        """Restores application settings and loaded workspace data from persistent storage."""
        try:
            # 1. Restore Application Settings (Theme, Window Geometry, Graph Toggles/X-Axis)
            settings = self.state_manager.load_settings()
            if settings:
                logger.info("Restoring application settings...")
                if "theme_mode" in settings:
                    self.set_theme_mode(settings.get("theme_mode", "auto"))

                window_data = settings.get("window", {})
                geo = window_data.get("geometry")
                if geo:
                    self.restoreGeometry(QByteArray.fromHex(geo.encode("ascii")))
                self._restore_is_maximized = bool(window_data.get("is_maximized", False))
                if self._restore_is_maximized:
                    self.setWindowState(Qt.WindowMaximized)
                if window_data.get("main_splitter") and hasattr(self, "main_splitter"):
                    self.main_splitter.setSizes(window_data["main_splitter"])

                if hasattr(self, "graph_view") and "graph" in settings:
                    self.graph_view.set_view_state(settings.get("graph", {}))
                    if hasattr(self, "cursor_on_graph_action"):
                        self.cursor_on_graph_action.setChecked(self.graph_view.show_cursor_values_on_graph)
                    if hasattr(self, "cursor_above_graph_action"):
                        self.cursor_above_graph_action.setChecked(self.graph_view.show_cursor_values_above_graph)

                sidebar_settings = settings.get("sidebar", {})
                if hasattr(self, "sidebar") and sidebar_settings:
                    if "bottom_tab_index" in sidebar_settings:
                        self.sidebar.set_bottom_tab_index(int(sidebar_settings["bottom_tab_index"]))
                    if "selected_map" in sidebar_settings and sidebar_settings["selected_map"]:
                        self.sidebar.set_selected_map(sidebar_settings["selected_map"])

            # 2. Restore Loaded Workspace Data (Sessions, Laps, Custom Labels, Sidebar Channels)
            workspace_data = self.state_manager.load_workspace_state()
            if not workspace_data:
                logger.debug("No saved workspace state found on startup")
                return

            sessions_list = workspace_data.get("sessions", [])
            custom_labels_dict = workspace_data.get("custom_lap_labels", {})

            valid_sessions = [s for s in sessions_list if s.get("file_path") and os.path.exists(s["file_path"])]

            if valid_sessions:
                logger.info("Restoring %d valid saved session(s) in background", len(valid_sessions))
                restore_worker = WorkspaceRestoreWorker(
                    sessions_data=valid_sessions,
                    custom_labels_dict=custom_labels_dict,
                    lap_label=self.state_manager.get_lap_label(),
                    time_label=self.state_manager.get_time_label(),
                    dist_label=self.state_manager.get_distance_label()
                )

                loaded_items = []
                def _handle_loaded_session(session, selected_laps, session_custom_labels):
                    loaded_items.append((session, selected_laps, session_custom_labels))

                def _on_restore_progress(current, total, filename):
                    if splash is not None:
                        pct = 50 + int(45 * current / total)
                        splash.set_progress(pct, f"Restoring session {current} of {total}: {filename}")

                restore_worker.session_loaded.connect(_handle_loaded_session, Qt.QueuedConnection)
                restore_worker.progress.connect(_on_restore_progress, Qt.QueuedConnection)

                loop = QEventLoop()
                restore_worker.finished_all.connect(loop.quit)
                restore_worker.start()
                loop.exec()
                restore_worker.wait()

                app = QApplication.instance()
                if app:
                    app.sendPostedEvents()
                    app.processEvents()

                # Process all loaded sessions cleanly AFTER thread is joined
                for session, selected_laps, session_custom_labels in loaded_items:
                    self.sessions[session.id] = session
                    self.sidebar.add_session(session)
                    if session_custom_labels and hasattr(self, "graph_view"):
                        for lap_num, custom_name in session_custom_labels.items():
                            self.graph_view.custom_lap_labels[(session.id, int(lap_num))] = str(custom_name)

            # 3. Restore exact lap selections and color allocations across all sessions
            lap_entries_to_restore = []
            selected_laps_order = workspace_data.get("selected_laps_order")
            if selected_laps_order and isinstance(selected_laps_order, list):
                path_to_session_id = {}
                for s_id, sess in self.sessions.items():
                    if sess.file_path:
                        path_to_session_id[os.path.abspath(sess.file_path)] = s_id
                        path_to_session_id[sess.file_path] = s_id

                for entry in selected_laps_order:
                    if isinstance(entry, dict):
                        f_path = entry.get("file_path")
                        l_num = entry.get("lap_number")
                        col = entry.get("color")
                        s_id = path_to_session_id.get(f_path) or (path_to_session_id.get(os.path.abspath(f_path)) if f_path else None)
                        if s_id and l_num is not None:
                            lap_entries_to_restore.append((s_id, int(l_num), col))
            else:
                for s_info in sessions_list:
                    f_path = s_info.get("file_path")
                    matched_id = None
                    for s_id, sess in self.sessions.items():
                        if sess.file_path == f_path or (f_path and os.path.abspath(sess.file_path) == os.path.abspath(f_path)):
                            matched_id = s_id
                            break
                    if matched_id:
                        for lap_entry in s_info.get("selected_laps", []):
                            if isinstance(lap_entry, dict):
                                lap_entries_to_restore.append((matched_id, int(lap_entry["lap_number"]), lap_entry.get("color")))
                            else:
                                lap_entries_to_restore.append((matched_id, int(lap_entry), None))

            if lap_entries_to_restore and hasattr(self, "sidebar"):
                self.sidebar.restore_selected_laps(lap_entries_to_restore)

            # 4. Restore Sidebar Selected Channels
            selected_channels = workspace_data.get("sidebar", {}).get("selected_channels", [])
            if selected_channels and hasattr(self, "sidebar"):
                self.sidebar.set_selected_channels(selected_channels)

            # 5. Restore Zoom Ranges if saved
            zoom_data = workspace_data.get("zoom", {})
            if zoom_data and hasattr(self, "graph_view"):
                self.graph_view.set_view_state(zoom_data)

            if self.sessions and hasattr(self, "graph_view"):
                self.graph_view.set_sessions(self.sessions)

            logger.info("UI state restoration complete")
        except Exception as e:
            logger.error("Failed to restore UI state: %s", e, exc_info=True)

    def closeEvent(self, event):
        """Saves UI state and cleanly terminates on exit."""
        logger.info("Closing application...")
        self._save_ui_state()
        super().closeEvent(event)

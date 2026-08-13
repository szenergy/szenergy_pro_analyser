"""
Main application window organizing the toolbar, left sidebar, and stacked graph views.
"""

import uuid
from typing import Dict
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QSplitter, QFileDialog,
    QMessageBox, QMenuBar, QMenu, QStatusBar
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QIcon

from core.state_manager import StateManager
from core.file_parser import get_file_columns_and_preview, parse_session
from core.data_models import Session
from ui.sidebar import SidebarWidget
from ui.graph_view import GraphViewWidget
from ui.import_wizard import ImportWizardDialog
from utils.constants import APP_NAME, APP_VERSION


class MainWindow(QMainWindow):
    """Main window of the SZenergy Pro Analyser desktop application."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(1200, 750)

        self.state_manager = StateManager()
        self.sessions: Dict[str, Session] = {}

        self._init_menu_and_toolbar()
        self._init_ui()

    def _init_menu_and_toolbar(self):
        menu_bar = self.menuBar()

        # File Menu
        file_menu = menu_bar.addMenu("&File")

        open_action = QAction("&Open Log File...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._on_open_file)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Status Bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready")

    def _init_ui(self):
        main_splitter = QSplitter(Qt.Horizontal)

        # Left Sidebar
        self.sidebar = SidebarWidget()
        self.sidebar.lap_visibility_changed.connect(self._on_lap_visibility_changed)
        self.sidebar.channels_selection_changed.connect(self._on_channels_selection_changed)
        main_splitter.addWidget(self.sidebar)

        # Right Graph View
        self.graph_view = GraphViewWidget()
        main_splitter.addWidget(self.graph_view)

        # Set initial splitter ratio (25% left sidebar, 75% main graph view)
        main_splitter.setSizes([300, 900])

        self.setCentralWidget(main_splitter)

    def _on_open_file(self):
        """File open dialog handler supporting CSV, XLSX, and TDMS."""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Telemetry Log Files",
            "",
            "Supported Log Files (*.csv *.xlsx *.xls *.tdms);;CSV Files (*.csv);;Excel Files (*.xlsx *.xls);;TDMS Files (*.tdms);;All Files (*)"
        )

        for path in file_paths:
            self._import_file(path)

    def _import_file(self, file_path: str):
        """Processes file import with preset detection and mapping wizard."""
        try:
            raw_columns, preview_df = get_file_columns_and_preview(file_path)
        except Exception as e:
            QMessageBox.critical(self, "Import Error", f"Failed to read file '{file_path}':\n{str(e)}")
            return

        matching_preset = self.state_manager.find_matching_preset(raw_columns)
        chosen_mapping = None

        if matching_preset:
            # Prompt user to confirm detected preset
            reply = QMessageBox.question(
                self,
                "Preset Detected",
                f"Matching preset '{matching_preset}' detected for file:\n{file_path}\n\nDo you want to apply this preset?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes
            )

            if reply == QMessageBox.Cancel:
                return
            elif reply == QMessageBox.Yes:
                presets = self.state_manager.load_presets()
                chosen_mapping = presets.get(matching_preset)

        # If no preset applied, launch wizard dialog
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
                return  # User cancelled wizard

        if not chosen_mapping:
            return

        # Parse session data
        session_id = str(uuid.uuid4())
        try:
            session = parse_session(file_path, chosen_mapping, session_id)
        except Exception as e:
            QMessageBox.critical(self, "Parse Error", f"Failed to parse log file:\n{str(e)}")
            return

        self.sessions[session_id] = session
        self.sidebar.add_session(session)
        self.graph_view.set_sessions(self.sessions)
        self.statusBar.showMessage(f"Successfully loaded '{session.name}' ({len(session.laps)} laps)")

    def _on_lap_visibility_changed(self, session_id: str, lap_number: int, is_visible: bool):
        self.graph_view.update_lap_visibility(session_id, lap_number, is_visible)

    def _on_channels_selection_changed(self, selected_channels: set):
        self.graph_view.set_selected_channels(selected_channels)

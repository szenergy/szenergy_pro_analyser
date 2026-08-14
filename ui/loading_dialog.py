"""
Background file loader worker threads and loading progress dialog for smooth GUI responsiveness.
Ensures proper thread lifetime, cancellation handling, and garbage collection safety.
"""

import os
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar

from core.file_parser import parse_session, get_file_columns_and_preview


class FileParseWorker(QThread):
    """Background worker thread for reading and parsing log files into Session objects."""
    success = Signal(object)  # Session object
    error = Signal(str)

    def __init__(self, file_path: str, mapping: dict, session_id: str,
                 lap_label: str, time_label: str, dist_label: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.mapping = mapping
        self.session_id = session_id
        self.lap_label = lap_label
        self.time_label = time_label
        self.dist_label = dist_label

    def run(self):
        try:
            session = parse_session(
                self.file_path,
                self.mapping,
                self.session_id,
                self.lap_label,
                self.time_label,
                self.dist_label
            )
            if not self.isInterruptionRequested():
                self.success.emit(session)
        except Exception as e:
            if not self.isInterruptionRequested():
                self.error.emit(str(e))


class FilePreviewWorker(QThread):
    """Background worker thread for inspecting log file headers and generating previews."""
    success = Signal(list, object)  # (raw_columns, preview_df)
    error = Signal(str)

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path

    def run(self):
        try:
            raw_columns, preview_df = get_file_columns_and_preview(self.file_path)
            if not self.isInterruptionRequested():
                self.success.emit(raw_columns, preview_df)
        except Exception as e:
            if not self.isInterruptionRequested():
                self.error.emit(str(e))


class LoadingDialog(QDialog):
    """Modal loading dialog with an indeterminate progress bar shown during background operations."""

    def __init__(self, message: str, worker: QThread = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Processing Telemetry Log")
        self.setFixedSize(420, 120)
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        self.setModal(True)
        self.worker = worker

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        self.label = QLabel(message)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # Indeterminate animated bar
        layout.addWidget(self.progress)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(1000)
        super().closeEvent(event)

    def reject(self):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(1000)
        super().reject()

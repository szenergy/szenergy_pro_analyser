import logging
import os
import uuid
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar

from core.file_parser import parse_session, get_file_columns_and_preview
from utils.constants import STD_CH_LAP_NUM_SLUG, STD_CH_LAP_TIME_SLUG, STD_CH_LAP_DIST_SLUG

logger = logging.getLogger(__name__)


class FileParseWorker(QThread):
    """Background worker thread for reading and parsing log files into Session objects."""
    success = Signal(object)  # Session object
    error = Signal(str)

    def __init__(self, file_path: str, mapping: dict, session_id: str,
                 lap_label: str, time_label: str, dist_label: str,
                 lap_slug: str = STD_CH_LAP_NUM_SLUG, time_slug: str = STD_CH_LAP_TIME_SLUG, dist_slug: str = STD_CH_LAP_DIST_SLUG,
                 parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.mapping = mapping
        self.session_id = session_id
        self.lap_label = lap_label
        self.time_label = time_label
        self.dist_label = dist_label
        self.lap_slug = lap_slug
        self.time_slug = time_slug
        self.dist_slug = dist_slug

    def run(self):
        try:
            logger.debug("FileParseWorker started for: %s", os.path.basename(self.file_path))
            session = parse_session(
                self.file_path,
                self.mapping,
                self.session_id,
                self.lap_label,
                self.time_label,
                self.dist_label,
                self.lap_slug,
                self.time_slug,
                self.dist_slug
            )
            if not self.isInterruptionRequested():
                logger.debug("FileParseWorker completed successfully for: %s", os.path.basename(self.file_path))
                self.success.emit(session)
        except Exception as e:
            logger.error("FileParseWorker error on %s: %s", self.file_path, e, exc_info=True)
            if not self.isInterruptionRequested():
                self.error.emit(str(e))


class FilePreviewWorker(QThread):
    """Background worker thread for inspecting log file headers and generating previews."""
    success = Signal(object, object)  # (raw_columns, preview_df)
    error = Signal(str)

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path

    def run(self):
        try:
            logger.debug("FilePreviewWorker inspecting: %s", os.path.basename(self.file_path))
            raw_columns, preview_df = get_file_columns_and_preview(self.file_path)
            if not self.isInterruptionRequested():
                logger.debug("FilePreviewWorker finished with %d columns for: %s", len(raw_columns), os.path.basename(self.file_path))
                self.success.emit(raw_columns, preview_df)
        except Exception as e:
            logger.error("FilePreviewWorker error on %s: %s", self.file_path, e, exc_info=True)
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
        if self.worker and self.worker.parent() is None:
            self.worker.setParent(self)
        self.is_success = False
        self.result_data = None
        self.error_message = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        self.label = QLabel(message)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # Indeterminate animated bar
        layout.addWidget(self.progress)

    def exec_worker(self) -> bool:
        """Starts worker thread, connects signals via queued connections, blocks modal dialog, and joins worker thread."""
        if not self.worker:
            return False

        def _on_success(*args):
            self.is_success = True
            if len(args) == 1:
                self.result_data = args[0]
            elif len(args) > 1:
                self.result_data = args
            else:
                self.result_data = None
            # Stop indeterminate animation timer before accepting
            self.progress.setRange(0, 1)
            self.progress.setValue(1)
            self.accept()

        def _on_error(err_msg: str):
            self.is_success = False
            self.error_message = str(err_msg)
            # Stop indeterminate animation timer before rejecting
            self.progress.setRange(0, 1)
            self.progress.setValue(0)
            self.reject()

        self.worker.success.connect(_on_success, Qt.QueuedConnection)
        self.worker.error.connect(_on_error, Qt.QueuedConnection)

        self.worker.start()
        try:
            self.exec()
        finally:
            self.progress.setRange(0, 1)
            try:
                self.worker.success.disconnect(_on_success)
            except Exception:
                pass
            try:
                self.worker.error.disconnect(_on_error)
            except Exception:
                pass

            # Guarantee the background worker thread has completely exited before continuing
            if self.worker.isRunning():
                self.worker.requestInterruption()
                self.worker.wait(3000)
            else:
                self.worker.wait()

        return self.is_success

    def closeEvent(self, event):
        self.progress.setRange(0, 1)
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(1000)
        super().closeEvent(event)

    def reject(self):
        self.progress.setRange(0, 1)
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(1000)
        super().reject()

    def accept(self):
        self.progress.setRange(0, 1)
        if self.worker and self.worker.isRunning():
            self.worker.wait(2000)
        super().accept()


class WorkspaceRestoreWorker(QThread):
    """Background worker thread for restoring previously opened workspace sessions on startup."""
    progress = Signal(int, int, str)  # (current_index, total_count, filename)
    session_loaded = Signal(object, object, object)  # (session, selected_laps, session_custom_labels)
    finished_all = Signal()
    error = Signal(str)

    def __init__(
        self,
        sessions_data: list,
        custom_labels_dict: dict,
        lap_label: str,
        time_label: str,
        dist_label: str,
        lap_slug: str = STD_CH_LAP_NUM_SLUG,
        time_slug: str = STD_CH_LAP_TIME_SLUG,
        dist_slug: str = STD_CH_LAP_DIST_SLUG,
        parent=None
    ):
        super().__init__(parent)
        self.sessions_data = sessions_data
        self.custom_labels_dict = custom_labels_dict
        self.lap_label = lap_label
        self.time_label = time_label
        self.dist_label = dist_label
        self.lap_slug = lap_slug
        self.time_slug = time_slug
        self.dist_slug = dist_slug

    def run(self):
        valid_items = [s for s in self.sessions_data if s.get("file_path") and os.path.exists(s["file_path"])]
        total = len(valid_items)

        for i, s_info in enumerate(valid_items, start=1):
            if self.isInterruptionRequested():
                break

            file_path = s_info.get("file_path")
            mapping = s_info.get("mapping", {})
            preset_slug = s_info.get("preset_slug")
            preset_name = s_info.get("preset_name")
            selected_laps = s_info.get("selected_laps", [])

            filename = os.path.basename(file_path)
            self.progress.emit(i, total, filename)

            try:
                session_id = str(uuid.uuid4())
                session = parse_session(
                    file_path=file_path,
                    mapping=mapping,
                    session_id=session_id,
                    lap_label=self.lap_label,
                    time_label=self.time_label,
                    dist_label=self.dist_label,
                    lap_slug=self.lap_slug,
                    time_slug=self.time_slug,
                    dist_slug=self.dist_slug,
                    preset_slug=preset_slug,
                    preset_name=preset_name
                )
                session.preset_slug = preset_slug
                session.preset_name = preset_name

                # Custom labels for this session
                session_custom_labels = {}
                norm_path = os.path.abspath(file_path)
                for lap in session.laps:
                    key1 = f"{norm_path}::{lap.lap_number}"
                    key2 = f"{file_path}::{lap.lap_number}"
                    if key1 in self.custom_labels_dict:
                        session_custom_labels[lap.lap_number] = self.custom_labels_dict[key1]
                    elif key2 in self.custom_labels_dict:
                        session_custom_labels[lap.lap_number] = self.custom_labels_dict[key2]

                if not self.isInterruptionRequested():
                    self.session_loaded.emit(session, selected_laps, session_custom_labels)
            except Exception:
                pass

        if not self.isInterruptionRequested():
            self.finished_all.emit()


class WorkspaceRestoreDialog(QDialog):
    """Modal progress dialog shown while restoring workspace sessions on application startup."""

    def __init__(self, worker: WorkspaceRestoreWorker, total_sessions: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Restoring Workspace")
        self.setFixedSize(450, 130)
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        self.setModal(True)
        self.worker = worker
        if self.worker and self.worker.parent() is None:
            self.worker.setParent(self)
        self.total_sessions = total_sessions

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        self.status_label = QLabel(f"Restoring saved workspace sessions (0/{total_sessions})...\nPlease wait.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, total_sessions)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

    def exec_restore(self, on_session_loaded_callback) -> None:
        """Starts the worker thread, updates UI with progress, and collects loaded sessions."""
        def _on_progress(current: int, total: int, filename: str):
            self.progress_bar.setValue(current)
            self.status_label.setText(
                f"<b>Restoring session {current} of {total}:</b><br>{filename}"
            )

        def _on_session_loaded(session, selected_laps, custom_labels):
            on_session_loaded_callback(session, selected_laps, custom_labels)

        def _on_finished():
            self.accept()

        self.worker.progress.connect(_on_progress, Qt.QueuedConnection)
        self.worker.session_loaded.connect(_on_session_loaded, Qt.QueuedConnection)
        self.worker.finished_all.connect(_on_finished, Qt.QueuedConnection)

        self.worker.start()
        try:
            self.exec()
        finally:
            try:
                self.worker.progress.disconnect(_on_progress)
            except Exception:
                pass
            try:
                self.worker.session_loaded.disconnect(_on_session_loaded)
            except Exception:
                pass
            try:
                self.worker.finished_all.disconnect(_on_finished)
            except Exception:
                pass

            if self.worker.isRunning():
                self.worker.requestInterruption()
                self.worker.wait(3000)
            else:
                self.worker.wait()

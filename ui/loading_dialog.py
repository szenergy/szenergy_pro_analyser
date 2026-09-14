"""
Thread-safe background workers and progress dialogs for file parsing and workspace restoration.
Uses pure Python threading with main-thread QTimer status checking to eliminate
Shiboken C++ cross-thread lifecycle deallocation crashes on PySide6 / Python 3.14.
"""

import logging
import os
import threading
import uuid
from typing import Optional, Any
from PySide6.QtCore import QObject, Signal, Slot, Qt, QTimer
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar

from core.file_parser import parse_session, get_file_columns_and_preview
from utils.constants import STD_CH_LAP_NUM_SLUG, STD_CH_LAP_TIME_SLUG, STD_CH_LAP_DIST_SLUG

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Background Worker Base & Concrete Implementations
# ---------------------------------------------------------------------------

class BaseWorker:
    """
    Pure Python background worker thread.
    Does not inherit from QObject or QThread, completely eliminating
    Shiboken C++ binding deallocation lifecycle segfaults.
    """

    def __init__(self, parent=None):
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.error_message: Optional[str] = None
        self.result: Any = None

    def start(self):
        """Spawns worker execution inside a daemon Python thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_wrapper, daemon=True)
        self._thread.start()

    def _run_wrapper(self):
        try:
            self.result = self.do_work()
        except Exception as e:
            logger.error("Worker error: %s", e, exc_info=True)
            self.error_message = str(e)

    def do_work(self):
        raise NotImplementedError

    def run(self):
        """Allows synchronous direct execution in test environments."""
        self._run_wrapper()

    def requestInterruption(self):
        self._stop_event.set()

    def isInterruptionRequested(self) -> bool:
        return self._stop_event.is_set()

    def isRunning(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def wait(self, timeout_ms: Optional[int] = None):
        if self._thread is not None:
            timeout_sec = (timeout_ms / 1000.0) if timeout_ms is not None else None
            self._thread.join(timeout=timeout_sec)


class FileParseWorker(BaseWorker):
    """Background worker thread that parses a log file into a Session."""

    def __init__(
        self,
        file_path: str,
        mapping: dict,
        session_id: str,
        lap_label: str,
        time_label: str,
        dist_label: str,
        lap_slug: str = STD_CH_LAP_NUM_SLUG,
        time_slug: str = STD_CH_LAP_TIME_SLUG,
        dist_slug: str = STD_CH_LAP_DIST_SLUG,
        parent=None
    ):
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

    def do_work(self):
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
        logger.debug("FileParseWorker completed successfully for: %s", os.path.basename(self.file_path))
        return session


class FilePreviewWorker(BaseWorker):
    """Background worker thread that reads file headers for preview."""

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path

    def do_work(self):
        logger.debug("FilePreviewWorker inspecting: %s", os.path.basename(self.file_path))
        raw_columns, preview_df = get_file_columns_and_preview(self.file_path)
        logger.debug("FilePreviewWorker finished with %d columns for: %s", len(raw_columns), os.path.basename(self.file_path))
        return raw_columns, preview_df


class WorkspaceRestoreWorker(BaseWorker, QObject):
    """Background worker thread that restores previously opened sessions."""
    progress = Signal(int, int, str)  # (current_index, total_count, filename)
    finished_all = Signal()

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
        BaseWorker.__init__(self, parent)
        QObject.__init__(self, parent)
        self.sessions_data = sessions_data
        self.custom_labels_dict = custom_labels_dict
        self.lap_label = lap_label
        self.time_label = time_label
        self.dist_label = dist_label
        self.lap_slug = lap_slug
        self.time_slug = time_slug
        self.dist_slug = dist_slug
        self.loaded_sessions: list = []

    def do_work(self):
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
                    self.loaded_sessions.append((session, selected_laps, session_custom_labels))
            except Exception as e:
                logger.warning("Failed to restore session from %s: %s", file_path, e)

        if not self.isInterruptionRequested():
            self.finished_all.emit()


# ---------------------------------------------------------------------------
# Dialog widgets
# ---------------------------------------------------------------------------

class LoadingDialog(QDialog):
    """Modal loading dialog with an indeterminate progress bar shown during background operations."""

    def __init__(self, message: str, worker: Optional[BaseWorker] = None, parent=None):
        dialog_parent = parent if (parent is not None and getattr(parent, "isVisible", lambda: False)()) else None
        super().__init__(dialog_parent)
        self.setWindowTitle("Processing Telemetry Log")
        self.setFixedSize(420, 120)
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        self.setModal(True)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.worker = worker
        self.is_success = False
        self.result_data = None
        self.error_message = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        self.label = QLabel(message)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

        self.progress = QProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(25)
        self._poll_timer.timeout.connect(self._check_worker_status)

    @Slot()
    def _check_worker_status(self):
        if self.worker is None or not self.worker.isRunning():
            self._poll_timer.stop()
            self.progress.setValue(100)
            if self.worker is not None and self.worker.error_message is not None:
                self.is_success = False
                self.error_message = self.worker.error_message
                self.reject()
            else:
                self.is_success = True
                if self.worker is not None:
                    self.result_data = self.worker.result
                self.accept()
        else:
            # Smooth animated pulse driven by the controlled poll timer
            self.progress.setValue((self.progress.value() + 5) % 100)

    def exec_worker(self) -> bool:
        """Starts worker thread, monitors with timer, blocks modal dialog, and joins worker thread."""
        if not self.worker:
            return False

        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            self.worker.run()
            if self.worker.error_message is not None:
                self.is_success = False
                self.error_message = self.worker.error_message
            else:
                self.is_success = True
                self.result_data = self.worker.result
            return self.is_success

        self.worker.start()
        self._poll_timer.start()
        try:
            self.exec()
        finally:
            self._poll_timer.stop()
            if self.worker.isRunning():
                self.worker.requestInterruption()
                self.worker.wait(5000)
            else:
                self.worker.wait()
            self.hide()

        return self.is_success

    def closeEvent(self, event):
        self._poll_timer.stop()
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
        super().closeEvent(event)

    def reject(self):
        self._poll_timer.stop()
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
        super().reject()

    def accept(self):
        self._poll_timer.stop()
        super().accept()

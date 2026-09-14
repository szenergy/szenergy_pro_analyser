"""
Modal dialog for configuring maximum allowable time (seconds) and distance (meters)
gap thresholds before line segments are disconnected.
"""

import logging
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout,
    QLabel, QDoubleSpinBox, QDialogButtonBox, QGroupBox
)

from utils.constants import DEFAULT_GAP_TIME_THRESHOLD, DEFAULT_GAP_DIST_THRESHOLD

logger = logging.getLogger(__name__)


class GapThresholdDialog(QDialog):
    """Dialog allowing the user to configure time (seconds) and distance (meters) line gap thresholds."""

    def __init__(
        self,
        current_time_threshold: float = DEFAULT_GAP_TIME_THRESHOLD,
        current_dist_threshold: float = DEFAULT_GAP_DIST_THRESHOLD,
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("Configure Line Gap Thresholds")
        self.setMinimumWidth(380)
        self.setModal(True)

        self._time_val = float(current_time_threshold)
        self._dist_val = float(current_dist_threshold)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        # Description Header
        desc_label = QLabel(
            "When gap disconnection is enabled, consecutive data points"
            "that are separated by more than any of these thresholds are not connectedcle."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #888; font-size: 11px; margin-bottom: 4px;")
        layout.addWidget(desc_label)

        # Form Group Box
        group = QGroupBox()
        form_layout = QFormLayout(group)
        form_layout.setContentsMargins(12, 14, 12, 14)
        form_layout.setSpacing(12)

        # 1. Time Threshold SpinBox
        self.spin_time = QDoubleSpinBox()
        self.spin_time.setRange(0.01, 10000.0)
        self.spin_time.setDecimals(2)
        self.spin_time.setSingleStep(0.1)
        self.spin_time.setSuffix(" s")
        self.spin_time.setValue(self._time_val)
        self.spin_time.setMinimumHeight(28)
        form_layout.addRow("<b>Max Time Gap:</b>", self.spin_time)

        # 2. Distance Threshold SpinBox
        self.spin_dist = QDoubleSpinBox()
        self.spin_dist.setRange(0.1, 100000.0)
        self.spin_dist.setDecimals(1)
        self.spin_dist.setSingleStep(5.0)
        self.spin_dist.setSuffix(" m")
        self.spin_dist.setValue(self._dist_val)
        self.spin_dist.setMinimumHeight(28)
        form_layout.addRow("<b>Max Distance Gap:</b>", self.spin_dist)

        layout.addWidget(group)

        # Action Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._on_save)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    @property
    def time_threshold(self) -> float:
        return self._time_val

    @property
    def dist_threshold(self) -> float:
        return self._dist_val

    def _on_save(self):
        self._time_val = float(self.spin_time.value())
        self._dist_val = float(self.spin_dist.value())
        logger.debug("Configured gap thresholds: Time=%.2fs, Dist=%.1fm", self._time_val, self._dist_val)
        self.accept()

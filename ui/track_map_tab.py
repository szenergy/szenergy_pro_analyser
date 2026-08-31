"""
Track Map tab widget component for sidebar bottom tabs.
Provides UI controls for selecting and rotating track maps with a central canvas area.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QSlider, QLabel, QFrame
)
from PySide6.QtCore import Qt


class TrackMapTabWidget(QWidget):
    """Widget embedded in the sidebar tab containing track map selection and rotation controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # 1. Top Controls Bar: Map selector dropdown & Rotation slider
        controls_layout = QVBoxLayout()
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(4)

        # Map dropdown row
        map_row = QHBoxLayout()
        map_row.setContentsMargins(0, 0, 0, 0)
        map_row.setSpacing(6)
        map_row.addWidget(QLabel("Map:"))
        self.map_combo = QComboBox()
        self.map_combo.addItems(["Default Map", "Track Map 1", "Track Map 2"])
        map_row.addWidget(self.map_combo, 1)
        controls_layout.addLayout(map_row)

        # Rotation slider row
        rot_row = QHBoxLayout()
        rot_row.setContentsMargins(0, 0, 0, 0)
        rot_row.setSpacing(6)
        rot_row.addWidget(QLabel("Rotation:"))

        self.rotation_slider = QSlider(Qt.Horizontal)
        self.rotation_slider.setRange(0, 360)
        self.rotation_slider.setValue(0)
        self.rotation_slider.setSingleStep(1)
        self.rotation_slider.setPageStep(15)
        rot_row.addWidget(self.rotation_slider, 1)

        self.rotation_value_label = QLabel("0°")
        self.rotation_value_label.setMinimumWidth(32)
        rot_row.addWidget(self.rotation_value_label)

        self.rotation_slider.valueChanged.connect(
            lambda val: self.rotation_value_label.setText(f"{val}°")
        )
        controls_layout.addLayout(rot_row)

        layout.addLayout(controls_layout)

        # 2. Track Map Viewport / Canvas Placeholder
        self.map_canvas = QFrame()
        self.map_canvas.setFrameShape(QFrame.StyledPanel)
        self.map_canvas.setFrameShadow(QFrame.Sunken)

        canvas_layout = QVBoxLayout(self.map_canvas)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        self.placeholder_canvas_label = QLabel("Track Map View")
        self.placeholder_canvas_label.setAlignment(Qt.AlignCenter)
        self.placeholder_canvas_label.setStyleSheet("color: #777777; font-style: italic;")
        canvas_layout.addWidget(self.placeholder_canvas_label)

        layout.addWidget(self.map_canvas, 1)

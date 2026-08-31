"""
Dialog allowing the user to rename the legend / curve labels that specify what the colors mean.
"""

from typing import Dict, List, Tuple
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QLineEdit, QHeaderView, QAbstractItemView
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap, QIcon

from core.data_models import Session


class RenameLegendLabelsDialog(QDialog):
    """
    Dialog allowing the user to rename the legend / curve labels that specify what the colors mean.
    """

    def __init__(
        self,
        selected_laps_info: List[Tuple[str, int, str]],
        sessions: Dict[str, Session],
        current_custom_labels: Dict[Tuple[str, int], str],
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("Rename Legend & Curve Labels")
        self.setMinimumSize(540, 360)
        self.selected_laps_info = selected_laps_info
        self.sessions = sessions
        self.current_custom_labels = current_custom_labels
        self.renamed_labels: Dict[Tuple[str, int], str] = {}
        self.inputs: Dict[Tuple[str, int], QLineEdit] = {}

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        info_label = QLabel(
            "<b>Rename Curve / Color Legend Labels:</b><br>"
            "Customize the legend labels that specify what each curve color represents on the graphs."
        )
        info_label.setTextFormat(Qt.RichText)
        layout.addWidget(info_label)

        # Table: Color & Session/Lap | Custom Legend Label
        self.table = QTableWidget(len(self.selected_laps_info), 2)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setHorizontalHeaderLabels(["Curve / Session Lap", "Custom Legend Label"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        for row, (session_id, lap_num, color) in enumerate(self.selected_laps_info):
            session = self.sessions.get(session_id)
            session_name = session.name if session else session_id
            default_name = f"{session_name} L{lap_num}"

            # Color swatch icon + session lap info
            item_info = QTableWidgetItem(f"  {session_name} — Lap {lap_num}")
            item_info.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

            pixmap = QPixmap(16, 16)
            pixmap.fill(QColor(color))
            item_info.setIcon(QIcon(pixmap))
            self.table.setItem(row, 0, item_info)

            # Editable custom name
            current_val = self.current_custom_labels.get((session_id, lap_num), default_name)
            edit = QLineEdit(current_val)
            edit.setPlaceholderText(default_name)
            self.inputs[(session_id, lap_num)] = edit
            self.table.setCellWidget(row, 1, edit)

        layout.addWidget(self.table)

        # Action Buttons
        btn_layout = QHBoxLayout()

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self._on_reset_defaults)
        btn_layout.addWidget(reset_btn)

        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        apply_btn = QPushButton("Apply & Save")
        apply_btn.setStyleSheet("background-color: #00E676; color: black; font-weight: bold;")
        apply_btn.clicked.connect(self._on_apply)
        btn_layout.addWidget(apply_btn)

        layout.addLayout(btn_layout)

    def _on_reset_defaults(self):
        for (session_id, lap_num), edit in self.inputs.items():
            session = self.sessions.get(session_id)
            session_name = session.name if session else session_id
            edit.setText(f"{session_name} L{lap_num}")

    def _on_apply(self):
        for (session_id, lap_num), edit in self.inputs.items():
            txt = edit.text().strip()
            if not txt:
                session = self.sessions.get(session_id)
                session_name = session.name if session else session_id
                txt = f"{session_name} L{lap_num}"
            self.renamed_labels[(session_id, lap_num)] = txt

        self.accept()

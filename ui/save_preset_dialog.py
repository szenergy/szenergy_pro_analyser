"""
Dialog prompting user whether to update an existing loaded preset or create a new one
when saving with a modified preset name in ImportWizardDialog.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QGridLayout
)
from PySide6.QtCore import Qt


class SavePresetChoiceDialog(QDialog):
    """
    Dialog prompting user whether to update an existing loaded preset or create a new one
    when saving with a modified preset name.
    """
    ACTION_UPDATE = "update"
    ACTION_CREATE_NEW = "create_new"
    ACTION_CANCEL = "cancel"

    selected_action: str = ACTION_CANCEL

    def __init__(self, old_name: str, new_name: str, channels_changed: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save Preset")
        self.setMinimumWidth(400)
        self.old_name = old_name
        self.new_name = new_name
        self.channels_changed = channels_changed
        self.selected_action = self.ACTION_CANCEL

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        prompt_label = QLabel(
            "<b>Save Preset Options</b><br>"
            "You have changed the name of the loaded preset. Would you like to update the existing preset or create a new one?"
        )
        prompt_label.setWordWrap(True)
        layout.addWidget(prompt_label)

        # Info Box Frame
        info_frame = QFrame()
        info_frame.setFrameShape(QFrame.StyledPanel)
        info_layout = QGridLayout(info_frame)
        info_layout.setContentsMargins(12, 10, 12, 10)
        info_layout.setHorizontalSpacing(12)
        info_layout.setVerticalSpacing(6)

        info_layout.addWidget(QLabel("<b>Original Name:</b>"), 0, 0)
        old_name_lbl = QLabel(self.old_name)
        old_name_lbl.setWordWrap(True)
        info_layout.addWidget(old_name_lbl, 0, 1)

        info_layout.addWidget(QLabel("<b>New Name:</b>"), 1, 0)
        new_name_lbl = QLabel(self.new_name)
        new_name_lbl.setWordWrap(True)
        info_layout.addWidget(new_name_lbl, 1, 1)

        info_layout.addWidget(QLabel("<b>Channels Changed:</b>"), 2, 0)
        ch_text = f"{self.channels_changed} channel" if self.channels_changed == 1 else f"{self.channels_changed} channels"
        info_layout.addWidget(QLabel(ch_text), 2, 1)

        layout.addWidget(info_frame)

        # Action Buttons Layout
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(cancel_btn)

        btn_layout.addStretch()

        update_btn = QPushButton("Update Existing")
        update_btn.setToolTip("Rename and update the currently loaded preset")
        update_btn.clicked.connect(self._on_update)
        btn_layout.addWidget(update_btn)

        create_btn = QPushButton("Create New")
        create_btn.setStyleSheet("background-color: #00E676; color: black; font-weight: bold;")
        create_btn.setToolTip("Create a brand new preset with this name and keep the original preset unchanged")
        create_btn.clicked.connect(self._on_create_new)
        btn_layout.addWidget(create_btn)

        layout.addLayout(btn_layout)

    def _on_cancel(self):
        self.selected_action = self.ACTION_CANCEL
        self.reject()

    def _on_update(self):
        self.selected_action = self.ACTION_UPDATE
        self.accept()

    def _on_create_new(self):
        self.selected_action = self.ACTION_CREATE_NEW
        self.accept()

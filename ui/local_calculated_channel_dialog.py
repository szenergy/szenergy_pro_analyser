"""
Dialog for creating and editing local calculated channels on a per-file basis.
Allows defining mathematical formulas using raw file columns as inputs (A, B, C...)
and mapping the evaluated result to a target global telemetry channel.
"""

import string
import logging
from typing import Any, Dict, List, Optional, Tuple
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.channel_calculator import validate_formula, extract_formula_variables
from core.state_manager import StateManager, generate_slug
from ui.calculated_channel_dialog import InputRowWidget
from utils.theme import is_system_dark_theme

logger = logging.getLogger(__name__)


class LocalCalculatedChannelDialog(QDialog):
    """
    Dialog for configuring a local calculated channel:
    - Name of the local calculation
    - Target global channel to map the result into
    - Input variables (A, B, C...) mapped to raw file columns
    - Mathematical formula with live AST validation
    """

    def __init__(
        self,
        raw_columns: List[str],
        state_manager: Optional[StateManager] = None,
        channel_data: Optional[Dict[str, Any]] = None,
        is_dark: Optional[bool] = None,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.raw_columns = list(raw_columns)
        self.state_manager = state_manager
        self.channel_data = channel_data or {}
        self.is_dark = is_dark if is_dark is not None else is_system_dark_theme()
        self.result_channel_data: Optional[Dict[str, Any]] = None

        self.input_rows: List[InputRowWidget] = []
        # Raw file columns formatted as [(col, col), ...] for InputRowWidget
        self.available_columns: List[Tuple[str, str]] = [(col, col) for col in self.raw_columns]

        is_editing = bool(self.channel_data and self.channel_data.get("formula"))
        self.setWindowTitle("Edit Local Calculated Channel" if is_editing else "Add Local Calculated Channel")
        self.setMinimumSize(560, 580)
        self.resize(600, 620)
        self.setModal(True)

        self._init_ui()
        self._populate_existing_data()
        self._validate_live()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(20, 18, 20, 18)

        # 1. Properties Form (Target Global Channel)
        prop_group = QGroupBox("Target Global Channel")
        prop_layout = QFormLayout(prop_group)
        prop_layout.setContentsMargins(14, 14, 14, 14)
        prop_layout.setSpacing(12)

        self.target_combo = QComboBox()
        self.target_combo.setEditable(True)
        self.target_combo.addItem("-- Select Target Global Channel --", "")
        if self.state_manager:
            for ch in self.state_manager.get_channel_defs():
                slug = ch.get("slug", "")
                disp_name = self.state_manager.get_display_name_by_slug(slug, ch.get("label", slug))
                self.target_combo.addItem(disp_name, slug)
        self.target_combo.setMinimumHeight(28)
        prop_layout.addRow("<b>Map to Global Channel:</b>", self.target_combo)

        main_layout.addWidget(prop_group)

        # 2. Formula Input Variables Group (From Raw File Columns)
        inputs_group = QGroupBox("Formula Input Variables (from File Channels)")
        inputs_vbox = QVBoxLayout(inputs_group)
        inputs_vbox.setContentsMargins(14, 14, 14, 14)
        inputs_vbox.setSpacing(10)

        self.inputs_container = QWidget()
        self.inputs_layout = QVBoxLayout(self.inputs_container)
        self.inputs_layout.setContentsMargins(4, 4, 4, 4)
        self.inputs_layout.setSpacing(8)
        self.inputs_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.inputs_container)
        scroll.setMinimumHeight(150)
        scroll.setStyleSheet("QScrollArea { border: 1px solid rgba(128, 128, 128, 0.25); border-radius: 4px; }")
        inputs_vbox.addWidget(scroll)

        self.btn_add_input = QPushButton("+ Add Input Variable")
        self.btn_add_input.setCursor(Qt.PointingHandCursor)
        self.btn_add_input.setStyleSheet("QPushButton { padding: 5px 14px; }")
        self.btn_add_input.clicked.connect(self._on_add_input_row)
        inputs_vbox.addWidget(self.btn_add_input, alignment=Qt.AlignLeft)

        main_layout.addWidget(inputs_group)

        # 3. Formula Group
        formula_group = QGroupBox("Formula Expression")
        formula_layout = QVBoxLayout(formula_group)
        formula_layout.setContentsMargins(14, 14, 14, 14)
        formula_layout.setSpacing(10)

        self.formula_input = QLineEdit()
        self.formula_input.setPlaceholderText("e.g. (A + B) / 2.0 or A * 3.6 or sqrt(A**2 + B**2)")
        self.formula_input.setMinimumHeight(32)
        mono_font = QFont("Monospace", 10)
        mono_font.setStyleHint(QFont.Monospace)
        self.formula_input.setFont(mono_font)
        self.formula_input.textChanged.connect(self._validate_live)
        formula_layout.addWidget(self.formula_input)

        func_help = QLabel(
            "<div style='color: #888; font-size: 11px; line-height: 140%;'>"
            "<div><b>Operators:</b> <code>+</code>, <code>-</code>, <code>*</code>, <code>/</code>, <code>**</code>, <code>%</code></div>"
            "<div style='margin-top: 4px;'><b>Functions:</b> <code>sqrt()</code>, <code>abs()</code>, <code>min()</code>, <code>max()</code>, "
            "<code>sin()</code>, <code>cos()</code>, <code>tan()</code>, <code>clip()</code>, <code>round()</code></div>"
            "</div>"
        )
        func_help.setTextFormat(Qt.RichText)
        func_help.setWordWrap(True)
        formula_layout.addWidget(func_help)

        self.status_label = QLabel("Status: Pending validation")
        self.status_label.setStyleSheet("font-size: 12px; font-weight: bold; padding: 4px 0;")
        formula_layout.addWidget(self.status_label)

        main_layout.addWidget(formula_group)

        # 4. Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setStyleSheet("padding: 6px 16px;")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("Save Channel")
        self.btn_save.setStyleSheet("background-color: #00E676; color: black; font-weight: bold; padding: 6px 20px;")
        self.btn_save.clicked.connect(self._on_save)
        btn_layout.addWidget(self.btn_save)

        main_layout.addLayout(btn_layout)

    def _populate_existing_data(self):
        """Populates dialog with existing channel data if editing."""
        self.formula_input.setText(self.channel_data.get("formula", ""))

        target_slug = self.channel_data.get("target_slug", "")
        if target_slug:
            idx = self.target_combo.findData(target_slug)
            if idx >= 0:
                self.target_combo.setCurrentIndex(idx)
            else:
                target_label = self.channel_data.get("target_label") or target_slug
                if self.state_manager:
                    target_label = self.state_manager.get_display_name_by_slug(target_slug, target_label)
                self.target_combo.setEditText(target_label)

        inputs = self.channel_data.get("inputs", {})
        if inputs:
            for letter, col in sorted(inputs.items()):
                self._add_input_row(var_letter=letter, selected_col=col)
        else:
            self._add_input_row(var_letter="A")

    def _get_next_letter(self) -> str:
        """Returns next available letter from alphabet A..Z."""
        used = {row.var_letter for row in self.input_rows}
        for char in string.ascii_uppercase:
            if char not in used:
                return char
        return "Z"

    def _on_add_input_row(self):
        next_letter = self._get_next_letter()
        self._add_input_row(var_letter=next_letter)
        self._validate_live()

    def _add_input_row(self, var_letter: str, selected_col: Optional[str] = None):
        row = InputRowWidget(
            var_letter=var_letter,
            available_channels=self.available_columns,
            selected_slug=selected_col,
            is_dark=self.is_dark,
            parent=self.inputs_container
        )
        row.combo.currentIndexChanged.connect(self._validate_live)
        row.btn_remove.clicked.connect(lambda _, r=row: self._remove_input_row(r))

        count = self.inputs_layout.count()
        self.inputs_layout.insertWidget(count - 1, row)
        self.input_rows.append(row)

    def _remove_input_row(self, row: InputRowWidget):
        if len(self.input_rows) <= 1:
            QMessageBox.information(self, "Minimum Inputs", "At least one input variable is required.")
            return

        self.inputs_layout.removeWidget(row)
        self.input_rows.remove(row)
        row.deleteLater()

        for idx, r in enumerate(self.input_rows):
            r.set_letter(string.ascii_uppercase[idx])

        self._validate_live()

    def _get_current_inputs_map(self) -> Dict[str, str]:
        """Returns {var_letter: raw_column_name}."""
        res = {}
        for r in self.input_rows:
            col = r.get_selected_slug()
            if col:
                res[r.var_letter] = col
        return res

    def _validate_live(self):
        """Runs live validation on current formula and input variables."""
        formula = self.formula_input.text().strip()
        defined_letters = {r.var_letter for r in self.input_rows}

        if not formula:
            self.status_label.setText("Status: <span style='color: #888;'>Enter a formula</span>")
            return

        is_valid, msg = validate_formula(formula, expected_vars=defined_letters)
        if is_valid:
            inputs_map = self._get_current_inputs_map()
            used_vars = extract_formula_variables(formula)
            unmapped = [v for v in used_vars if v not in inputs_map]
            if unmapped:
                self.status_label.setText(
                    f"Status: <span style='color: #FFB300;'>⚠ Select a file channel for variable(s): {', '.join(unmapped)}</span>"
                )
            else:
                self.status_label.setText("Status: <span style='color: #00E676;'>✓ Formula is valid</span>")
        else:
            self.status_label.setText(f"Status: <span style='color: #FF5252;'>⚠ {msg}</span>")

    def _on_save(self):
        formula = self.formula_input.text().strip()
        target_text = self.target_combo.currentText().strip()
        target_slug = self.target_combo.currentData() or ""

        if not target_text or target_text == "-- Select Target Global Channel --":
            QMessageBox.warning(self, "Validation Error", "Please select or enter a Target Global Channel.")
            self.target_combo.setFocus()
            return

        if not target_slug:
            idx = self.target_combo.findText(target_text)
            if idx >= 0:
                target_slug = self.target_combo.itemData(idx) or ""

        if not target_slug:
            # Resolve from text or generate slug
            if self.state_manager:
                target_slug = self.state_manager.get_slug_by_label(target_text) or generate_slug(target_text)
            else:
                target_slug = generate_slug(target_text)

        if not formula:
            QMessageBox.warning(self, "Validation Error", "Please provide a Formula expression.")
            self.formula_input.setFocus()
            return

        defined_letters = {r.var_letter for r in self.input_rows}
        is_valid, msg = validate_formula(formula, expected_vars=defined_letters)
        if not is_valid:
            QMessageBox.critical(self, "Formula Error", f"Formula error:\n{msg}")
            self.formula_input.setFocus()
            return

        inputs_map = self._get_current_inputs_map()
        used_vars = extract_formula_variables(formula)
        unmapped = [v for v in used_vars if v not in inputs_map]
        if unmapped:
            QMessageBox.warning(
                self, "Missing Channel Input",
                f"Please select a file channel for variable(s): {', '.join(unmapped)}."
            )
            return

        target_display = target_text
        if self.state_manager and target_slug:
            target_display = self.state_manager.get_display_name_by_slug(target_slug, target_text)

        self.result_channel_data = {
            "name": target_display,
            "formula": formula,
            "inputs": inputs_map,
            "target_slug": target_slug,
            "target_label": target_display,
        }

        self.accept()

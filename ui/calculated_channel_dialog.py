"""
Dialog for creating and editing calculated telemetry channels with
variable assignments (A, B, C...) and live formula validation.
"""

import string
from typing import Any, Dict, List, Optional, Set, Tuple
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QIcon, QColor
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
from core.state_manager import StateManager, format_channel_display
from utils.theme import is_system_dark_theme
from ui.graph_icons import create_icon_trash


class InputRowWidget(QWidget):
    """Row displaying variable letter badge, channel selector combo, and remove button."""

    def __init__(
        self,
        var_letter: str,
        available_channels: List[Tuple[str, str]],  # [(slug, display_name), ...]
        selected_slug: Optional[str] = None,
        is_dark: bool = False,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.var_letter = var_letter
        self.is_dark = is_dark

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 3, 2, 3)
        layout.setSpacing(10)

        # Variable letter badge
        self.badge = QLabel(f"<b>[{var_letter}]</b>")
        self.badge.setFixedSize(36, 28)
        self.badge.setAlignment(Qt.AlignCenter)
        badge_bg = "#2A2E35" if is_dark else "#E8EAF0"
        badge_fg = "#64B5F6" if is_dark else "#1976D2"
        self.badge.setStyleSheet(
            f"background-color: {badge_bg}; color: {badge_fg}; "
            f"border: 1px solid rgba(100, 181, 246, 0.3); border-radius: 4px; "
            f"font-family: monospace; font-size: 13px;"
        )
        layout.addWidget(self.badge)

        # Equals sign
        eq_label = QLabel("=")
        eq_label.setStyleSheet("font-weight: bold; color: #888; font-size: 14px;")
        layout.addWidget(eq_label)

        # Channel selection combobox
        self.combo = QComboBox()
        self.combo.addItem("-- Select Input Channel --", "")
        for slug, disp_name in available_channels:
            self.combo.addItem(disp_name, slug)

        if selected_slug:
            idx = self.combo.findData(selected_slug)
            if idx >= 0:
                self.combo.setCurrentIndex(idx)

        self.combo.setMinimumHeight(28)
        layout.addWidget(self.combo, 1)

        # Remove button with vector trash icon
        self.btn_remove = QPushButton()
        self.btn_remove.setIcon(create_icon_trash(is_dark))
        self.btn_remove.setIconSize(QSize(16, 16))
        self.btn_remove.setFixedSize(28, 28)
        self.btn_remove.setCursor(Qt.PointingHandCursor)
        self.btn_remove.setToolTip(f"Remove variable {var_letter}")
        self.btn_remove.setStyleSheet(
            "QPushButton { background-color: transparent; border: 1px solid rgba(255, 82, 82, 0.35); "
            "border-radius: 4px; padding: 2px; } "
            "QPushButton:hover { background-color: rgba(255, 82, 82, 0.15); border-color: #FF5252; }"
        )
        layout.addWidget(self.btn_remove)

    def set_letter(self, letter: str):
        self.var_letter = letter
        self.badge.setText(f"<b>[{letter}]</b>")
        self.btn_remove.setToolTip(f"Remove variable {letter}")

    def get_selected_slug(self) -> str:
        return self.combo.currentData() or ""


class CalculatedChannelDialog(QDialog):
    """
    Dialog allowing the user to configure a calculated channel:
    - Label and Unit
    - Variable letters (A, B, C...) mapped to existing telemetry channel slugs
    - Mathematical / Python formula expression with live validation
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        channel_data: Optional[Dict[str, Any]] = None,
        state_manager: Optional[StateManager] = None,
        is_dark: Optional[bool] = None
    ):
        super().__init__(parent)
        self.state_manager = state_manager
        self.channel_data = channel_data or {}
        self.is_dark = is_dark if is_dark is not None else is_system_dark_theme()
        self.result_channel_data: Optional[Dict[str, Any]] = None

        self.input_rows: List[InputRowWidget] = []
        self._load_available_channels()

        is_editing = bool(channel_data and channel_data.get("formula"))
        self.setWindowTitle("Edit Calculated Channel" if is_editing else "Add Calculated Channel")
        self.setMinimumSize(540, 600)
        self.resize(580, 640)
        self.setModal(True)

        self._init_ui()
        self._populate_existing_data()
        self._validate_live()

    def _load_available_channels(self):
        """Loads available standard channels excluding current channel if editing to avoid direct self-reference."""
        self.available_channels: List[Tuple[str, str]] = []
        if not self.state_manager:
            return

        current_slug = self.channel_data.get("slug", "")
        for ch in self.state_manager.get_channel_defs():
            slug = ch.get("slug", "")
            if slug and slug != current_slug:
                disp_name = format_channel_display(ch.get("label", slug), ch.get("unit", ""))
                self.available_channels.append((slug, disp_name))

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(20, 18, 20, 18)

        # 1. Properties Form (Label & Unit)
        prop_group = QGroupBox("Channel Properties")
        prop_layout = QFormLayout(prop_group)
        prop_layout.setContentsMargins(14, 14, 14, 14)
        prop_layout.setSpacing(12)

        self.label_input = QLineEdit()
        self.label_input.setPlaceholderText("e.g. Power, Slip Ratio, Roll Angle")
        self.label_input.setMinimumHeight(28)
        prop_layout.addRow("<b>Channel Label:</b>", self.label_input)

        self.unit_input = QLineEdit()
        self.unit_input.setPlaceholderText("e.g. kW, %, deg, bar")
        self.unit_input.setMinimumHeight(28)
        self.unit_input.setMaximumWidth(160)
        prop_layout.addRow("<b>Engineering Unit:</b>", self.unit_input)

        main_layout.addWidget(prop_group)

        # 2. Input Channels Group
        inputs_group = QGroupBox("Input Channel Variables")
        inputs_vbox = QVBoxLayout(inputs_group)
        inputs_vbox.setContentsMargins(14, 14, 14, 14)
        inputs_vbox.setSpacing(10)

        hint_label = QLabel(
            "<span style='color: #888;'>Assign letters to channels. Use these letters in your equation below:</span>"
        )
        hint_label.setWordWrap(True)
        inputs_vbox.addWidget(hint_label)

        # Scroll area for input variable rows
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

        # Add Input Button
        self.btn_add_input = QPushButton("+ Add Input Variable")
        self.btn_add_input.setCursor(Qt.PointingHandCursor)
        self.btn_add_input.setStyleSheet("QPushButton { padding: 5px 14px; }")
        self.btn_add_input.clicked.connect(self._on_add_input_row)
        inputs_vbox.addWidget(self.btn_add_input, alignment=Qt.AlignLeft)

        main_layout.addWidget(inputs_group)

        # 3. Formula Group
        formula_group = QGroupBox("Formula / Equation")
        formula_layout = QVBoxLayout(formula_group)
        formula_layout.setContentsMargins(14, 14, 14, 14)
        formula_layout.setSpacing(10)

        self.formula_input = QLineEdit()
        self.formula_input.setPlaceholderText("e.g. (A * B) / 1000.0   or   sqrt(A**2 + B**2)")
        self.formula_input.setMinimumHeight(32)
        mono_font = QFont("Monospace", 10)
        mono_font.setStyleHint(QFont.Monospace)
        self.formula_input.setFont(mono_font)
        self.formula_input.textChanged.connect(self._validate_live)
        formula_layout.addWidget(self.formula_input)

        # Vertically stacked hints for operators and functions
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

        # Live Status Label
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
        """Populates dialog with existing channel data if editing or carried over."""
        self.label_input.setText(self.channel_data.get("label", ""))
        self.unit_input.setText(self.channel_data.get("unit", ""))
        self.formula_input.setText(self.channel_data.get("formula", ""))

        inputs = self.channel_data.get("inputs", {})
        if inputs:
            for letter, slug in sorted(inputs.items()):
                self._add_input_row(var_letter=letter, selected_slug=slug)
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

    def _add_input_row(self, var_letter: str, selected_slug: Optional[str] = None):
        row = InputRowWidget(
            var_letter=var_letter,
            available_channels=self.available_channels,
            selected_slug=selected_slug,
            is_dark=self.is_dark,
            parent=self.inputs_container
        )
        row.combo.currentIndexChanged.connect(self._validate_live)
        row.btn_remove.clicked.connect(lambda _, r=row: self._remove_input_row(r))

        # Insert before stretch item in inputs_layout
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

        # Re-assign sequential letters A, B, C...
        for idx, r in enumerate(self.input_rows):
            r.set_letter(string.ascii_uppercase[idx])

        self._validate_live()

    def _get_current_inputs_map(self) -> Dict[str, str]:
        """Returns {var_letter: channel_slug}."""
        res = {}
        for r in self.input_rows:
            slug = r.get_selected_slug()
            if slug:
                res[r.var_letter] = slug
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
            # Check if all variables in formula actually have an assigned channel selected
            inputs_map = self._get_current_inputs_map()
            used_vars = extract_formula_variables(formula)
            unmapped = [v for v in used_vars if v not in inputs_map]
            if unmapped:
                self.status_label.setText(
                    f"Status: <span style='color: #FFB300;'>⚠ Select a channel for variable(s): {', '.join(unmapped)}</span>"
                )
            else:
                self.status_label.setText("Status: <span style='color: #00E676;'>✓ Formula is valid</span>")
        else:
            self.status_label.setText(f"Status: <span style='color: #FF5252;'>⚠ {msg}</span>")

    def _on_save(self):
        label = self.label_input.text().strip()
        unit = self.unit_input.text().strip()
        formula = self.formula_input.text().strip()

        if not label:
            QMessageBox.warning(self, "Validation Error", "Please provide a Channel Label.")
            self.label_input.setFocus()
            return

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

        # Ensure all variables used in formula have a selected channel
        inputs_map = self._get_current_inputs_map()
        used_vars = extract_formula_variables(formula)
        unmapped = [v for v in used_vars if v not in inputs_map]
        if unmapped:
            QMessageBox.warning(
                self, "Missing Channel Input",
                f"Please select a channel for variable(s): {', '.join(unmapped)}."
            )
            return

        # Determine slug
        slug = self.channel_data.get("slug")
        if not slug:
            if self.state_manager:
                existing_slugs = [ch["slug"] for ch in self.state_manager.get_channel_defs()]
                slug = self.state_manager.generate_unique_slug(label, existing_slugs)
            else:
                from core.state_manager import generate_slug
                slug = generate_slug(label)

        self.result_channel_data = {
            "label": label,
            "unit": unit,
            "slug": slug,
            "type": "calculated",
            "formula": formula,
            "inputs": inputs_map,
        }

        self.accept()

"""
Unit and integration tests for UI components including GraphViewWidget and SidebarWidget.
"""

import sys
import unittest
import numpy as np
from PySide6.QtWidgets import QApplication

from core.data_models import Session, Lap
from ui.graph_view import GraphViewWidget
from ui.sidebar import SidebarWidget
from ui.edit_dialogs import RenameLegendLabelsDialog

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)


class TestUIComponents(unittest.TestCase):

    def setUp(self):
        # Create dummy session
        self.session = Session(
            id="s_test",
            name="test_session.csv",
            file_path="/tmp/test.csv",
            channels=["Speed", "RPM"]
        )
        data1 = {
            "Time": np.array([0.0, 1.0, 2.0]),
            "Speed": np.array([10.0, 20.0, 30.0]),
            "RPM": np.array([1000.0, 2000.0, 3000.0])
        }
        lap1 = Lap("s_test", 1, 2.0, 30.0, data1)
        self.session.laps.append(lap1)

    def test_graph_view_rebuild_plots_no_crash(self):
        widget = GraphViewWidget()
        sessions = {self.session.id: self.session}
        widget.set_sessions(sessions)

        # Select laps and channels
        widget.set_selected_laps([(self.session.id, 1, "#00E676")])
        widget.set_selected_channels({"Speed", "RPM"})

        # Should rebuild plots without raising AttributeError
        self.assertEqual(len(widget.plot_widgets), 2)
        self.assertIn("Speed", widget.plot_widgets)
        self.assertIn("RPM", widget.plot_widgets)

    def test_equal_viewbox_heights_and_x_grid_on_all_plots(self):
        widget = GraphViewWidget()
        widget.resize(800, 600)
        sessions = {self.session.id: self.session}
        widget.set_sessions(sessions)
        widget.set_selected_laps([(self.session.id, 1, "#00E676")])
        widget.set_selected_channels({"Speed", "RPM"})

        widget.show()
        app.processEvents()

        # Both plots must have bottom axis with grid enabled
        p1 = widget.plot_widgets["Speed"]
        p2 = widget.plot_widgets["RPM"]

        self.assertNotEqual(p1.getAxis("bottom").grid, False)
        self.assertNotEqual(p2.getAxis("bottom").grid, False)

        # ViewBox heights should be equal
        h1 = p1.vb.geometry().height()
        h2 = p2.vb.geometry().height()
        self.assertAlmostEqual(h1, h2, delta=2.0)

    def test_graph_view_toolbar_buttons(self):
        widget = GraphViewWidget()
        sessions = {self.session.id: self.session}
        widget.set_sessions(sessions)
        widget.set_selected_laps([(self.session.id, 1, "#00E676")])
        widget.set_selected_channels({"Speed"})

        # 1. Test X Grid Toggle
        self.assertTrue(widget.btn_x_grid.isChecked())
        widget.btn_x_grid.setChecked(False)
        self.assertFalse(widget.show_x_grid)
        widget.btn_x_grid.setChecked(True)
        self.assertTrue(widget.show_x_grid)

        # 2. Test Y Grid Toggle
        self.assertTrue(widget.btn_y_grid.isChecked())
        widget.btn_y_grid.setChecked(False)
        self.assertFalse(widget.show_y_grid)

        # 3. Test Cursor Value Toggle
        self.assertTrue(widget.btn_cursor.isChecked())
        widget.btn_cursor.setChecked(False)
        self.assertFalse(widget.show_cursor_values)
        for v_line in widget.v_lines:
            self.assertFalse(v_line.isVisible())

        # 4. Test Legend Toggle
        self.assertTrue(widget.btn_legend.isChecked())
        widget.btn_legend.setChecked(False)
        self.assertFalse(widget.show_legend)
        if widget.legend:
            self.assertFalse(widget.legend.isVisible())

        # 5. Test Auto Range Click
        widget.btn_autorange.click()

        # 6. Test Theme application with icon updates
        widget.apply_theme(True)
        widget.apply_theme(False)

    def test_rename_legend_labels_dialog_and_application(self):
        selected_laps = [(self.session.id, 1, "#00E676")]
        sessions = {self.session.id: self.session}
        custom_labels = {}

        # 1. Test dialog logic
        dialog = RenameLegendLabelsDialog(selected_laps, sessions, custom_labels)
        dialog.inputs[(self.session.id, 1)].setText("Baseline Run 1 (Hard Compound)")
        dialog._on_apply()

        self.assertEqual(
            dialog.renamed_labels[(self.session.id, 1)],
            "Baseline Run 1 (Hard Compound)"
        )

        # 2. Test applying renaming on GraphViewWidget
        widget = GraphViewWidget()
        widget.set_sessions(sessions)
        widget.set_selected_laps(selected_laps)
        widget.set_selected_channels({"Speed"})

        # Apply custom label
        widget.custom_lap_labels.update(dialog.renamed_labels)
        widget.rebuild_plots()

        # Verify legend item text in first plot
        self.assertIsNotNone(widget.legend)
        legend_labels = [label.text for _, label in widget.legend.items]
        self.assertIn("Baseline Run 1 (Hard Compound)", legend_labels)


if __name__ == "__main__":
    unittest.main()

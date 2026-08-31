"""
Unit tests for track map parser, state manager map storage, ImportMapDialog,
MapManagerDialog, and TrackMapTabWidget with Excel and CSV map support.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import numpy as np
import pandas as pd

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QFileDialog
from PySide6.QtCore import Qt

from core.state_manager import StateManager
from core.map_parser import (
    get_map_file_columns, load_map_file_data
)
from ui.import_map_dialog import ImportMapDialog
from ui.map_manager_dialog import MapManagerDialog
from ui.track_map_tab import TrackMapTabWidget
from utils.constants import LAP_COLORS

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)


class TestMapComponents(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_mgr = StateManager(config_dir=self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_csv_file_parsing_and_loading(self):
        """Validates that CSV (.csv) files are parsed for track map columns with automatic delimiter detection."""
        csv_path = os.path.join(self.temp_dir.name, "circuit.csv")
        df = pd.DataFrame({
            "pos_x": [0.0, 10.0, 20.0, 30.0],
            "pos_y": [0.0, 5.0, 15.0, 25.0],
            "lap_distance": [0.0, 11.1, 25.0, 39.0]
        })
        df.to_csv(csv_path, index=False)

        cols = get_map_file_columns(csv_path)
        self.assertIn("pos_x", cols)
        self.assertIn("pos_y", cols)
        self.assertIn("lap_distance", cols)

        x, y, dist = load_map_file_data(csv_path, "pos_x", "pos_y", "lap_distance")
        self.assertEqual(len(x), 4)
        self.assertEqual(len(y), 4)
        self.assertIsNotNone(dist)
        self.assertEqual(len(dist), 4)
        self.assertEqual(x[1], 10.0)
        self.assertEqual(y[2], 15.0)

    def test_excel_file_parsing_and_loading(self):
        """Validates that Excel .xlsx files are parsed for track map columns."""
        xlsx_path = os.path.join(self.temp_dir.name, "track_data.xlsx")
        df = pd.DataFrame({
            "Coord_X": [100.0, 110.0, 120.0],
            "Coord_Y": [200.0, 210.0, 220.0],
            "Dist_m": [0.0, 14.14, 28.28]
        })
        df.to_excel(xlsx_path, index=False)

        cols = get_map_file_columns(xlsx_path)
        self.assertIn("Coord_X", cols)
        self.assertIn("Coord_Y", cols)
        self.assertIn("Dist_m", cols)

        x, y, dist = load_map_file_data(xlsx_path, "Coord_X", "Coord_Y", "Dist_m")
        self.assertEqual(len(x), 3)
        self.assertEqual(len(y), 3)
        self.assertIsNotNone(dist)
        self.assertEqual(x[0], 100.0)

    def test_headerless_csv_file_parsing_preserves_first_row_data(self):
        """Validates that headerless CSV files (numeric row 0) don't lose the first data row."""
        csv_path = os.path.join(self.temp_dir.name, "headerless.csv")
        # Raw lines starting with numbers
        with open(csv_path, "w") as f:
            f.write("1.23,4.56,0.0\n")
            f.write("7.89,10.11,10.0\n")
            f.write("12.13,14.15,20.0\n")

        cols = get_map_file_columns(csv_path)
        self.assertEqual(cols, ["Column 1", "Column 2", "Column 3"])

        x, y, dist = load_map_file_data(csv_path, "Column 1", "Column 2", "Column 3")
        self.assertEqual(len(x), 3)
        self.assertEqual(x[0], 1.23)
        self.assertEqual(y[0], 4.56)
        self.assertEqual(dist[0], 0.0)

    def test_headerless_excel_file_parsing_preserves_first_row_data(self):
        """Validates that headerless Excel files (numeric row 0) don't lose the first data row."""
        xlsx_path = os.path.join(self.temp_dir.name, "headerless.xlsx")
        df = pd.DataFrame([
            [10.5, 20.5, 0.0],
            [30.5, 40.5, 50.0],
            [50.5, 60.5, 100.0]
        ])
        df.to_excel(xlsx_path, index=False, header=False)

        cols = get_map_file_columns(xlsx_path)
        self.assertEqual(cols, ["Column 1", "Column 2", "Column 3"])

        x, y, dist = load_map_file_data(xlsx_path, "Column 1", "Column 2", "Column 3")
        self.assertEqual(len(x), 3)
        self.assertEqual(x[0], 10.5)
        self.assertEqual(y[0], 20.5)
        self.assertEqual(dist[0], 0.0)

    def test_state_manager_map_persistence_in_maps_directory(self):
        """Validates that maps are saved to <config_dir>/maps, loaded, and deleted."""
        maps_dir = self.state_mgr.get_maps_dir()
        self.assertTrue(os.path.exists(maps_dir))

        # 1. Save Map
        x_data = np.array([1.0, 2.0, 3.0])
        y_data = np.array([4.0, 5.0, 6.0])
        dist_data = np.array([0.0, 10.0, 20.0])

        saved_path = self.state_mgr.save_map("Hungaroring", x_data, y_data, dist_data)
        self.assertTrue(os.path.exists(saved_path))
        self.assertEqual(os.path.basename(saved_path), "hungaroring.json")

        # 2. Load Maps
        maps = self.state_mgr.load_maps()
        self.assertEqual(len(maps), 1)
        self.assertEqual(maps[0]["name"], "Hungaroring")
        np.testing.assert_array_equal(maps[0]["x"], x_data)
        np.testing.assert_array_equal(maps[0]["y"], y_data)
        np.testing.assert_array_equal(maps[0]["distance"], dist_data)

        # 3. Get Map
        m = self.state_mgr.get_map("hungaroring")
        self.assertIsNotNone(m)
        self.assertEqual(m["name"], "Hungaroring")

        # 4. Rename Map
        self.state_mgr.save_map("Hungaroring GP", x_data, y_data, dist_data, old_name="Hungaroring")
        self.assertFalse(os.path.exists(os.path.join(maps_dir, "hungaroring.json")))
        self.assertTrue(os.path.exists(os.path.join(maps_dir, "hungaroring_gp.json")))

        # 5. Delete Map
        self.assertTrue(self.state_mgr.delete_map("Hungaroring GP"))
        self.assertEqual(len(self.state_mgr.load_maps()), 0)

    def test_import_map_dialog_auto_detection_and_validation(self):
        """Validates ImportMapDialog column heuristics and input validation."""
        cols = ["Time", "pos_x", "pos_y", "lap_dist", "Speed"]
        dlg = ImportMapDialog(file_path="/tmp/circuit_test.xlsx", columns=cols)

        # Verify auto-detection
        self.assertEqual(dlg.x_combo.currentText(), "pos_x")
        self.assertEqual(dlg.y_combo.currentText(), "pos_y")
        self.assertEqual(dlg.dist_combo.currentText(), "lap_dist")

        # Validation test: empty name
        dlg.map_name_input.setText("")
        with patch.object(QMessageBox, "warning") as mock_warn:
            dlg._on_import_clicked()
            mock_warn.assert_called_once()

        # Validation test: valid inputs
        dlg.map_name_input.setText("Test Track")
        dlg._on_import_clicked()
        self.assertEqual(dlg.selected_map_name, "Test Track")
        self.assertEqual(dlg.selected_x_col, "pos_x")
        self.assertEqual(dlg.selected_y_col, "pos_y")
        self.assertEqual(dlg.selected_dist_col, "lap_dist")

    def test_map_manager_dialog_add_and_render_flow(self):
        """Validates adding a map via MapManagerDialog and rendering on plot canvas."""
        # Create test track file
        csv_path = os.path.join(self.temp_dir.name, "monza.csv")
        pd.DataFrame({
            "x": [0.0, 100.0, 200.0, 0.0],
            "y": [0.0, 50.0, 0.0, 0.0]
        }).to_csv(csv_path, index=False)

        dlg = MapManagerDialog(state_manager=self.state_mgr)
        self.assertEqual(dlg.map_list.count(), 0)

        def _mock_import_exec(import_dlg):
            import_dlg.selected_map_name = "Monza"
            import_dlg.selected_x_col = "x"
            import_dlg.selected_y_col = "y"
            import_dlg.selected_dist_col = None
            return QDialog.Accepted

        # Mock user adding the file and accepting Import dialog
        with patch.object(QFileDialog, "getOpenFileName", return_value=(csv_path, "CSV Files (*.csv)")):
            with patch.object(ImportMapDialog, "exec", _mock_import_exec):
                dlg._on_add_map()

        self.assertEqual(dlg.map_list.count(), 1)
        self.assertEqual(dlg.map_list.item(0).text(), "Monza")
        self.assertEqual(dlg.map_name_input.text(), "Monza")
        self.assertEqual(len(dlg.map_curve.xData), 4)

        # Test Renaming
        dlg.map_name_input.setText("Monza Autodromo")
        dlg._on_save_map()
        self.assertEqual(dlg.map_list.item(0).text(), "Monza Autodromo")

        # Test Removing
        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            dlg._on_remove_map()
        self.assertEqual(dlg.map_list.count(), 0)

    def test_track_map_tab_dropdown_and_rotation(self):
        """Validates TrackMapTabWidget map loading, dropdown switching, and 2D rotation."""
        # Pre-save a map
        x = np.array([0.0, 10.0, 10.0, 0.0])
        y = np.array([0.0, 0.0, 10.0, 10.0])
        self.state_mgr.save_map("Square Track", x, y)

        tab = TrackMapTabWidget(state_manager=self.state_mgr)
        self.assertIn("Square Track", [tab.map_combo.itemText(i) for i in range(tab.map_combo.count())])
        self.assertEqual(tab.map_combo.currentText(), "Square Track")

        # Verify slider range and initial center value
        self.assertEqual(tab.rotation_slider.minimum(), -180)
        self.assertEqual(tab.rotation_slider.maximum(), 180)
        self.assertEqual(tab.rotation_slider.value(), 0)
        self.assertEqual(tab.plot_widget.contextMenuPolicy(), Qt.NoContextMenu)

        # Initial curve data
        self.assertEqual(len(tab.map_curve.xData), 4)
        np.testing.assert_allclose(tab.map_curve.xData, x)
        np.testing.assert_allclose(tab.map_curve.yData, y)

        # Rotate +90 degrees
        tab.rotation_slider.setValue(90)
        self.assertEqual(tab.rotation_value_label.text(), "90°")
        self.assertAlmostEqual(tab.map_curve.xData[0], 10.0, places=4)
        self.assertAlmostEqual(tab.map_curve.yData[0], 0.0, places=4)

        # Rotate -90 degrees
        tab.rotation_slider.setValue(-90)
        self.assertEqual(tab.rotation_value_label.text(), "-90°")
        # For point (0, 0) rotated -90 deg:
        # dx = -5, dy = -5, cos(-90)=0, sin(-90)=-1
        # x_rot = (-5*0) - (-5*-1) + 5 = 0.0
        # y_rot = (-5*-1) + (-5*0) + 5 = 10.0
        self.assertAlmostEqual(tab.map_curve.xData[0], 0.0, places=4)
        self.assertAlmostEqual(tab.map_curve.yData[0], 10.0, places=4)

    def test_track_map_theme_adaptation_and_pen_width(self):
        """Validates that track map canvas and pen adapt properly to dark and light themes with thick width."""
        tab = TrackMapTabWidget(state_manager=self.state_mgr)

        # 1. Dark Theme
        tab.apply_theme(is_dark=True)
        self.assertTrue(tab.is_dark)
        self.assertEqual(tab.map_curve.opts["pen"].width(), 4)

        # 2. Light Theme
        tab.apply_theme(is_dark=False)
        self.assertFalse(tab.is_dark)
        self.assertEqual(tab.map_curve.opts["pen"].width(), 4)

        # 3. Map Manager Dialog Theme
        dlg = MapManagerDialog(state_manager=self.state_mgr)
        dlg.apply_theme(is_dark=True)
        self.assertEqual(dlg.map_curve.opts["pen"].width(), 4)
        dlg.apply_theme(is_dark=False)
        self.assertEqual(dlg.map_curve.opts["pen"].width(), 4)

    def test_track_map_rotation_remembered_per_map(self):
        """Validates that TrackMapTabWidget remembers and restores individual rotation for each map."""
        x = np.array([0.0, 10.0, 10.0, 0.0])
        y = np.array([0.0, 0.0, 10.0, 10.0])
        self.state_mgr.save_map("Track Alpha", x, y, rotation=45.0)
        self.state_mgr.save_map("Track Beta", x, y, rotation=-90.0)

        tab = TrackMapTabWidget(state_manager=self.state_mgr)
        tab.map_combo.setCurrentText("Track Alpha")
        self.assertEqual(tab.rotation_slider.value(), 45)
        self.assertEqual(tab.rotation_value_label.text(), "45°")

        tab.map_combo.setCurrentText("Track Beta")
        self.assertEqual(tab.rotation_slider.value(), -90)
        self.assertEqual(tab.rotation_value_label.text(), "-90°")

        # Change rotation for Beta in the tab
        tab.rotation_slider.setValue(120)
        self.assertEqual(tab.rotation_value_label.text(), "120°")

        # Switch away and back
        tab.map_combo.setCurrentText("Track Alpha")
        self.assertEqual(tab.rotation_slider.value(), 45)

        tab.map_combo.setCurrentText("Track Beta")
        self.assertEqual(tab.rotation_slider.value(), 120)

    def test_map_manager_rotation_slider_and_persistence(self):
        """Validates MapManagerDialog rotation slider live preview and save persistence."""
        x = np.array([0.0, 10.0, 10.0, 0.0])
        y = np.array([0.0, 0.0, 10.0, 10.0])
        self.state_mgr.save_map("Silverstone", x, y, rotation=0.0)

        dlg = MapManagerDialog(state_manager=self.state_mgr)
        self.assertEqual(dlg.map_list.count(), 1)
        self.assertEqual(dlg.rotation_slider.value(), 0)
        self.assertEqual(dlg.rotation_value_label.text(), "0°")

        # Adjust rotation slider in Map Manager
        dlg.rotation_slider.setValue(90)
        self.assertEqual(dlg.rotation_value_label.text(), "90°")
        self.assertAlmostEqual(dlg.map_curve.xData[0], 10.0, places=4)
        self.assertAlmostEqual(dlg.map_curve.yData[0], 0.0, places=4)

        # Save map and verify persistence in StateManager
        dlg._on_save_map()
        saved = self.state_mgr.get_map("Silverstone")
        self.assertIsNotNone(saved)
        self.assertEqual(saved["rotation"], 90.0)

    def test_map_manager_color_selector_and_persistence(self):
        """Validates MapManagerDialog color selection from LAP_COLORS and save persistence."""
        x = np.array([0.0, 10.0, 10.0, 0.0])
        y = np.array([0.0, 0.0, 10.0, 10.0])
        self.state_mgr.save_map("Hungaroring", x, y, color=LAP_COLORS[0])

        dlg = MapManagerDialog(state_manager=self.state_mgr)
        self.assertEqual(dlg._current_color, LAP_COLORS[0])
        self.assertIn(LAP_COLORS[0], dlg.color_btn.styleSheet())

        # Select a new color from LAP_COLORS
        new_color = LAP_COLORS[4]
        dlg._on_color_selected(new_color)
        self.assertEqual(dlg._current_color, new_color)
        self.assertIn(new_color, dlg.color_btn.styleSheet())

        # Save and verify
        dlg._on_save_map()
        saved = self.state_mgr.get_map("Hungaroring")
        self.assertIsNotNone(saved)
        self.assertEqual(saved["color"], new_color)

    def test_track_map_tab_displays_saved_color(self):
        """Validates that TrackMapTabWidget loads and renders the track using its saved color."""
        x = np.array([0.0, 10.0, 10.0, 0.0])
        y = np.array([0.0, 0.0, 10.0, 10.0])
        self.state_mgr.save_map("Track Color A", x, y, color=LAP_COLORS[3])
        self.state_mgr.save_map("Track Color B", x, y, color=LAP_COLORS[6])

        tab = TrackMapTabWidget(state_manager=self.state_mgr)
        tab.map_combo.setCurrentText("Track Color A")
        self.assertEqual(tab._current_color, LAP_COLORS[3])

        tab.map_combo.setCurrentText("Track Color B")
        self.assertEqual(tab._current_color, LAP_COLORS[6])


if __name__ == "__main__":
    unittest.main()

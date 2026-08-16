import os
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from PySide6.QtWidgets import (
    QApplication, QMessageBox, QDialog, QTableWidget, QTableWidgetItem, QComboBox, QLineEdit, QHeaderView, QMenu
)
from PySide6.QtCore import QPointF, QPoint, Qt, QEvent
from PySide6.QtGui import QKeyEvent

from core.data_models import Session, Lap
from core.state_manager import StateManager
from ui.graph_view import GraphViewWidget, _get_nearest_channel_sample, XZoomViewBox
from ui.sidebar import SidebarWidget
from ui.import_wizard import ImportWizardDialog
from ui.edit_dialogs import PresetManagerDialog, ChannelManagerDialog, RenameLegendLabelsDialog

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)


class TestUIComponents(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        # Create dummy session
        self.session = Session(
            id="s_test",
            name="test_session.csv",
            file_path="/tmp/test.csv",
            channels=["speed", "rpm", "distance"]
        )
        data1 = {
            "time": np.array([0.0, 1.0, 2.0]),
            "distance": np.array([0.0, 10.0, 20.0]),
            "speed": np.array([10.0, 20.0, 30.0]),
            "rpm": np.array([1000.0, 2000.0, 3000.0])
        }
        lap1 = Lap("s_test", 1, 2.0, 30.0, data1)
        self.session.laps.append(lap1)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_graph_view_rebuild_plots_no_crash(self):
        widget = GraphViewWidget()
        sessions = {self.session.id: self.session}
        widget.set_sessions(sessions)

        # Select laps and channels
        widget.set_selected_laps([(self.session.id, 1, "#00E676")])
        widget.set_selected_channels({"speed", "rpm"})

        # Should rebuild plots without raising AttributeError
        self.assertEqual(len(widget.plot_widgets), 2)
        self.assertIn("speed", widget.plot_widgets)
        self.assertIn("rpm", widget.plot_widgets)

    def test_equal_viewbox_heights_and_x_grid_on_all_plots(self):
        widget = GraphViewWidget()
        widget.resize(800, 600)
        sessions = {self.session.id: self.session}
        widget.set_sessions(sessions)
        widget.set_selected_laps([(self.session.id, 1, "#00E676")])
        widget.set_selected_channels({"speed", "rpm"})

        widget.show()
        app.processEvents()

        # Both plots must have bottom axis with grid enabled
        p1 = widget.plot_widgets["speed"]
        p2 = widget.plot_widgets["rpm"]

        self.assertEqual(p1.getAxis("bottom").grid, False)
        self.assertEqual(p2.getAxis("bottom").grid, False)

        # ViewBox heights should be equal
        h1 = p1.vb.geometry().height()
        h2 = p2.vb.geometry().height()
        self.assertAlmostEqual(h1, h2, delta=2.0)

    def test_graph_view_toolbar_buttons(self):
        widget = GraphViewWidget()
        sessions = {self.session.id: self.session}
        widget.set_sessions(sessions)
        widget.set_selected_laps([(self.session.id, 1, "#00E676")])
        widget.set_selected_channels({"speed"})

        # 1. Test X Grid Toggle
        self.assertFalse(widget.btn_x_grid.isChecked())
        widget.btn_x_grid.setChecked(True)
        self.assertTrue(widget.show_x_grid)
        widget.btn_x_grid.setChecked(False)
        self.assertFalse(widget.show_x_grid)

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
        widget.set_selected_channels({"speed"})

        # Apply custom label
        widget.custom_lap_labels.update(dialog.renamed_labels)
        widget.rebuild_plots()

        # Verify legend item text in first plot
        self.assertIsNotNone(widget.legend)
        legend_labels = [label.text for _, label in widget.legend.items]
        self.assertIn("Baseline Run 1 (Hard Compound)", legend_labels)

    def test_tracking_dots_creation_and_movement(self):
        widget = GraphViewWidget()
        sessions = {self.session.id: self.session}
        widget.set_sessions(sessions)
        widget.set_selected_laps([(self.session.id, 1, "#00E676")])
        widget.set_selected_channels({"speed", "rpm"})

        # 2 channels * 1 lap = 2 tracking dots
        self.assertEqual(len(widget.tracking_dots), 2)

        # Test cursor movement at X = 1.0s (requires Time as X-axis)
        widget.x_axis_slug = "time"
        first_plot = widget.plot_widgets["speed"]
        scene_pos = first_plot.vb.mapViewToScene(QPointF(1.0, 20.0))
        widget._on_mouse_moved(scene_pos)

        # Verify dot data updated (Speed should be 20.0 at X=1.0)
        speed_dot = [d for d, _, _, ch in widget.tracking_dots if ch == "speed"][0]
        points = speed_dot.points()
        self.assertEqual(len(points), 1)
        self.assertAlmostEqual(points[0].pos().x(), 1.0, places=2)
        self.assertAlmostEqual(points[0].pos().y(), 20.0, places=2)

        # Verify toggle cursor values hides tracking dots
        widget.btn_cursor.setChecked(False)
        self.assertFalse(speed_dot.isVisible())

    def test_auto_guess_mapping_comprehensive(self):
        """Validates auto-guess matching across automotive telemetry patterns and confirms non-matches."""
        state_mgr = StateManager(config_dir=self.temp_dir.name)
        wizard = ImportWizardDialog(
            file_path="test.csv",
            raw_columns=["Time", "Speed"],
            preview_df=pd.DataFrame(),
            state_manager=state_mgr
        )

        expected_matches = {
            # Lap
            "lap": "Lap", "lap_no": "Lap", "kor": "Lap", "round": "Lap", "korszam": "Lap", "kor_szam": "Lap",
            # Time
            "time": "Time", "timestamp": "Time", "ido": "Time", "sec": "Time", "t": "Time",
            # Distance
            "distance": "Distance", "dist": "Distance", "tavolsag": "Distance", "pos": "Distance", "position": "Distance", "odo": "Distance", "d": "Distance", "dist_m": "Distance",
            # Speed
            "speed": "Speed", "spd": "Speed", "velocity": "Speed", "vel": "Speed", "sebesseg": "Speed", "kmh": "Speed", "kph": "Speed", "mph": "Speed",
            # RPM
            "rpm": "RPM", "engine_rpm": "RPM", "motor_rpm": "RPM", "fordulat": "RPM",
            # Voltage
            "voltage": "Voltage", "volt": "Voltage", "batt_volt": "Voltage", "v_bat": "Voltage", "v": "Voltage",
            # Current
            "current": "Current", "curr": "Current", "amp": "Current", "batt_curr": "Current", "i_bat": "Current", "a": "Current", "i": "Current",
            # Throttle
            "throttle": "Throttle", "tps": "Throttle", "pedal": "Throttle", "accel_pedal": "Throttle", "gaz": "Throttle",
            # Temperature
            "temperature": "Temperature", "temp": "Temperature", "homerseklet": "Temperature", "degc": "Temperature",
            # SteeringAngle
            "steering": "SteeringAngle", "steer": "SteeringAngle", "kormanyszog": "SteeringAngle",
            # Power & Energy
            "power": "Power", "watt": "Power", "kw": "Power",
            "energy": "Energy", "wh": "Energy", "kwh": "Energy", "joule": "Energy",
            # GPS
            "latitude": "GPS_Lat", "gps_lat": "GPS_Lat", "lat": "GPS_Lat",
            "longitude": "GPS_Lon", "gps_lon": "GPS_Lon", "lon": "GPS_Lon", "long": "GPS_Lon",
        }

        for raw_col, expected_target in expected_matches.items():
            guessed = wizard._auto_guess_mapping(raw_col, set())
            self.assertEqual(guessed, expected_target, f"Failed matching for '{raw_col}'")

        # Non-matching channels MUST NOT be mapped to Current, Voltage, or any other channel
        non_matching = ["Brake", "Brake_Pressure", "Status", "Gear", "Drive_Mode", "Notes", "Flag"]
        for raw_col in non_matching:
            guessed = wizard._auto_guess_mapping(raw_col, set())
            self.assertIsNone(guessed, f"Non-matching channel '{raw_col}' was unexpectedly mapped to '{guessed}'")

    def test_auto_guess_dynamic_custom_labels(self):
        """Validates that auto-guess resolves candidate labels dynamically from custom state_manager channels."""
        state_mgr = StateManager(config_dir=self.temp_dir.name)
        custom_defs = [
            {"label": "Kör", "slug": "lap"},
            {"label": "Idő", "slug": "time"},
            {"label": "Távolság", "slug": "distance"},
            {"label": "Sebesség", "slug": "speed"},
            {"label": "Áram", "slug": "current"},
            {"label": "Feszültség", "slug": "voltage"},
        ]
        state_mgr.save_channel_defs(custom_defs)

        wizard = ImportWizardDialog(
            file_path="test.csv",
            raw_columns=["lap_no", "time"],
            preview_df=pd.DataFrame(),
            state_manager=state_mgr
        )

        self.assertEqual(wizard._auto_guess_mapping("lap_no", set()), "Kör")
        self.assertEqual(wizard._auto_guess_mapping("timestamp", set()), "Idő")
        self.assertEqual(wizard._auto_guess_mapping("dist", set()), "Távolság")
        self.assertEqual(wizard._auto_guess_mapping("velocity", set()), "Sebesség")
        self.assertEqual(wizard._auto_guess_mapping("i_bat", set()), "Áram")
        self.assertEqual(wizard._auto_guess_mapping("v_bat", set()), "Feszültség")

    def test_preset_manager_saves_new_custom_channels(self):
        """Validates that PresetManagerDialog persists new custom channel names and has no dead state."""
        state_mgr = StateManager(config_dir=self.temp_dir.name)
        dlg = PresetManagerDialog(state_mgr)

        # Confirm dead state self.combos is removed
        self.assertFalse(hasattr(dlg, "combos"))

        # Save preset with new custom channel names
        mapping = {
            "Raw_Brake": "brake_pressure_bar",
            "Raw_Coolant": "coolant_temp_c"
        }
        dlg.preset_name_input.setText("Custom_Sensors_Preset")
        dlg.table.setRowCount(2)
        # row 0
        dlg.table.setItem(0, 0, QTableWidgetItem("Raw_Brake"))
        combo1 = QComboBox()
        combo1.addItems(["Brake Pressure [bar]"])
        combo1.setCurrentIndex(0)
        dlg.table.setCellWidget(0, 1, combo1)
        # row 1
        dlg.table.setItem(1, 0, QTableWidgetItem("Raw_Coolant"))
        combo2 = QComboBox()
        combo2.addItems(["Coolant Temp [C]"])
        combo2.setCurrentIndex(0)
        dlg.table.setCellWidget(1, 1, combo2)

        dlg._save_new_custom_channels_from_table()
        state_mgr.save_preset("Custom_Sensors_Preset", mapping)

        labels = state_mgr.get_channel_labels()
        self.assertIn("Brake Pressure [bar]", labels)
        self.assertIn("Coolant Temp [C]", labels)

        defs = state_mgr.get_channel_defs()
        slugs = [d["slug"] for d in defs]
        self.assertIn("brake_pressure_bar", slugs)
        self.assertIn("coolant_temp_c", slugs)

    def test_channel_manager_rename_custom_and_system_channels(self):
        """Validates that renaming non-system channels regenerates slugs, while system slugs are preserved."""
        state_mgr = StateManager(config_dir=self.temp_dir.name)
        custom_defs = [
            {"label": "Lap", "slug": "lap"},
            {"label": "Time", "slug": "time"},
            {"label": "Distance", "slug": "distance"},
            {"label": "Old Sensor", "slug": "old_sensor"}
        ]
        state_mgr.save_channel_defs(custom_defs)

        dlg = ChannelManagerDialog(state_mgr)

        # 1. Rename custom non-system channel
        dlg.table.selectRow(3)
        with patch("PySide6.QtWidgets.QInputDialog.getText", return_value=("Suspension Travel [mm]", True)):
            dlg._on_rename_channel()

        self.assertEqual(dlg.channels[3]["label"], "Suspension Travel [mm]")
        self.assertEqual(dlg.channels[3]["slug"], "suspension_travel_mm")

        # 2. Rename system required channel
        dlg.table.selectRow(0)
        with patch("PySide6.QtWidgets.QInputDialog.getText", return_value=("Kör", True)):
            dlg._on_rename_channel()

        self.assertEqual(dlg.channels[0]["label"], "Kör")
        self.assertEqual(dlg.channels[0]["slug"], "lap")  # System slug must be preserved

    def test_sidebar_lap_multi_selection_limit_clamping(self):
        """Validates that selecting >12 laps at once clamps selection to 12 and updates state cleanly."""
        sidebar = SidebarWidget()
        # Create session with 15 laps
        session_15 = Session(id="s_15", name="sess_15.csv", file_path="/tmp/15.csv", channels=["speed"])
        for i in range(1, 16):
            lap = Lap("s_15", i, 1.0, 10.0, {"time": np.array([0.0, 1.0]), "speed": np.array([10.0, 20.0])})
            session_15.laps.append(lap)

        sidebar.add_session(session_15)

        # Select all 15 laps in the tree
        session_item = sidebar.session_tree.topLevelItem(0)
        sidebar.session_tree.blockSignals(True)
        for i in range(session_item.childCount()):
            session_item.child(i).setSelected(True)
        sidebar.session_tree.blockSignals(False)

        with patch("PySide6.QtWidgets.QMessageBox.warning") as mock_warn:
            sidebar._on_lap_selection_changed()
            mock_warn.assert_called_once()

        # Selection and allocated colors must be clamped to 12
        selected_laps = [
            item.data(0, Qt.UserRole)
            for item in sidebar.session_tree.selectedItems()
            if item.data(0, Qt.UserRole) and item.data(0, Qt.UserRole)[0] == "lap"
        ]
        self.assertEqual(len(selected_laps), 12)
        self.assertEqual(len(sidebar.allocated_colors), 12)

        # Subsequent click/deselect must NOT raise another limit warning
        with patch("PySide6.QtWidgets.QMessageBox.warning") as mock_warn2:
            session_item.child(0).setSelected(False)
            sidebar._on_lap_selection_changed()
            mock_warn2.assert_not_called()

        self.assertEqual(len(sidebar.allocated_colors), 11)

    def test_sidebar_channel_multi_selection_limit_clamping(self):
        """Validates that selecting >6 channels at once clamps selection to 6 items."""
        sidebar = SidebarWidget()
        session_ch = Session(
            id="s_ch", name="sess_ch.csv", file_path="/tmp/ch.csv",
            channels=[f"Channel_{i}" for i in range(1, 11)]
        )
        sidebar.add_session(session_ch)

        # Select all 10 channels
        sidebar.channel_tree.blockSignals(True)
        for i in range(sidebar.channel_tree.topLevelItemCount()):
            sidebar.channel_tree.topLevelItem(i).setSelected(True)
        sidebar.channel_tree.blockSignals(False)

        with patch("PySide6.QtWidgets.QMessageBox.warning") as mock_warn:
            sidebar._on_channel_selection_changed()
            mock_warn.assert_called_once()

        self.assertEqual(len(sidebar.channel_tree.selectedItems()), 6)
        self.assertEqual(len(sidebar.selected_channels), 6)

    def test_sidebar_channel_preservation_on_session_add_remove(self):
        """Validates that valid channel selections are preserved and synced when sessions are added/removed."""
        sidebar = SidebarWidget()
        session1 = Session(
            id="s1", name="s1.csv", file_path="/tmp/s1.csv",
            channels=["speed", "rpm", "throttle"]
        )
        session2 = Session(
            id="s2", name="s2.csv", file_path="/tmp/s2.csv",
            channels=["speed", "rpm", "battery_temp"]
        )

        emitted_channels = []
        sidebar.channels_selection_changed.connect(emitted_channels.append)

        # Add session 1 and select Speed and RPM
        sidebar.add_session(session1)
        sidebar.selected_channels = {"speed", "rpm"}
        for i in range(sidebar.channel_tree.topLevelItemCount()):
            item = sidebar.channel_tree.topLevelItem(i)
            if item.text(0) in {"speed", "rpm"}:
                item.setSelected(True)

        # Add session 2: Speed and RPM must remain selected and tree must be checked
        sidebar.add_session(session2)
        self.assertEqual(sidebar.selected_channels, {"speed", "rpm"})
        selected_in_tree = {
            sidebar.channel_tree.topLevelItem(i).text(0)
            for i in range(sidebar.channel_tree.topLevelItemCount())
            if sidebar.channel_tree.topLevelItem(i).isSelected()
        }
        self.assertEqual(selected_in_tree, {"speed", "rpm"})
        self.assertEqual(emitted_channels[-1], {"speed", "rpm"})

        # Remove session 1: Speed and RPM exist in session2, so they should remain
        sidebar.remove_session("s1")
        self.assertEqual(sidebar.selected_channels, {"speed", "rpm"})
        self.assertEqual(emitted_channels[-1], {"speed", "rpm"})

        # Remove session 2: All channels gone
        sidebar.remove_session("s2")
        self.assertEqual(sidebar.selected_channels, set())
        self.assertEqual(emitted_channels[-1], set())

    def test_sidebar_laps_selection_deterministic_sorting(self):
        """Validates that laps_selection_changed emits deterministically sorted tuples by (session_id, lap_num)."""
        sidebar = SidebarWidget()
        sess = Session(id="s_sort", name="sort.csv", file_path="/tmp/sort.csv", channels=["speed"])
        for i in range(1, 6):
            sess.laps.append(Lap("s_sort", i, 1.0, 10.0, {"time": np.array([0.0, 1.0]), "speed": np.array([10.0, 20.0])}))
        sidebar.add_session(sess)

        emitted_laps = []
        sidebar.laps_selection_changed.connect(emitted_laps.append)

        # Select Lap 4, Lap 2, Lap 5 in arbitrary order
        session_item = sidebar.session_tree.topLevelItem(0)
        session_item.child(3).setSelected(True)  # Lap 4
        session_item.child(1).setSelected(True)  # Lap 2
        session_item.child(4).setSelected(True)  # Lap 5

        sidebar._on_lap_selection_changed()

        last_result = emitted_laps[-1]
        lap_nums = [item[1] for item in last_result]
        self.assertEqual(lap_nums, [2, 4, 5], "Laps must be sorted deterministically in emission")

    def test_single_plot_n1_viewbox_height_and_no_overflow(self):
        """Validates ViewBox height calculation for N=1 single-channel plot."""
        widget = GraphViewWidget()
        widget.resize(800, 600)
        sessions = {self.session.id: self.session}
        widget.set_sessions(sessions)
        widget.set_selected_laps([(self.session.id, 1, "#00E676")])
        widget.set_selected_channels({"speed"})

        widget.show()
        app.processEvents()

        self.assertEqual(len(widget.plot_widgets), 1)
        plot = widget.plot_widgets["speed"]
        vb_h = plot.vb.geometry().height()
        self.assertGreater(vb_h, 300)
        # Verify bottom axis is active on N=1
        self.assertTrue(plot.getAxis("bottom").isVisible())

    def test_crosshair_nearest_sample_with_nans_duplicates_and_non_monotonic(self):
        """Validates that _get_nearest_channel_sample snaps to nearest recorded sample without interpolation."""
        # 1. Array with NaNs
        raw_x = np.array([0.0, np.nan, 2.0, 4.0])
        raw_y = np.array([10.0, 20.0, np.nan, 50.0])
        # valid points: (0.0, 10.0) and (4.0, 50.0). At x_val=1.5, closest point is (0.0, 10.0)
        sample = _get_nearest_channel_sample(raw_x, raw_y, 1.5)
        self.assertIsNotNone(sample)
        self.assertEqual(sample, (0.0, 10.0))

        # At x_val=3.0, closest point is (4.0, 50.0)
        sample2 = _get_nearest_channel_sample(raw_x, raw_y, 3.0)
        self.assertIsNotNone(sample2)
        self.assertEqual(sample2, (4.0, 50.0))

        # 2. Array with duplicate X values (e.g. car stationary at start)
        raw_x_dup = np.array([0.0, 0.0, 1.0, 2.0])
        raw_y_dup = np.array([0.0, 5.0, 10.0, 20.0])
        sample_dup = _get_nearest_channel_sample(raw_x_dup, raw_y_dup, 0.9)
        self.assertIsNotNone(sample_dup)
        self.assertEqual(sample_dup, (1.0, 10.0))

        # 3. Out of bounds values
        self.assertIsNone(_get_nearest_channel_sample(raw_x_dup, raw_y_dup, -5.0))
        self.assertIsNone(_get_nearest_channel_sample(raw_x_dup, raw_y_dup, 100.0))

        # 4. None or empty arrays
        self.assertIsNone(_get_nearest_channel_sample(None, None, 1.0))
        self.assertIsNone(_get_nearest_channel_sample(np.array([]), np.array([]), 1.0))

    def test_custom_lap_labels_cleanup_on_session_removal(self):
        """Validates that stale custom lap labels are cleaned up when sessions are removed."""
        widget = GraphViewWidget()
        widget.custom_lap_labels = {
            ("s1", 1): "S1 Lap 1 Custom",
            ("s2", 1): "S2 Lap 1 Custom"
        }

        # Keep only s1
        widget.set_sessions({"s1": self.session})
        self.assertIn(("s1", 1), widget.custom_lap_labels)
        self.assertNotIn(("s2", 1), widget.custom_lap_labels)

    def test_x_axis_selection_preservation_during_sync(self):
        """Validates that user X-axis choice (Distance or Time) uses slugs and is preserved when labels are re-synced."""
        widget = GraphViewWidget()
        # Default is Time slug
        self.assertEqual(widget.x_axis_slug, "time")
        self.assertEqual(widget.x_axis_channel, widget.time_label)

        # User chooses Distance
        dist_idx = [i for i in range(widget.x_axis_combo.count()) if widget.x_axis_combo.itemData(i) == "distance"][0]
        widget.x_axis_combo.setCurrentIndex(dist_idx)
        self.assertEqual(widget.x_axis_slug, "distance")
        self.assertEqual(widget.x_axis_channel, widget.dist_label)

        # Sync labels to Hungarian
        widget.set_x_axis_labels("Idő", "Távolság")
        self.assertEqual(widget.x_axis_slug, "distance")
        self.assertEqual(widget.x_axis_channel, "Távolság")
        self.assertEqual(widget.x_axis_combo.currentText(), "Távolság")

        # User switches to Time (Idő)
        time_idx = [i for i in range(widget.x_axis_combo.count()) if widget.x_axis_combo.itemData(i) == "time"][0]
        widget.x_axis_combo.setCurrentIndex(time_idx)
        self.assertEqual(widget.x_axis_slug, "time")
        self.assertEqual(widget.x_axis_channel, "Idő")

        # Sync labels back to English
        widget.set_x_axis_labels("Time", "Distance")
        self.assertEqual(widget.x_axis_slug, "time")
        self.assertEqual(widget.x_axis_channel, "Time")
        self.assertEqual(widget.x_axis_combo.currentText(), "Time")

    def test_auto_range_triggered_on_laps_and_channels_selection_changed(self):
        """Validates that auto-range is automatically invoked when lap or channel selection changes."""
        widget = GraphViewWidget()
        sessions = {self.session.id: self.session}
        widget.set_sessions(sessions)
        widget.selected_channels = ["speed"]

        with patch.object(widget, "_on_autorange") as mock_autorange:
            # 1. Changing selected laps triggers auto-range
            widget.set_selected_laps([(self.session.id, 1, "#00E676")])
            mock_autorange.assert_called()

        with patch.object(widget, "_on_autorange") as mock_autorange2:
            # 2. Changing selected channels triggers auto-range
            widget.set_selected_channels({"speed", "rpm"})
            mock_autorange2.assert_called()

    def test_legend_displays_all_laps_across_multiple_files_with_unequal_channels(self):
        """Validates that legend shows laps from all files even if row 0 channel is missing in some files."""
        widget = GraphViewWidget()

        # Session 1 has Brake and Speed
        s1 = Session(id="s1", name="run1.csv", file_path="/tmp/run1.csv", channels=["brake", "speed"])
        s1.laps.append(Lap("s1", 1, 10.0, 100.0, {"time": np.array([0, 1]), "brake": np.array([50, 100]), "speed": np.array([10, 20])}))

        # Session 2 has ONLY Speed (NO Brake)
        s2 = Session(id="s2", name="run2.csv", file_path="/tmp/run2.csv", channels=["speed"])
        s2.laps.append(Lap("s2", 1, 11.0, 100.0, {"time": np.array([0, 1]), "speed": np.array([12, 22])}))

        widget.set_sessions({"s1": s1, "s2": s2})
        # Brake is row 0 ('brake' < 'speed'), Speed is row 1
        widget.set_selected_channels({"brake", "speed"})
        widget.set_selected_laps([("s1", 1, "#00E676"), ("s2", 1, "#FF5252")])

        self.assertIsNotNone(widget.legend)
        legend_texts = [item[1].text for item in widget.legend.items]
        self.assertEqual(len(legend_texts), 2)
        self.assertIn("run1.csv L1", legend_texts)
        self.assertIn("run2.csv L1", legend_texts)

    def test_sidebar_preserves_selected_laps_when_adding_new_session(self):
        """Validates that adding a new session does not deselect previously selected laps in existing sessions."""
        sidebar = SidebarWidget()
        s1 = Session(id="s1", name="file1.csv", file_path="/tmp/f1.csv", channels=["speed"])
        s1.laps.append(Lap("s1", 1, 10.0, 100.0, {"time": np.array([0, 1]), "speed": np.array([10, 20])}))

        s2 = Session(id="s2", name="file2.csv", file_path="/tmp/f2.csv", channels=["speed"])
        s2.laps.append(Lap("s2", 1, 11.0, 100.0, {"time": np.array([0, 1]), "speed": np.array([12, 22])}))

        # Add session 1 and select Lap 1
        sidebar.add_session(s1)
        item_s1_l1 = sidebar.session_tree.topLevelItem(0).child(0)
        item_s1_l1.setSelected(True)
        sidebar._on_lap_selection_changed()

        self.assertIn(("s1", 1), sidebar.allocated_colors)

        # Add session 2: s1 Lap 1 must remain selected and in allocated_colors
        sidebar.add_session(s2)
        self.assertTrue(item_s1_l1.isSelected())
        self.assertIn(("s1", 1), sidebar.allocated_colors)

    def test_sidebar_tree_header_and_indentation_styling(self):
        """Validates that time column is tight, channel header is hidden, and indentations are compact."""
        sidebar = SidebarWidget()
        # 1. Time column tight fit & no stretch
        self.assertFalse(sidebar.session_tree.header().stretchLastSection())
        self.assertEqual(sidebar.session_tree.header().sectionResizeMode(1), QHeaderView.ResizeToContents)

        # 2. Reduced indentation in both trees
        self.assertEqual(sidebar.session_tree.indentation(), 10)
        self.assertEqual(sidebar.channel_tree.indentation(), 10)

        # 3. Channel tree header hidden
        self.assertTrue(sidebar.channel_tree.isHeaderHidden())

    def test_session_context_menu_edit_mapping_action(self):
        """Validates that right-clicking a session offers 'Edit Channel Mapping...' and emits signal."""
        sidebar = SidebarWidget()
        s1 = Session(id="s1", name="run1.csv", file_path="/tmp/run1.csv", channels=["speed"])
        sidebar.add_session(s1)

        received_session_id = []
        sidebar.session_edit_mapping_requested.connect(lambda sid: received_session_id.append(sid))

        item = sidebar.session_tree.topLevelItem(0)
        menu = sidebar._create_session_context_menu(item)
        self.assertIsNotNone(menu)

        action_texts = [a.text() for a in menu.actions()]
        self.assertIn("Edit Channel Mapping...", action_texts)

        # Trigger Edit Channel Mapping action
        edit_act = [a for a in menu.actions() if a.text() == "Edit Channel Mapping..."][0]
        edit_act.trigger()

        self.assertEqual(received_session_id, ["s1"])

    def test_import_wizard_remapping_mode_and_initial_mapping(self):
        """Validates that ImportWizardDialog pre-populates combos and preset name when is_remapping=True."""
        state_mgr = StateManager(config_dir=self.temp_dir.name)
        raw_cols = ["Raw_Lap", "Raw_Time", "Raw_Spd"]
        preview_df = pd.DataFrame({"Raw_Lap": [1], "Raw_Time": [0.0], "Raw_Spd": [25.0]})
        initial_map = {"Raw_Lap": "lap", "Raw_Time": "time", "Raw_Spd": "speed"}

        wizard = ImportWizardDialog(
            file_path="/tmp/test_log.csv",
            raw_columns=raw_cols,
            preview_df=preview_df,
            state_manager=state_mgr,
            initial_preset="MyCarPreset",
            initial_mapping=initial_map,
            is_remapping=True
        )

        self.assertIn("Edit Channel Mapping", wizard.windowTitle())
        self.assertEqual(wizard.import_btn.text(), "Apply Changes")
        self.assertEqual(wizard.combos["Raw_Lap"].currentText(), "Lap")
        self.assertEqual(wizard.combos["Raw_Time"].currentText(), "Time")
        self.assertEqual(wizard.combos["Raw_Spd"].currentText(), "Speed")
        self.assertEqual(wizard.preset_input.text(), "MyCarPreset")

        # Saving preset should update the preset in state_manager
        with patch.object(QMessageBox, "information"):
            wizard._on_save_preset()
        saved_presets = state_mgr.load_presets()
        self.assertIn("MyCarPreset", saved_presets)
        self.assertEqual(saved_presets["MyCarPreset"]["Raw_Spd"], "speed")
        self.assertEqual(wizard.result_preset_name, "MyCarPreset")

    def test_sidebar_update_session_preserves_selection_and_colors(self):
        """Validates that update_session replaces session laps while retaining lap selections and allocated colors."""
        sidebar = SidebarWidget()
        s1 = Session(id="s1", name="run1.csv", file_path="/tmp/run1.csv", channels=["speed"])
        s1.laps.append(Lap("s1", 1, 10.0, 100.0, {"time": np.array([0, 1]), "speed": np.array([10, 20])}))
        s1.laps.append(Lap("s1", 2, 12.0, 100.0, {"time": np.array([0, 1]), "speed": np.array([15, 25])}))

        sidebar.add_session(s1)

        # Select Lap 1
        item_l1 = sidebar.session_tree.topLevelItem(0).child(0)
        item_l1.setSelected(True)
        sidebar._on_lap_selection_changed()

        self.assertIn(("s1", 1), sidebar.allocated_colors)
        saved_color = sidebar.allocated_colors[("s1", 1)]

        # Update session with renamed channel "vehiclespeed"
        s1_updated = Session(
            id="s1", name="run1.csv", file_path="/tmp/run1.csv",
            channels=["vehiclespeed"],
            mapping={"Raw_Lap": "lap", "Raw_Time": "time", "Raw_Spd": "vehiclespeed"}
        )
        s1_updated.laps.append(Lap("s1", 1, 10.0, 100.0, {"time": np.array([0, 1]), "vehiclespeed": np.array([10, 20])}))
        s1_updated.laps.append(Lap("s1", 2, 12.0, 100.0, {"time": np.array([0, 1]), "vehiclespeed": np.array([15, 25])}))

        sidebar.update_session(s1_updated)

        # Lap 1 must remain selected with same color
        updated_item_l1 = sidebar.session_tree.topLevelItem(0).child(0)
        self.assertTrue(updated_item_l1.isSelected())
        self.assertEqual(sidebar.allocated_colors[("s1", 1)], saved_color)
        self.assertIn("vehiclespeed", sidebar.sessions["s1"].channels)

    def test_sequential_multi_file_import_and_graph_stability(self):
        """Validates that importing multiple files sequentially with active plots does not crash or leak threads."""
        from ui.main_window import MainWindow
        from ui.import_wizard import ImportWizardDialog

        win = MainWindow()
        win.state_manager.config_dir = self.temp_dir.name

        # Create two CSV files
        csv1 = os.path.join(self.temp_dir.name, "log1.csv")
        csv2 = os.path.join(self.temp_dir.name, "log2.csv")

        df1 = pd.DataFrame({
            "Lap": [1, 1, 2, 2],
            "Time": [0.0, 1.0, 2.0, 3.0],
            "Distance": [0, 10, 20, 30],
            "Speed": [10, 20, 30, 40]
        })
        df1.to_csv(csv1, index=False)
        df1.to_csv(csv2, index=False)

        # Mock wizard to return standard mapping automatically
        def fake_wizard_exec(wizard_self):
            wizard_self.result_mapping = {"Lap": "lap", "Time": "time", "Distance": "distance", "Speed": "speed"}
            wizard_self.result_preset_name = None
            return ImportWizardDialog.Accepted

        with patch.object(ImportWizardDialog, "exec", fake_wizard_exec):
            win._import_file(csv1)
            self.assertEqual(len(win.sessions), 1)

            # Select lap and channel to activate plots
            win.sidebar.selected_channels = {"speed"}
            win.sidebar.update_available_channels()
            win.graph_view.set_selected_laps([(list(win.sessions.keys())[0], 1, "#00E676")])
            win.graph_view.set_selected_channels({"speed"})

            # Simulate mouse movement on active plot
            first_plot = list(win.graph_view.plot_widgets.values())[0]
            scene_pos = first_plot.vb.mapViewToScene(QPointF(1.0, 20.0))
            win.graph_view._on_mouse_moved(scene_pos)

            # Import second file while plot is active
            win._import_file(csv2)
            self.assertEqual(len(win.sessions), 2)

            # Move mouse again
            win.graph_view._on_mouse_moved(scene_pos)

    def test_preset_preview_dialog_preset_switching_and_stats(self):
        """Validates that PresetPreviewDialog displays match stats and allows switching presets."""
        from ui.import_wizard import PresetPreviewDialog

        state_mgr = StateManager(config_dir=self.temp_dir.name)
        state_mgr.save_preset("PresetA", {"Time": "time", "Lap": "lap", "Speed": "speed", "Missing_Col": "rpm"})
        state_mgr.save_preset("PresetB", {"Time": "time", "Lap": "lap"})

        raw_columns = ["Time", "Lap", "Speed", "Unmapped_Col"]

        dlg = PresetPreviewDialog(
            file_path="/tmp/run.csv",
            preset_name="PresetA",
            mapping={"Time": "time", "Lap": "lap", "Speed": "speed", "Missing_Col": "rpm"},
            raw_columns=raw_columns,
            state_manager=state_mgr
        )

        # Initial PresetA stats: 3 mapped, 1 missing in file, 1 unmapped in file
        self.assertIn("3 Mapped in File", dlg.stats_label.text())
        self.assertIn("1 in Preset but Missing in File", dlg.stats_label.text())
        self.assertIn("1 Skipped", dlg.stats_label.text())

        filtered_map = dlg.get_filtered_mapping()
        self.assertEqual(len(filtered_map), 3)
        self.assertNotIn("Missing_Col", filtered_map)

        # Switch to PresetB
        dlg.preset_combo.setCurrentText("PresetB")
        self.assertEqual(dlg.selected_preset_name, "PresetB")
        self.assertIn("2 Mapped in File", dlg.stats_label.text())
        self.assertIn("0 in Preset but Missing in File", dlg.stats_label.text())
        self.assertIn("2 Skipped", dlg.stats_label.text())

    def test_import_wizard_manual_preset_loading(self):
        """Validates that ImportWizardDialog allows selecting and applying a preset manually."""
        state_mgr = StateManager(config_dir=self.temp_dir.name)
        state_mgr.save_preset("CustomTelemetry", {
            "Raw_Lap": "lap",
            "Raw_Time": "time",
            "Raw_Spd": "speed"
        })

        raw_cols = ["Raw_Lap", "Raw_Time", "Raw_Spd", "Raw_Extra"]
        preview_df = pd.DataFrame({c: [0.0] for c in raw_cols})

        wizard = ImportWizardDialog(
            file_path="/tmp/test_unmapped.csv",
            raw_columns=raw_cols,
            preview_df=preview_df,
            state_manager=state_mgr
        )

        # Manually select and apply CustomTelemetry preset
        wizard.load_preset_combo.setCurrentText("CustomTelemetry")
        wizard._on_apply_preset_button_clicked()

        self.assertEqual(wizard.combos["Raw_Lap"].currentText(), "Lap")
        self.assertEqual(wizard.combos["Raw_Time"].currentText(), "Time")
        self.assertEqual(wizard.combos["Raw_Spd"].currentText(), "Speed")
        self.assertEqual(wizard.combos["Raw_Extra"].currentText(), "-- Skip --")
        self.assertEqual(wizard.preset_input.text(), "CustomTelemetry")
        self.assertFalse(wizard.preset_status_label.isHidden())
        self.assertIn("3 channels mapped", wizard.preset_status_label.text())

    def test_x_zoom_viewbox_drag_selection_and_zoom(self):
        """Validates that left-click dragging horizontally across a graph shows the selection box on all plots and zooms on release."""
        widget = GraphViewWidget()
        sessions = {self.session.id: self.session}
        widget.set_sessions(sessions)
        widget.set_selected_laps([(self.session.id, 1, "#00E676")])
        widget.set_selected_channels({"speed", "rpm"})
        widget.resize(800, 600)
        widget.show()
        app.processEvents()

        self.assertEqual(len(widget.plot_widgets), 2)
        p1 = widget.plot_widgets["speed"]
        p2 = widget.plot_widgets["rpm"]
        self.assertIsInstance(p1.vb, XZoomViewBox)
        self.assertIsInstance(p2.vb, XZoomViewBox)

        # Initial X range should span the full data (0.0 to 2.0)
        initial_x = p1.vb.viewRange()[0]

        class FakeDragEvent:
            def __init__(self, p1, p2, finish=False, button=Qt.MouseButton.LeftButton):
                self._p1 = p1
                self._p2 = p2
                self.finish = finish
                self._button = button
                self.accepted = False
            def button(self): return self._button
            def buttonDownPos(self): return self._p1
            def pos(self): return self._p2
            def isFinish(self): return self.finish
            def accept(self): self.accepted = True

        # Map data coordinates X=0.5 and X=1.5 to ViewBox pixels
        pt_start = p1.vb.mapFromView(QPointF(0.5, 15.0))
        pt_curr = p1.vb.mapFromView(QPointF(1.5, 25.0))

        # 1. Drag move event: selection box should become visible on ALL stacked plots
        ev_drag = FakeDragEvent(pt_start, pt_curr, finish=False)
        p1.vb.mouseDragEvent(ev_drag)
        self.assertTrue(ev_drag.accepted)
        self.assertTrue(p1.vb.rbScaleBox.isVisible())
        self.assertTrue(p2.vb.rbScaleBox.isVisible())

        # 2. Release / Finish drag event: selection boxes hide and view zooms to [0.5, 1.5]
        ev_finish = FakeDragEvent(pt_start, pt_curr, finish=True)
        p1.vb.mouseDragEvent(ev_finish)
        app.processEvents()

        self.assertFalse(p1.vb.rbScaleBox.isVisible())
        self.assertFalse(p2.vb.rbScaleBox.isVisible())

        # Check zoomed X range on all stacked plots
        x_range_1 = p1.vb.viewRange()[0]
        x_range_2 = p2.vb.viewRange()[0]
        self.assertAlmostEqual(x_range_1[0], 0.5, places=2)
        self.assertAlmostEqual(x_range_1[1], 1.5, places=2)
        self.assertAlmostEqual(x_range_2[0], 0.5, places=2)
        self.assertAlmostEqual(x_range_2[1], 1.5, places=2)

    def test_x_zoom_viewbox_drag_reverse_direction(self):
        """Validates that dragging from right to left properly zooms to the selected X interval."""
        widget = GraphViewWidget()
        sessions = {self.session.id: self.session}
        widget.set_sessions(sessions)
        widget.set_selected_laps([(self.session.id, 1, "#00E676")])
        widget.set_selected_channels({"speed"})
        widget.resize(800, 600)
        widget.show()
        app.processEvents()

        p1 = widget.plot_widgets["speed"]

        class FakeDragEvent:
            def __init__(self, p1, p2, finish=False):
                self._p1 = p1
                self._p2 = p2
                self.finish = finish
                self.accepted = False
            def button(self): return Qt.MouseButton.LeftButton
            def buttonDownPos(self): return self._p1
            def pos(self): return self._p2
            def isFinish(self): return self.finish
            def accept(self): self.accepted = True

        pt_start = p1.vb.mapFromView(QPointF(1.8, 20.0))
        pt_end = p1.vb.mapFromView(QPointF(0.4, 20.0))

        ev_finish = FakeDragEvent(pt_start, pt_end, finish=True)
        p1.vb.mouseDragEvent(ev_finish)
        app.processEvents()

        x_range = p1.vb.viewRange()[0]
        self.assertAlmostEqual(x_range[0], 0.4, places=2)
        self.assertAlmostEqual(x_range[1], 1.8, places=2)

    def test_x_zoom_viewbox_drag_on_secondary_plot(self):
        """Validates that dragging on the second stacked plot updates and zooms all stacked plots."""
        widget = GraphViewWidget()
        sessions = {self.session.id: self.session}
        widget.set_sessions(sessions)
        widget.set_selected_laps([(self.session.id, 1, "#00E676")])
        widget.set_selected_channels({"speed", "rpm"})
        widget.resize(800, 600)
        widget.show()
        app.processEvents()

        p1 = widget.plot_widgets["speed"]
        p2 = widget.plot_widgets["rpm"]

        class FakeDragEvent:
            def __init__(self, p1, p2, finish=False):
                self._p1 = p1
                self._p2 = p2
                self.finish = finish
                self.accepted = False
            def button(self): return Qt.MouseButton.LeftButton
            def buttonDownPos(self): return self._p1
            def pos(self): return self._p2
            def isFinish(self): return self.finish
            def accept(self): self.accepted = True

        pt_start = p2.vb.mapFromView(QPointF(0.2, 1500.0))
        pt_end = p2.vb.mapFromView(QPointF(1.2, 2500.0))

        ev_finish = FakeDragEvent(pt_start, pt_end, finish=True)
        p2.vb.mouseDragEvent(ev_finish)
        app.processEvents()

        x_range_1 = p1.vb.viewRange()[0]
        x_range_2 = p2.vb.viewRange()[0]
        self.assertAlmostEqual(x_range_1[0], 0.2, places=2)
        self.assertAlmostEqual(x_range_1[1], 1.2, places=2)
        self.assertAlmostEqual(x_range_2[0], 0.2, places=2)
        self.assertAlmostEqual(x_range_2[1], 1.2, places=2)

    def test_x_zoom_viewbox_click_without_drag_does_not_zoom(self):
        """Validates that a simple click or tiny movement below the threshold does not zoom the graphs."""
        widget = GraphViewWidget()
        sessions = {self.session.id: self.session}
        widget.set_sessions(sessions)
        widget.set_selected_laps([(self.session.id, 1, "#00E676")])
        widget.set_selected_channels({"speed"})
        widget.resize(800, 600)
        widget.show()
        app.processEvents()

        p1 = widget.plot_widgets["speed"]
        x_range_before = p1.vb.viewRange()[0]

        class FakeDragEvent:
            def __init__(self, p1, p2, finish=False):
                self._p1 = p1
                self._p2 = p2
                self.finish = finish
                self.accepted = False
            def button(self): return Qt.MouseButton.LeftButton
            def buttonDownPos(self): return self._p1
            def pos(self): return self._p2
            def isFinish(self): return self.finish
            def accept(self): self.accepted = True

        # Click with only 2 pixels delta (under 5 px threshold)
        pt_start = QPointF(100.0, 100.0)
        pt_end = QPointF(102.0, 100.0)

        ev_finish = FakeDragEvent(pt_start, pt_end, finish=True)
        p1.vb.mouseDragEvent(ev_finish)
        app.processEvents()

        x_range_after = p1.vb.viewRange()[0]
        self.assertEqual(x_range_before, x_range_after)

    def test_x_zoom_viewbox_autorange_restores_view(self):
        """Validates that clicking the Auto Range toolbar button resets the zoomed view."""
        widget = GraphViewWidget()
        sessions = {self.session.id: self.session}
        widget.set_sessions(sessions)
        widget.set_selected_laps([(self.session.id, 1, "#00E676")])
        widget.set_selected_channels({"speed"})
        widget.resize(800, 600)
        widget.show()
        app.processEvents()

        p1 = widget.plot_widgets["speed"]
        widget.zoom_x_range(0.5, 1.0)
        app.processEvents()

        self.assertAlmostEqual(p1.vb.viewRange()[0][0], 0.5, places=2)
        self.assertAlmostEqual(p1.vb.viewRange()[0][1], 1.0, places=2)

        # Click auto range button
        widget.btn_autorange.click()
        app.processEvents()

        # View should be restored to include 0.0 to 2.0
        x_range = p1.vb.viewRange()[0]
        self.assertLessEqual(x_range[0], 0.05)
        self.assertGreaterEqual(x_range[1], 1.95)

    def test_x_zoom_viewbox_theme_update(self):
        """Validates that XZoomViewBox theme pen and brush change correctly on theme toggle."""
        vb = XZoomViewBox()
        vb.update_theme(is_dark=True)
        self.assertEqual(vb.rbScaleBox.pen().color().name().lower(), "#00e676")

        vb.update_theme(is_dark=False)
        self.assertEqual(vb.rbScaleBox.pen().color().name().lower(), "#00c853")

    def test_x_zoom_escape_cancels_drag_selection(self):
        """Validates that pressing Escape while dragging cancels selection and prevents zooming."""
        widget = GraphViewWidget()
        sessions = {self.session.id: self.session}
        widget.set_sessions(sessions)
        widget.set_selected_laps([(self.session.id, 1, "#00E676")])
        widget.set_selected_channels({"speed", "rpm"})
        widget.resize(800, 600)
        widget.show()
        app.processEvents()

        p1 = widget.plot_widgets["speed"]
        p2 = widget.plot_widgets["rpm"]
        initial_x_range = p1.vb.viewRange()[0]

        class FakeDragEvent:
            def __init__(self, p1, p2, finish=False):
                self._p1 = p1
                self._p2 = p2
                self.finish = finish
                self.accepted = False
            def button(self): return Qt.MouseButton.LeftButton
            def buttonDownPos(self): return self._p1
            def pos(self): return self._p2
            def isFinish(self): return self.finish
            def accept(self): self.accepted = True

        pt_start = p1.vb.mapFromView(QPointF(0.3, 15.0))
        pt_curr = p1.vb.mapFromView(QPointF(1.7, 25.0))

        # 1. Start drag
        ev_drag = FakeDragEvent(pt_start, pt_curr, finish=False)
        p1.vb.mouseDragEvent(ev_drag)
        self.assertTrue(p1.vb.rbScaleBox.isVisible())
        self.assertTrue(p2.vb.rbScaleBox.isVisible())

        # 2. Cancel drag via cancel_drag_selection (simulating Escape key press)
        canceled = widget.cancel_drag_selection()
        self.assertTrue(canceled)
        self.assertFalse(p1.vb.rbScaleBox.isVisible())
        self.assertFalse(p2.vb.rbScaleBox.isVisible())

        # 3. Further mouse move should NOT make the box visible again
        pt_further = p1.vb.mapFromView(QPointF(1.9, 25.0))
        ev_move = FakeDragEvent(pt_start, pt_further, finish=False)
        p1.vb.mouseDragEvent(ev_move)
        self.assertFalse(p1.vb.rbScaleBox.isVisible())
        self.assertFalse(p2.vb.rbScaleBox.isVisible())

        # 4. Finish/release mouse: must NOT zoom
        ev_finish = FakeDragEvent(pt_start, pt_further, finish=True)
        p1.vb.mouseDragEvent(ev_finish)
        app.processEvents()

        self.assertEqual(p1.vb.viewRange()[0], initial_x_range)
        self.assertEqual(p2.vb.viewRange()[0], initial_x_range)

        # 5. Subsequent drag works normally and zooms
        ev_new_drag = FakeDragEvent(pt_start, pt_curr, finish=False)
        p1.vb.mouseDragEvent(ev_new_drag)
        self.assertTrue(p1.vb.rbScaleBox.isVisible())

        ev_new_finish = FakeDragEvent(pt_start, pt_curr, finish=True)
        p1.vb.mouseDragEvent(ev_new_finish)
        app.processEvents()

        self.assertAlmostEqual(p1.vb.viewRange()[0][0], 0.3, places=2)
        self.assertAlmostEqual(p1.vb.viewRange()[0][1], 1.7, places=2)

    def test_x_zoom_escape_key_event_delivery(self):
        """Validates that a QKeyEvent with Qt.Key_Escape delivered to GraphViewWidget cancels active drag."""
        widget = GraphViewWidget()
        sessions = {self.session.id: self.session}
        widget.set_sessions(sessions)
        widget.set_selected_laps([(self.session.id, 1, "#00E676")])
        widget.set_selected_channels({"speed"})
        widget.resize(800, 600)
        widget.show()
        app.processEvents()

        p1 = widget.plot_widgets["speed"]
        initial_x = p1.vb.viewRange()[0]

        class FakeDragEvent:
            def __init__(self, p1, p2, finish=False):
                self._p1 = p1
                self._p2 = p2
                self.finish = finish
                self.accepted = False
            def button(self): return Qt.MouseButton.LeftButton
            def buttonDownPos(self): return self._p1
            def pos(self): return self._p2
            def isFinish(self): return self.finish
            def accept(self): self.accepted = True

        pt_start = p1.vb.mapFromView(QPointF(0.4, 20.0))
        pt_curr = p1.vb.mapFromView(QPointF(1.6, 20.0))

        # Start drag
        p1.vb.mouseDragEvent(FakeDragEvent(pt_start, pt_curr, finish=False))
        self.assertTrue(p1.vb.rbScaleBox.isVisible())

        # Send Escape key event to widget
        key_ev = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
        app.sendEvent(widget, key_ev)
        app.processEvents()

        self.assertFalse(p1.vb.rbScaleBox.isVisible())

        # Release mouse: no zoom
        p1.vb.mouseDragEvent(FakeDragEvent(pt_start, pt_curr, finish=True))
        app.processEvents()
        self.assertEqual(p1.vb.viewRange()[0], initial_x)

    def test_y_zoom_viewbox_drag_selection_and_zoom_single_plot(self):
        """Validates that vertical dragging (dy > dx) zooms Y only on the active plot, leaving other plots and X intact."""
        widget = GraphViewWidget()
        sessions = {self.session.id: self.session}
        widget.set_sessions(sessions)
        widget.set_selected_laps([(self.session.id, 1, "#00E676")])
        widget.set_selected_channels({"speed", "rpm"})
        widget.resize(800, 600)
        widget.show()
        app.processEvents()

        p1 = widget.plot_widgets["speed"]
        p2 = widget.plot_widgets["rpm"]

        p1_x_initial = p1.vb.viewRange()[0]
        p2_y_initial = p2.vb.viewRange()[1]

        class FakeDragEvent:
            def __init__(self, p1, p2, finish=False):
                self._p1 = p1
                self._p2 = p2
                self.finish = finish
                self.accepted = False
            def button(self): return Qt.MouseButton.LeftButton
            def buttonDownPos(self): return self._p1
            def pos(self): return self._p2
            def isFinish(self): return self.finish
            def accept(self): self.accepted = True

        # Pure vertical drag on p1 (speed) from Y=12.0 to Y=28.0
        pt_start = p1.vb.mapFromView(QPointF(1.0, 12.0))
        pt_curr = p1.vb.mapFromView(QPointF(1.0, 28.0))

        # 1. During drag: only p1's scaleBox is visible; p2's is NOT visible
        p1.vb.mouseDragEvent(FakeDragEvent(pt_start, pt_curr, finish=False))
        app.processEvents()
        self.assertTrue(p1.vb.rbScaleBox.isVisible())
        self.assertFalse(p2.vb.rbScaleBox.isVisible())

        # 2. Release drag: p1 zoomed in Y, p2 Y unchanged, X on both unchanged
        p1.vb.mouseDragEvent(FakeDragEvent(pt_start, pt_curr, finish=True))
        app.processEvents()
        self.assertFalse(p1.vb.rbScaleBox.isVisible())
        self.assertFalse(p2.vb.rbScaleBox.isVisible())

        p1_y = p1.vb.viewRange()[1]
        self.assertAlmostEqual(p1_y[0], 12.0, places=2)
        self.assertAlmostEqual(p1_y[1], 28.0, places=2)

        # Other plot's Y range must remain completely untouched
        self.assertEqual(p2.vb.viewRange()[1], p2_y_initial)

        # X range on all plots must remain completely untouched
        self.assertEqual(p1.vb.viewRange()[0], p1_x_initial)
        self.assertEqual(p2.vb.viewRange()[0], p1_x_initial)

    def test_y_zoom_reverse_direction(self):
        """Validates that dragging vertically in reverse direction (bottom-to-top) zooms correctly."""
        widget = GraphViewWidget()
        sessions = {self.session.id: self.session}
        widget.set_sessions(sessions)
        widget.set_selected_laps([(self.session.id, 1, "#00E676")])
        widget.set_selected_channels({"rpm"})
        widget.resize(800, 600)
        widget.show()
        app.processEvents()

        p1 = widget.plot_widgets["rpm"]

        class FakeDragEvent:
            def __init__(self, p1, p2, finish=False):
                self._p1 = p1
                self._p2 = p2
                self.finish = finish
                self.accepted = False
            def button(self): return Qt.MouseButton.LeftButton
            def buttonDownPos(self): return self._p1
            def pos(self): return self._p2
            def isFinish(self): return self.finish
            def accept(self): self.accepted = True

        pt_start = p1.vb.mapFromView(QPointF(1.0, 2800.0))
        pt_end = p1.vb.mapFromView(QPointF(1.0, 1200.0))

        p1.vb.mouseDragEvent(FakeDragEvent(pt_start, pt_end, finish=True))
        app.processEvents()

        y_range = p1.vb.viewRange()[1]
        self.assertAlmostEqual(y_range[0], 1200.0, places=1)
        self.assertAlmostEqual(y_range[1], 2800.0, places=1)

    def test_y_zoom_escape_cancels_drag(self):
        """Validates that pressing Escape cancels vertical Y-axis drag selection."""
        widget = GraphViewWidget()
        sessions = {self.session.id: self.session}
        widget.set_sessions(sessions)
        widget.set_selected_laps([(self.session.id, 1, "#00E676")])
        widget.set_selected_channels({"speed"})
        widget.resize(800, 600)
        widget.show()
        app.processEvents()

        p1 = widget.plot_widgets["speed"]
        initial_y = p1.vb.viewRange()[1]

        class FakeDragEvent:
            def __init__(self, p1, p2, finish=False):
                self._p1 = p1
                self._p2 = p2
                self.finish = finish
                self.accepted = False
            def button(self): return Qt.MouseButton.LeftButton
            def buttonDownPos(self): return self._p1
            def pos(self): return self._p2
            def isFinish(self): return self.finish
            def accept(self): self.accepted = True

        pt_start = p1.vb.mapFromView(QPointF(1.0, 12.0))
        pt_curr = p1.vb.mapFromView(QPointF(1.0, 28.0))

        p1.vb.mouseDragEvent(FakeDragEvent(pt_start, pt_curr, finish=False))
        self.assertTrue(p1.vb.rbScaleBox.isVisible())

        # Press Escape
        widget.cancel_drag_selection()
        self.assertFalse(p1.vb.rbScaleBox.isVisible())

        # Release mouse: no Y zoom
        p1.vb.mouseDragEvent(FakeDragEvent(pt_start, pt_curr, finish=True))
        app.processEvents()
        self.assertEqual(p1.vb.viewRange()[1], initial_y)

    def test_zoom_preserved_across_data_modifications_until_autorange_button(self):
        """Validates that manual zoom is preserved across lap/channel data modifications until Auto Range button is clicked."""
        # Create multi-lap session
        data1 = {
            "time": np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0]),
            "distance": np.array([0.0, 10.0, 20.0, 30.0, 40.0, 50.0]),
            "speed": np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0]),
            "rpm": np.array([1000.0, 2000.0, 3000.0, 4000.0, 5000.0, 6000.0]),
        }
        lap1 = Lap("s_multi", 1, 5.0, 50.0, data1)
        data2 = {
            "time": np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0]),
            "distance": np.array([0.0, 10.0, 20.0, 30.0, 40.0, 50.0]),
            "speed": np.array([15.0, 25.0, 35.0, 45.0, 55.0, 65.0]),
            "rpm": np.array([1200.0, 2200.0, 3200.0, 4200.0, 5200.0, 6200.0]),
        }
        lap2 = Lap("s_multi", 2, 5.0, 50.0, data2)
        sess = Session(id="s_multi", name="multi.csv", file_path="/tmp/multi.csv", channels=["speed", "rpm"])
        sess.laps.extend([lap1, lap2])

        widget = GraphViewWidget()
        widget.set_sessions({"s_multi": sess})
        widget.set_selected_laps([("s_multi", 1, "#00E676")])
        widget.set_selected_channels({"speed", "rpm"})
        widget.resize(800, 600)
        widget.show()
        app.processEvents()

        # Initially, has_manual_zoom_or_pan should be False
        self.assertFalse(widget.has_manual_zoom_or_pan)

        # 1. Modifying laps before any manual zoom triggers auto-range as normal
        with patch.object(widget, "_on_autorange", wraps=widget._on_autorange) as mock_autorange:
            widget.set_selected_laps([("s_multi", 1, "#00E676"), ("s_multi", 2, "#FF5252")])
            mock_autorange.assert_called_once()

        # 2. User manually zooms in on X range [1.0, 3.0]
        widget.zoom_x_range(1.0, 3.0)
        app.processEvents()
        self.assertTrue(widget.has_manual_zoom_or_pan)
        p1 = widget.plot_widgets["speed"]
        self.assertAlmostEqual(p1.vb.viewRange()[0][0], 1.0, places=2)
        self.assertAlmostEqual(p1.vb.viewRange()[0][1], 3.0, places=2)

        # 3. User modifies data being displayed (e.g. removes Lap 2)
        with patch.object(widget, "_on_autorange") as mock_autorange_skip:
            widget.set_selected_laps([("s_multi", 1, "#00E676")])
            app.processEvents()
            # _on_autorange should NOT have been called!
            mock_autorange_skip.assert_not_called()

        # X zoom is preserved!
        p1_after = widget.plot_widgets["speed"]
        self.assertAlmostEqual(p1_after.vb.viewRange()[0][0], 1.0, places=2)
        self.assertAlmostEqual(p1_after.vb.viewRange()[0][1], 3.0, places=2)

        # 4. User modifies channels (e.g. only select "speed")
        widget.set_selected_channels({"speed"})
        app.processEvents()
        p1_after_ch = widget.plot_widgets["speed"]
        self.assertAlmostEqual(p1_after_ch.vb.viewRange()[0][0], 1.0, places=2)
        self.assertAlmostEqual(p1_after_ch.vb.viewRange()[0][1], 3.0, places=2)

        # 5. User clicks the Auto Range button: resets zoom and clears manual zoom flag
        widget.btn_autorange.click()
        app.processEvents()
        self.assertFalse(widget.has_manual_zoom_or_pan)

        # 6. Subsequent data modification auto-ranges again
        with patch.object(widget, "_on_autorange", wraps=widget._on_autorange) as mock_autorange_again:
            widget.set_selected_channels({"speed", "rpm"})
            mock_autorange_again.assert_called_once()


if __name__ == "__main__":
    unittest.main()

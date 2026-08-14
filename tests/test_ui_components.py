import os
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF, Qt

from core.data_models import Session, Lap
from core.state_manager import StateManager
from ui.graph_view import GraphViewWidget, _get_nearest_channel_sample
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
            channels=["Speed", "RPM"]
        )
        data1 = {
            "Time": np.array([0.0, 1.0, 2.0]),
            "Speed": np.array([10.0, 20.0, 30.0]),
            "RPM": np.array([1000.0, 2000.0, 3000.0])
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

    def test_tracking_dots_creation_and_movement(self):
        widget = GraphViewWidget()
        sessions = {self.session.id: self.session}
        widget.set_sessions(sessions)
        widget.set_selected_laps([(self.session.id, 1, "#00E676")])
        widget.set_selected_channels({"Speed", "RPM"})

        # 2 channels * 1 lap = 2 tracking dots
        self.assertEqual(len(widget.tracking_dots), 2)

        # Test cursor movement at X = 1.0s
        first_plot = widget.plot_widgets["Speed"]
        scene_pos = first_plot.vb.mapViewToScene(QPointF(1.0, 20.0))
        widget._on_mouse_moved(scene_pos)

        # Verify dot data updated (Speed should be 20.0 at X=1.0)
        speed_dot = [d for d, _, _, ch in widget.tracking_dots if ch == "Speed"][0]
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
            "distance": "Distance", "dist": "Distance", "tavolsag": "Distance", "pos": "Distance", "position": "Distance", "odo": "Distance", "d": "Distance",
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
            "temperature": "Temperature", "temp": "Temperature", "homerséklet": "Temperature", "degc": "Temperature", "homerseklet": "Temperature", "Battery_Temp": "Temperature",
            # SteeringAngle
            "steering": "SteeringAngle", "steer": "SteeringAngle", "kormanyszog": "SteeringAngle", "kormányszög": "SteeringAngle", "Steering_Angle": "SteeringAngle",
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
            "Raw_Brake": "Brake Pressure [bar]",
            "Raw_Coolant": "Coolant Temp [C]"
        }
        dlg.preset_name_input.setText("Custom_Sensors_Preset")
        dlg._save_new_custom_channels(mapping)
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
        session_15 = Session(id="s_15", name="sess_15.csv", file_path="/tmp/15.csv", channels=["Speed"])
        for i in range(1, 16):
            lap = Lap("s_15", i, 1.0, 10.0, {"Time": np.array([0.0, 1.0]), "Speed": np.array([10.0, 20.0])})
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
            channels=["Speed", "RPM", "Throttle"]
        )
        session2 = Session(
            id="s2", name="s2.csv", file_path="/tmp/s2.csv",
            channels=["Speed", "RPM", "Battery_Temp"]
        )

        emitted_channels = []
        sidebar.channels_selection_changed.connect(emitted_channels.append)

        # Add session 1 and select Speed and RPM
        sidebar.add_session(session1)
        sidebar.selected_channels = {"Speed", "RPM"}
        for i in range(sidebar.channel_tree.topLevelItemCount()):
            item = sidebar.channel_tree.topLevelItem(i)
            if item.text(0) in {"Speed", "RPM"}:
                item.setSelected(True)

        # Add session 2: Speed and RPM must remain selected and tree must be checked
        sidebar.add_session(session2)
        self.assertEqual(sidebar.selected_channels, {"Speed", "RPM"})
        selected_in_tree = {
            sidebar.channel_tree.topLevelItem(i).text(0)
            for i in range(sidebar.channel_tree.topLevelItemCount())
            if sidebar.channel_tree.topLevelItem(i).isSelected()
        }
        self.assertEqual(selected_in_tree, {"Speed", "RPM"})
        self.assertEqual(emitted_channels[-1], {"Speed", "RPM"})

        # Remove session 1: Speed and RPM exist in session2, so they should remain
        sidebar.remove_session("s1")
        self.assertEqual(sidebar.selected_channels, {"Speed", "RPM"})
        self.assertEqual(emitted_channels[-1], {"Speed", "RPM"})

        # Remove session 2: All channels gone
        sidebar.remove_session("s2")
        self.assertEqual(sidebar.selected_channels, set())
        self.assertEqual(emitted_channels[-1], set())

    def test_sidebar_laps_selection_deterministic_sorting(self):
        """Validates that laps_selection_changed emits deterministically sorted tuples by (session_id, lap_num)."""
        sidebar = SidebarWidget()
        sess = Session(id="s_sort", name="sort.csv", file_path="/tmp/sort.csv", channels=["Speed"])
        for i in range(1, 6):
            sess.laps.append(Lap("s_sort", i, 1.0, 10.0, {"Time": np.array([0.0, 1.0]), "Speed": np.array([10.0, 20.0])}))
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
        widget.set_selected_channels({"Speed"})

        widget.show()
        app.processEvents()

        self.assertEqual(len(widget.plot_widgets), 1)
        plot = widget.plot_widgets["Speed"]
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
        widget.selected_channels = ["Speed"]

        with patch.object(widget, "_on_autorange") as mock_autorange:
            # 1. Changing selected laps triggers auto-range
            widget.set_selected_laps([(self.session.id, 1, "#00E676")])
            mock_autorange.assert_called()

        with patch.object(widget, "_on_autorange") as mock_autorange2:
            # 2. Changing selected channels triggers auto-range
            widget.set_selected_channels({"Speed", "RPM"})
            mock_autorange2.assert_called()

    def test_legend_displays_all_laps_across_multiple_files_with_unequal_channels(self):
        """Validates that legend shows laps from all files even if row 0 channel is missing in some files."""
        widget = GraphViewWidget()

        # Session 1 has Brake and Speed
        s1 = Session(id="s1", name="run1.csv", file_path="/tmp/run1.csv", channels=["Brake", "Speed"])
        s1.laps.append(Lap("s1", 1, 10.0, 100.0, {"Time": np.array([0, 1]), "Brake": np.array([50, 100]), "Speed": np.array([10, 20])}))

        # Session 2 has ONLY Speed (NO Brake)
        s2 = Session(id="s2", name="run2.csv", file_path="/tmp/run2.csv", channels=["Speed"])
        s2.laps.append(Lap("s2", 1, 11.0, 100.0, {"Time": np.array([0, 1]), "Speed": np.array([12, 22])}))

        widget.set_sessions({"s1": s1, "s2": s2})
        # Brake is row 0 ('Brake' < 'Speed'), Speed is row 1
        widget.set_selected_channels({"Brake", "Speed"})
        widget.set_selected_laps([("s1", 1, "#00E676"), ("s2", 1, "#FF5252")])

        self.assertIsNotNone(widget.legend)
        legend_texts = [item[1].text for item in widget.legend.items]
        self.assertEqual(len(legend_texts), 2)
        self.assertIn("run1.csv L1", legend_texts)
        self.assertIn("run2.csv L1", legend_texts)

    def test_sidebar_preserves_selected_laps_when_adding_new_session(self):
        """Validates that adding a new session does not deselect previously selected laps in existing sessions."""
        sidebar = SidebarWidget()
        s1 = Session(id="s1", name="file1.csv", file_path="/tmp/f1.csv", channels=["Speed"])
        s1.laps.append(Lap("s1", 1, 10.0, 100.0, {"Time": np.array([0, 1]), "Speed": np.array([10, 20])}))

        s2 = Session(id="s2", name="file2.csv", file_path="/tmp/f2.csv", channels=["Speed"])
        s2.laps.append(Lap("s2", 1, 11.0, 100.0, {"Time": np.array([0, 1]), "Speed": np.array([12, 22])}))

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


if __name__ == "__main__":
    unittest.main()

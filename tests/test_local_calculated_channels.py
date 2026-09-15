"""
Unit tests for per-file local calculated channels.
Tests formula evaluation against raw file columns, cascading calculations,
X-axis resolution, preset persistence, and UI dialog/wizard workflows.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from core.data_models import Session, Lap
from core.file_parser import parse_session_from_dataframe, parse_session
from core.state_manager import StateManager
from ui.import_wizard import ImportWizardDialog
from ui.local_calculated_channel_dialog import LocalCalculatedChannelDialog

app = QApplication.instance()
if not app:
    app = QApplication([])


class TestLocalCalculatedChannels(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.state_mgr = StateManager(config_dir=self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_parse_session_with_local_calculated_channels(self):
        """
        Validates that a local calculated channel computes values from unmapped raw file columns
        and correctly maps the evaluated array to a target global channel slug.
        """
        raw_df = pd.DataFrame({
            "Lap_Raw": [1, 1, 1, 2, 2, 2],
            "Time_Raw": [0.0, 1.0, 2.0, 3.0, 4.0, 5.0],
            "Wheel_FL": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0],
            "Wheel_FR": [12.0, 22.0, 32.0, 42.0, 52.0, 62.0],
        })

        mapping = {
            "Lap_Raw": "lap_num",
            "Time_Raw": "lap_time",
        }

        local_calcs = [
            {
                "formula": "(A + B) / 2.0",
                "inputs": {"A": "Wheel_FL", "B": "Wheel_FR"},
                "target_slug": "speed"
            }
        ]

        session = parse_session_from_dataframe(
            raw_df=raw_df,
            file_path="test_log.csv",
            mapping=mapping,
            session_id="session-1",
            local_calculated_channels=local_calcs
        )

        self.assertEqual(len(session.laps), 2)
        self.assertIn("speed", session.channels)
        self.assertEqual(len(session.local_calculated_channels), 1)
        self.assertEqual(session.local_calculated_channels[0]["target_slug"], "speed")

        # Lap 1: (Wheel_FL + Wheel_FR) / 2.0 = [11.0, 21.0, 31.0]
        lap1_speed = session.laps[0].get_channel("speed")
        self.assertIsNotNone(lap1_speed)
        np.testing.assert_allclose(lap1_speed, [11.0, 21.0, 31.0])

        # Lap 2: [41.0, 51.0, 61.0]
        lap2_speed = session.laps[1].get_channel("speed")
        self.assertIsNotNone(lap2_speed)
        np.testing.assert_allclose(lap2_speed, [41.0, 51.0, 61.0])

    def test_cascading_local_calculated_channels(self):
        """
        Validates that a local calculated channel can consume the output of a prior local calculated channel.
        """
        raw_df = pd.DataFrame({
            "Lap": [1, 1, 1],
            "Time": [0.0, 1.0, 2.0],
            "Motor_V": [48.0, 48.0, 48.0],
            "Motor_I": [10.0, 20.0, 30.0],
        })

        mapping = {"Lap": "lap_num", "Time": "lap_time"}
        local_calcs = [
            {
                "formula": "A * B",
                "inputs": {"A": "Motor_V", "B": "Motor_I"},
                "target_slug": "power"
            },
            {
                "formula": "A / 1000.0",
                "inputs": {"A": "power"},
                "target_slug": "power_kw"
            }
        ]

        session = parse_session_from_dataframe(
            raw_df=raw_df,
            file_path="cascade.csv",
            mapping=mapping,
            session_id="session-cascade",
            local_calculated_channels=local_calcs
        )

        lap = session.laps[0]
        np.testing.assert_allclose(lap.get_channel("power"), [480.0, 960.0, 1440.0])
        np.testing.assert_allclose(lap.get_channel("power_kw"), [0.48, 0.96, 1.44])

    def test_local_calculated_channel_as_x_axis(self):
        """
        Validates that mapping a local calculated channel to lap_dist or lap_time
        properly resolves the X-axis and calculates lap distance/duration.
        """
        raw_df = pd.DataFrame({
            "Lap": [1, 1, 1],
            "Time": [0.0, 1.0, 2.0],
            "Ticks": [0.0, 50.0, 100.0],
        })

        mapping = {"Lap": "lap_num", "Time": "lap_time"}
        local_calcs = [
            {
                "name": "Distance_Calc",
                "formula": "A * 1.5",
                "inputs": {"A": "Ticks"},
                "target_slug": "lap_dist"
            }
        ]

        session = parse_session_from_dataframe(
            raw_df=raw_df,
            file_path="xaxis.csv",
            mapping=mapping,
            session_id="session-xaxis",
            local_calculated_channels=local_calcs
        )

        lap = session.laps[0]
        self.assertAlmostEqual(lap.distance, 150.0)
        np.testing.assert_allclose(lap.get_channel("lap_dist"), [0.0, 75.0, 150.0])

    def test_preset_persistence_with_local_calculated_channels(self):
        """
        Validates saving and loading presets with local calculated channels.
        """
        mapping = {"Lap": "lap_num", "Time": "lap_time"}
        local_calcs = [
            {
                "name": "Steer_Angle",
                "formula": "A * 0.1",
                "inputs": {"A": "Steer_Pot"},
                "target_slug": "steering_angle"
            }
        ]

        slug = self.state_mgr.save_preset(
            preset_name="Test Preset Calcs",
            mapping=mapping,
            local_calculated_channels=local_calcs
        )

        preset = self.state_mgr.get_preset_by_slug(slug)
        self.assertIsNotNone(preset)
        self.assertEqual(preset["mapping"], mapping)
        self.assertEqual(len(preset.get("local_calculated_channels", [])), 1)
        self.assertEqual(preset["local_calculated_channels"][0]["name"], "Steer_Angle")

        # Test export and re-import
        export_file = os.path.join(self.temp_dir, "export.json")
        self.state_mgr.export_config_to_file(export_file)

        new_state_mgr = StateManager(config_dir=os.path.join(self.temp_dir, "new_cfg"))
        new_state_mgr.import_config_from_file(export_file)

        imported_p = new_state_mgr.get_preset_by_slug(slug)
        self.assertIsNotNone(imported_p)
        self.assertEqual(len(imported_p.get("local_calculated_channels", [])), 1)
        self.assertEqual(imported_p["local_calculated_channels"][0]["target_slug"], "steering_angle")

    def test_local_calculated_channel_dialog(self):
        """
        Validates LocalCalculatedChannelDialog form entry, input selection, formula validation, and save.
        """
        self.state_mgr.save_channel_defs([
            {"label": "Lap Number", "slug": "lap_num", "type": "system", "unit": ""},
            {"label": "Lap Time", "slug": "lap_time", "type": "system", "unit": "s"},
            {"label": "Lap Distance", "slug": "lap_dist", "type": "system", "unit": "m"},
            {"label": "Speed", "slug": "speed", "type": "normal", "unit": "km/h"},
        ])
        raw_cols = ["FL_Speed", "FR_Speed", "Steering"]
        dlg = LocalCalculatedChannelDialog(
            raw_columns=raw_cols,
            state_manager=self.state_mgr
        )

        # Set target channel
        dlg.target_combo.setEditText("Speed [km/h]")
        # Set input A = FL_Speed
        dlg.input_rows[0].combo.setCurrentIndex(dlg.input_rows[0].combo.findData("FL_Speed"))
        # Add input B = FR_Speed
        dlg._on_add_input_row()
        dlg.input_rows[1].combo.setCurrentIndex(dlg.input_rows[1].combo.findData("FR_Speed"))

        # Formula
        dlg.formula_input.setText("(A + B) / 2.0")
        dlg._validate_live()
        self.assertIn("✓", dlg.status_label.text())

        # Save
        dlg._on_save()
        self.assertEqual(dlg.result(), QDialog.Accepted)
        self.assertIsNotNone(dlg.result_channel_data)
        self.assertEqual(dlg.result_channel_data["target_slug"], "speed")
        self.assertEqual(dlg.result_channel_data["target_label"], "Speed [km/h]")
        self.assertEqual(dlg.result_channel_data["inputs"], {"A": "FL_Speed", "B": "FR_Speed"})
        self.assertEqual(dlg.result_channel_data["formula"], "(A + B) / 2.0")

    def test_import_wizard_local_calculated_channels(self):
        """
        Validates that ImportWizardDialog exposes local calculated channel management,
        checks for duplicate target channels across raw mappings and calcs, and loads/saves presets.
        """
        raw_cols = ["Lap", "Time", "V1", "V2"]
        initial_mapping = {"Lap": "lap_num", "Time": "lap_time"}
        initial_calcs = [
            {
                "formula": "A - B",
                "inputs": {"A": "V1", "B": "V2"},
                "target_slug": "voltage_delta",
                "target_label": "Voltage Delta"
            }
        ]

        wizard = ImportWizardDialog(
            file_path="wizard_test.csv",
            raw_columns=raw_cols,
            state_manager=self.state_mgr,
            initial_mapping=initial_mapping,
            initial_local_calculated_channels=initial_calcs
        )

        self.assertEqual(len(wizard.local_calculated_channels), 1)
        self.assertEqual(wizard.calc_table.rowCount(), 1)
        self.assertEqual(wizard.calc_table.columnCount(), 4)
        self.assertEqual(wizard.calc_table.item(0, 0).text(), "✓")
        self.assertEqual(wizard.calc_table.item(0, 1).text(), "Voltage Delta")
        self.assertEqual(wizard.stat_calc_missing.text(), "⚠ 0 Formulas Missing Inputs")

        # Test duplicate detection: map V1 directly to "voltage_delta" as well
        wizard.combos["V1"].setEditText("voltage_delta")
        with patch.object(wizard, "reject") as _:
            # Submitting should fail validation due to duplicate target channel
            with patch("ui.import_wizard.QMessageBox.critical") as mock_crit:
                wizard._on_submit()
                mock_crit.assert_called()

        # Reset V1 to skip
        wizard.combos["V1"].setCurrentIndex(0)

        # Save preset with local calculation
        wizard.preset_combo.setEditText("Wizard Calc Preset")
        with patch.object(QMessageBox, "information"):
            wizard._on_save_preset()

        saved_preset = self.state_mgr.get_preset_by_name("Wizard Calc Preset")
        self.assertIsNotNone(saved_preset)
        self.assertEqual(len(saved_preset.get("local_calculated_channels", [])), 1)
        self.assertEqual(saved_preset["local_calculated_channels"][0]["target_slug"], "voltage_delta")

        # Submit
        wizard._on_submit()
        self.assertEqual(wizard.result(), QDialog.Accepted)
        self.assertEqual(len(wizard.result_local_calculated_channels), 1)
        self.assertEqual(wizard.result_local_calculated_channels[0]["target_slug"], "voltage_delta")

    def test_local_calculated_channel_missing_input_indicator(self):
        """
        Validates that when a local calculation requires an input not present in the file:
        1. An indicator badge on top shows '⚠ 1 Calc Channel Missing Inputs'.
        2. The calc table displays a warning icon '⚠' and marks the missing input in the formula.
        3. Submitting is blocked with an informative error.
        """
        raw_cols = ["Lap", "Time", "V1"]
        initial_mapping = {"Lap": "lap_num", "Time": "lap_time"}
        calcs_with_missing = [
            {
                "formula": "A - B",
                "inputs": {"A": "V1", "B": "V_Missing_Col"},
                "target_slug": "voltage_delta",
                "target_label": "Voltage Delta"
            }
        ]

        wizard = ImportWizardDialog(
            file_path="wizard_missing.csv",
            raw_columns=raw_cols,
            state_manager=self.state_mgr,
            initial_mapping=initial_mapping,
            initial_local_calculated_channels=calcs_with_missing
        )

        # 1. Top badge indicator
        self.assertEqual(wizard.stat_calc_missing.text(), "⚠ 1 Formula Missing Inputs")
        self.assertIn("rgba(255, 215, 64", wizard.stat_calc_missing.styleSheet())
        self.assertIn("V_Missing_Col", wizard.stat_calc_missing.toolTip())

        # 2. Table row indicator
        self.assertEqual(wizard.calc_table.item(0, 0).text(), "⚠")
        self.assertIn("V_Missing_Col", wizard.calc_table.item(0, 0).toolTip())
        self.assertIn("missing", wizard.calc_table.item(0, 2).text().lower())

        # 3. Submitting should be blocked
        with patch("ui.import_wizard.QMessageBox.critical") as mock_crit:
            wizard._on_submit()
            mock_crit.assert_called_once()
            call_args = mock_crit.call_args[0]
            self.assertIn("V_Missing_Col", call_args[2])
            self.assertNotEqual(wizard.result(), QDialog.Accepted)

    def test_session_raw_df_and_mapping_not_polluted_by_calculated_channels(self):
        """
        Validates that Session.raw_df and Session.mapping strictly contain raw file columns
        and do not contain local calculated channel targets or names.
        """
        raw_df = pd.DataFrame({
            "Lap_Raw": [1, 1, 1],
            "Time_Raw": [0.0, 1.0, 2.0],
            "V1": [10.0, 20.0, 30.0],
            "V2": [5.0, 10.0, 15.0],
        })
        mapping = {
            "Lap_Raw": "lap_num",
            "Time_Raw": "lap_time",
        }
        local_calcs = [
            {
                "formula": "A - B",
                "inputs": {"A": "V1", "B": "V2"},
                "target_slug": "voltage_delta",
                "name": "Voltage Delta Calc"
            }
        ]
        session = parse_session_from_dataframe(
            raw_df=raw_df,
            file_path="test_clean.csv",
            mapping=mapping,
            session_id="session-clean",
            local_calculated_channels=local_calcs
        )

        # raw_df columns must only be original raw columns
        self.assertNotIn("voltage_delta", session.raw_df.columns)
        self.assertNotIn("Voltage Delta Calc", session.raw_df.columns)
        self.assertEqual(list(session.raw_df.columns), ["Lap_Raw", "Time_Raw", "V1", "V2"])

        # mapping must not map the calculated channel
        self.assertNotIn("voltage_delta", session.mapping)
        self.assertNotIn("voltage_delta", session.mapping.values())
        self.assertEqual(session.mapping, {"Lap_Raw": "lap_num", "Time_Raw": "lap_time"})

        # session.channels and lap data DO contain the calculated channel
        self.assertIn("voltage_delta", session.channels)
        self.assertIsNotNone(session.laps[0].get_channel("voltage_delta"))

    def test_remapping_session_with_calculated_channels_in_wizard(self):
        """
        Validates that opening ImportWizardDialog for an existing session with local calculated channels:
        1. Does not list calculated channel targets in the raw table.
        2. Does not fail _validate_no_duplicates with duplicate channel error.
        3. Allows saving and updating cleanly.
        """
        raw_df = pd.DataFrame({
            "Lap": [1, 1, 1],
            "Time": [0.0, 1.0, 2.0],
            "Current": [10.0, 12.0, 14.0],
            "Voltage": [48.0, 48.0, 48.0]
        })
        mapping = {"Lap": "lap_num", "Time": "lap_time"}
        local_calcs = [
            {
                "formula": "A * B",
                "inputs": {"A": "Voltage", "B": "Current"},
                "target_slug": "power",
                "target_label": "Power"
            }
        ]
        session = parse_session_from_dataframe(
            raw_df=raw_df,
            file_path="remap_test.csv",
            mapping=mapping,
            session_id="s1",
            local_calculated_channels=local_calcs
        )

        wizard = ImportWizardDialog(
            file_path=session.file_path,
            raw_columns=list(session.raw_df.columns),
            state_manager=self.state_mgr,
            initial_mapping=dict(session.mapping),
            initial_local_calculated_channels=session.local_calculated_channels,
            is_remapping=True
        )

        # 1. Calculated channel target 'power' must not be in raw_columns or table combos
        self.assertNotIn("power", wizard.raw_columns)
        self.assertNotIn("Power", wizard.raw_columns)
        self.assertNotIn("power", wizard.combos)
        self.assertEqual(wizard.table.rowCount(), len(wizard.raw_columns))

        # 2. _validate_no_duplicates must succeed
        label_mapping = wizard._get_current_label_mapping()
        self.assertTrue(wizard._validate_no_duplicates(label_mapping))

        # 3. Submitting succeeds without duplicate error
        with patch("ui.import_wizard.QMessageBox.critical") as mock_crit:
            wizard._on_submit()
            mock_crit.assert_not_called()
            self.assertEqual(wizard.result(), QDialog.Accepted)
            self.assertIn("power", [c["target_slug"] for c in wizard.result_local_calculated_channels])
            self.assertNotIn("power", wizard.result_mapping)

    def test_preset_mapping_excludes_local_calculated_channels(self):
        """
        Validates that saving a preset with local calculated channels does not write
        calculated channel targets into the preset mapping, and loading cleans up any legacy targets.
        """
        raw_cols = ["Lap", "Time", "V", "I"]
        mapping = {"Lap": "lap_num", "Time": "lap_time", "power": "power"}
        local_calcs = [
            {
                "formula": "A * B",
                "inputs": {"A": "V", "B": "I"},
                "target_slug": "power",
                "target_label": "Power"
            }
        ]
        slug = self.state_mgr.save_preset(
            preset_name="CleanPreset",
            mapping=mapping,
            local_calculated_channels=local_calcs
        )

        preset = self.state_mgr.get_preset_by_slug(slug)
        self.assertIsNotNone(preset)
        self.assertNotIn("power", preset["mapping"])
        self.assertEqual(len(preset["local_calculated_channels"]), 1)

        # Wizard loading preset does not show 'power' under missing channels
        wizard = ImportWizardDialog(
            file_path="preset_test.csv",
            raw_columns=raw_cols,
            state_manager=self.state_mgr,
            initial_preset=slug
        )
        self.assertNotIn("power", wizard.raw_columns)
        self.assertNotIn("power", wizard.combos)
        # Verify no warning row for power
        missing_labels = [wizard.table.item(r, 1).text() for r in range(wizard.table.rowCount()) if wizard.table.item(r, 1)]
        self.assertFalse(any("power" in text.lower() for text in missing_labels))


if __name__ == "__main__":
    unittest.main()



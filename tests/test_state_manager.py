"""
Unit tests for core.state_manager covering presets, slug generation, channel defs, and best-fit matching.
"""

import os
import tempfile
import unittest
from core.state_manager import StateManager, generate_slug


class TestStateManager(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_manager = StateManager(config_dir=self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_slug_generation(self):
        self.assertEqual(generate_slug("Lap Time [s]"), "lap_time_s")
        self.assertEqual(generate_slug("Battery Voltage (V)"), "battery_voltage_v")
        self.assertEqual(generate_slug("   Motor_RPM   "), "motor_rpm")
        self.assertEqual(generate_slug("---"), "channel")

    def test_save_and_load_presets(self):
        mapping = {"Raw_Lap": "Lap", "Raw_Time": "Time", "Raw_Spd": "Speed"}
        self.state_manager.save_preset("MoTeC_Test", mapping)

        presets = self.state_manager.load_presets()
        self.assertIn("MoTeC_Test", presets)
        self.assertEqual(presets["MoTeC_Test"], mapping)

        self.state_manager.delete_preset("MoTeC_Test")
        presets_after = self.state_manager.load_presets()
        self.assertNotIn("MoTeC_Test", presets_after)

    def test_coverage_based_best_fit_preset_matching(self):
        # 1. Preset with 2 channels
        self.state_manager.save_preset("Minimal_Preset", {
            "Time": "Time",
            "Lap": "Lap"
        })
        # 2. Preset with 4 channels
        self.state_manager.save_preset("Full_MoTeC_Preset", {
            "Time": "Time",
            "Lap": "Lap",
            "Speed": "Speed",
            "RPM": "RPM"
        })

        raw_columns = ["Time", "Lap", "Speed", "RPM", "Throttle", "Voltage"]
        # Must pick Full_MoTeC_Preset because it matches 4 channels instead of 2
        best = self.state_manager.find_matching_preset(raw_columns)
        self.assertEqual(best, "Full_MoTeC_Preset")

        # If file only has Time, Lap, Notes:
        limited_cols = ["Time", "Lap", "Notes"]
        matched_limited = self.state_manager.find_matching_preset(limited_cols)
        self.assertEqual(matched_limited, "Minimal_Preset")

        # If file has no matching channels:
        none_cols = ["Random_A", "Random_B"]
        self.assertIsNone(self.state_manager.find_matching_preset(none_cols))

    def test_channel_defs_and_labels(self):
        labels = self.state_manager.get_channel_labels()
        self.assertIn("Lap", labels)
        self.assertIn("Time", labels)
        self.assertIn("Distance", labels)
        self.assertIn("Speed", labels)

        custom_channels = [
            {"label": "Kör", "slug": "lap"},
            {"label": "Idő", "slug": "time"},
            {"label": "Távolság", "slug": "distance"}
        ]
        self.state_manager.save_channel_defs(custom_channels)

        self.assertEqual(self.state_manager.get_lap_label(), "Kör")
        self.assertEqual(self.state_manager.get_time_label(), "Idő")
        self.assertEqual(self.state_manager.get_distance_label(), "Távolság")


if __name__ == "__main__":
    unittest.main()

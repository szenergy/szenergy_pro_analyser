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

    def test_no_redundant_disk_io_on_get_channel_defs(self):
        """Validates that reading channel definitions does not write back to disk when format is unchanged."""
        from unittest.mock import patch

        # First call creates the file if not present
        _ = self.state_manager.get_channel_defs()

        # Subsequent reads should NOT call save_channel_defs
        with patch.object(self.state_manager, "save_channel_defs") as mock_save:
            _ = self.state_manager.get_channel_defs()
            _ = self.state_manager.get_channel_labels()
            _ = self.state_manager.get_lap_label()
            _ = self.state_manager.get_time_label()
            _ = self.state_manager.get_distance_label()
            mock_save.assert_not_called()

    def test_legacy_channel_defs_migration(self):
        """Validates that legacy string-only channel definitions are migrated to dicts and persisted once."""
        import json
        from unittest.mock import patch

        # Write legacy string format
        legacy_data = ["Lap", "Time", "Custom_Sensor"]
        with open(self.state_manager.channels_file, "w", encoding="utf-8") as f:
            json.dump(legacy_data, f)

        # Loading should migrate and save to disk
        migrated_defs = self.state_manager.get_channel_defs()
        self.assertEqual(len(migrated_defs), 3)
        self.assertEqual(migrated_defs[0], {"label": "Lap", "slug": "lap"})
        self.assertEqual(migrated_defs[1], {"label": "Time", "slug": "time"})
        self.assertEqual(migrated_defs[2], {"label": "Custom_Sensor", "slug": "custom_sensor"})

        # Verify disk content is now modern format
        with open(self.state_manager.channels_file, "r", encoding="utf-8") as f:
            persisted = json.load(f)
            self.assertEqual(persisted, migrated_defs)

        # Subsequent reads should not trigger disk writes
        with patch.object(self.state_manager, "save_channel_defs") as mock_save:
            _ = self.state_manager.get_channel_defs()
            mock_save.assert_not_called()


if __name__ == "__main__":
    unittest.main()

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
        mapping = {"Raw_Lap": "lap", "Raw_Time": "time", "Raw_Spd": "speed"}
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
            "Time": "time",
            "Lap": "lap"
        })
        # 2. Preset with 4 channels
        self.state_manager.save_preset("Full_MoTeC_Preset", {
            "Time": "time",
            "Lap": "lap",
            "Speed": "speed",
            "RPM": "rpm"
        })

        raw_columns = ["Time", "Lap", "Speed", "RPM", "Throttle", "Voltage"]
        # Must pick Full_MoTeC_Preset because it matches 4 channels instead of 2
        best = self.state_manager.find_matching_preset(raw_columns)
        self.assertEqual(best, "Full_MoTeC_Preset")

        # If file only has Time, Lap, Notes:
        limited_cols = ["Time", "Lap", "Notes"]
        matched_limited = self.state_manager.find_matching_preset(limited_cols)
        self.assertEqual(matched_limited, "Minimal_Preset")

        # Partial matching: File has Time, Lap, Speed (3 of 4 from Full_MoTeC_Preset, missing RPM)
        partial_cols = ["Time", "Lap", "Speed", "Oil_Pressure"]
        matched_partial = self.state_manager.find_matching_preset(partial_cols)
        self.assertEqual(matched_partial, "Full_MoTeC_Preset")

        # If file has no matching channels:
        none_cols = ["Random_A", "Random_B"]
        self.assertIsNone(self.state_manager.find_matching_preset(none_cols))

    def test_preset_match_stats(self):
        """Validates calculation of preset match statistics."""
        self.state_manager.save_preset("Telemetry_Preset", {
            "Time": "time",
            "Lap": "lap",
            "Speed": "speed",
            "RPM": "rpm",
            "Missing_Temp": "temperature"
        })
        raw_columns = ["Time", "Lap", "Speed", "RPM", "Unmapped_Flag"]

        stats = self.state_manager.get_preset_match_stats("Telemetry_Preset", raw_columns)
        self.assertEqual(stats["matched_count"], 4)
        self.assertEqual(stats["preset_total"], 5)
        self.assertEqual(stats["missing_in_file_count"], 1)
        self.assertEqual(stats["unmapped_in_file_count"], 1)
        self.assertAlmostEqual(stats["match_ratio"], 0.8)
        self.assertIn("Missing_Temp", stats["missing_channels"])
        self.assertIn("Unmapped_Flag", stats["unmapped_channels"])

    def test_channel_defs_and_labels(self):
        labels = self.state_manager.get_channel_labels()
        self.assertIn("Lap Number", labels)
        self.assertIn("Lap Time", labels)
        self.assertIn("Lap Distance", labels)
        self.assertIn("Speed", labels)

        custom_channels = [
            {"label": "Kör", "slug": "lap_num"},
            {"label": "Idő", "slug": "lap_time"},
            {"label": "Távolság", "slug": "lap_dist"}
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

        # Subsequent reads should NOT call save_channel_defs (unless they write)
        with patch.object(self.state_manager, "save_channel_defs") as mock_save:
            _ = self.state_manager.get_channel_defs()
            _ = self.state_manager.get_channel_labels()
            _ = self.state_manager.get_lap_label()
            _ = self.state_manager.get_time_label()
            _ = self.state_manager.get_distance_label()
            # If get_channel_defs calls save_channel_defs, it will now always write.
            # But get_channel_defs should not call save_channel_defs on read unless migrating.
            mock_save.assert_not_called()

    def test_label_to_slug_mapping(self):
        mapping = self.state_manager.label_to_slug_mapping()
        self.assertEqual(mapping["Lap Number"], "lap_num")
        self.assertEqual(mapping["Lap Time"], "lap_time")
        self.assertEqual(mapping["Lap Distance"], "lap_dist")

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

        # Verify disk content is now modern format (versioned envelope)
        with open(self.state_manager.channels_file, "r", encoding="utf-8") as f:
            persisted = json.load(f)
            self.assertIn("schema_version", persisted)
            self.assertEqual(persisted["data"], migrated_defs)

        # Subsequent reads should not trigger disk writes
        with patch.object(self.state_manager, "save_channel_defs") as mock_save:
            _ = self.state_manager.get_channel_defs()
            mock_save.assert_not_called()

    def test_unique_slug_generation_and_custom_channel_persistence(self):
        """Validates generate_unique_slug appends numeric counters and save_new_custom_channels persists."""
        slug1 = self.state_manager.generate_unique_slug("Speed", ["speed", "rpm"])
        self.assertEqual(slug1, "speed_1")
        slug2 = self.state_manager.generate_unique_slug("Speed", ["speed", "speed_1", "speed_2"])
        self.assertEqual(slug2, "speed_3")

        # Adding new channels
        added = self.state_manager.save_new_custom_channels(["Brake Pressure", "Coolant Temp", "Speed"])
        self.assertTrue(added)
        labels = self.state_manager.get_channel_labels()
        self.assertIn("Brake Pressure", labels)
        self.assertIn("Coolant Temp", labels)
        self.assertEqual(self.state_manager.get_slug_by_label("Brake Pressure"), "brake_pressure")

        # Second call with same channels does not re-add or change anything
        added_again = self.state_manager.save_new_custom_channels(["Brake Pressure"])
        self.assertFalse(added_again)


if __name__ == "__main__":
    unittest.main()

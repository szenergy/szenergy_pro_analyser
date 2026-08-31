"""
Unit tests for core.state_manager covering presets, slug generation, channel defs, and best-fit matching.
"""

import json
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
        slug = self.state_manager.save_preset("MoTeC_Test", mapping)
        self.assertEqual(slug, "motec_test")

        preset = self.state_manager.get_preset_by_slug(slug)
        self.assertIsNotNone(preset)
        self.assertEqual(preset["name"], "MoTeC_Test")
        self.assertEqual(preset["mapping"], mapping)

        # Renaming preset preserves slug
        renamed_slug = self.state_manager.save_preset("MoTeC_Renamed", mapping, slug=slug)
        self.assertEqual(renamed_slug, slug)
        preset_renamed = self.state_manager.get_preset_by_slug(slug)
        self.assertEqual(preset_renamed["name"], "MoTeC_Renamed")

        self.state_manager.delete_preset(slug)
        self.assertIsNone(self.state_manager.get_preset_by_slug(slug))

    def test_coverage_based_best_fit_preset_matching(self):
        # 1. Preset with 2 channels
        slug_min = self.state_manager.save_preset("Minimal_Preset", {
            "Time": "time",
            "Lap": "lap"
        })
        # 2. Preset with 4 channels
        slug_full = self.state_manager.save_preset("Full_MoTeC_Preset", {
            "Time": "time",
            "Lap": "lap",
            "Speed": "speed",
            "RPM": "rpm"
        })

        raw_columns = ["Time", "Lap", "Speed", "RPM", "Throttle", "Voltage"]
        # Must pick Full_MoTeC_Preset because it matches 4 channels instead of 2
        best = self.state_manager.find_matching_preset(raw_columns)
        self.assertEqual(best, slug_full)

        # If file only has Time, Lap, Notes:
        limited_cols = ["Time", "Lap", "Notes"]
        matched_limited = self.state_manager.find_matching_preset(limited_cols)
        self.assertEqual(matched_limited, slug_min)

        # Partial matching: File has Time, Lap, Speed (3 of 4 from Full_MoTeC_Preset, missing RPM)
        partial_cols = ["Time", "Lap", "Speed", "Oil_Pressure"]
        matched_partial = self.state_manager.find_matching_preset(partial_cols)
        self.assertEqual(matched_partial, slug_full)

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

    def test_file_mapping_persistence(self):
        """Validates saving, retrieving, and removing per-file remembered preset slugs."""
        file_path = "/path/to/telemetry_race1.csv"
        preset_slug = "race_preset"

        self.assertIsNone(self.state_manager.get_file_preset(file_path))

        self.state_manager.save_file_preset(file_path, preset_slug)
        remembered = self.state_manager.get_file_preset(file_path)
        self.assertEqual(remembered, preset_slug)

        self.state_manager.remove_file_preset(file_path)
        self.assertIsNone(self.state_manager.get_file_preset(file_path))

    def test_ui_state_persistence(self):
        """Validates saving, loading, and clearing settings and workspace state in StateManager."""
        self.assertEqual(self.state_manager.load_settings(), {})
        self.assertEqual(self.state_manager.load_workspace_state(), {})

        sample_settings = {
            "window": {"is_maximized": True, "main_splitter": [320, 880]},
            "graph": {"show_x_grid": True, "show_y_grid": False, "x_axis_slug": "lap_dist"},
            "theme_mode": "dark"
        }
        sample_workspace = {
            "sidebar": {"selected_channels": ["speed", "throttle"]},
            "sessions": [{"file_path": "/path/to/log.csv", "selected_laps": [1, 2]}]
        }

        # 1. Test saving and loading settings
        self.state_manager.save_settings(sample_settings)
        self.assertTrue(os.path.exists(self.state_manager.settings_file))
        loaded_settings = self.state_manager.load_settings()
        self.assertEqual(loaded_settings["window"]["is_maximized"], True)
        self.assertEqual(loaded_settings["graph"]["show_x_grid"], True)
        self.assertEqual(loaded_settings["theme_mode"], "dark")

        # 2. Test saving and loading workspace state
        self.state_manager.save_workspace_state(sample_workspace)
        self.assertTrue(os.path.exists(self.state_manager.workspace_state_file))
        loaded_ws = self.state_manager.load_workspace_state()
        self.assertEqual(loaded_ws["sidebar"]["selected_channels"], ["speed", "throttle"])
        self.assertEqual(len(loaded_ws["sessions"]), 1)

        # 3. Test clear_workspace_state removes workspace file but keeps settings
        self.state_manager.clear_workspace_state()
        self.assertFalse(os.path.exists(self.state_manager.workspace_state_file))
        self.assertEqual(self.state_manager.load_workspace_state(), {})
        # Settings remain untouched!
        self.assertTrue(os.path.exists(self.state_manager.settings_file))
        self.assertEqual(self.state_manager.load_settings()["theme_mode"], "dark")

    def test_export_and_import_config(self):
        """Validates export and import of non-machine-specific configuration (presets & channels)."""
        # Set up state manager with custom channels, preset, and machine-specific file mapping and UI state
        self.state_manager.save_new_custom_channels(["Motor Temp", "Inverter Temp"])
        slug1 = self.state_manager.save_preset("Race Telemetry", {"raw_lap": "lap_num", "raw_temp": "motor_temp"})
        self.state_manager.save_file_preset("/my/local/machine/file.csv", slug1)
        self.state_manager.save_ui_state({"window": {"is_maximized": True}})

        # 1. Export configuration
        exported = self.state_manager.export_config()
        self.assertEqual(exported["schema_version"], 1)
        self.assertEqual(exported["type"], "szenergypro_config_export")
        self.assertIn("presets", exported["data"])
        self.assertIn("channels", exported["data"])

        # Verify machine-specific items are NOT exported
        self.assertNotIn("file_mappings", exported["data"])
        self.assertNotIn("ui_state", exported["data"])
        self.assertNotIn("window", exported["data"])

        # Write export to file
        export_file = os.path.join(self.temp_dir.name, "exported_config.json")
        self.state_manager.export_config_to_file(export_file)
        self.assertTrue(os.path.exists(export_file))

        # 2. Create fresh target StateManager in a separate clean directory
        target_dir = tempfile.TemporaryDirectory()
        target_mgr = StateManager(config_dir=target_dir.name)

        # Before import, target manager has default channels and no presets
        self.assertEqual(len(target_mgr.load_presets()), 0)
        self.assertIsNone(target_mgr.get_slug_by_label("Motor Temp"))

        # Import config into target manager
        num_presets, num_channels = target_mgr.import_config_from_file(export_file)
        self.assertGreaterEqual(num_presets, 1)
        self.assertGreaterEqual(num_channels, 2)

        # Verify presets and channels are restored in target
        target_presets = target_mgr.load_presets()
        self.assertEqual(len(target_presets), 1)
        self.assertEqual(target_presets[0]["name"], "Race Telemetry")
        self.assertEqual(target_presets[0]["slug"], slug1)
        self.assertEqual(target_mgr.get_slug_by_label("Motor Temp"), "motor_temp")
        self.assertEqual(target_mgr.get_slug_by_label("Inverter Temp"), "inverter_temp")

        # Verify machine-specific state was NOT imported into target
        self.assertEqual(target_mgr.load_file_presets(), {})
        self.assertEqual(target_mgr.load_ui_state(), {})

        # 3. Test importing renamed system-required channels
        renamed_config_file = os.path.join(self.temp_dir.name, "renamed_sys_channels.json")
        with open(renamed_config_file, "w") as f:
            json.dump({
                "schema_version": 1,
                "data": {
                    "channels": [
                        {"label": "Kör", "slug": "lap_num"},
                        {"label": "Köridő", "slug": "lap_time"},
                        {"label": "Megtett út", "slug": "lap_dist"},
                        {"label": "Féknyomás", "slug": "brake_press"}
                    ]
                }
            }, f)

        target_mgr.import_config_from_file(renamed_config_file)
        self.assertEqual(target_mgr.get_label_by_slug("lap_num"), "Kör")
        self.assertEqual(target_mgr.get_label_by_slug("lap_time"), "Köridő")
        self.assertEqual(target_mgr.get_label_by_slug("lap_dist"), "Megtett út")
        self.assertEqual(target_mgr.get_label_by_slug("brake_press"), "Féknyomás")

        # 4. Test error handling
        invalid_file = os.path.join(self.temp_dir.name, "corrupted.json")
        with open(invalid_file, "w") as f:
            f.write("not a json string")
        with self.assertRaises(ValueError):
            target_mgr.import_config_from_file(invalid_file)

        with self.assertRaises(FileNotFoundError):
            target_mgr.import_config_from_file("/non/existent/path.json")

        target_dir.cleanup()


if __name__ == "__main__":
    unittest.main()

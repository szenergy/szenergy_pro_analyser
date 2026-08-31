"""
Unit tests for core/migrations.py schema versioning and migration execution.
"""

import json
import os
import tempfile
import unittest

from core.migrations import (
    CURRENT_CHANNELS_VERSION,
    CURRENT_PRESETS_VERSION,
    CURRENT_FILE_MAPPINGS_VERSION,
    _migrate_channels_v0_to_v1,
    _migrate_presets_v0_to_v1,
    _migrate_presets_v1_to_v2,
    _migrate_file_mappings_to_slugs,
    _migrate_legacy_ui_state,
    run_migrations,
)
from core.state_manager import StateManager, read_versioned_json, write_versioned_json


class TestMigrations(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_mgr = StateManager(config_dir=self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_migrate_presets_v0_to_v1_conversion(self):
        """Validates that v0 display-label presets are converted to slug-based mappings in v1."""
        legacy_presets = {
            "RaceSetup": {
                "Time_s": "Time",
                "Lap_num": "Lap",
                "Distance_m": "Distance",
                "Engine_RPM": "RPM",
                "V_Bat": "Voltage",
                "Custom_Temp": "Custom Temp"
            }
        }
        migrated = _migrate_presets_v0_to_v1(legacy_presets, self.state_mgr)
        self.assertIn("RaceSetup", migrated)
        mapping = migrated["RaceSetup"]
        self.assertEqual(mapping["Time_s"], "time")
        self.assertEqual(mapping["Lap_num"], "lap")
        self.assertEqual(mapping["Distance_m"], "distance")
        self.assertEqual(mapping["Engine_RPM"], "rpm")
        self.assertEqual(mapping["V_Bat"], "voltage")
        self.assertEqual(mapping["Custom_Temp"], "custom_temp")

    def test_migrate_presets_v1_to_v2_conversion(self):
        """Validates that v1 dict format presets are converted to list of dicts with unique slugs in v2."""
        from core.migrations import _migrate_presets_v1_to_v2
        v1_presets = {
            "MoTeC C125": {"Time": "lap_time", "Lap": "lap_num"},
            "MoTeC C125 Pro": {"Time": "lap_time", "Dist": "lap_dist"}
        }
        migrated = _migrate_presets_v1_to_v2(v1_presets, self.state_mgr)
        self.assertEqual(len(migrated), 2)
        slugs = [p["slug"] for p in migrated]
        names = [p["name"] for p in migrated]
        self.assertIn("motec_c125", slugs)
        self.assertIn("motec_c125_pro", slugs)
        self.assertIn("MoTeC C125", names)

    def test_migrate_channels_v0_to_v1_conversion(self):
        """Validates that v0 string-only channel definitions are converted to list of dicts."""
        legacy_channels = ["Lap", "Time", "Distance", "Custom Pressure"]
        migrated = _migrate_channels_v0_to_v1(legacy_channels, self.state_mgr)
        self.assertEqual(len(migrated), 4)
        self.assertEqual(migrated[0], {"label": "Lap", "slug": "lap"})
        self.assertEqual(migrated[1], {"label": "Time", "slug": "time"})
        self.assertEqual(migrated[2], {"label": "Distance", "slug": "distance"})
        self.assertEqual(migrated[3], {"label": "Custom Pressure", "slug": "custom_pressure"})

    def test_migrate_file_mappings_to_slugs(self):
        """Validates that file_mappings with display names or dicts are converted to preset slugs."""
        self.state_mgr.save_preset("MoTeC C125", {"Time": "lap_time", "Lap": "lap_num"})
        legacy_file_mappings = {
            "/path/to/log1.csv": {"preset_name": "MoTeC C125", "mapping": {}},
            "/path/to/log2.csv": "MoTeC C125",
            "/path/to/log3.csv": "Custom Unknown Preset"
        }
        migrated = _migrate_file_mappings_to_slugs(legacy_file_mappings, self.state_mgr)
        self.assertEqual(migrated["/path/to/log1.csv"], "motec_c125")
        self.assertEqual(migrated["/path/to/log2.csv"], "motec_c125")
        self.assertEqual(migrated["/path/to/log3.csv"], "custom_unknown_preset")

    def test_run_migrations_end_to_end_on_startup(self):
        """Validates that run_migrations upgrades legacy unversioned files on disk to versioned envelope."""
        # 1. Write legacy v0 flat files
        legacy_presets = {
            "OldPreset": {
                "lap_raw": "Lap",
                "time_raw": "Time",
                "speed_raw": "Speed"
            }
        }
        with open(self.state_mgr.presets_file, "w", encoding="utf-8") as f:
            json.dump(legacy_presets, f)

        legacy_channels = ["Lap", "Time", "Distance", "Coolant Temp"]
        with open(self.state_mgr.channels_file, "w", encoding="utf-8") as f:
            json.dump(legacy_channels, f)

        legacy_file_mappings = {
            "/tmp/race_log.csv": {"preset_name": "OldPreset", "mapping": {}}
        }
        with open(self.state_mgr.file_mappings_file, "w", encoding="utf-8") as f:
            json.dump(legacy_file_mappings, f)

        # 2. Run migrations
        run_migrations(self.state_mgr)

        # 3. Check version and content in presets.json
        preset_ver, preset_data = read_versioned_json(self.state_mgr.presets_file)
        self.assertEqual(preset_ver, CURRENT_PRESETS_VERSION)
        self.assertTrue(isinstance(preset_data, list))
        preset_entry = preset_data[0]
        self.assertEqual(preset_entry["name"], "OldPreset")
        self.assertEqual(preset_entry["slug"], "oldpreset")
        self.assertEqual(preset_entry["mapping"]["lap_raw"], "lap")
        self.assertEqual(preset_entry["mapping"]["time_raw"], "time")
        self.assertEqual(preset_entry["mapping"]["speed_raw"], "speed")

        # 4. Check version and content in custom_channels.json
        chan_ver, chan_data = read_versioned_json(self.state_mgr.channels_file)
        self.assertEqual(chan_ver, CURRENT_CHANNELS_VERSION)
        labels = [c["label"] for c in chan_data]
        self.assertIn("Coolant Temp", labels)

        # 5. Check version and content in file_mappings.json
        fm_ver, fm_data = read_versioned_json(self.state_mgr.file_mappings_file)
        self.assertEqual(fm_ver, CURRENT_FILE_MAPPINGS_VERSION)
        self.assertEqual(fm_data["/tmp/race_log.csv"], "oldpreset")

    def test_run_migrations_idempotent_on_up_to_date_files(self):
        """Validates that run_migrations does nothing if files are already at latest version."""
        write_versioned_json(
            self.state_mgr.presets_file,
            CURRENT_PRESETS_VERSION,
            [{"slug": "v2_preset", "name": "V2 Preset", "mapping": {"raw": "slug"}}]
        )
        write_versioned_json(
            self.state_mgr.channels_file,
            CURRENT_CHANNELS_VERSION,
            [{"label": "Lap", "slug": "lap"}]
        )

        # Run migrations
        run_migrations(self.state_mgr)

        preset_ver, preset_data = read_versioned_json(self.state_mgr.presets_file)
        self.assertEqual(preset_ver, CURRENT_PRESETS_VERSION)
        self.assertEqual(preset_data, [{"slug": "v2_preset", "name": "V2 Preset", "mapping": {"raw": "slug"}}])

    def test_run_migrations_handles_non_existent_files(self):
        """Validates that run_migrations does not crash if config files do not exist yet."""
        if os.path.exists(self.state_mgr.presets_file):
            os.remove(self.state_mgr.presets_file)
        if os.path.exists(self.state_mgr.channels_file):
            os.remove(self.state_mgr.channels_file)

        # Should not raise exception
        run_migrations(self.state_mgr)

    def test_migrate_legacy_ui_state(self):
        """Validates that legacy ui_state.json is extracted into settings.json and workspace_state.json."""
        legacy_ui_state = {
            "theme_mode": "light",
            "window": {"is_maximized": False, "main_splitter": [400, 800]},
            "graph": {"show_x_grid": True, "show_y_grid": True, "x_axis_slug": "lap_dist"},
            "workspace": {
                "sessions": [{"file_path": "/path/to/race.csv", "selected_laps": [1]}],
                "sidebar": {"selected_channels": ["speed"]}
            }
        }
        write_versioned_json(self.state_mgr.ui_state_file, 1, legacy_ui_state)
        self.assertTrue(os.path.exists(self.state_mgr.ui_state_file))

        # Run migration
        result = _migrate_legacy_ui_state(self.state_mgr)
        self.assertTrue(result)

        # Legacy file should be removed
        self.assertFalse(os.path.exists(self.state_mgr.ui_state_file))

        # Settings should be extracted
        self.assertTrue(os.path.exists(self.state_mgr.settings_file))
        settings = self.state_mgr.load_settings()
        self.assertEqual(settings["theme_mode"], "light")
        self.assertEqual(settings["graph"]["show_x_grid"], True)
        self.assertEqual(settings["window"]["main_splitter"], [400, 800])

        # Workspace state should be extracted
        self.assertTrue(os.path.exists(self.state_mgr.workspace_state_file))
        ws = self.state_mgr.load_workspace_state()
        self.assertEqual(len(ws["sessions"]), 1)
        self.assertEqual(ws["sessions"][0]["file_path"], "/path/to/race.csv")
        self.assertEqual(ws["sidebar"]["selected_channels"], ["speed"])


if __name__ == "__main__":
    unittest.main()

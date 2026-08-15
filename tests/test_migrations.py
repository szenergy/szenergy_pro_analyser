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
    _migrate_channels_v0_to_v1,
    _migrate_presets_v0_to_v1,
    run_migrations,
)
from core.state_manager import StateManager, _read_versioned_json, _write_versioned_json


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

    def test_migrate_channels_v0_to_v1_conversion(self):
        """Validates that v0 string-only channel definitions are converted to list of dicts."""
        legacy_channels = ["Lap", "Time", "Distance", "Custom Pressure"]
        migrated = _migrate_channels_v0_to_v1(legacy_channels, self.state_mgr)
        self.assertEqual(len(migrated), 4)
        self.assertEqual(migrated[0], {"label": "Lap", "slug": "lap"})
        self.assertEqual(migrated[1], {"label": "Time", "slug": "time"})
        self.assertEqual(migrated[2], {"label": "Distance", "slug": "distance"})
        self.assertEqual(migrated[3], {"label": "Custom Pressure", "slug": "custom_pressure"})

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

        # 2. Run migrations
        run_migrations(self.state_mgr)

        # 3. Check version and content in presets.json
        preset_ver, preset_data = _read_versioned_json(self.state_mgr.presets_file)
        self.assertEqual(preset_ver, CURRENT_PRESETS_VERSION)
        self.assertIn("OldPreset", preset_data)
        self.assertEqual(preset_data["OldPreset"]["lap_raw"], "lap")
        self.assertEqual(preset_data["OldPreset"]["time_raw"], "time")
        self.assertEqual(preset_data["OldPreset"]["speed_raw"], "speed")

        # 4. Check version and content in custom_channels.json
        chan_ver, chan_data = _read_versioned_json(self.state_mgr.channels_file)
        self.assertEqual(chan_ver, CURRENT_CHANNELS_VERSION)
        labels = [c["label"] for c in chan_data]
        self.assertIn("Coolant Temp", labels)

    def test_run_migrations_idempotent_on_up_to_date_files(self):
        """Validates that run_migrations does nothing if files are already at latest version."""
        _write_versioned_json(
            self.state_mgr.presets_file,
            CURRENT_PRESETS_VERSION,
            {"V1Preset": {"raw": "slug"}}
        )
        _write_versioned_json(
            self.state_mgr.channels_file,
            CURRENT_CHANNELS_VERSION,
            [{"label": "Lap", "slug": "lap"}]
        )

        # Run migrations
        run_migrations(self.state_mgr)

        preset_ver, preset_data = _read_versioned_json(self.state_mgr.presets_file)
        self.assertEqual(preset_ver, CURRENT_PRESETS_VERSION)
        self.assertEqual(preset_data, {"V1Preset": {"raw": "slug"}})

    def test_run_migrations_handles_non_existent_files(self):
        """Validates that run_migrations does not crash if config files do not exist yet."""
        if os.path.exists(self.state_mgr.presets_file):
            os.remove(self.state_mgr.presets_file)
        if os.path.exists(self.state_mgr.channels_file):
            os.remove(self.state_mgr.channels_file)

        # Should not raise exception
        run_migrations(self.state_mgr)


if __name__ == "__main__":
    unittest.main()

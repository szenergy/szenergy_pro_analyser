"""
Unit and integration tests for core.file_parser supporting CSV, XLSX, and TDMS formats.
"""

import os
import tempfile
import unittest
import numpy as np
import pandas as pd
from nptdms import TdmsWriter, GroupObject, ChannelObject

from core.file_parser import (
    get_file_columns_and_preview, load_full_dataframe, parse_session, parse_session_from_dataframe
)


class TestFileParser(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.csv_path = os.path.join(self.temp_dir.name, "test.csv")
        self.xlsx_path = os.path.join(self.temp_dir.name, "test.xlsx")
        self.tdms_path = os.path.join(self.temp_dir.name, "test.tdms")
        self.unequal_tdms_path = os.path.join(self.temp_dir.name, "unequal.tdms")

        # Create test CSV (2 Laps)
        df_csv = pd.DataFrame({
            "Lap": [1, 1, 1, 2, 2, 2],
            "Time": [0.0, 1.0, 2.0, 2.5, 3.5, 4.5],
            "Distance": [0.0, 10.0, 20.0, 25.0, 35.0, 45.0],
            "Speed": ["10.5", "15.2", "20.1", "22.0", "25.5", "28.0"],  # String numbers to test coercion
            "Notes": ["a", "b", "c", "d", "e", "f"]
        })
        df_csv.to_csv(self.csv_path, index=False)

        # Create test XLSX
        df_xlsx = pd.DataFrame({
            "Lap_No": [1, 1, 2, 2],
            "Timestamp": [0.0, 1.5, 2.0, 3.5],
            "Dist": [0.0, 15.0, 20.0, 35.0],
            "RPM": [2000, 2500, 2700, 3000]
        })
        with pd.ExcelWriter(self.xlsx_path, engine="openpyxl") as writer:
            df_xlsx.to_excel(writer, sheet_name="Telemetry", index=False)

        # Create test TDMS (Equal length)
        with TdmsWriter(self.tdms_path) as writer:
            grp = GroupObject("Telemetry")
            c_lap = ChannelObject("Telemetry", "Lap", np.array([1, 1, 2, 2]))
            c_time = ChannelObject("Telemetry", "Time", np.array([0.0, 1.0, 1.5, 2.5]))
            c_dist = ChannelObject("Telemetry", "Distance", np.array([0.0, 10.0, 15.0, 25.0]))
            c_spd = ChannelObject("Telemetry", "Speed", np.array([10.0, 20.0, 30.0, 40.0]))
            writer.write_segment([grp, c_lap, c_time, c_dist, c_spd])

        # Create multi-rate TDMS with unequal channel lengths
        with TdmsWriter(self.unequal_tdms_path) as writer:
            grp = GroupObject("Sensors")
            c_gps = ChannelObject("Sensors", "GPS_Speed", np.array([10.0, 12.0]))  # 2 samples
            c_imu = ChannelObject("Sensors", "Accel_X", np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6]))  # 6 samples
            writer.write_segment([grp, c_gps, c_imu])

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_csv_preview_and_parsing(self):
        cols, preview = get_file_columns_and_preview(self.csv_path)
        self.assertIn("Lap", cols)
        self.assertIn("Speed", cols)
        self.assertEqual(len(preview), 5)

        mapping = {"Lap": "lap", "Time": "time", "Distance": "distance", "Speed": "speed"}
        session = parse_session(self.csv_path, mapping, "sess_csv")

        self.assertEqual(session.name, "test.csv")
        self.assertEqual(len(session.laps), 2)
        
        lap1 = session.get_lap(1)
        self.assertIsNotNone(lap1)
        self.assertEqual(lap1.duration, 2.0)
        self.assertEqual(lap1.distance, 20.0)
        self.assertTrue(np.issubdtype(lap1.get_channel("speed").dtype, np.floating))

        lap2 = session.get_lap(2)
        self.assertIsNotNone(lap2)
        self.assertEqual(lap2.duration, 2.0)

    def test_excel_preview_and_parsing(self):
        cols, preview = get_file_columns_and_preview(self.xlsx_path)
        self.assertIn("Lap_No", cols)
        self.assertIn("RPM", cols)

        mapping = {"Lap_No": "lap", "Timestamp": "time", "Dist": "distance", "RPM": "rpm"}
        session = parse_session(self.xlsx_path, mapping, "sess_xlsx")

        self.assertEqual(len(session.laps), 2)
        lap1 = session.get_lap(1)
        self.assertEqual(lap1.duration, 1.5)
        self.assertEqual(lap1.distance, 15.0)

    def test_tdms_preview_and_parsing(self):
        cols, preview = get_file_columns_and_preview(self.tdms_path)
        self.assertIn("Telemetry/Lap", cols)
        self.assertIn("Telemetry/Speed", cols)

        mapping = {
            "Telemetry/Lap": "lap",
            "Telemetry/Time": "time",
            "Telemetry/Distance": "distance",
            "Telemetry/Speed": "speed"
        }
        session = parse_session(self.tdms_path, mapping, "sess_tdms")
        self.assertEqual(len(session.laps), 2)
        lap1 = session.get_lap(1)
        self.assertEqual(lap1.duration, 1.0)
        self.assertEqual(lap1.distance, 10.0)

    def test_unequal_length_tdms_support(self):
        cols, preview = get_file_columns_and_preview(self.unequal_tdms_path)
        self.assertEqual(len(cols), 2)
        self.assertEqual(len(preview), 5)

        df = load_full_dataframe(self.unequal_tdms_path)
        self.assertEqual(len(df), 6)
        self.assertTrue(np.isnan(df["Sensors/GPS_Speed"].iloc[3]))

    def test_sample_data_files_if_present(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sample_dir = os.path.join(base_dir, "sample_data")
        if not os.path.exists(sample_dir):
            return

        motec_csv = os.path.join(sample_dir, "sample_motec.csv")
        if os.path.exists(motec_csv):
            cols, _ = get_file_columns_and_preview(motec_csv)
            mapping = {c: c for c in cols}
            session = parse_session(motec_csv, mapping, "s_motec")
            self.assertEqual(len(session.laps), 3)

        ecu_xlsx = os.path.join(sample_dir, "sample_ecu.xlsx")
        if os.path.exists(ecu_xlsx):
            cols, _ = get_file_columns_and_preview(ecu_xlsx)
            mapping = {
                "Lap_Index": "lap",
                "Timestamp_s": "time",
                "Distance_m": "distance",
                "Speed_kmh": "speed"
            }
            session = parse_session(ecu_xlsx, mapping, "s_ecu")
            self.assertEqual(len(session.laps), 2)

        ni_tdms = os.path.join(sample_dir, "sample_ni.tdms")
        if os.path.exists(ni_tdms):
            cols, _ = get_file_columns_and_preview(ni_tdms)
            mapping = {
                "Vehicle/Lap": "lap",
                "Vehicle/Time": "time",
                "Vehicle/Distance": "distance",
                "Vehicle/Speed": "speed"
            }
            session = parse_session(ni_tdms, mapping, "s_ni")
            self.assertEqual(len(session.laps), 2)

    def test_nan_preservation_in_telemetry_curves(self):
        """Validates that NaN values in telemetry channels are preserved rather than coerced to 0.0."""
        nan_csv_path = os.path.join(self.temp_dir.name, "nan_test.csv")
        df_nan = pd.DataFrame({
            "Lap": [1, 1, 1],
            "Time": [0.0, 1.0, 2.0],
            "Distance": [0.0, 10.0, 20.0],
            "SensorA": [10.5, np.nan, 25.0],
            "SensorB": ["1.2", "invalid_text", "3.4"]
        })
        df_nan.to_csv(nan_csv_path, index=False)

        mapping = {
            "Lap": "lap",
            "Time": "time",
            "Distance": "distance",
            "SensorA": "sensora",
            "SensorB": "sensorb"
        }
        session = parse_session(nan_csv_path, mapping, "sess_nan")
        lap1 = session.get_lap(1)
        self.assertIsNotNone(lap1)

        sensor_a = lap1.get_channel("sensora")
        self.assertEqual(len(sensor_a), 3)
        self.assertEqual(sensor_a[0], 10.5)
        self.assertTrue(np.isnan(sensor_a[1]), "Missing value must remain np.nan, not 0.0")
        self.assertEqual(sensor_a[2], 25.0)

        sensor_b = lap1.get_channel("sensorb")
        self.assertEqual(len(sensor_b), 3)
        self.assertAlmostEqual(sensor_b[0], 1.2)
        self.assertTrue(np.isnan(sensor_b[1]), "Non-numeric string must become np.nan, not 0.0")
        self.assertAlmostEqual(sensor_b[2], 3.4)

    def test_multi_rate_tdms_nan_preservation_in_laps(self):
        """Validates that multi-rate channels padded with NaN preserve NaN in Lap channel data."""
        mapping = {
            "Sensors/GPS_Speed": "speed",
            "Sensors/Accel_X": "accel_x"
        }
        session = parse_session(self.unequal_tdms_path, mapping, "sess_unequal")
        self.assertEqual(len(session.laps), 1)
        lap1 = session.get_lap(1)
        speed = lap1.get_channel("speed")
        self.assertEqual(len(speed), 6)
        self.assertEqual(speed[0], 10.0)
        self.assertEqual(speed[1], 12.0)
        self.assertTrue(np.isnan(speed[2]))
        self.assertTrue(np.isnan(speed[5]))

    def test_slug_and_fallback_label_resolution(self):
        """Tests custom label, standard fallback, and slug resolution for Lap, Time, and Distance."""
        custom_csv_path = os.path.join(self.temp_dir.name, "custom_labels.csv")
        df_custom = pd.DataFrame({
            "kor_szam": [1, 1, 2, 2],
            "ido": [0.0, 5.0, 10.0, 15.0],
            "tavolsag": [0.0, 50.0, 100.0, 150.0],
            "sebesseg": [20.0, 25.0, 30.0, 35.0]
        })
        df_custom.to_csv(custom_csv_path, index=False)

        # 1. Hungarian custom configured labels
        mapping_hu = {
            "kor_szam": "lap",
            "ido": "time",
            "tavolsag": "distance",
            "sebesseg": "speed"
        }
        session_hu = parse_session(
            custom_csv_path, mapping_hu, "sess_hu",
            lap_label="Kör", time_label="Idő", dist_label="Távolság"
        )
        self.assertEqual(len(session_hu.laps), 2)
        lap1 = session_hu.get_lap(1)
        self.assertEqual(lap1.duration, 5.0)
        self.assertEqual(lap1.distance, 50.0)

        # 2. Configured label mismatch fallback to standard / slug
        mapping_std = {
            "kor_szam": "lap",
            "ido": "time",
            "tavolsag": "distance",
            "sebesseg": "speed"
        }
        # lap_label passed as custom "Kör", but mapped to standard "Lap"
        session_fallback = parse_session(
            custom_csv_path, mapping_std, "sess_fb",
            lap_label="Kör", time_label="Idő", dist_label="Távolság"
        )
        self.assertEqual(len(session_fallback.laps), 2)
        self.assertEqual(session_fallback.get_lap(1).duration, 5.0)
        self.assertEqual(session_fallback.get_lap(1).distance, 50.0)

        # 3. Slug matching (e.g. 'timestamp' or 'dist')
        mapping_slugs = {
            "kor_szam": "lap_number",
            "ido": "timestamp",
            "tavolsag": "dist",
            "sebesseg": "speed"
        }
        session_slugs = parse_session(
            custom_csv_path, mapping_slugs, "sess_slugs",
            lap_slug="lap_number", time_slug="timestamp", dist_slug="dist"
        )
        self.assertEqual(len(session_slugs.laps), 2)
        self.assertEqual(session_slugs.get_lap(1).duration, 5.0)
        self.assertEqual(session_slugs.get_lap(1).distance, 50.0)

    def test_session_retains_raw_df_and_in_memory_reparsing(self):
        """Validates that parse_session keeps raw_df in Session and parse_session_from_dataframe re-parses in memory."""
        mapping = {"Lap": "lap", "Time": "time", "Distance": "distance", "Speed": "speed"}
        session = parse_session(self.csv_path, mapping, "sess_raw", preset_name="OriginalPreset")

        self.assertIsNotNone(session.raw_df)
        self.assertIn("Notes", session.raw_df.columns)
        self.assertEqual(session.preset_name, "OriginalPreset")

        # Now re-parse directly from session.raw_df without disk I/O
        updated_mapping = {"Lap": "lap", "Time": "time", "Distance": "distance", "Notes": "commentary"}
        updated_session = parse_session_from_dataframe(
            raw_df=session.raw_df,
            file_path=session.file_path,
            mapping=updated_mapping,
            session_id="sess_raw",
            preset_name="UpdatedPreset"
        )

        self.assertEqual(updated_session.preset_name, "UpdatedPreset")
        self.assertIn("commentary", updated_session.channels)
        self.assertNotIn("speed", updated_session.channels)
        self.assertIsNotNone(updated_session.raw_df)


if __name__ == "__main__":
    unittest.main()

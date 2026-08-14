"""
Unit and integration tests for core.file_parser supporting CSV, XLSX, and TDMS formats.
"""

import os
import tempfile
import unittest
import numpy as np
import pandas as pd
from nptdms import TdmsWriter, GroupObject, ChannelObject

from core.file_parser import get_file_columns_and_preview, load_full_dataframe, parse_session


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

        mapping = {"Lap": "Lap", "Time": "Time", "Distance": "Distance", "Speed": "Speed"}
        session = parse_session(self.csv_path, mapping, "sess_csv")

        self.assertEqual(session.name, "test.csv")
        self.assertEqual(len(session.laps), 2)
        
        lap1 = session.get_lap(1)
        self.assertIsNotNone(lap1)
        self.assertEqual(lap1.duration, 2.0)
        self.assertEqual(lap1.distance, 20.0)
        self.assertTrue(np.issubdtype(lap1.get_channel("Speed").dtype, np.floating))

        lap2 = session.get_lap(2)
        self.assertIsNotNone(lap2)
        self.assertEqual(lap2.duration, 2.0)

    def test_excel_preview_and_parsing(self):
        cols, preview = get_file_columns_and_preview(self.xlsx_path)
        self.assertIn("Lap_No", cols)
        self.assertIn("RPM", cols)

        mapping = {"Lap_No": "Lap", "Timestamp": "Time", "Dist": "Distance", "RPM": "RPM"}
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
            "Telemetry/Lap": "Lap",
            "Telemetry/Time": "Time",
            "Telemetry/Distance": "Distance",
            "Telemetry/Speed": "Speed"
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
                "Lap_Index": "Lap",
                "Timestamp_s": "Time",
                "Distance_m": "Distance",
                "Speed_kmh": "Speed"
            }
            session = parse_session(ecu_xlsx, mapping, "s_ecu")
            self.assertEqual(len(session.laps), 2)

        ni_tdms = os.path.join(sample_dir, "sample_ni.tdms")
        if os.path.exists(ni_tdms):
            cols, _ = get_file_columns_and_preview(ni_tdms)
            mapping = {
                "Vehicle/Lap": "Lap",
                "Vehicle/Time": "Time",
                "Vehicle/Distance": "Distance",
                "Vehicle/Speed": "Speed"
            }
            session = parse_session(ni_tdms, mapping, "s_ni")
            self.assertEqual(len(session.laps), 2)


if __name__ == "__main__":
    unittest.main()

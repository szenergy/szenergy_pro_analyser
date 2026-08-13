"""
Script to generate sample telemetry log files (CSV, XLSX, TDMS) for testing the SZenergy Pro Analyser.
"""

import os
import numpy as np
import pandas as pd
from nptdms import TdmsWriter, ChannelObject


def generate_sample_data():
    os.makedirs("sample_data", exist_ok=True)

    # 3 Laps of data, 100 points per lap
    n_points = 300
    t = np.linspace(0, 180, n_points)
    distance = np.linspace(0, 3000, n_points)
    laps = np.repeat([1, 2, 3], 100)

    # Simulated telemetries
    speed = 30 + 15 * np.sin(t / 10) + np.random.normal(0, 0.5, n_points)
    rpm = speed * 120 + np.random.normal(0, 10, n_points)
    voltage = 48 - 0.05 * t + np.random.normal(0, 0.1, n_points)
    current = 10 + 8 * np.sin(t / 5) ** 2 + np.random.normal(0, 0.3, n_points)

    # 1. Save CSV
    df_csv = pd.DataFrame({
        "t_sec": t,
        "dist_m": distance,
        "Lap_No": laps,
        "Speed_kmh": speed,
        "Motor_RPM": rpm,
        "Battery_V": voltage,
        "Current_A": current
    })
    csv_path = os.path.join("sample_data", "sample_motec.csv")
    df_csv.to_csv(csv_path, index=False)
    print(f"Generated {csv_path}")

    # 2. Save XLSX
    df_xlsx = pd.DataFrame({
        "Time_s": t,
        "Distance_m": distance,
        "lap_num": laps,
        "GPS_Speed": speed,
        "Engine_RPM": rpm,
        "Voltage": voltage
    })
    xlsx_path = os.path.join("sample_data", "sample_ecu.xlsx")
    df_xlsx.to_excel(xlsx_path, index=False)
    print(f"Generated {xlsx_path}")

    # 3. Save TDMS
    tdms_path = os.path.join("sample_data", "sample_ni.tdms")
    with TdmsWriter(tdms_path) as tdms_writer:
        ch_time = ChannelObject("Telemetry", "Time", t)
        ch_dist = ChannelObject("Telemetry", "Distance", distance)
        ch_lap = ChannelObject("Telemetry", "LapNumber", laps)
        ch_speed = ChannelObject("Telemetry", "VehicleSpeed", speed)
        ch_rpm = ChannelObject("Telemetry", "RPM", rpm)
        tdms_writer.write_segment([ch_time, ch_dist, ch_lap, ch_speed, ch_rpm])
    print(f"Generated {tdms_path}")


if __name__ == "__main__":
    generate_sample_data()

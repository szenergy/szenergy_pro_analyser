"""
Helper script to generate synthetic multi-lap telemetry log files for testing SZenergy Pro Analyser.
Generates:
1. sample_data/sample_motec.csv (CSV format)
2. sample_data/sample_ecu.xlsx (Excel format)
3. sample_data/sample_ni.tdms (National Instruments TDMS format)
"""

import os
import numpy as np
import pandas as pd
from nptdms import TdmsWriter, ChannelObject, GroupObject


def generate_lap_data(num_samples: int = 500, lap_number: int = 1, start_time: float = 0.0, start_dist: float = 0.0):
    dt = 0.05  # 20 Hz
    t = start_time + np.arange(num_samples) * dt
    dist_step = 2.5 + 0.5 * np.sin(np.linspace(0, 4 * np.pi, num_samples))
    dist = start_dist + np.cumsum(dist_step)
    
    speed = 30.0 + 15.0 * np.sin(np.linspace(0, 6 * np.pi, num_samples)) + np.random.normal(0, 0.5, num_samples)
    speed = np.clip(speed, 0, 60)
    
    rpm = speed * 120 + np.random.normal(0, 20, num_samples)
    throttle = np.clip((speed / 50.0) * 100 + np.random.normal(0, 2, num_samples), 0, 100)
    voltage = 48.0 - (throttle / 100.0) * 3.5 + np.random.normal(0, 0.1, num_samples)
    current = (throttle / 100.0) * 25.0 + np.random.normal(0, 0.5, num_samples)
    laps = np.full(num_samples, lap_number)

    return {
        "Lap": laps,
        "Time": t,
        "Distance": dist,
        "Speed": speed,
        "RPM": rpm,
        "Throttle": throttle,
        "Voltage": voltage,
        "Current": current
    }


def create_samples():
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_data")
    os.makedirs(output_dir, exist_ok=True)

    print(f"Generating test telemetry data in '{output_dir}'...")

    # 1. MoTeC Style CSV (3 Laps)
    lap1 = generate_lap_data(600, lap_number=1, start_time=0.0, start_dist=0.0)
    lap2 = generate_lap_data(580, lap_number=2, start_time=lap1["Time"][-1] + 0.05, start_dist=lap1["Distance"][-1] + 2.5)
    lap3 = generate_lap_data(590, lap_number=3, start_time=lap2["Time"][-1] + 0.05, start_dist=lap2["Distance"][-1] + 2.5)

    csv_data = {k: np.concatenate([lap1[k], lap2[k], lap3[k]]) for k in lap1}
    df_csv = pd.DataFrame(csv_data)
    csv_path = os.path.join(output_dir, "sample_motec.csv")
    df_csv.to_csv(csv_path, index=False)
    print(f" -> Created {csv_path} ({len(df_csv)} samples, 3 laps)")

    # 2. ECU Style Excel XLSX (2 Laps, custom column names)
    lap1_ecu = generate_lap_data(500, lap_number=1, start_time=0.0, start_dist=0.0)
    lap2_ecu = generate_lap_data(510, lap_number=2, start_time=lap1_ecu["Time"][-1] + 0.05, start_dist=lap1_ecu["Distance"][-1] + 2.5)
    
    excel_data = {
        "Lap_Index": np.concatenate([lap1_ecu["Lap"], lap2_ecu["Lap"]]),
        "Timestamp_s": np.concatenate([lap1_ecu["Time"], lap2_ecu["Time"]]),
        "Distance_m": np.concatenate([lap1_ecu["Distance"], lap2_ecu["Distance"]]),
        "Speed_kmh": np.concatenate([lap1_ecu["Speed"], lap2_ecu["Speed"]]),
        "Motor_RPM": np.concatenate([lap1_ecu["RPM"], lap2_ecu["RPM"]]),
        "Batt_Voltage": np.concatenate([lap1_ecu["Voltage"], lap2_ecu["Voltage"]]),
        "Batt_Current": np.concatenate([lap1_ecu["Current"], lap2_ecu["Current"]])
    }
    df_excel = pd.DataFrame(excel_data)
    xlsx_path = os.path.join(output_dir, "sample_ecu.xlsx")
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df_excel.to_excel(writer, sheet_name="Telemetry", index=False)
    print(f" -> Created {xlsx_path} ({len(df_excel)} samples, 2 laps)")

    # 3. National Instruments TDMS (2 Laps)
    tdms_path = os.path.join(output_dir, "sample_ni.tdms")
    with TdmsWriter(tdms_path) as tdms_writer:
        group_veh = GroupObject("Vehicle")
        group_pwr = GroupObject("Powertrain")

        chan_lap = ChannelObject("Vehicle", "Lap", excel_data["Lap_Index"])
        chan_time = ChannelObject("Vehicle", "Time", excel_data["Timestamp_s"])
        chan_dist = ChannelObject("Vehicle", "Distance", excel_data["Distance_m"])
        chan_spd = ChannelObject("Vehicle", "Speed", excel_data["Speed_kmh"])

        chan_rpm = ChannelObject("Powertrain", "RPM", excel_data["Motor_RPM"])
        chan_volt = ChannelObject("Powertrain", "Voltage", excel_data["Batt_Voltage"])
        chan_curr = ChannelObject("Powertrain", "Current", excel_data["Batt_Current"])

        tdms_writer.write_segment([group_veh, group_pwr, chan_lap, chan_time, chan_dist, chan_spd, chan_rpm, chan_volt, chan_curr])

    print(f" -> Created {tdms_path}")
    print("\nSample generation complete!")


if __name__ == "__main__":
    create_samples()

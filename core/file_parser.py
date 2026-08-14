"""
Robust parser for CSV, XLSX, and TDMS telemetry files.
Handles multi-rate TDMS channels, non-UTF8 encodings, custom delimiters,
metadata header preambles, and non-numeric value coercion.
"""

import os
from typing import Dict, List, Tuple, Optional
import numpy as np
import pandas as pd
from nptdms import TdmsFile

from core.data_models import Session, Lap
from utils.constants import STD_CHANNEL_LAP, STD_CHANNEL_TIME, STD_CHANNEL_DISTANCE


def _read_csv_with_fallback(file_path: str, nrows: Optional[int] = None) -> pd.DataFrame:
    """Reads a CSV file trying common encodings and sniffing delimiters."""
    encodings = ["utf-8", "latin-1", "cp1252", "iso-8859-1"]
    
    for encoding in encodings:
        try:
            # Try python engine with separator auto-detection
            return pd.read_csv(file_path, sep=None, engine="python", encoding=encoding, nrows=nrows)
        except Exception:
            pass

    # Fallback to standard comma and C engine
    for encoding in encodings:
        try:
            return pd.read_csv(file_path, encoding=encoding, nrows=nrows)
        except Exception:
            pass

    raise ValueError(f"Unable to read CSV file '{file_path}' with supported encodings.")


def get_file_columns_and_preview(file_path: str) -> Tuple[List[str], pd.DataFrame]:
    """
    Inspects a telemetry file and returns its raw column headers and a preview DataFrame (first 5 rows).
    Supports CSV, XLSX, and TDMS. Safely handles multi-rate channels of varying length.
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".csv":
        df_preview = _read_csv_with_fallback(file_path, nrows=5)
        return list(df_preview.columns), df_preview

    elif ext in [".xlsx", ".xls"]:
        excel_file = pd.ExcelFile(file_path)
        # Select best sheet: 'Data', 'Telemetry', or first sheet
        target_sheet = excel_file.sheet_names[0]
        for s in excel_file.sheet_names:
            if s.lower() in ["data", "telemetry", "log", "channels"]:
                target_sheet = s
                break

        df_preview = pd.read_excel(file_path, sheet_name=target_sheet, nrows=5)
        return [str(c) for c in df_preview.columns], df_preview

    elif ext == ".tdms":
        tdms = TdmsFile.read(file_path)
        all_channels = []
        data_dict = {}
        max_rows = 5

        for group in tdms.groups():
            for channel in group.channels():
                chan_name = f"{group.name}/{channel.name}"
                all_channels.append(chan_name)
                slice_data = channel[:max_rows]
                data_dict[chan_name] = list(slice_data)

        # Pad unequal preview lengths with None to allow DataFrame creation
        for chan_name, vals in data_dict.items():
            if len(vals) < max_rows:
                vals.extend([None] * (max_rows - len(vals)))

        df_preview = pd.DataFrame(data_dict)
        return all_channels, df_preview

    else:
        raise ValueError(f"Unsupported file format: {ext}")


def load_full_dataframe(file_path: str) -> pd.DataFrame:
    """Reads the full dataset from a file into a pandas DataFrame, aligning unequal channel lengths."""
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".csv":
        return _read_csv_with_fallback(file_path)

    elif ext in [".xlsx", ".xls"]:
        excel_file = pd.ExcelFile(file_path)
        target_sheet = excel_file.sheet_names[0]
        for s in excel_file.sheet_names:
            if s.lower() in ["data", "telemetry", "log", "channels"]:
                target_sheet = s
                break
        return pd.read_excel(file_path, sheet_name=target_sheet)

    elif ext == ".tdms":
        tdms = TdmsFile.read(file_path)
        data_dict = {}
        max_len = 0

        for group in tdms.groups():
            for channel in group.channels():
                chan_name = f"{group.name}/{channel.name}"
                arr = channel[:]
                data_dict[chan_name] = arr
                if len(arr) > max_len:
                    max_len = len(arr)

        # Handle multi-rate TDMS channels: pad shorter arrays with NaN to max_len
        padded_dict = {}
        for chan_name, arr in data_dict.items():
            if len(arr) < max_len:
                if np.issubdtype(arr.dtype, np.number):
                    padded = np.full(max_len, np.nan, dtype=float)
                    padded[:len(arr)] = arr
                    padded_dict[chan_name] = padded
                else:
                    padded_obj = np.empty(max_len, dtype=object)
                    padded_obj[:len(arr)] = arr
                    padded_dict[chan_name] = padded_obj
            else:
                padded_dict[chan_name] = arr

        return pd.DataFrame(padded_dict)

    else:
        raise ValueError(f"Unsupported file format: {ext}")


def parse_session(file_path: str, mapping: Dict[str, str], session_id: str,
                  lap_label: str = STD_CHANNEL_LAP,
                  time_label: str = STD_CHANNEL_TIME,
                  dist_label: str = STD_CHANNEL_DISTANCE) -> Session:
    """
    Parses a log file using the provided column mapping dictionary (raw_col -> mapped_col).
    Splits data into Lap objects with numeric data coercion and safe lap time/distance calculations.
    """
    df = load_full_dataframe(file_path)

    # Filter only columns present in mapping and rename to target names
    valid_mapping = {raw: mapped for raw, mapped in mapping.items() if raw in df.columns}
    df = df[list(valid_mapping.keys())].rename(columns=valid_mapping)

    # Coerce all mapped columns to numeric (except if impossible, where errors become NaN)
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    session_name = os.path.basename(file_path)
    session = Session(
        id=session_id,
        name=session_name,
        file_path=file_path,
        channels=[str(col) for col in df.columns if col != lap_label],
        raw_df=None  # Do not retain full duplicate raw dataframe to save memory
    )

    if df.empty:
        return session

    # If no Lap column exists in mapped data, treat the entire log as Lap 1
    if lap_label not in df.columns:
        lap_df = df
        duration = 0.0
        distance = 0.0

        if time_label in lap_df.columns:
            valid_time = lap_df[time_label].dropna()
            if len(valid_time) >= 2:
                duration = float(valid_time.iloc[-1] - valid_time.iloc[0])
        if dist_label in lap_df.columns:
            valid_dist = lap_df[dist_label].dropna()
            if len(valid_dist) >= 2:
                distance = float(valid_dist.iloc[-1] - valid_dist.iloc[0])

        channel_data = {
            col: np.nan_to_num(lap_df[col].to_numpy(dtype=float, copy=True), nan=0.0)
            for col in lap_df.columns
        }
        single_lap = Lap(
            session_id=session_id,
            lap_number=1,
            duration=max(0.0, duration),
            distance=max(0.0, distance),
            data=channel_data
        )
        session.laps.append(single_lap)
        return session

    # Split by lap numbers
    lap_series = df[lap_label].dropna()
    unique_laps = lap_series.unique()

    # Sort laps numerically
    try:
        sorted_laps = sorted(unique_laps, key=lambda x: float(x))
    except Exception:
        sorted_laps = list(unique_laps)

    for lap_val in sorted_laps:
        try:
            lap_num = int(float(lap_val))
        except (ValueError, TypeError):
            continue

        lap_df = df[df[lap_label] == lap_val]
        if lap_df.empty:
            continue

        duration = 0.0
        distance = 0.0
        if time_label in lap_df.columns:
            valid_time = lap_df[time_label].dropna()
            if len(valid_time) >= 2:
                duration = float(valid_time.iloc[-1] - valid_time.iloc[0])
        if dist_label in lap_df.columns:
            valid_dist = lap_df[dist_label].dropna()
            if len(valid_dist) >= 2:
                distance = float(valid_dist.iloc[-1] - valid_dist.iloc[0])

        channel_data = {
            col: np.nan_to_num(lap_df[col].to_numpy(dtype=float, copy=True), nan=0.0)
            for col in lap_df.columns if col != lap_label
        }

        lap_obj = Lap(
            session_id=session_id,
            lap_number=lap_num,
            duration=max(0.0, duration),
            distance=max(0.0, distance),
            data=channel_data
        )
        session.laps.append(lap_obj)

    # Fallback if no valid laps were parsed despite having lap column
    if not session.laps:
        channel_data = {
            col: np.nan_to_num(df[col].to_numpy(dtype=float, copy=True), nan=0.0)
            for col in df.columns if col != lap_label
        }
        session.laps.append(Lap(
            session_id=session_id,
            lap_number=1,
            duration=0.0,
            distance=0.0,
            data=channel_data
        ))

    return session

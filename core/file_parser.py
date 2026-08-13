"""
Parser for CSV, XLSX, and TDMS telemetry files.
"""

import os
from typing import Dict, List, Tuple, Optional
import numpy as np
import pandas as pd
from nptdms import TdmsFile

from core.data_models import Session, Lap
from utils.constants import STD_CHANNEL_LAP, STD_CHANNEL_TIME, STD_CHANNEL_DISTANCE, LAP_COLORS


def get_file_columns_and_preview(file_path: str) -> Tuple[List[str], pd.DataFrame]:
    """
    Inspects a telemetry file and returns its raw column headers and a preview DataFrame (first 5 rows).
    Supports CSV, XLSX, and TDMS.
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".csv":
        df_preview = pd.read_csv(file_path, nrows=5)
        return list(df_preview.columns), df_preview

    elif ext in [".xlsx", ".xls"]:
        df_preview = pd.read_excel(file_path, nrows=5)
        return list(df_preview.columns), df_preview

    elif ext == ".tdms":
        tdms = TdmsFile.read(file_path)
        all_channels = []
        data_dict = {}
        for group in tdms.groups():
            for channel in group.channels():
                # Format: GroupName/ChannelName or just ChannelName if unique
                chan_name = f"{group.name}/{channel.name}"
                all_channels.append(chan_name)
                # Load first 5 values for preview
                data_dict[chan_name] = channel[:5]
        df_preview = pd.DataFrame(data_dict)
        return all_channels, df_preview

    else:
        raise ValueError(f"Unsupported file format: {ext}")


def load_full_dataframe(file_path: str) -> pd.DataFrame:
    """Reads the full dataset from a file into a pandas DataFrame."""
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".csv":
        return pd.read_csv(file_path)

    elif ext in [".xlsx", ".xls"]:
        return pd.read_excel(file_path)

    elif ext == ".tdms":
        tdms = TdmsFile.read(file_path)
        data_dict = {}
        for group in tdms.groups():
            for channel in group.channels():
                chan_name = f"{group.name}/{channel.name}"
                data_dict[chan_name] = channel[:]
        return pd.DataFrame(data_dict)

    else:
        raise ValueError(f"Unsupported file format: {ext}")


def parse_session(file_path: str, mapping: Dict[str, str], session_id: str) -> Session:
    """
    Parses a log file using the provided column mapping dictionary (raw_col -> mapped_col).
    Splits the data into Lap objects based on the mapped Lap channel.
    """
    df = load_full_dataframe(file_path)
    
    # Select only columns present in mapping, and rename them
    valid_mapping = {raw: mapped for raw, mapped in mapping.items() if raw in df.columns}
    df = df[list(valid_mapping.keys())].rename(columns=valid_mapping)
    
    session_name = os.path.basename(file_path)
    session = Session(
        id=session_id,
        name=session_name,
        file_path=file_path,
        channels=[col for col in df.columns if col != STD_CHANNEL_LAP],
        raw_df=df
    )

    if STD_CHANNEL_LAP not in df.columns:
        # Fallback: treat entire file as Lap 1 if Lap channel wasn't mapped
        lap_df = df
        lap_num = 1
        duration = 0.0
        distance = 0.0
        if STD_CHANNEL_TIME in lap_df.columns:
            duration = float(lap_df[STD_CHANNEL_TIME].iloc[-1] - lap_df[STD_CHANNEL_TIME].iloc[0])
        if STD_CHANNEL_DISTANCE in lap_df.columns:
            distance = float(lap_df[STD_CHANNEL_DISTANCE].iloc[-1] - lap_df[STD_CHANNEL_DISTANCE].iloc[0])
        
        channel_data = {col: lap_df[col].to_numpy() for col in lap_df.columns}
        single_lap = Lap(
            session_id=session_id,
            lap_number=lap_num,
            duration=duration,
            distance=distance,
            color=LAP_COLORS[0],
            is_visible=True,
            data=channel_data
        )
        session.laps.append(single_lap)
        return session

    # Group by Lap channel values while preserving order
    # Handle lap numbers (e.g. 0, 1, 2, 3...)
    unique_laps = df[STD_CHANNEL_LAP].dropna().unique()
    
    color_index = 0
    for lap_val in unique_laps:
        try:
            lap_num = int(lap_val)
        except (ValueError, TypeError):
            continue
            
        lap_df = df[df[STD_CHANNEL_LAP] == lap_val].copy()
        if lap_df.empty:
            continue

        duration = 0.0
        distance = 0.0
        if STD_CHANNEL_TIME in lap_df.columns:
            duration = float(lap_df[STD_CHANNEL_TIME].iloc[-1] - lap_df[STD_CHANNEL_TIME].iloc[0])
        if STD_CHANNEL_DISTANCE in lap_df.columns:
            distance = float(lap_df[STD_CHANNEL_DISTANCE].iloc[-1] - lap_df[STD_CHANNEL_DISTANCE].iloc[0])

        channel_data = {col: lap_df[col].to_numpy() for col in lap_df.columns}
        color = LAP_COLORS[color_index % len(LAP_COLORS)]
        color_index += 1

        lap_obj = Lap(
            session_id=session_id,
            lap_number=lap_num,
            duration=duration,
            distance=distance,
            color=color,
            is_visible=True,  # Default selected/visible
            data=channel_data
        )
        session.laps.append(lap_obj)

    return session

"""
Robust parser for CSV, XLSX, and TDMS telemetry files.
Handles multi-rate TDMS channels, non-UTF8 encodings, custom delimiters,
metadata header preambles, and non-numeric value coercion.
All internal keys use slugs (not display labels).
"""

import logging
import os
import warnings
from typing import Dict, List, Tuple, Optional
import numpy as np
import pandas as pd
from nptdms import TdmsFile

from core.data_models import Session, Lap
from core.state_manager import generate_slug
from utils.constants import (
    STD_CH_LAP_NUM, STD_CH_LAP_TIME, STD_CH_LAP_DIST,
    STD_CH_LAP_NUM_SLUG, STD_CH_LAP_TIME_SLUG, STD_CH_LAP_DIST_SLUG
)

logger = logging.getLogger(__name__)


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


def _resolve_channel_column(
    columns: List[str],
    configured_label: Optional[str],
    standard_label: str,
    target_slug: str,
    extra_slugs: Optional[List[str]] = None
) -> Optional[str]:
    """
    Resolves a column from available dataframe columns using:
    1. Exact match against configured custom label.
    2. Exact match against standard channel name (e.g. 'Lap', 'Time', 'Distance').
    3. Case-insensitive match against configured or standard channel name.
    4. Slug/fallback matching against target slug or aliases.
    """
    if not columns:
        return None

    # 1. Exact match with configured label
    if configured_label and configured_label in columns:
        return configured_label

    # 2. Exact match with standard label
    if standard_label in columns:
        return standard_label

    # 3. Case-insensitive match with configured label
    if configured_label:
        cfg_lower = configured_label.strip().lower()
        for col in columns:
            if col.strip().lower() == cfg_lower:
                return col

    # 4. Case-insensitive match with standard label
    std_lower = standard_label.strip().lower()
    for col in columns:
        if col.strip().lower() == std_lower:
            return col

    # 5. Slug-based matching
    target_slugs = {target_slug}
    if configured_label:
        target_slugs.add(generate_slug(configured_label))
    target_slugs.add(generate_slug(standard_label))
    if extra_slugs:
        target_slugs.update(extra_slugs)

    for col in columns:
        if generate_slug(col) in target_slugs:
            return col

    return None


def _read_excel_dataframe(file_path: str, nrows: Optional[int] = None) -> pd.DataFrame:
    """
    Reads an Excel workbook using its primary sheet.
    Prefers the memory-safe, high-performance 'calamine' Rust engine if available,
    with a graceful fallback to 'openpyxl'.
    """
    # 1. Try calamine engine (Rust-based, memory-safe, fast, immune to C XML parser segfaults)
    try:
        df = pd.read_excel(file_path, sheet_name=0, nrows=nrows, engine="calamine")
        df.columns = [str(c) for c in df.columns]
        return df
    except Exception as e:
        logger.debug("Calamine engine unavailable or failed for '%s' (%s), attempting openpyxl fallback", file_path, e)

    # 2. Fallback to openpyxl directly without nested ExcelFile context leaks
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")
        df = pd.read_excel(file_path, sheet_name=0, nrows=nrows, engine="openpyxl")
        df.columns = [str(c) for c in df.columns]
        return df


def _read_tdms_with_alignment(file_path: str, nrows: Optional[int] = None) -> Tuple[List[str], pd.DataFrame]:
    """Reads a TDMS file, returning all channel names and aligning channels with padding."""
    if nrows is not None:
        with TdmsFile.open(file_path) as tdms:
            all_channels = []
            data_dict = {}
            for group in tdms.groups():
                for channel in group.channels():
                    chan_name = f"{group.name}/{channel.name}"
                    all_channels.append(chan_name)
                    slice_data = list(channel[:nrows])
                    if len(slice_data) < nrows:
                        slice_data.extend([None] * (nrows - len(slice_data)))
                    data_dict[chan_name] = slice_data
            return all_channels, pd.DataFrame(data_dict)

    with TdmsFile.read(file_path) as tdms:
        all_channels = []
        data_dict = {}
        max_len = 0

        for group in tdms.groups():
            for channel in group.channels():
                chan_name = f"{group.name}/{channel.name}"
                all_channels.append(chan_name)
                arr = channel[:]
                data_dict[chan_name] = arr
                if len(arr) > max_len:
                    max_len = len(arr)

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

        return all_channels, pd.DataFrame(padded_dict)


def get_file_columns_and_preview(file_path: str) -> Tuple[List[str], pd.DataFrame]:
    """
    Inspects a telemetry file and returns its raw column headers and a preview DataFrame (first 5 rows).
    Supports CSV, XLSX, and TDMS. Safely handles multi-rate channels of varying length.
    """
    ext = os.path.splitext(file_path)[1].lower()
    logger.debug("Inspecting header preview for '%s' (format: %s)", os.path.basename(file_path), ext)

    if ext == ".csv":
        df_preview = _read_csv_with_fallback(file_path, nrows=5)
        return list(df_preview.columns), df_preview
    elif ext in [".xlsx", ".xls"]:
        df_preview = _read_excel_dataframe(file_path, nrows=5)
        return list(df_preview.columns), df_preview
    elif ext == ".tdms":
        return _read_tdms_with_alignment(file_path, nrows=5)
    else:
        raise ValueError(f"Unsupported file format: {ext}")


def load_full_dataframe(file_path: str) -> pd.DataFrame:
    """Reads the full dataset from a file into a pandas DataFrame, aligning unequal channel lengths."""
    ext = os.path.splitext(file_path)[1].lower()
    logger.debug("Loading full dataset from disk: '%s'", file_path)

    if ext == ".csv":
        return _read_csv_with_fallback(file_path)
    elif ext in [".xlsx", ".xls"]:
        return _read_excel_dataframe(file_path)
    elif ext == ".tdms":
        _, df = _read_tdms_with_alignment(file_path)
        return df
    else:
        raise ValueError(f"Unsupported file format: {ext}")


def parse_session_from_dataframe(raw_df: pd.DataFrame, file_path: str, mapping: Dict[str, str], session_id: str,
                                lap_label: str = STD_CH_LAP_NUM,
                                time_label: str = STD_CH_LAP_TIME,
                                dist_label: str = STD_CH_LAP_DIST,
                                lap_slug: str = STD_CH_LAP_NUM_SLUG,
                                time_slug: str = STD_CH_LAP_TIME_SLUG,
                                dist_slug: str = STD_CH_LAP_DIST_SLUG,
                                preset_slug: Optional[str] = None,
                                preset_name: Optional[str] = None) -> Session:
    """
    Parses a Session in memory from an existing raw DataFrame and mapping dictionary.
    Mapping values are slugs (e.g. {"Speed_kmh": "speed"}).
    DataFrame columns are renamed to slugs. All internal keys use slugs.
    """
    logger.debug("Parsing session '%s' with %d mapped channels (raw rows: %d)",
                 os.path.basename(file_path), len(mapping), len(raw_df))
    # Filter only columns present in mapping and rename to slug keys
    valid_mapping = {raw: slug for raw, slug in mapping.items() if raw in raw_df.columns}
    df = raw_df[list(valid_mapping.keys())].rename(columns=valid_mapping)

    # Coerce all mapped columns to numeric (non-numeric values become NaN)
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Resolve actual lap, time, and distance columns using configured labels or slug fallbacks.
    # After renaming, columns are slugs, so we resolve against slug names.
    resolved_lap = _resolve_channel_column(list(df.columns), lap_slug, lap_label, lap_slug)
    resolved_time = _resolve_channel_column(list(df.columns), time_slug, time_label, time_slug)
    resolved_dist = _resolve_channel_column(list(df.columns), dist_slug, dist_label, dist_slug)

    session_name = os.path.basename(file_path)
    session = Session(
        id=session_id,
        name=session_name,
        file_path=file_path,
        channels=[str(col) for col in df.columns if col != resolved_lap],
        mapping=valid_mapping,
        preset_slug=preset_slug,
        preset_name=preset_name,
        raw_df=raw_df
    )

    if df.empty:
        return session

    # If no Lap column exists in mapped data, treat the entire log as Lap 1
    if resolved_lap is None or resolved_lap not in df.columns:
        lap_df = df
        duration = 0.0
        distance = 0.0

        if resolved_time and resolved_time in lap_df.columns:
            valid_time = lap_df[resolved_time].dropna()
            if len(valid_time) >= 2:
                duration = float(valid_time.iloc[-1] - valid_time.iloc[0])
        if resolved_dist and resolved_dist in lap_df.columns:
            valid_dist = lap_df[resolved_dist].dropna()
            if len(valid_dist) >= 2:
                distance = float(valid_dist.iloc[-1] - valid_dist.iloc[0])

        channel_data = {
            col: lap_df[col].to_numpy(dtype=float, copy=True)
            for col in lap_df.columns
        }
        single_lap = Lap(
            session_id=session_id,
            lap_number=1,
            duration=max(0.0, duration),
            distance=max(0.0, distance),
            data=channel_data,
        )
        session.laps.append(single_lap)
        return session

    # Split by lap numbers
    lap_series = df[resolved_lap].dropna()
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

        lap_df = df[df[resolved_lap] == lap_val]
        if lap_df.empty:
            continue

        duration = 0.0
        distance = 0.0
        if resolved_time and resolved_time in lap_df.columns:
            valid_time = lap_df[resolved_time].dropna()
            if len(valid_time) >= 2:
                duration = float(valid_time.iloc[-1] - valid_time.iloc[0])
        if resolved_dist and resolved_dist in lap_df.columns:
            valid_dist = lap_df[resolved_dist].dropna()
            if len(valid_dist) >= 2:
                distance = float(valid_dist.iloc[-1] - valid_dist.iloc[0])

        channel_data = {
            col: lap_df[col].to_numpy(dtype=float, copy=True)
            for col in lap_df.columns if col != resolved_lap
        }

        lap_obj = Lap(
            session_id=session_id,
            lap_number=lap_num,
            duration=max(0.0, duration),
            distance=max(0.0, distance),
            data=channel_data,
        )
        session.laps.append(lap_obj)

    # Fallback if no valid laps were parsed despite having lap column
    if not session.laps:
        channel_data = {
            col: df[col].to_numpy(dtype=float, copy=True)
            for col in df.columns if col != resolved_lap
        }
        session.laps.append(Lap(
            session_id=session_id,
            lap_number=1,
            duration=0.0,
            distance=0.0,
            data=channel_data,
        ))

    return session


def parse_session(file_path: str, mapping: Dict[str, str], session_id: str,
                  lap_label: str = STD_CH_LAP_NUM,
                  time_label: str = STD_CH_LAP_TIME,
                  dist_label: str = STD_CH_LAP_DIST,
                  lap_slug: str = STD_CH_LAP_NUM_SLUG,
                  time_slug: str = STD_CH_LAP_TIME_SLUG,
                  dist_slug: str = STD_CH_LAP_DIST_SLUG,
                  preset_slug: Optional[str] = None,
                  preset_name: Optional[str] = None) -> Session:
    """
    Parses a log file from disk into a Session object and retains raw_df in memory.
    Mapping values should be slugs.
    """
    raw_df = load_full_dataframe(file_path)
    return parse_session_from_dataframe(
        raw_df=raw_df,
        file_path=file_path,
        mapping=mapping,
        session_id=session_id,
        lap_label=lap_label,
        time_label=time_label,
        dist_label=dist_label,
        lap_slug=lap_slug,
        time_slug=time_slug,
        dist_slug=dist_slug,
        preset_slug=preset_slug,
        preset_name=preset_name
    )

"""
Parser module for track map files (.xlsx, .xls, and .csv files).
Supports extracting coordinate columns and numeric arrays for track layout rendering.
"""

import os
import logging
from typing import List, Tuple, Optional
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _is_numeric_value(val) -> bool:
    """Checks if a cell value represents a numeric number."""
    if val is None or pd.isna(val):
        return True
    if isinstance(val, (int, float, np.number)):
        return True
    s = str(val).strip()
    if not s:
        return True
    try:
        float(s)
        return True
    except ValueError:
        return False


def _has_header_row(first_row_values: list) -> bool:
    """
    Checks if the first row contains non-numeric text column names.
    If all non-empty values in the first row are numeric, returns False (indicating headerless data).
    If any non-empty value is non-numeric text, returns True (indicating text headers).
    """
    non_empty = [
        v for v in first_row_values
        if v is not None and not (isinstance(v, float) and np.isnan(v)) and str(v).strip() != ""
    ]
    if not non_empty:
        return False
    all_numeric = all(_is_numeric_value(v) for v in non_empty)
    return not all_numeric


def _read_csv_dataframe(file_path: str, nrows: Optional[int] = None) -> pd.DataFrame:
    """Reads a CSV file into DataFrame detecting whether the first row is text headers or numeric data."""
    delimiters = [",", ";", "\t"]
    for delim in delimiters:
        try:
            # Read first row without assuming header to inspect data types
            sample_df = pd.read_csv(file_path, sep=delim, nrows=1, header=None, engine="c", low_memory=False)
            if len(sample_df.columns) > 1:
                first_row = sample_df.iloc[0].tolist()
                has_header = _has_header_row(first_row)
                if has_header:
                    return pd.read_csv(file_path, sep=delim, nrows=nrows, header=0, engine="c", low_memory=False)
                else:
                    df = pd.read_csv(file_path, sep=delim, nrows=nrows, header=None, engine="c", low_memory=False)
                    df.columns = [f"Column {i + 1}" for i in range(len(df.columns))]
                    return df
        except Exception:
            continue

    # Fallback with default sniffer / engine
    try:
        sample_df = pd.read_csv(file_path, nrows=1, header=None)
        first_row = sample_df.iloc[0].tolist() if len(sample_df) > 0 else []
        has_header = _has_header_row(first_row)
        if has_header:
            return pd.read_csv(file_path, nrows=nrows, header=0)
        else:
            df = pd.read_csv(file_path, nrows=nrows, header=None)
            df.columns = [f"Column {i + 1}" for i in range(len(df.columns))]
            return df
    except Exception:
        return pd.read_csv(file_path, nrows=nrows)


def _read_excel_dataframe(file_path: str, nrows: Optional[int] = None) -> pd.DataFrame:
    """Reads an Excel (.xlsx / .xls) file into DataFrame detecting whether the first row is text headers or numeric data."""
    try:
        sample_df = pd.read_excel(file_path, nrows=1, header=None, engine="calamine")
    except Exception:
        try:
            sample_df = pd.read_excel(file_path, nrows=1, header=None)
        except Exception:
            sample_df = pd.DataFrame()

    first_row = sample_df.iloc[0].tolist() if len(sample_df) > 0 else []
    has_header = _has_header_row(first_row)

    try:
        if has_header:
            return pd.read_excel(file_path, nrows=nrows, header=0, engine="calamine")
        else:
            df = pd.read_excel(file_path, nrows=nrows, header=None, engine="calamine")
            df.columns = [f"Column {i + 1}" for i in range(len(df.columns))]
            return df
    except Exception:
        if has_header:
            return pd.read_excel(file_path, nrows=nrows, header=0)
        else:
            df = pd.read_excel(file_path, nrows=nrows, header=None)
            df.columns = [f"Column {i + 1}" for i in range(len(df.columns))]
            return df


def get_map_file_columns(file_path: str) -> List[str]:
    """
    Returns available column names for a .csv, .xlsx, or .xls track map file.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Track map file not found: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".csv":
        df = _read_csv_dataframe(file_path, nrows=5)
        return [str(c) for c in df.columns]
    elif ext in (".xlsx", ".xls"):
        df = _read_excel_dataframe(file_path, nrows=5)
        return [str(c) for c in df.columns]
    else:
        raise ValueError(f"Unsupported track map file format: '{ext}'. Supported: .csv, .xlsx, .xls")


def load_map_file_data(
    file_path: str,
    x_col: str,
    y_col: str,
    dist_col: Optional[str] = None
) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]:
    """
    Extracts numeric coordinate arrays (X, Y) and optional Distance from a .csv or Excel file.
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".csv":
        df = _read_csv_dataframe(file_path)
    elif ext in (".xlsx", ".xls"):
        df = _read_excel_dataframe(file_path)
    else:
        raise ValueError(f"Unsupported map file format: '{ext}'. Supported: .csv, .xlsx, .xls")

    if x_col not in df.columns:
        raise KeyError(f"X Column '{x_col}' not found in file columns: {list(df.columns)}")
    if y_col not in df.columns:
        raise KeyError(f"Y Column '{y_col}' not found in file columns: {list(df.columns)}")

    x_arr = pd.to_numeric(df[x_col], errors="coerce").fillna(0.0).to_numpy(dtype=np.float64)
    y_arr = pd.to_numeric(df[y_col], errors="coerce").fillna(0.0).to_numpy(dtype=np.float64)
    dist_arr = (
        pd.to_numeric(df[dist_col], errors="coerce").fillna(0.0).to_numpy(dtype=np.float64)
        if dist_col and dist_col in df.columns else None
    )

    # Clean out any non-finite NaN/Inf values
    valid_mask = np.isfinite(x_arr) & np.isfinite(y_arr)
    if not np.all(valid_mask):
        x_arr = x_arr[valid_mask]
        y_arr = y_arr[valid_mask]
        if dist_arr is not None and len(dist_arr) == len(valid_mask):
            dist_arr = dist_arr[valid_mask]

    return x_arr, y_arr, dist_arr

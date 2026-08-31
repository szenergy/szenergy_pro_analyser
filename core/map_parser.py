"""
Parser module for track map files (.xlsx, .xls, and .csv files).
Supports extracting coordinate columns and numeric arrays for track layout rendering.
"""

import os
import math
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


def compute_start_line_coords(
    raw_x: Optional[np.ndarray],
    raw_y: Optional[np.ndarray],
    angle_deg: float = 0.0
) -> Tuple[List[float], List[float]]:
    """
    Computes rotated 2D line endpoints ([x1, x2], [y1, y2]) for a perpendicular start/finish line
    across the track at the starting point (index 0).
    """
    if raw_x is None or raw_y is None or len(raw_x) < 2 or len(raw_y) < 2:
        return [], []

    x0 = float(raw_x[0])
    y0 = float(raw_y[0])

    # Find forward direction vector from start
    dx, dy = 1.0, 0.0
    for i in range(1, min(len(raw_x), len(raw_y))):
        d_x = float(raw_x[i]) - x0
        d_y = float(raw_y[i]) - y0
        if (d_x * d_x + d_y * d_y) > 1e-8:
            dx, dy = d_x, d_y
            break

    length = math.sqrt(dx * dx + dy * dy)
    if length > 0:
        tx, ty = dx / length, dy / length
    else:
        tx, ty = 1.0, 0.0

    # Normal vector perpendicular to track direction
    nx, ny = -ty, tx

    # Sizing relative to track bounding box
    span_x = float(np.ptp(raw_x))
    span_y = float(np.ptp(raw_y))
    track_span = max(span_x, span_y)
    half_width = max(0.03 * track_span, 1.0)

    p1x = x0 - half_width * nx
    p1y = y0 - half_width * ny
    p2x = x0 + half_width * nx
    p2y = y0 + half_width * ny

    # Rotate around centroid
    cx = float(np.mean(raw_x))
    cy = float(np.mean(raw_y))
    rad = math.radians(angle_deg)
    cos_theta = math.cos(rad)
    sin_theta = math.sin(rad)

    def _rot(px: float, py: float) -> Tuple[float, float]:
        ox = px - cx
        oy = py - cy
        rx = (ox * cos_theta) - (oy * sin_theta) + cx
        ry = (ox * sin_theta) + (oy * cos_theta) + cy
        return rx, ry

    r1x, r1y = _rot(p1x, p1y)
    r2x, r2y = _rot(p2x, p2y)

    return [r1x, r2x], [r1y, r2y]

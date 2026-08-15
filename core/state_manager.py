"""
State and settings manager for persistent user preferences, import presets, and standard channels.
Supports custom labels for all channels including system-required channels (lap, time, distance).
Includes coverage-based best-fit preset matching.
JSON files use a versioned envelope: {"schema_version": N, "data": ...}.
"""

import json
import os
import re
from typing import Dict, List, Optional
from PySide6.QtCore import QStandardPaths, QSettings
from utils.constants import (
    APP_NAME, ORGANIZATION_NAME, STD_CHANNEL_LAP, STD_CHANNEL_TIME, STD_CHANNEL_DISTANCE,
    SLUG_LAP, SLUG_TIME, SLUG_DISTANCE, STANDARD_SLUGS, REQUIRED_SLUGS
)


DEFAULT_CHANNEL_DEFS = [
    {"label": STD_CHANNEL_LAP, "slug": SLUG_LAP},
    {"label": STD_CHANNEL_TIME, "slug": SLUG_TIME},
    {"label": STD_CHANNEL_DISTANCE, "slug": SLUG_DISTANCE},
    {"label": "Speed", "slug": "speed"},
    {"label": "RPM", "slug": "rpm"},
    {"label": "Current", "slug": "current"},
    {"label": "Voltage", "slug": "voltage"},
    {"label": "Power", "slug": "power"},
    {"label": "Energy", "slug": "energy"},
    {"label": "Throttle", "slug": "throttle"},
    {"label": "SteeringAngle", "slug": "steering_angle"},
    {"label": "Temperature", "slug": "temperature"},
    {"label": "GPS_Lat", "slug": "gps_lat"},
    {"label": "GPS_Lon", "slug": "gps_lon"},
]


def generate_slug(label: str) -> str:
    """Generates a clean non-visible slug identifier from a channel label."""
    slug = re.sub(r'[^a-zA-Z0-9_]+', '_', label.strip().lower()).strip('_')
    return slug if slug else "channel"


def _read_versioned_json(file_path: str):
    """
    Reads a JSON file and returns (schema_version, data).
    Handles both versioned envelope and legacy flat formats.
    """
    if not os.path.exists(file_path):
        return 0, None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return 0, None

    if isinstance(raw, dict) and "schema_version" in raw:
        return raw["schema_version"], raw.get("data")
    # Legacy (v0) format: raw data without envelope
    return 0, raw


def _write_versioned_json(file_path: str, version: int, data) -> None:
    """Writes data in the versioned envelope format."""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump({"schema_version": version, "data": data}, f, indent=4)
    except OSError:
        pass


class StateManager:
    """Manages persistent application state, settings, channel presets, and standard channel definitions."""

    def __init__(self, config_dir: Optional[str] = None):
        self.settings = QSettings(ORGANIZATION_NAME, APP_NAME)
        if config_dir:
            self.config_dir = config_dir
        else:
            self.config_dir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
        
        try:
            if not os.path.exists(self.config_dir):
                os.makedirs(self.config_dir, exist_ok=True)
        except OSError:
            pass

        self.presets_file = os.path.join(self.config_dir, "presets.json")
        self.channels_file = os.path.join(self.config_dir, "custom_channels.json")

    def load_presets(self) -> Dict[str, Dict[str, str]]:
        """Load saved presets from JSON file. Handles both versioned and legacy formats."""
        version, data = _read_versioned_json(self.presets_file)
        if data is None:
            return {}
        if isinstance(data, dict):
            return data
        return {}

    def save_preset(self, preset_name: str, mapping: Dict[str, str]) -> None:
        """Save or update a preset mapping (values should be slugs)."""
        presets = self.load_presets()
        presets[preset_name] = mapping
        _write_versioned_json(self.presets_file, 1, presets)

    def delete_preset(self, preset_name: str) -> None:
        """Delete a preset by name."""
        presets = self.load_presets()
        if preset_name in presets:
            del presets[preset_name]
            _write_versioned_json(self.presets_file, 1, presets)

    def get_preset_match_stats(self, preset_name: str, raw_columns: List[str]) -> Dict[str, Any]:
        """
        Computes detailed matching statistics for a preset against a list of file columns.
        """
        presets = self.load_presets()
        mapping = presets.get(preset_name, {})
        raw_set = set(raw_columns)
        preset_cols = list(mapping.keys())

        matched_channels = [c for c in preset_cols if c in raw_set]
        missing_channels = [c for c in preset_cols if c not in raw_set]
        unmapped_channels = [c for c in raw_columns if c not in mapping]

        matched_count = len(matched_channels)
        preset_total = len(preset_cols)
        match_ratio = (matched_count / preset_total) if preset_total > 0 else 0.0

        return {
            "matched_count": matched_count,
            "preset_total": preset_total,
            "missing_in_file_count": len(missing_channels),
            "unmapped_in_file_count": len(unmapped_channels),
            "match_ratio": match_ratio,
            "matched_channels": matched_channels,
            "missing_channels": missing_channels,
            "unmapped_channels": unmapped_channels,
        }

    def find_matching_preset(self, raw_columns: List[str]) -> Optional[str]:
        """
        Finds the best matching saved preset for raw columns based on highest overlap score.
        Works even if some channels in the preset are missing in the file.
        Threshold: At least 2 matched channels (or matched == total for small 1-2 channel presets),
        and at least 40% of the preset's channels must match.
        Ranked by (matched_count, match_ratio, preset_total).
        """
        presets = self.load_presets()
        raw_set = set(raw_columns)
        best_preset = None
        best_rank = (-1, -1.0, -1)

        for preset_name, mapping in presets.items():
            if not mapping:
                continue
            preset_cols = set(mapping.keys())
            matched = preset_cols.intersection(raw_set)
            matched_count = len(matched)
            preset_total = len(preset_cols)
            match_ratio = matched_count / preset_total if preset_total > 0 else 0.0

            # Threshold check: works for full matches or partial matches with >=40% overlap
            if preset_total <= 2:
                is_valid_match = (matched_count == preset_total)
            else:
                is_valid_match = (matched_count >= 2 and match_ratio >= 0.4)

            if is_valid_match:
                rank = (matched_count, match_ratio, preset_total)
                if rank > best_rank:
                    best_rank = rank
                    best_preset = preset_name

        return best_preset

    def get_channel_defs(self) -> List[Dict[str, str]]:
        """Returns the list of channel dicts [{'label': ..., 'slug': ...}]."""
        version, data = _read_versioned_json(self.channels_file)

        if data is None:
            self.save_channel_defs(DEFAULT_CHANNEL_DEFS)
            return [dict(d) for d in DEFAULT_CHANNEL_DEFS]

        if isinstance(data, list):
            converted = []
            migrated = False
            for item in data:
                if isinstance(item, dict) and "label" in item and "slug" in item:
                    converted.append(item)
                elif isinstance(item, str):
                    converted.append({"label": item, "slug": generate_slug(item)})
                    migrated = True
                elif isinstance(item, dict) and "label" in item:
                    converted.append({"label": item["label"], "slug": generate_slug(item["label"])})
                    migrated = True
                else:
                    migrated = True
            if converted:
                if migrated:
                    self.save_channel_defs(converted)
                return converted

        return [dict(d) for d in DEFAULT_CHANNEL_DEFS]

    def save_channel_defs(self, channels: List[Dict[str, str]]) -> None:
        """Persists the channel definitions list to JSON in versioned format."""
        _write_versioned_json(self.channels_file, 1, channels)

    def get_channel_labels(self) -> List[str]:
        """Returns just the display labels of all defined channels."""
        return [ch["label"] for ch in self.get_channel_defs()]

    def get_slug_by_label(self, label: str) -> Optional[str]:
        """Finds internal slug for a given display label."""
        for ch in self.get_channel_defs():
            if ch.get("label") == label:
                return ch.get("slug")
        return None

    def get_label_by_slug(self, slug: str, default: Optional[str] = None) -> str:
        """Finds display label for a specific system slug (e.g. 'lap', 'time', 'distance')."""
        for ch in self.get_channel_defs():
            if ch.get("slug") == slug:
                return ch["label"]
        if default is not None:
            return default
        if slug == SLUG_LAP:
            return STD_CHANNEL_LAP
        elif slug == SLUG_TIME:
            return STD_CHANNEL_TIME
        elif slug == SLUG_DISTANCE:
            return STD_CHANNEL_DISTANCE
        return slug

    def label_to_slug_mapping(self) -> Dict[str, str]:
        """Returns a {label: slug} dictionary for all defined channels. Used by migrations and import logic."""
        return {ch["label"]: ch["slug"] for ch in self.get_channel_defs()}

    def get_lap_label(self) -> str:
        return self.get_label_by_slug(SLUG_LAP, STD_CHANNEL_LAP)

    def get_time_label(self) -> str:
        return self.get_label_by_slug(SLUG_TIME, STD_CHANNEL_TIME)

    def get_distance_label(self) -> str:
        return self.get_label_by_slug(SLUG_DISTANCE, STD_CHANNEL_DISTANCE)

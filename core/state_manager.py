"""
State and settings manager for persistent user preferences, import presets, and standard channels.
Supports custom labels for all channels including system-required channels (lap, time, distance).
"""

import json
import os
import re
from typing import Dict, List, Optional
from PySide6.QtCore import QStandardPaths, QSettings
from utils.constants import APP_NAME, ORGANIZATION_NAME, STD_CHANNEL_LAP, STD_CHANNEL_TIME, STD_CHANNEL_DISTANCE


DEFAULT_CHANNEL_DEFS = [
    {"label": STD_CHANNEL_LAP, "slug": "lap"},
    {"label": STD_CHANNEL_TIME, "slug": "time"},
    {"label": STD_CHANNEL_DISTANCE, "slug": "distance"},
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


class StateManager:
    """Manages persistent application state, settings, channel presets, and standard channel definitions."""

    def __init__(self):
        self.settings = QSettings(ORGANIZATION_NAME, APP_NAME)
        self.config_dir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir, exist_ok=True)

        self.presets_file = os.path.join(self.config_dir, "presets.json")
        self.channels_file = os.path.join(self.config_dir, "custom_channels.json")

    def load_presets(self) -> Dict[str, Dict[str, str]]:
        """Load saved presets from JSON file."""
        if not os.path.exists(self.presets_file):
            return {}
        try:
            with open(self.presets_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_preset(self, preset_name: str, mapping: Dict[str, str]) -> None:
        """Save or update a preset mapping."""
        presets = self.load_presets()
        presets[preset_name] = mapping
        with open(self.presets_file, "w", encoding="utf-8") as f:
            json.dump(presets, f, indent=4)

    def delete_preset(self, preset_name: str) -> None:
        """Delete a preset by name."""
        presets = self.load_presets()
        if preset_name in presets:
            del presets[preset_name]
            with open(self.presets_file, "w", encoding="utf-8") as f:
                json.dump(presets, f, indent=4)

    def find_matching_preset(self, raw_columns: List[str]) -> Optional[str]:
        """Find if any saved preset matches the raw columns in a file."""
        presets = self.load_presets()
        raw_set = set(raw_columns)
        for preset_name, mapping in presets.items():
            mapping_keys = set(mapping.keys())
            if mapping_keys and mapping_keys.issubset(raw_set):
                return preset_name
        return None

    def get_channel_defs(self) -> List[Dict[str, str]]:
        """Returns the list of channel dicts [{'label': ..., 'slug': ...}]."""
        if not os.path.exists(self.channels_file):
            self.save_channel_defs(DEFAULT_CHANNEL_DEFS)
            return list(DEFAULT_CHANNEL_DEFS)
        try:
            with open(self.channels_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    converted = []
                    for item in data:
                        if isinstance(item, dict) and "label" in item and "slug" in item:
                            converted.append(item)
                        elif isinstance(item, str):
                            converted.append({"label": item, "slug": generate_slug(item)})
                    if converted:
                        self.save_channel_defs(converted)
                        return converted
                return list(DEFAULT_CHANNEL_DEFS)
        except Exception:
            return list(DEFAULT_CHANNEL_DEFS)

    def save_channel_defs(self, channels: List[Dict[str, str]]) -> None:
        """Persists the channel definitions list to JSON."""
        with open(self.channels_file, "w", encoding="utf-8") as f:
            json.dump(channels, f, indent=4)

    def get_channel_labels(self) -> List[str]:
        """Returns just the display labels of all defined channels."""
        return [ch["label"] for ch in self.get_channel_defs()]

    def get_label_by_slug(self, slug: str, default: str) -> str:
        """Finds display label for a specific system slug (e.g. 'lap', 'time', 'distance')."""
        for ch in self.get_channel_defs():
            if ch.get("slug") == slug:
                return ch["label"]
        return default

    def get_lap_label(self) -> str:
        return self.get_label_by_slug("lap", STD_CHANNEL_LAP)

    def get_time_label(self) -> str:
        return self.get_label_by_slug("time", STD_CHANNEL_TIME)

    def get_distance_label(self) -> str:
        return self.get_label_by_slug("distance", STD_CHANNEL_DISTANCE)

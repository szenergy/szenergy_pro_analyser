"""
State and settings manager for persistent user preferences, import presets, and standard channels.
Supports custom labels for all channels including system-required channels (lap, time, distance).
Includes coverage-based best-fit preset matching.
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
        os.makedirs(os.path.dirname(self.presets_file), exist_ok=True)
        presets = self.load_presets()
        presets[preset_name] = mapping
        with open(self.presets_file, "w", encoding="utf-8") as f:
            json.dump(presets, f, indent=4)

    def delete_preset(self, preset_name: str) -> None:
        """Delete a preset by name."""
        presets = self.load_presets()
        if preset_name in presets:
            del presets[preset_name]
            os.makedirs(os.path.dirname(self.presets_file), exist_ok=True)
            with open(self.presets_file, "w", encoding="utf-8") as f:
                json.dump(presets, f, indent=4)

    def find_matching_preset(self, raw_columns: List[str]) -> Optional[str]:
        """
        Finds the best matching saved preset for raw columns based on highest coverage score.
        Avoids false positives from minimal presets matching before comprehensive presets.
        """
        presets = self.load_presets()
        raw_set = set(raw_columns)
        best_preset = None
        best_score = 0

        for preset_name, mapping in presets.items():
            mapping_keys = set(mapping.keys())
            if mapping_keys and mapping_keys.issubset(raw_set):
                score = len(mapping_keys)
                if score > best_score:
                    best_score = score
                    best_preset = preset_name

        return best_preset

    def get_channel_defs(self) -> List[Dict[str, str]]:
        """Returns the list of channel dicts [{'label': ..., 'slug': ...}]."""
        if not os.path.exists(self.channels_file):
            self.save_channel_defs(DEFAULT_CHANNEL_DEFS)
            return [dict(d) for d in DEFAULT_CHANNEL_DEFS]
        try:
            with open(self.channels_file, "r", encoding="utf-8") as f:
                data = json.load(f)
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
                        if migrated or converted != data:
                            self.save_channel_defs(converted)
                        return converted
                return [dict(d) for d in DEFAULT_CHANNEL_DEFS]
        except Exception:
            return [dict(d) for d in DEFAULT_CHANNEL_DEFS]

    def save_channel_defs(self, channels: List[Dict[str, str]]) -> None:
        """Persists the channel definitions list to JSON."""
        os.makedirs(os.path.dirname(self.channels_file), exist_ok=True)
        with open(self.channels_file, "w", encoding="utf-8") as f:
            json.dump(channels, f, indent=4)

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

    def get_lap_label(self) -> str:
        return self.get_label_by_slug(SLUG_LAP, STD_CHANNEL_LAP)

    def get_time_label(self) -> str:
        return self.get_label_by_slug(SLUG_TIME, STD_CHANNEL_TIME)

    def get_distance_label(self) -> str:
        return self.get_label_by_slug(SLUG_DISTANCE, STD_CHANNEL_DISTANCE)

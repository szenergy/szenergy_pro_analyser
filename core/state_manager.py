"""
State and settings manager for persistent user preferences and import presets.
"""

import json
import os
from typing import Dict, List, Optional
from PySide6.QtCore import QStandardPaths, QSettings
from utils.constants import APP_NAME, ORGANIZATION_NAME


class StateManager:
    """Manages persistent application state, settings, and channel mapping presets."""

    def __init__(self):
        self.settings = QSettings(ORGANIZATION_NAME, APP_NAME)
        self.config_dir = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir, exist_ok=True)
        self.presets_file = os.path.join(self.config_dir, "presets.json")

    def load_presets(self) -> Dict[str, Dict[str, str]]:
        """Load saved presets from JSON file. Returns dict of preset_name -> mapping."""
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
            # Check if all raw keys in mapping exist in raw_columns
            mapping_keys = set(mapping.keys())
            if mapping_keys and mapping_keys.issubset(raw_set):
                return preset_name
        return None

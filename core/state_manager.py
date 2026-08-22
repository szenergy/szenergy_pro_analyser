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
    APP_NAME, ORGANIZATION_NAME, DEFAULT_CHANNEL_DEFS,
    STD_CH_LAP_NUM, STD_CH_LAP_TIME, STD_CH_LAP_DIST,
    STD_CH_LAP_NUM_SLUG, STD_CH_LAP_TIME_SLUG, STD_CH_LAP_DIST_SLUG
)


def generate_slug(label: str) -> str:
    """Generates a clean non-visible slug identifier from a channel label."""
    slug = re.sub(r'[^a-zA-Z0-9_]+', '_', label.strip().lower()).strip('_')
    return slug if slug else "channel"


def read_versioned_json(file_path: str):
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


def write_versioned_json(file_path: str, version: int, data) -> None:
    """Writes data in the versioned envelope format."""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump({"schema_version": version, "data": data}, f, indent=4)
    except OSError:
        pass


# Aliases for backward compatibility
_read_versioned_json = read_versioned_json
_write_versioned_json = write_versioned_json


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
        self.file_mappings_file = os.path.join(self.config_dir, "file_mappings.json")
        self.ui_state_file = os.path.join(self.config_dir, "ui_state.json")

    def load_ui_state(self) -> Dict[str, Any]:
        """Loads persistent UI state (window geometry, graph toggles, sidebar selections, workspace)."""
        version, data = read_versioned_json(self.ui_state_file)
        if isinstance(data, dict):
            return data
        return {}

    def save_ui_state(self, state: Dict[str, Any]) -> None:
        """Saves persistent UI state in versioned envelope format."""
        write_versioned_json(self.ui_state_file, 1, state)

    def load_presets(self) -> List[Dict[str, Any]]:
        """Load saved presets from JSON file. Handles versioned envelope and returns list of preset dicts."""
        version, data = read_versioned_json(self.presets_file)
        if data is None:
            return []

        if isinstance(data, list):
            presets: List[Dict[str, Any]] = []
            for item in data:
                if isinstance(item, dict) and "name" in item and "mapping" in item:
                    slug = item.get("slug") or generate_slug(item["name"])
                    presets.append({
                        "slug": slug,
                        "name": item["name"],
                        "mapping": item["mapping"]
                    })
            return presets

        if isinstance(data, dict):
            # Legacy v0/v1 dict format {"Preset Name": {"raw_col": "slug"}}
            migrated = []
            for name, mapping in data.items():
                if isinstance(mapping, dict):
                    migrated.append({
                        "slug": generate_slug(name),
                        "name": name,
                        "mapping": mapping
                    })
            return migrated

        return []

    def get_preset_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        """Returns preset dict with matching slug, or None."""
        for preset in self.load_presets():
            if preset.get("slug") == slug:
                return preset
        return None

    def get_preset_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Returns preset dict with matching display name, or None."""
        for preset in self.load_presets():
            if preset.get("name") == name:
                return preset
        return None

    def get_preset_name_by_slug(self, slug: str, fallback: Optional[str] = None) -> str:
        """Returns display name for a preset slug, or fallback/slug."""
        preset = self.get_preset_by_slug(slug)
        if preset and "name" in preset:
            return preset["name"]
        return fallback if fallback is not None else slug

    def get_preset_slug_by_name(self, name: str) -> Optional[str]:
        """Returns slug for a preset display name, or None."""
        preset = self.get_preset_by_name(name)
        if preset and "slug" in preset:
            return preset["slug"]
        return None

    def save_preset(self, preset_name: str, mapping: Dict[str, str], slug: Optional[str] = None) -> str:
        """
        Save or update a preset mapping. If slug is provided and exists, updates name and mapping.
        If slug is None, checks for matching name; if new, generates unique slug.
        Returns the preset slug.
        """
        presets = self.load_presets()
        existing_slugs = [p["slug"] for p in presets if "slug" in p]

        target_preset = None
        if slug:
            for p in presets:
                if p.get("slug") == slug:
                    target_preset = p
                    break

        if not target_preset:
            for p in presets:
                if p.get("name") == preset_name:
                    target_preset = p
                    break

        if target_preset:
            target_preset["name"] = preset_name
            target_preset["mapping"] = mapping
            saved_slug = target_preset["slug"]
        else:
            saved_slug = self.generate_unique_slug(slug or preset_name, existing_slugs)
            presets.append({
                "slug": saved_slug,
                "name": preset_name,
                "mapping": mapping
            })

        write_versioned_json(self.presets_file, 2, presets)
        return saved_slug

    def delete_preset(self, slug_or_name: str) -> None:
        """Delete a preset by slug (or name fallback)."""
        presets = self.load_presets()
        filtered = [p for p in presets if p.get("slug") != slug_or_name and p.get("name") != slug_or_name]
        if len(filtered) != len(presets):
            write_versioned_json(self.presets_file, 2, filtered)

    def load_file_presets(self) -> Dict[str, str]:
        """Load mapping of file paths to their remembered preset slugs."""
        version, data = read_versioned_json(self.file_mappings_file)
        if isinstance(data, dict):
            result = {}
            for path, val in data.items():
                preset_ident = None
                if isinstance(val, str):
                    preset_ident = val
                elif isinstance(val, dict) and "preset_slug" in val and val["preset_slug"]:
                    preset_ident = val["preset_slug"]
                elif isinstance(val, dict) and "preset_name" in val and val["preset_name"]:
                    preset_ident = val["preset_name"]

                if preset_ident:
                    # Resolve display name to slug if known, else check existing preset or generate slug
                    slug = self.get_preset_slug_by_name(preset_ident)
                    if not slug:
                        p = self.get_preset_by_slug(preset_ident)
                        slug = p["slug"] if p else generate_slug(preset_ident)
                    result[path] = slug
            return result
        return {}

    def get_file_preset(self, file_path: str) -> Optional[str]:
        """Returns remembered preset slug for a file path, or None."""
        presets = self.load_file_presets()
        return presets.get(file_path)

    def save_file_preset(self, file_path: str, preset_slug: str) -> None:
        """Remembers a preset slug for a specific file path."""
        presets = self.load_file_presets()
        presets[file_path] = preset_slug
        write_versioned_json(self.file_mappings_file, 2, presets)

    def remove_file_preset(self, file_path: str) -> None:
        """Removes remembered preset slug for a specific file path."""
        presets = self.load_file_presets()
        if file_path in presets:
            del presets[file_path]
            write_versioned_json(self.file_mappings_file, 2, presets)

    def get_preset_match_stats(self, slug_or_name: str, raw_columns: List[str]) -> Dict[str, Any]:
        """
        Computes detailed matching statistics for a preset (by slug or name) against raw file columns.
        """
        preset = self.get_preset_by_slug(slug_or_name) or self.get_preset_by_name(slug_or_name)
        mapping = preset.get("mapping", {}) if preset else {}
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
        Finds the best matching saved preset slug for raw columns based on highest overlap score.
        Ranked by (matched_count, match_ratio, preset_total).
        """
        presets = self.load_presets()
        raw_set = set(raw_columns)
        best_preset_slug = None
        best_rank = (-1, -1.0, -1)

        for preset in presets:
            mapping = preset.get("mapping", {})
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
                    best_preset_slug = preset.get("slug")

        return best_preset_slug

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

    def generate_unique_slug(self, label: str, existing_slugs: Optional[List[str]] = None) -> str:
        """Generates a unique slug identifier for a given label, appending _1, _2, etc. if already taken."""
        if existing_slugs is None:
            existing_slugs = [ch["slug"] for ch in self.get_channel_defs()]
        base_slug = generate_slug(label)
        slug = base_slug
        counter = 1
        while slug in existing_slugs:
            slug = f"{base_slug}_{counter}"
            counter += 1
        return slug

    def save_new_custom_channels(self, labels: List[str]) -> bool:
        """
        Adds any new custom channel labels to the saved channels definitions.
        Returns True if any new channel was added and persisted.
        """
        existing_defs = self.get_channel_defs()
        existing_labels = set(ch["label"] for ch in existing_defs)
        existing_slugs = [ch["slug"] for ch in existing_defs]

        updated = False
        for label in labels:
            label_clean = label.strip()
            if label_clean and label_clean != "-- Skip --" and label_clean not in existing_labels:
                slug = self.generate_unique_slug(label_clean, existing_slugs)
                existing_defs.append({"label": label_clean, "slug": slug})
                existing_labels.add(label_clean)
                existing_slugs.append(slug)
                updated = True

        if updated:
            self.save_channel_defs(existing_defs)
        return updated

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
        """Finds display label for a specific system slug (e.g. 'lap_num', 'lap_time', 'lap_dist')."""
        for ch in self.get_channel_defs():
            if ch.get("slug") == slug:
                return ch["label"]
        if default is not None:
            return default
        if slug == STD_CH_LAP_NUM_SLUG:
            return STD_CH_LAP_NUM
        elif slug == STD_CH_LAP_TIME_SLUG:
            return STD_CH_LAP_TIME
        elif slug == STD_CH_LAP_DIST_SLUG:
            return STD_CH_LAP_DIST
        return slug

    def label_to_slug_mapping(self) -> Dict[str, str]:
        """Returns a {label: slug} dictionary for all defined channels. Used by migrations and import logic."""
        return {ch["label"]: ch["slug"] for ch in self.get_channel_defs()}

    def get_lap_label(self) -> str:
        return self.get_label_by_slug(STD_CH_LAP_NUM_SLUG, STD_CH_LAP_NUM)

    def get_time_label(self) -> str:
        return self.get_label_by_slug(STD_CH_LAP_TIME_SLUG, STD_CH_LAP_TIME)

    def get_distance_label(self) -> str:
        return self.get_label_by_slug(STD_CH_LAP_DIST_SLUG, STD_CH_LAP_DIST)

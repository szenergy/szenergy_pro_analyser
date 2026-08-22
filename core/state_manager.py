"""
State and settings manager for persistent user preferences, import presets, and standard channels.
Supports custom labels for all channels including system-required channels (lap, time, distance).
Includes coverage-based best-fit preset matching.
JSON files use a versioned envelope: {"schema_version": N, "data": ...}.
"""

import json
import logging
import os
import re
from typing import Dict, List, Optional, Any, Tuple
from PySide6.QtCore import QStandardPaths, QSettings
from utils.constants import (
    APP_NAME, ORGANIZATION_NAME, DEFAULT_CHANNEL_DEFS,
    STD_CH_LAP_NUM, STD_CH_LAP_TIME, STD_CH_LAP_DIST,
    STD_CH_LAP_NUM_SLUG, STD_CH_LAP_TIME_SLUG, STD_CH_LAP_DIST_SLUG
)

logger = logging.getLogger(__name__)


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

    def clear_ui_state(self) -> None:
        """Deletes the persistent ui_state.json file if it exists."""
        if os.path.exists(self.ui_state_file):
            try:
                os.remove(self.ui_state_file)
                logger.info("Removed persistent UI state file '%s'", self.ui_state_file)
            except OSError as e:
                logger.warning("Failed to remove UI state file '%s': %s", self.ui_state_file, e)

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
            logger.info("Updated preset '%s' (slug: '%s') with %d channels", preset_name, saved_slug, len(mapping))
        else:
            saved_slug = self.generate_unique_slug(slug or preset_name, existing_slugs)
            presets.append({
                "slug": saved_slug,
                "name": preset_name,
                "mapping": mapping
            })
            logger.info("Created new preset '%s' (slug: '%s') with %d channels", preset_name, saved_slug, len(mapping))

        write_versioned_json(self.presets_file, 2, presets)
        return saved_slug

    def delete_preset(self, slug_or_name: str) -> None:
        """Delete a preset by slug (or name fallback)."""
        presets = self.load_presets()
        filtered = [p for p in presets if p.get("slug") != slug_or_name and p.get("name") != slug_or_name]
        if len(filtered) != len(presets):
            write_versioned_json(self.presets_file, 2, filtered)
            logger.info("Deleted preset '%s'", slug_or_name)

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
        logger.info("Saved file preset mapping: '%s' -> slug '%s'", os.path.basename(file_path), preset_slug)

    def remove_file_preset(self, file_path: str) -> None:
        """Removes remembered preset slug for a specific file path."""
        presets = self.load_file_presets()
        if file_path in presets:
            del presets[file_path]
            write_versioned_json(self.file_mappings_file, 2, presets)
            logger.info("Removed file preset mapping for '%s'", os.path.basename(file_path))

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

    def save_presets(self, presets: List[Dict[str, Any]]) -> None:
        """Persists the presets list to presets.json in version 2 envelope format."""
        write_versioned_json(self.presets_file, 2, presets)

    def export_config(self) -> Dict[str, Any]:
        """
        Exports non-machine-specific configuration (presets and standard channel definitions)
        into a versioned dictionary. Excludes machine-specific file mappings and UI state.
        """
        return {
            "schema_version": 1,
            "type": "szenergypro_config_export",
            "data": {
                "presets": self.load_presets(),
                "channels": self.get_channel_defs()
            }
        }

    def export_config_to_file(self, file_path: str) -> None:
        """Writes the exported configuration dictionary to a JSON file."""
        config_data = self.export_config()
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4)
        logger.info("Exported configuration to '%s' (%d presets, %d channels)",
                    file_path, len(config_data["data"]["presets"]), len(config_data["data"]["channels"]))

    def import_config_from_file(self, file_path: str) -> Tuple[int, int]:
        """
        Imports non-machine-specific configuration (presets and channels) from a JSON file.
        Validates structure and updates StateManager.
        Returns (num_presets_imported, num_channels_imported).
        Raises FileNotFoundError or ValueError on invalid file format or corrupted content.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Configuration file not found: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            raise ValueError(f"Could not parse JSON file: {str(e)}")

        if not isinstance(raw, dict):
            raise ValueError("Invalid configuration format: root must be a JSON object.")

        # Extract data from envelope or flat dict
        if "data" in raw and isinstance(raw["data"], dict):
            payload = raw["data"]
        else:
            payload = raw

        imported_presets = payload.get("presets")
        imported_channels = payload.get("channels") or payload.get("custom_channels")

        if imported_presets is None and imported_channels is None:
            raise ValueError("Invalid configuration file: neither 'presets' nor 'channels' found.")

        num_presets_imported = 0
        if imported_presets is not None:
            if not isinstance(imported_presets, (list, dict)):
                raise ValueError("'presets' in configuration must be a list or dict.")

            existing_presets = self.load_presets()
            existing_presets_by_slug = {p["slug"]: p for p in existing_presets if "slug" in p}
            existing_presets_by_name = {p["name"]: p for p in existing_presets if "name" in p}

            preset_items = []
            if isinstance(imported_presets, list):
                for p in imported_presets:
                    if isinstance(p, dict) and "name" in p and "mapping" in p and isinstance(p["mapping"], dict):
                        slug = p.get("slug") or generate_slug(p["name"])
                        preset_items.append({"slug": slug, "name": p["name"], "mapping": p["mapping"]})
            elif isinstance(imported_presets, dict):
                for name, mapping in imported_presets.items():
                    if isinstance(mapping, dict):
                        preset_items.append({"slug": generate_slug(name), "name": name, "mapping": mapping})

            for p in preset_items:
                slug = p["slug"]
                name = p["name"]
                mapping = p["mapping"]

                if slug in existing_presets_by_slug:
                    existing_presets_by_slug[slug]["name"] = name
                    existing_presets_by_slug[slug]["mapping"] = mapping
                elif name in existing_presets_by_name:
                    existing_presets_by_name[name]["mapping"] = mapping
                else:
                    existing_presets_by_slug[slug] = p
                num_presets_imported += 1

            self.save_presets(list(existing_presets_by_slug.values()))

        num_channels_imported = 0
        if imported_channels is not None:
            if not isinstance(imported_channels, list):
                raise ValueError("'channels' in configuration must be a list of channel definitions.")

            existing_channels = self.get_channel_defs()
            existing_channels_by_slug = {ch["slug"]: ch for ch in existing_channels if "slug" in ch}
            existing_slugs = list(existing_channels_by_slug.keys())

            for ch in imported_channels:
                if isinstance(ch, dict) and "label" in ch:
                    label = str(ch["label"]).strip()
                    slug = ch.get("slug")
                    if slug:
                        if slug in existing_channels_by_slug:
                            existing_channels_by_slug[slug]["label"] = label
                        else:
                            new_ch = {"label": label, "slug": slug}
                            existing_channels_by_slug[slug] = new_ch
                            existing_slugs.append(slug)
                        num_channels_imported += 1
                    else:
                        slug = self.generate_unique_slug(label, existing_slugs)
                        new_ch = {"label": label, "slug": slug}
                        existing_channels_by_slug[slug] = new_ch
                        existing_slugs.append(slug)
                        num_channels_imported += 1
                elif isinstance(ch, str):
                    label = ch.strip()
                    if label:
                        slug = self.generate_unique_slug(label, existing_slugs)
                        new_ch = {"label": label, "slug": slug}
                        existing_channels_by_slug[slug] = new_ch
                        existing_slugs.append(slug)
                        num_channels_imported += 1

            # System-required channels are identified exclusively by their slugs:
            # - STD_CH_LAP_NUM_SLUG ("lap_num")
            # - STD_CH_LAP_TIME_SLUG ("lap_time")
            # - STD_CH_LAP_DIST_SLUG ("lap_dist")
            # Since these can be renamed to any custom display label, check purely if the slug is present.
            # If the slug is already present, its current or imported custom label is untouched.
            # Only if the slug is completely missing from the channel definitions, add a fallback entry.
            for req_slug, req_default_label in [
                (STD_CH_LAP_NUM_SLUG, STD_CH_LAP_NUM),
                (STD_CH_LAP_TIME_SLUG, STD_CH_LAP_TIME),
                (STD_CH_LAP_DIST_SLUG, STD_CH_LAP_DIST)
            ]:
                if req_slug not in existing_channels_by_slug:
                    existing_channels_by_slug[req_slug] = {"label": req_default_label, "slug": req_slug}

            self.save_channel_defs(list(existing_channels_by_slug.values()))

        logger.info("Imported configuration from '%s' (%d presets, %d channels)",
                    file_path, num_presets_imported, num_channels_imported)
        return num_presets_imported, num_channels_imported

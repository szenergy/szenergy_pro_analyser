"""
Versioned migration system for persistent config files (presets.json, custom_channels.json).
Each JSON file uses a versioned envelope: {"schema_version": N, "data": ...}.
Migrations run sequentially on program startup to upgrade legacy formats.
"""

import json
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.state_manager import StateManager, generate_slug, read_versioned_json, write_versioned_json

logger = logging.getLogger(__name__)

# Current target versions
CURRENT_PRESETS_VERSION = 2
CURRENT_CHANNELS_VERSION = 1


# ---------------------------------------------------------------------------
# Preset Migrations
# ---------------------------------------------------------------------------

def _migrate_presets_v0_to_v1(data: Any, state_manager: StateManager) -> Dict[str, Dict[str, str]]:
    """
    v0 -> v1: Convert preset mapping values from display labels to slugs.
    Legacy format: {"preset_name": {"raw_col": "DisplayLabel", ...}, ...}
    Target format: {"preset_name": {"raw_col": "slug", ...}, ...}
    """
    if not isinstance(data, dict):
        return {}

    label_to_slug = state_manager.label_to_slug_mapping()
    migrated_presets: Dict[str, Dict[str, str]] = {}

    for preset_name, mapping in data.items():
        if not isinstance(mapping, dict):
            continue
        migrated_mapping: Dict[str, str] = {}
        for raw_col, target in mapping.items():
            if target in label_to_slug:
                # Known display label -> convert to slug
                migrated_mapping[raw_col] = label_to_slug[target]
            else:
                # Already a slug, or a custom value -> use generate_slug as fallback
                if generate_slug(target) == target:
                    migrated_mapping[raw_col] = target
                else:
                    migrated_mapping[raw_col] = generate_slug(target)
        migrated_presets[preset_name] = migrated_mapping

    return migrated_presets


def _migrate_presets_v1_to_v2(data: Any, state_manager: StateManager) -> List[Dict[str, Any]]:
    """
    v1 -> v2: Add unique slug to each preset and structure presets as a list of dicts.
    v1 format: {"preset_name": {"raw_col": "slug", ...}, ...}
    v2 format: [{"slug": "preset_slug", "name": "preset_name", "mapping": {"raw_col": "slug", ...}}, ...]
    """
    if isinstance(data, list):
        converted: List[Dict[str, Any]] = []
        existing_slugs: List[str] = []
        for item in data:
            if isinstance(item, dict) and "name" in item and "mapping" in item:
                slug = item.get("slug") or generate_slug(item["name"])
                base_slug = slug
                counter = 1
                while slug in existing_slugs:
                    slug = f"{base_slug}_{counter}"
                    counter += 1
                existing_slugs.append(slug)
                converted.append({
                    "slug": slug,
                    "name": item["name"],
                    "mapping": item["mapping"]
                })
        return converted

    if not isinstance(data, dict):
        return []

    migrated_presets: List[Dict[str, Any]] = []
    existing_slugs: List[str] = []

    for preset_name, mapping in data.items():
        if not isinstance(mapping, dict):
            continue
        slug = generate_slug(preset_name)
        base_slug = slug
        counter = 1
        while slug in existing_slugs:
            slug = f"{base_slug}_{counter}"
            counter += 1
        existing_slugs.append(slug)
        migrated_presets.append({
            "slug": slug,
            "name": preset_name,
            "mapping": mapping
        })

    return migrated_presets


PRESET_MIGRATIONS: List[Tuple[int, int, Callable]] = [
    (0, 1, _migrate_presets_v0_to_v1),
    (1, 2, _migrate_presets_v1_to_v2),
]


# ---------------------------------------------------------------------------
# Channel Definitions Migrations
# ---------------------------------------------------------------------------

def _migrate_channels_v0_to_v1(data: Any, state_manager: StateManager) -> List[Dict[str, str]]:
    """
    v0 -> v1: Wrap legacy channel defs list in versioned envelope.
    Content transformation is handled by StateManager.get_channel_defs() which already
    handles legacy string-only and missing-slug formats. This migration just ensures
    the versioned envelope is written.
    """
    if isinstance(data, list):
        converted = []
        for item in data:
            if isinstance(item, dict) and "label" in item and "slug" in item:
                converted.append(item)
            elif isinstance(item, str):
                converted.append({"label": item, "slug": generate_slug(item)})
            elif isinstance(item, dict) and "label" in item:
                converted.append({"label": item["label"], "slug": generate_slug(item["label"])})
        return converted if converted else []
    return []


CHANNEL_MIGRATIONS: List[Tuple[int, int, Callable]] = [
    (0, 1, _migrate_channels_v0_to_v1),
]


# ---------------------------------------------------------------------------
# File Mappings Migrations
# ---------------------------------------------------------------------------

CURRENT_FILE_MAPPINGS_VERSION = 2


def _migrate_file_mappings_to_slugs(data: Any, state_manager: StateManager) -> Dict[str, str]:
    """
    Converts remembered file presets from legacy display names or nested dicts to persistent preset slugs.
    """
    if not isinstance(data, dict):
        return {}

    migrated: Dict[str, str] = {}
    for file_path, entry in data.items():
        preset_ident = None
        if isinstance(entry, dict):
            preset_ident = entry.get("preset_slug") or entry.get("preset_name")
        elif isinstance(entry, str):
            preset_ident = entry

        if preset_ident:
            slug = state_manager.get_preset_slug_by_name(preset_ident)
            if not slug:
                p = state_manager.get_preset_by_slug(preset_ident)
                slug = p["slug"] if p else generate_slug(preset_ident)
            migrated[file_path] = slug

    return migrated


FILE_MAPPINGS_MIGRATIONS: List[Tuple[int, int, Callable]] = [
    (0, 1, _migrate_file_mappings_to_slugs),
    (1, 2, _migrate_file_mappings_to_slugs),
]


# ---------------------------------------------------------------------------
# Migration Runner
# ---------------------------------------------------------------------------

def _apply_migrations(
    file_path: str,
    current_version: int,
    target_version: int,
    migrations: List[Tuple[int, int, Callable]],
    state_manager: StateManager,
    file_label: str
) -> bool:
    """
    Reads a config file, applies sequential migrations, and writes back.
    Returns True if any migration was applied.
    """
    version, data = read_versioned_json(file_path)

    if data is None and version == 0:
        # File doesn't exist yet — nothing to migrate
        return False

    if version >= target_version:
        return False

    original_version = version
    for from_v, to_v, migrate_fn in migrations:
        if version == from_v:
            logger.info(f"Migrating {file_label} from v{from_v} to v{to_v}...")
            data = migrate_fn(data, state_manager)
            version = to_v

    if version != original_version:
        write_versioned_json(file_path, version, data)
        logger.info(f"Successfully migrated {file_label} to v{version}.")
        return True

    return False


def run_migrations(state_manager: StateManager) -> None:
    """
    Runs all pending migrations for config files. Call once on application startup.
    Checks schema versions and applies upgrades sequentially.
    """
    # Migrate channel definitions first (presets migration may depend on channel defs)
    _apply_migrations(
        file_path=state_manager.channels_file,
        current_version=0,
        target_version=CURRENT_CHANNELS_VERSION,
        migrations=CHANNEL_MIGRATIONS,
        state_manager=state_manager,
        file_label="custom_channels.json"
    )

    # Migrate presets
    _apply_migrations(
        file_path=state_manager.presets_file,
        current_version=0,
        target_version=CURRENT_PRESETS_VERSION,
        migrations=PRESET_MIGRATIONS,
        state_manager=state_manager,
        file_label="presets.json"
    )

    # Migrate file mappings (after presets migration so preset slugs exist)
    _apply_migrations(
        file_path=state_manager.file_mappings_file,
        current_version=0,
        target_version=CURRENT_FILE_MAPPINGS_VERSION,
        migrations=FILE_MAPPINGS_MIGRATIONS,
        state_manager=state_manager,
        file_label="file_mappings.json"
    )

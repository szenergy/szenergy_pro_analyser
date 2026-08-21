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
CURRENT_PRESETS_VERSION = 1
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
                migrated_mapping[raw_col] = generate_slug(target) if target != target.lower().replace(' ', '_') else target
                # If it looks like it could already be a valid slug, keep it
                if generate_slug(target) == target:
                    migrated_mapping[raw_col] = target
                else:
                    migrated_mapping[raw_col] = generate_slug(target)
        migrated_presets[preset_name] = migrated_mapping

    return migrated_presets


PRESET_MIGRATIONS: List[Tuple[int, int, Callable]] = [
    (0, 1, _migrate_presets_v0_to_v1),
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

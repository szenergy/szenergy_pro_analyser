"""
JSON versioned envelope I/O utilities and slug generation helpers.
"""

import json
import os
import re
from typing import Any, Tuple


def generate_slug(label: str) -> str:
    """Generates a clean non-visible slug identifier from a channel label."""
    slug = re.sub(r'[^a-zA-Z0-9_]+', '_', label.strip().lower()).strip('_')
    return slug if slug else "channel"


def read_versioned_json(file_path: str) -> Tuple[int, Any]:
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


def write_versioned_json(file_path: str, version: int, data: Any) -> None:
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

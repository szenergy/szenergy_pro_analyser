"""
Data models representing telemetry sessions, laps, and channels.
All internal keys use immutable slugs (e.g. 'speed', 'rpm') rather than
user-renamable display labels.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import numpy as np
import pandas as pd


@dataclass
class Lap:
    """Represents a single lap within a session."""
    session_id: str
    lap_number: int
    duration: float = 0.0  # Total lap time in seconds
    distance: float = 0.0  # Total lap distance in meters/km
    
    # Storage for channel arrays specific to this lap, keyed by slug: {channel_slug: np.ndarray}
    data: Dict[str, np.ndarray] = field(default_factory=dict)

    def get_channel(
        self,
        slug: str,
        calculated_defs: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> Optional[np.ndarray]:
        """
        Retrieves channel data array by channel slug (e.g. 'time', 'distance', 'speed').
        If not directly present in data, evaluates calculated channel definition if provided.
        """
        if not slug:
            return None
        if slug in self.data:
            return self.data[slug]
        # Fallback: case-insensitive / normalized slug match
        target = slug.strip().lower()
        for key, arr in self.data.items():
            if key.strip().lower() == target or key.replace(' ', '_').lower() == target:
                return arr

        # If slug is a calculated channel, compute it on-the-fly and cache
        if calculated_defs and slug in calculated_defs:
            calc_def = calculated_defs[slug]
            if calc_def.get("type") == "calculated":
                from core.channel_calculator import calculate_lap_channel
                result = calculate_lap_channel(self, calc_def, calculated_defs)
                if result is not None:
                    self.data[slug] = result
                    return result

        return None

    def clear_calculated_cache(self, calculated_slugs: Optional[Set[str]] = None) -> None:
        """Purges cached calculated channel data from this lap."""
        if calculated_slugs is None:
            return
        for slug in calculated_slugs:
            self.data.pop(slug, None)


@dataclass
class Session:
    """Represents an imported telemetry log file/session."""
    id: str
    name: str
    file_path: str
    laps: List[Lap] = field(default_factory=list)
    channels: List[str] = field(default_factory=list)  # List of channel slugs (excluding lap)
    mapping: Dict[str, str] = field(default_factory=dict)  # {raw_column: slug}
    preset_slug: Optional[str] = None
    preset_name: Optional[str] = None
    
    # Reference to original parsed dataframe if needed
    raw_df: Optional[pd.DataFrame] = field(default=None, repr=False)

    def get_lap(self, lap_number: int) -> Optional[Lap]:
        for lap in self.laps:
            if lap.lap_number == lap_number:
                return lap
        return None

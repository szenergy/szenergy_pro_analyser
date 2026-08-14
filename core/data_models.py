"""
Data models representing telemetry sessions, laps, and channels.
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
    
    # Storage for channel arrays specific to this lap: {channel_name: np.ndarray}
    data: Dict[str, np.ndarray] = field(default_factory=dict)

    # Mapping of slugs to actual channel names in data: {slug: channel_name}
    slug_to_channel: Dict[str, str] = field(default_factory=dict)

    def get_channel(self, name_or_slug: str) -> Optional[np.ndarray]:
        """
        Retrieves channel data array by exact channel name or by channel slug (e.g. 'time', 'distance').
        """
        if not name_or_slug:
            return None
        if name_or_slug in self.data:
            return self.data[name_or_slug]
        if name_or_slug in self.slug_to_channel and self.slug_to_channel[name_or_slug] in self.data:
            return self.data[self.slug_to_channel[name_or_slug]]
        # Fallback: check case-insensitive / clean slug match
        target_slug = name_or_slug.strip().lower()
        for ch_name, arr in self.data.items():
            if ch_name.strip().lower() == target_slug or ch_name.replace(' ', '_').lower() == target_slug:
                return arr
        return None

    def get_channel_by_slug(self, slug: str) -> Optional[np.ndarray]:
        """Gets channel data array for a specific slug (e.g. 'time', 'distance', 'lap')."""
        return self.get_channel(slug)


@dataclass
class Session:
    """Represents an imported telemetry log file/session."""
    id: str
    name: str
    file_path: str
    laps: List[Lap] = field(default_factory=list)
    channels: List[str] = field(default_factory=list)
    preset_name: Optional[str] = None
    
    # Reference to original parsed dataframe if needed
    raw_df: Optional[pd.DataFrame] = field(default=None, repr=False)

    def get_lap(self, lap_number: int) -> Optional[Lap]:
        for lap in self.laps:
            if lap.lap_number == lap_number:
                return lap
        return None

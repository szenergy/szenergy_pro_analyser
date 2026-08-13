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

    def get_channel(self, name: str) -> Optional[np.ndarray]:
        return self.data.get(name)


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

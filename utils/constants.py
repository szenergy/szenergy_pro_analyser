"""
Global constants and configuration defaults for SZenergy Pro Analyser.
"""

APP_NAME = "SZenergy Pro Analyser"
ORGANIZATION_NAME = "SZenergy"
APP_VERSION = "1.0.0"

# Standard / Reserved Internal Channel Names
STD_CHANNEL_LAP = "Lap"
STD_CHANNEL_TIME = "Time"
STD_CHANNEL_DISTANCE = "Distance"

REQUIRED_CHANNELS = [STD_CHANNEL_LAP]

# Pool of distinct colors for dynamic assignment to selected laps
LAP_COLORS = [
    "#00E676",  # Bright Green
    "#FF5252",  # Bright Red
    "#40C4FF",  # Light Blue
    "#FFD740",  # Yellow
    "#E040FB",  # Purple
    "#FF6E40",  # Orange
    "#1DE9B6",  # Teal
    "#FF4081",  # Pink
    "#7C4DFF",  # Deep Purple
    "#A7FF83",  # Mint
    "#FFAB40",  # Amber
    "#00B0FF",  # Vivid Blue
]

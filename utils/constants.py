"""
Global constants and configuration defaults for the app.
"""

# Application Metadata
APP_NAME = "SZenergy Pro Analyser"
ORGANIZATION_NAME = "SZenergy"
APP_VERSION = "1.0.0"
APP_LOGO_FILENAME = "szenergy_logo.png"

# Default Channel Labels
STD_CH_LAP_NUM = "Lap Number"
STD_CH_LAP_TIME = "Lap Time"
STD_CH_LAP_DIST = "Lap Distance"

# Default Channel Slugs/Keys
STD_CH_LAP_NUM_SLUG = "lap_num"
STD_CH_LAP_TIME_SLUG = "lap_time"
STD_CH_LAP_DIST_SLUG = "lap_dist"

# Default Channel Definitions
DEFAULT_CHANNEL_DEFS = [
    {"label": STD_CH_LAP_NUM, "slug": STD_CH_LAP_NUM_SLUG},
    {"label": STD_CH_LAP_TIME, "slug": STD_CH_LAP_TIME_SLUG},
    {"label": STD_CH_LAP_DIST, "slug": STD_CH_LAP_DIST_SLUG},
]

# Application Limits
MAX_SELECTED_CHANNELS = 6

# UI Colors
CROSSHAIR_LINE_COLOR = "#FFD740"

# The number of selectable laps depends on the length of this list
LAP_COLORS = [
    "#FF0000",
    "#00FF00",
    "#0000FF",
    "#FFFF00",
    "#00FFFF",
    "#FF00FF",
    "#FF9600",
    "#FF0096",
    "#00FF96",
    "#96FF00",
    "#9600FF",
    "#0096FF",
]

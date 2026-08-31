"""
Dialogs for the Edit Menu: Preset Manager, Channel Manager, File Mappings, and Legend Renaming.
Modularized into component files and re-exported here for unified access and backwards compatibility.
"""

from ui.preset_manager_dialog import PresetManagerDialog
from ui.channel_manager_dialog import ChannelManagerDialog
from ui.file_mapping_dialog import FileMappingManagerDialog, PathElideLeftDelegate
from ui.rename_legend_dialog import RenameLegendLabelsDialog

__all__ = [
    "PresetManagerDialog",
    "ChannelManagerDialog",
    "FileMappingManagerDialog",
    "PathElideLeftDelegate",
    "RenameLegendLabelsDialog",
]

"""
Backward-compatible wrapper dialog for legacy references to PresetPreviewDialog.
"""

from typing import Dict, List, Optional
from ui.import_wizard import ImportWizardDialog


class PresetPreviewDialog(ImportWizardDialog):
    """Backward-compatible wrapper for legacy references to PresetPreviewDialog."""
    ACTION_APPLY = 1
    ACTION_EDIT = 2

    def __init__(self, file_path: str, preset_name: str, mapping: Dict[str, str],
                 raw_columns: Optional[List[str]] = None,
                 state_manager=None, parent=None):
        raw_cols = list(raw_columns) if raw_columns is not None else list(mapping.keys())
        super().__init__(
            file_path=file_path,
            raw_columns=raw_cols,
            state_manager=state_manager,
            initial_preset=preset_name,
            initial_mapping=mapping,
            parent=parent
        )
        self.selected_action = self.ACTION_APPLY

    @property
    def selected_preset_name(self) -> Optional[str]:
        return self.result_preset_name

    def get_filtered_mapping(self) -> Dict[str, str]:
        return self.result_mapping

# Agent Guidelines & Development Rules

These rules and guidelines must be followed by AI coding agents working on the SZenergy Pro Analyser repository.

---

### 1. Test Verification & Visual Validation
* There are and should be tests to verify your code before concluding work. Run the test suite to ensure there are no regressions.
* Always use `.venv/bin/python` to run tests and python scripts.
* Ensure tests run headlessly in offscreen mode (`QT_QPA_PLATFORM=offscreen`) so UI windows never pop up on the desktop.
* The final verification of visual appearance, layout, and UX flows will always be done by the user (this is a visual GUI application and agents cannot see).

### 2. Keep It Simple (Scope Discipline)
* Keep changes focused and simple.
* When asked for a specific thing, do not develop additional unrequested features or overengineer.

### 3. Consider Existing Systems & Flows
* Always evaluate what already in-place systems, architecture, and workflows a change impacts (e.g. state management, threading, event loops, theme handling, data models, or serialization).

### 4. Component-Based Architecture & Short Files
* Keep files short and modular using a component-style approach with clear single responsibilities.

### 5. Consult When Design Decisions Arise
* Most importantly, ask the user when there are multiple options on how to do something and one isn't objectively the best.

### 6. Bash Usage & File Creation
* Only use bash commands when absolutely necessary.
* Creating new files should always be done using the `touch` command before editing them.

### 7. Continuous Guideline Maintenance
* Keep this `AGENTS.md` file updated over time as new patterns, preferences, and project guidelines are established.

### 8. Global vs. Local Calculated Channels Pattern
* **Global Calculated Channels**: Configured in Channel Manager (`ui/channel_manager_dialog.py`). Defined system-wide across all files and laps using standard global channel slugs. Evaluated on-the-fly via `Lap.get_channel()`.
* **Local Calculated Channels**: Configured per-file in Import Wizard (`ui/import_wizard.py` and `ui/local_calculated_channel_dialog.py`). Compute mathematical values from raw unmapped file columns and map the result directly to target global channel slugs upon parsing. Preserved across presets, file remapping, and workspace restore. Strictly kept separate from `Session.raw_df` and `Session.mapping` (which must strictly contain genuine raw file columns only) to avoid duplicate entries in session remapping and preset saving.

### 9. Per-File Data Gap Disconnection Thresholds Pattern
* Configured per file in Import Wizard (`ui/import_wizard.py`) and Edit Channel Mapping.
* Stored on `Session` (`gap_time_threshold`, `gap_dist_threshold`) and persisted across presets, workspace state, and memory remapping.
* Used during curve generation in `ui/graph_view.py` for each session/curve independently when gap filtering is active. Global menu configuration dialog is removed; global button toggles gap disconnection on/off.

### 10. Global Presets vs. File-Specific Configurations Pattern
* **Global Presets (`presets.json`)**: Reusable templates across files. Modified **only** when the user explicitly clicks the "Save Preset" button.
* **File Configurations (`file_mappings.json`)**: Autonomous per-file memory saved when "Remember for this file" is checked on wizard submit ("Import Data" / "Apply Changes"). Submitting the wizard must **never** modify or create global presets in `presets.json`. Detailed flows documented in `docs/import_wizard_flows.md`.


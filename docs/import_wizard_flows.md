# Import & Manage Session Wizard Documentation

This document describes the architecture, persistent storage models, user flows, and operational rules for importing telemetry log files and managing session channel mappings in SZenergy Pro Analyser.

---

## 1. Architectural Separation: Global Presets vs. File-Specific Configurations

The application maintains a strict separation between **Global Presets** (reusable templates) and **File-Specific Configurations** (autonomous per-file memory).

### Global Presets (`presets.json`)
* **Purpose**: Shared, reusable channel mapping and configuration templates that can be applied across multiple log files (e.g., `Vehicle_CAN_Logger`, `ECU_Standard`).
* **Storage Location**: `presets.json` in the application configuration directory.
* **Fields**:
  * `name`: Human-readable preset name.
  * `slug`: Unique slug identifier (e.g., `trackdaypreset`).
  * `mapping`: Dictionary of raw file column names to standard channel slugs (`{ raw_col: standard_slug }`).
  * `local_calculated_channels`: List of calculation definitions (`target_slug`, `target_label`, `expression`, `inputs`).
  * `gap_time_threshold`: Default max time gap for data disconnection (seconds).
  * `gap_dist_threshold`: Default max distance gap for data disconnection (meters).
* **Mutation Rule**: Presets are **ONLY** modified or created when the user explicitly clicks the **"Save Preset"** button in the wizard. The "Import Data" and "Apply Changes" submit buttons must **never** modify `presets.json`.

### File-Specific Configurations (`file_mappings.json`)
* **Purpose**: Remembers the exact channel mapping, local calculations, and data rate configuration for a specific log file on disk.
* **Storage Location**: `file_mappings.json` in the application configuration directory, keyed by absolute file path.
* **Fields**:
  * `preset_slug`: Slug of the preset used as a base (or `null` if mapped manually without a preset).
  * `mapping`: The exact mapping dictionary chosen for this file (`{ raw_col: standard_slug }`).
  * `local_calculated_channels`: List of local calculations defined for this file.
  * `gap_time_threshold`: The file's configured time gap threshold (seconds).
  * `gap_dist_threshold`: The file's configured distance gap threshold (meters).
* **Mutation Rule**:
  * If **"Remember for this file"** is checked when submitting: Saves or updates the file's configuration in `file_mappings.json`.
  * If **"Remember for this file"** is unchecked when submitting: Removes the file's entry from `file_mappings.json`.
  * Submitting the wizard **never** modifies `presets.json`.

---

## 2. Wizard Operational Flows

### Flow 1: Initial File Import (`File -> Open Log File...` or Sidebar `+ Import Session...`)

#### 1.1 Standard Import with a Matching Preset
1. User selects a log file (e.g., `run_01.csv`).
2. System checks `file_mappings.json` for a remembered configuration. None exists.
3. System finds the best-fit preset based on header coverage (e.g., `TrackDayPreset`).
4. Import Wizard opens with `TrackDayPreset` pre-selected and pre-loaded.
5. User reviews the mapping table and badges. Makes no changes.
6. "Remember for this file" is checked by default.
7. User clicks **"Import Data"**.
8. **Result**:
   * `file_mappings.json` records `run_01.csv` with its current mapping, local calcs, gap thresholds, and `preset_slug: "trackdaypreset"`.
   * `presets.json` is **not touched**.
   * File is parsed and loaded into the workspace.

#### 1.2 Preset Loaded + File-Specific Customization
1. User selects `run_01.csv`.
2. Wizard loads `TrackDayPreset`.
3. User customizes the configuration for this file only:
   * Adds a local calculated channel (e.g., `WheelSlip = FL_Speed - RL_Speed`) relevant only to this sensor run.
   * Or alters a column mapping, or adjusts data gap thresholds.
4. User **does not** click "Save Preset" because the customization is specific to this file.
5. "Remember for this file" is checked.
6. User clicks **"Import Data"**.
7. **Result**:
   * `TrackDayPreset` in `presets.json` remains **completely unchanged**. Other files using `TrackDayPreset` will not see this local calculation or modified threshold.
   * `file_mappings.json` saves `run_01.csv` with its custom mapping, the local calculation, and thresholds.
   * The session parses and graphs with the local calculation.

#### 1.3 Preset Loaded + Explicit Global Preset Update
1. User selects `run_01.csv`.
2. Wizard loads `TrackDayPreset`.
3. User adds a calculation or maps a new channel that should become standard for **all files** using this preset.
4. User clicks **"Save Preset"**:
   * If the preset name in the combobox is unchanged: updates `TrackDayPreset` in `presets.json`.
   * If the user entered a different name: `SavePresetChoiceDialog` asks whether to "Update Existing" or "Create New".
5. User clicks **"Import Data"**.
6. **Result**:
   * Global preset in `presets.json` is updated.
   * File configuration in `file_mappings.json` is saved.

#### 1.4 Manual Mapping from Scratch (Preset: "None")
1. User selects a file with custom column names. Wizard opens with Preset set to `"None"`.
2. User manually maps channels, adds local calculations, and sets gap thresholds.
3. **If "Remember for this file" is checked**:
   * User clicks **"Import Data"**.
   * `file_mappings.json` saves the configuration for this file path with `preset_slug: null`.
   * **No global preset is created in `presets.json`** (avoids polluting the global preset list with file-named presets).
4. **If "Remember for this file" is unchecked**:
   * User clicks **"Import Data"**.
   * Data is imported for this session only. Neither `presets.json` nor `file_mappings.json` is modified.

#### 1.5 Manual Mapping + User Decides to Create a Preset
1. User selects a file with Preset set to `"None"`.
2. User maps channels, adds calcs, sets thresholds.
3. User types a new name (e.g., `DynoLogPreset`) into the Preset combobox.
4. User clicks **"Save Preset"**.
5. Preset `DynoLogPreset` is saved to `presets.json`.
6. User clicks **"Import Data"** (with "Remember for this file" checked).
7. File is imported and remembered with `preset_slug: "dynologpreset"`.

---

### Flow 2: Subsequent Import of a Remembered File

#### 2.1 Automatic Bypass
1. User selects `run_01.csv` via File menu or sidebar "+ Import Session...".
2. System looks up `run_01.csv` in `file_mappings.json` and finds its saved configuration.
3. System verifies that all mapped columns and local calculation input columns exist in the file.
4. If valid: The wizard is bypassed automatically, and the file imports directly with its remembered mapping, local calculations, and gap thresholds. (The user can always edit the session at any time from the right-click menu).

#### 2.2 Stale / Changed File Handling
1. User selects `run_01.csv`, but columns in the file were modified, deleted, or renamed on disk.
2. System detects missing mapped channels or missing inputs for local calculations.
3. Automatic bypass is aborted. Wizard opens with the remembered configuration pre-loaded.
4. Missing channels are highlighted with warning badges (`⚠`).
5. User adjusts mappings or deletes invalid calculations, then clicks "Import Data".

---

### Flow 3: Session Remapping ("Manage Session" / Edit Channel Mapping)

1. User right-clicks a loaded session in the sidebar -> "Edit Channel Mapping...".
2. Wizard opens as "Manage Session - <filename>":
   * Pre-fills current session's mapping, local calculated channels, gap thresholds, and base preset slug.
   * Action button text displays **"Apply Changes"**.
3. User edits mappings, adds/removes local calcs, or modifies data gap thresholds.
4. **User Actions**:
   * **Apply Changes (Remember checked)**: Session re-parses in memory and updates graphs immediately. `file_mappings.json` updates for this file. `presets.json` is **not touched**.
   * **Apply Changes (Remember unchecked)**: Session updates in memory. `file_mappings.json` removes the entry for this file. `presets.json` is **not touched**.
   * **Save Preset**: Updates or creates a preset in `presets.json` with the current settings before applying changes.

---

### Flow 4: In-Wizard Controls & Actions Summary

| Control / Action | Scope | Description |
| :--- | :--- | :--- |
| **Preset Combobox** | Selection | Selecting an existing preset loads its mappings, local calcs, and gap thresholds. Selecting "None" clears mappings to `-- Skip --`, empties local calcs, and resets thresholds to defaults. |
| **"Load Preset" Button** | In-Memory Table | Re-applies the selected preset from `presets.json`, resetting any manual edits in the wizard. |
| **"Save Preset" Button** | Global (`presets.json`) | Explicit action to save the current configuration as a reusable global preset template. Prompts if renaming an existing preset. |
| **"+ Add Calculated Channel"** | Per-Wizard / Per-File | Defines a formula mapped to a target global channel. Does not modify presets unless "Save Preset" is clicked. |
| **Data Rate Configuration** | Per-Wizard / Per-File | Configures max time gap and max distance gap disconnection thresholds for this file. |
| **"Remember for this file"** | Per-File (`file_mappings.json`) | Controls whether the file's configuration is persisted across restarts. Never touches `presets.json`. |
| **"Import Data" / "Apply Changes"** | Workspace & Per-File | Validates required channels, saves per-file configuration if remembered, and parses the dataset. |
| **"Cancel" Button** | None | Closes the wizard without modifying files, presets, or workspace state. |

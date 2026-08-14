# SZenergy Pro Analyser

A lightweight, high-performance, cross-platform desktop application for visualizing and analyzing telemetry log data for Shell Eco Marathon racing teams. Built with Python, PySide6, and PyQtGraph, it serves as a modern replacement for Unipro's Analyser software with native support for **CSV, XLSX, and TDMS** log file formats.

---

## 🌟 Key Features

### 📁 Multi-Format Log Support & Import Wizard
- **Supported Formats:** `CSV`, `XLSX`, and National Instruments `TDMS`.
- **Channel Mapping Wizard:** Map raw log column names to standard internal channels (`Lap`, `Time`, `Distance`, `Speed`, `RPM`, etc.).
- **Preset System:** Save mapping configurations as presets. When a matching file structure is detected, a **Preset Preview Dialog** opens with **[Apply Preset]**, **[Edit in Wizard]**, and **[Cancel]** options.
- **Duplicate Validation:** Prevents mapping multiple raw columns to the same target channel.

### 🗂 Unipro-Style Left Sidebar
- **Sessions & Laps Tree:** View loaded log sessions and expandable laps with formatted lap times.
- **Row Drag Multi-Selection:** Click, `Ctrl+click`, `Shift+click`, or click-and-drag across rows to select multiple laps or channels simultaneously.
- **Dynamic Color Pool:** Colors are assigned dynamically from a pool of distinct colors only when a lap is selected, and returned to the pool when deselected.

### 📊 Vertically Stacked Synchronized Graphs
- **High Performance:** Built on `pyqtgraph` for smooth rendering of high-frequency telemetry data.
- **Synchronized X-Axis:** Zooming or panning one graph automatically syncs the X-axis across all vertically stacked charts.
- **Lap Overlay Normalization:** Automatically normalizes each lap's X-axis data relative to the start of that lap ($X_{\text{overlay}} = X - X[0]$) so laps overlay on top of each other at $0.0\text{s}$ or $0.0\text{m}$ for direct comparison.
- **Aligned Y-Axes:** Aligns left Y-axes across stacked charts so all plot canvases start at the exact same pixel position.
- **Auto-Ranging:** Automatically auto-ranges plots when channels, laps, or X-axis modes change.
- **Synchronized Crosshair Cursor:** Vertical crosshair tracks mouse movement across all stacked charts simultaneously with real-time value readouts.

### ⚙️ Configurable Standard Channels & Presets Editor
- **Edit Menu:** Includes **Manage Saved Presets...** and **Manage Standard Channel List...**.
- **Slug Key Decoupling:** Channels use a display label and an auto-generated internal slug.
- **Renamable System Channels:** Rename system channels (`Lap`, `Time`, `Distance`) to any custom display label (e.g. `Kör`, `Idő`, `Távolság`).
- **Config Directory Opener:** Open your OS config directory (`presets.json` and `custom_channels.json`) directly in your native file explorer via **File -> Open Config Folder**.

### 🎨 Native OS Theme Adaptation
- Automatically detects whether your operating system is in **Light Mode** or **Dark Mode** and applies custom styled UI themes and matching graph canvas backgrounds.

---

## 🚀 Installation & Setup

### Prerequisites
- Python 3.10 or higher.

### 1. Clone the Repository
```bash
git clone https://github.com/szenergy/szenergypro_analyser.git
cd szenergypro_analyser
```

### 2. Create and Activate Virtual Environment
```bash
# On Linux / macOS:
python3 -m venv .venv
source .venv/bin/activate

# On Windows:
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

---

## 💻 Running the Application

Launch the main GUI application:
```bash
python main.py
```

### Generate Sample Test Data
To generate sample telemetry files in `CSV`, `XLSX`, and `TDMS` formats for testing:
```bash
python create_sample_data.py
```
This creates sample files in the `sample_data/` directory (`sample_motec.csv`, `sample_ecu.xlsx`, `sample_ni.tdms`).

---

## 📂 Project Architecture

```text
szenergypro_analyser/
├── main.py                 # Application entry point and theme initializer
├── create_sample_data.py   # Test helper script to generate sample log files
├── requirements.txt        # Minimal third-party dependencies
├── README.md               # Project documentation
├── core/                   # Non-UI data processing and state management
│   ├── data_models.py      # Dataclasses for Session and Lap
│   ├── file_parser.py      # Parsers for CSV, XLSX, and TDMS files
│   └── state_manager.py    # Persistent app settings, channel defs, and preset storage
├── ui/                     # PySide6 GUI components
│   ├── main_window.py      # Main application frame, menus, and layout orchestration
│   ├── sidebar.py          # Left tree panel for sessions, laps, and channels
│   ├── graph_view.py       # Stacked pyqtgraph charts with synchronized crosshairs
│   ├── import_wizard.py    # Channel mapping wizard & preset preview dialog
│   └── edit_dialogs.py     # Dialogs for Preset Manager and Channel Manager
└── utils/
    └── constants.py        # Global constants and color palettes
```

---

## 📄 License
Licensed under the [MIT License](LICENSE).

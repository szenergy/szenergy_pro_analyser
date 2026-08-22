# SZenergy Pro Analyser

A desktop application for telemetry analysis created by SZEnergy team. This app allows our team to analyze logs of various formats from our vehicles to spot irregularities, gauge driver or strategy preformance.

## Key Features

- **Multi-Format Telemetry Ingestion**: Load `.csv`, `.xlsx`, `.xls`, and `.tdms` files.
- **Synchronized Multi-Plot View**: Stack up to 6 telemetry channels vertically with synchronized panning, zoom, and cursors.
- **Overlay Lap Comparisons**: Compare multiple laps simultaneously with distinct color assignments and normalized Lap Distance or Lap Time X-axes.
- **Intelligent Channel Mapping & Presets**: Map raw telemetry channel names to standard ones using the import wizzard.
- **Select to Zoom**: Click-and-drag zooming on either axis and all the graphs.
- **Custom Legends**: Ability to rename laps and show it on the graph.
- **Workspace State Persistence**: Automatically saves and restores loaded sessions, selected laps, custom labels, graph zoom & pan on startup.
- **Config Export & Import**: Share configurations across machines with a single JSON file.
- **Native OS Theme Support**: Automatically adapts to system Dark and Light desktop themes.

## Quick Start (Download & Run)

No runtime installation or dependencies required, just download the executable and run.

1. Go to the **Releases** page of this repository.
2. Download the binary for your operating system
3. Run and enjoy


# User Manual

This section contains a more detailed user guide on how to use each feature of the application.

## 1. Importing Telemetry Logs

Open the **File** menu in the top-left and click on **Open Log File**. 

### Supported File Formats

SZenergy Pro Analyser natively supports:
- **CSV (`.csv`)**: Automatically sniffs delimiters (commas, semicolons, tabs) and encodings (`utf-8`, `latin-1`, `cp1252`).
- **Excel (`.xlsx`, `.xls`)**: Reads the first worksheet looking for columns of data.
- **NI TDMS (`.tdms`)**: Reads LabVIEW / National Instruments telemetry logs, automatically handling multi-rate channels and uneven sample rates.

### The Import Wizard & Channel Mapping

Once you selected one or more log files and hit **Open** in the file manager, the import wizzard will open.

If you are **using the program for the first time**, there likely aren't any presets saved, so all the channels will show **-- Skip --** status. You can map each channel by selecting from the list or inputing a new channel name which will be created automatically once you hit import. At this point it is also a good idea to save your mappings as a preset so you don't have to do it all over again.

If you already have presets saved, then the log you selected might have matched one. You can see the status of the match at the top. If the match is not correct you can select a different preset as well.


## 2. Analyzing Telemetry & Navigating Graphs

### Selecting Sessions & Laps
In the left sidebar under **Sessions & Laps**, you can see the loaded sessions and their laps with lap times (in Minutes:Seconds.Milliseconds format).
- Click and drag across laps or use Ctrl + Click to select them.
- Each selected lap is automatically assigned a distinct color.
- Up to 12 laps can be selected simultaneously.

### Choosing Channels
In the **Available Channels** section, select up to 6 channels to plot.
You can use the search bar above the channel list to quickly filter channels by name.

### Switching X-Axis
Use the **X-Axis** dropdown in the toolbar (top-right) to switch between **Lap Distance** and **Lap Time**.

### Zooming and Panning
- **X-Axis Zoom (Synchronized across all plots)**: Click and drag horizontally across any graph. A green highlighted region will appear. Release the mouse button to zoom into that segment across all stacked graphs simultaneously.
- **Y-Axis Zoom (Single plot)**: Click and drag vertically, it will only zoom the one graph.
- **Cancel Zoom Drag**: Press `Escape` while dragging to cancel without zooming.
- **Auto-Range**: Click the **Auto-Range** icon in the toolbar to instantly fit all graphs to their complete horizontal and vertical data extents.
- **Panning**: Middle mouse click + drag to pan the graphs.

### Using the Cursor
Move your cursor across the graphs to view the vertical cursor line and tracking points on all curves.
On the top of each graph, the exact numerical value at the current cursor position is shown.
- Click the **Cursor Values** toggle button in the toolbar to show or hide live cursor readouts.

### Grid Lines
Click the **Grid** toggle buttons to show or hide vertical and horizontal grid lines.


## 4. Customizing the Legend and Exporting

If you click the **Legend** button in the toolbar the legend overlay will appear. You can freely drag this around the all the graphs.
- Click the **Rename Legend** button to assign custom names to specific laps.
- Click the **Export** button in the toolbar to open the export dialog, allowing you to export graph views or raw plot data to image files (PNG/SVG), CSV, and other formats.

## 5. Managing Configuration

### Session Context Menu
Right-click any session in the sidebar to access the following options:
- **Select All Laps in Session**: Quickly selects all laps of that log.
- **Deselect All Laps in Session**: Deselects all laps in that log.
- **Edit Channel Mapping...**: Opens the import wizard that allows re-map channels without needing to reload the file.
- **Remove Session**: Unloads the log file from the workspace.

### Manage Channels and Presets
Access from the **Edit** menu:
- **Manage Presets...**: Rename or delete them or edit channel mappings.
- **Manage Channels...**: Add new telemetry channels or rename existing ones.
- **Manage File Mappings...**: View and delete remembered file-to-preset associations.

### View Menu
Access all graph and display controls directly from the **View** menu:
- **Auto Range All Graphs**: Reset all graphs to fit all selected data.
- **X-Axis / Y-Axis Grid Lines**: Toggle visibility of background grid lines.
- **Cursor Values & Crosshair**: Toggle live hover cursor readouts.
- **Curve Legend**: Show/hide the curve legend overlay.
- **Rename Legend Labels...**: Rename individual lap curve names.
- **Export Plots / Data...**: Open the export dialog.
- **X-Axis**: Switch between Lap Distance and Lap Time.
- **Theme**: Select between **Auto (System)**, **Dark**, and **Light** themes.

### Exporting and Importing Configurations
Easily share standard channel definitions and presets across machines:
- **File > Export Configuration...**: Exports all presets and channels into a single `.json` file.
- **File > Import Configuration...**: Imports presets and channels, automatically merging with your existing configuration.

### Clearing the Workspace
- Go to **File > Clear Workspace** to unload all sessions and reset all plots with a single click.


# For developers

This part is not for users, please consult the manual above.

### Running the app

If you want to run with python and not the prebuilt binary:
1. Clone this repo
2. Open a terminal in the folder you cloned to

The next part depends on your preferences, but this is the recommended way:

3. Create a venv with `python -m venv .venv`
4. Install dependencies: `.venv/bin/pip install -r requirements.txt`
5. Run the app: `.venv/bin/python main.py`

### Building

The app is built with pyinstaller into a single executable using two scripts, one for linux (`build_linux.sh`) and one for windows (`build_windows.bat`). These only work on their respective operating systems.

---

Created by SZEnergy team for Shell Eco-Marathon.

This project is licensed under the [MIT License](LICENSE).
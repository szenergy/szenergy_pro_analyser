"""
PyQtGraph-based main view displaying vertically stacked, synchronized plots for selected channels.
Normalizes lap X-axis data for accurate lap overlay comparisons.
Features toolbar icon toggle buttons for X/Y grids, cursor values, legend labels, custom legend renaming, and auto-ranging.
Displays tracking dots on each curve at the cursor crosshair position.
Ensures equal viewbox heights across all stacked plots and full X-axis grid support on every plot.
"""

import logging
from typing import Dict, List, Set, Tuple, Optional
import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QFrame, QPushButton, QMessageBox
)
from PySide6.QtCore import Qt, QSize, QPointF, QTimer, QEvent
from PySide6.QtGui import QColor, QPixmap, QPainter, QIcon, QPen, QPolygonF

from core.data_models import Session, Lap
from utils.constants import (
    STD_CH_LAP_TIME, STD_CH_LAP_DIST,
    STD_CH_LAP_TIME_SLUG, STD_CH_LAP_DIST_SLUG,
    CROSSHAIR_LINE_COLOR
)
from ui.graph_icons import (
    create_icon_x_grid, create_icon_y_grid, create_icon_cursor,
    create_icon_legend, create_icon_rename_legend, create_icon_autorange,
    create_icon_export
)
from ui.graph_viewbox import XZoomViewBox, _get_nearest_channel_sample

logger = logging.getLogger(__name__)


class GraphViewWidget(QWidget):
    """Main plotting area with vertically stacked charts, toolbar toggles, and on-graph value readouts."""

    def __init__(self, parent=None, state_manager=None):
        super().__init__(parent)
        self.state_manager = state_manager
        self.sessions: Dict[str, Session] = {}
        self.selected_channels: List[str] = []
        self.selected_laps_info: List[Tuple[str, int, str]] = []
        self.custom_lap_labels: Dict[Tuple[str, int], str] = {}
        self.x_axis_slug: str = STD_CH_LAP_DIST_SLUG
        self.time_label: str = STD_CH_LAP_TIME
        self.dist_label: str = STD_CH_LAP_DIST
        self.is_dark: bool = True

        # State tracking for zoom/pan preservation
        self.has_manual_zoom_or_pan: bool = False
        self.saved_x_range: Optional[List[float]] = None
        self.saved_y_ranges: Dict[str, List[float]] = {}

        # View and Display toggles
        self.show_x_grid: bool = False
        self.show_y_grid: bool = True
        self.show_cursor_values: bool = True
        self.show_legend: bool = False
        self._is_rebuilding: bool = False

        self.plot_widgets: Dict[str, pg.PlotItem] = {}
        self.v_lines: List[pg.InfiniteLine] = []
        self.tracking_dots: List[Tuple[pg.ScatterPlotItem, str, int, str]] = []
        self.legend: Optional[pg.LegendItem] = None

        self._init_ui()

    @property
    def x_axis_channel(self) -> str:
        """Returns the active display label for the selected X-axis slug."""
        return self.dist_label if self.x_axis_slug == STD_CH_LAP_DIST_SLUG else self.time_label

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Top Control Bar for X-Axis selection and interactive tool buttons
        self.control_bar = QFrame()
        c_layout = QHBoxLayout(self.control_bar)
        c_layout.setContentsMargins(10, 4, 10, 4)
        c_layout.setSpacing(6)

        # 1. Auto Range All Graphs Button
        self.btn_autorange = QPushButton()
        self.btn_autorange.setToolTip("Auto Range All Graphs")
        self.btn_autorange.setFixedSize(32, 28)
        self.btn_autorange.setIconSize(QSize(18, 18))
        self.btn_autorange.clicked.connect(self._on_autorange)
        c_layout.addWidget(self.btn_autorange)

        # 2. Toggle X-Axis Grid Button
        self.btn_x_grid = QPushButton()
        self.btn_x_grid.setCheckable(True)
        self.btn_x_grid.setChecked(self.show_x_grid)
        self.btn_x_grid.setToolTip("Toggle X-Axis Grid Lines")
        self.btn_x_grid.setFixedSize(32, 28)
        self.btn_x_grid.setIconSize(QSize(18, 18))
        self.btn_x_grid.toggled.connect(self._toggle_x_grid)
        c_layout.addWidget(self.btn_x_grid)

        # 3. Toggle Y-Axis Grid Button
        self.btn_y_grid = QPushButton()
        self.btn_y_grid.setCheckable(True)
        self.btn_y_grid.setChecked(self.show_y_grid)
        self.btn_y_grid.setToolTip("Toggle Y-Axis Grid Lines")
        self.btn_y_grid.setFixedSize(32, 28)
        self.btn_y_grid.setIconSize(QSize(18, 18))
        self.btn_y_grid.toggled.connect(self._toggle_y_grid)
        c_layout.addWidget(self.btn_y_grid)

        # 4. Toggle Cursor Values Display Button
        self.btn_cursor = QPushButton()
        self.btn_cursor.setCheckable(True)
        self.btn_cursor.setChecked(self.show_cursor_values)
        self.btn_cursor.setToolTip("Toggle Cursor Crosshair & Value Display")
        self.btn_cursor.setFixedSize(32, 28)
        self.btn_cursor.setIconSize(QSize(18, 18))
        self.btn_cursor.toggled.connect(self._toggle_cursor_values)
        c_layout.addWidget(self.btn_cursor)

        # 5. Toggle Legend / Label Button
        self.btn_legend = QPushButton()
        self.btn_legend.setCheckable(True)
        self.btn_legend.setChecked(self.show_legend)
        self.btn_legend.setToolTip("Toggle Curve Legend")
        self.btn_legend.setFixedSize(32, 28)
        self.btn_legend.setIconSize(QSize(18, 18))
        self.btn_legend.toggled.connect(self._toggle_legend)
        c_layout.addWidget(self.btn_legend)

        # 6. Rename Legend / Curve Labels Button
        self.btn_rename_legend = QPushButton()
        self.btn_rename_legend.setToolTip("Rename Legend / Curve Labels...")
        self.btn_rename_legend.setFixedSize(32, 28)
        self.btn_rename_legend.setIconSize(QSize(18, 18))
        self.btn_rename_legend.clicked.connect(self._on_rename_legend)
        c_layout.addWidget(self.btn_rename_legend)

        # 7. Export Plot / Data Button
        self.btn_export = QPushButton()
        self.btn_export.setToolTip("Export Plot / Data...")
        self.btn_export.setFixedSize(32, 28)
        self.btn_export.setIconSize(QSize(18, 18))
        self.btn_export.clicked.connect(self._on_export_plot)
        c_layout.addWidget(self.btn_export)

        c_layout.addStretch()

        # 8. X-Axis Selector (Using immutable Slugs as userData)
        c_layout.addWidget(QLabel("<b>X-Axis:</b>"))
        self.x_axis_combo = QComboBox()
        self.x_axis_combo.addItem(self.dist_label, userData=STD_CH_LAP_DIST_SLUG)
        self.x_axis_combo.addItem(self.time_label, userData=STD_CH_LAP_TIME_SLUG)
        self.x_axis_combo.currentIndexChanged.connect(self._on_x_axis_changed)
        c_layout.addWidget(self.x_axis_combo)

        layout.addWidget(self.control_bar)

        # PyQtGraph Layout Container (context menu disabled)
        self.setContextMenuPolicy(Qt.NoContextMenu)
        self.glw = pg.GraphicsLayoutWidget()
        self.glw.setContextMenuPolicy(Qt.NoContextMenu)
        layout.addWidget(self.glw)

        # Install event filters to capture Escape key during drag operations
        self.glw.installEventFilter(self)
        self.glw.scene().installEventFilter(self)

        # Connect scene mouse-move signal ONCE globally on initialization
        self.glw.scene().sigMouseMoved.connect(self._on_mouse_moved)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_row_heights()

    def _update_row_heights(self):
        """Ensures all stacked plot ViewBoxes have identical height."""
        n = len(self.selected_channels)
        if n == 0 or not self.plot_widgets:
            return

        h_axis = 40
        margin = 18
        spacing = 6 * (n - 1)
        total_h = self.glw.height() - margin - spacing
        if total_h <= h_axis:
            return

        h_plot = (total_h - h_axis) / n
        for i in range(n):
            if i == n - 1:
                self.glw.ci.layout.setRowFixedHeight(i, int(h_plot + h_axis))
            else:
                self.glw.ci.layout.setRowFixedHeight(i, int(h_plot))

    def set_x_axis_labels(self, time_label: str, dist_label: str):
        """Updates X-Axis options based on configured standard labels, preserving active slug selection."""
        self.time_label = time_label
        self.dist_label = dist_label

        self.x_axis_combo.blockSignals(True)
        self.x_axis_combo.clear()
        self.x_axis_combo.addItem(self.time_label, userData=STD_CH_LAP_TIME_SLUG)
        self.x_axis_combo.addItem(self.dist_label, userData=STD_CH_LAP_DIST_SLUG)

        target_idx = 0
        for idx in range(self.x_axis_combo.count()):
            if self.x_axis_combo.itemData(idx) == self.x_axis_slug:
                target_idx = idx
                break
        self.x_axis_combo.setCurrentIndex(target_idx)
        self.x_axis_combo.blockSignals(False)

        self.rebuild_plots()

    def apply_theme(self, is_dark: bool):
        self.is_dark = is_dark
        bg_color = "#191B1F" if is_dark else "#FFFFFF"
        fg_color = "#E0E0E0" if is_dark else "#202020"
        bar_style = (
            "background-color: #24272C; color: #E0E0E0; border-bottom: 1px solid #2C3036;"
            if is_dark else
            "background-color: #E8ECEF; color: #212529; border-bottom: 1px solid #DEE2E6;"
        )

        pg.setConfigOptions(background=bg_color, foreground=fg_color, antialias=True)
        self.glw.setBackground(bg_color)
        self.control_bar.setStyleSheet(bar_style)

        # Refresh icons with current theme colors
        self.btn_x_grid.setIcon(create_icon_x_grid(is_dark))
        self.btn_y_grid.setIcon(create_icon_y_grid(is_dark))
        self.btn_cursor.setIcon(create_icon_cursor(is_dark))
        self.btn_legend.setIcon(create_icon_legend(is_dark))
        self.btn_rename_legend.setIcon(create_icon_rename_legend(is_dark))
        self.btn_autorange.setIcon(create_icon_autorange(is_dark))
        self.btn_export.setIcon(create_icon_export(is_dark))

        for plot in self.plot_widgets.values():
            if hasattr(plot, "vb") and hasattr(plot.vb, "update_theme"):
                plot.vb.update_theme(is_dark)

        self.rebuild_plots()

    def show_drag_selection(self, x_min_data: float, x_max_data: float):
        """Displays the synchronized X-axis selection box on all stacked plots."""
        for plot in self.plot_widgets.values():
            if hasattr(plot, "vb") and hasattr(plot.vb, "show_x_drag_box"):
                plot.vb.show_x_drag_box(x_min_data, x_max_data)

    def hide_drag_selection(self):
        """Hides the selection box on all stacked plots."""
        for plot in self.plot_widgets.values():
            if hasattr(plot, "vb") and hasattr(plot.vb, "rbScaleBox"):
                plot.vb.rbScaleBox.hide()

    def hide_drag_selection_except(self, active_vb):
        """Hides the selection box on all stacked plots except the actively dragged plot."""
        for plot in self.plot_widgets.values():
            if hasattr(plot, "vb") and plot.vb is not active_vb and hasattr(plot.vb, "rbScaleBox"):
                plot.vb.rbScaleBox.hide()

    def zoom_x_range(self, x_min: float, x_max: float):
        """Sets the X-axis range on all linked plots without altering Y-axis ranges."""
        if not self.plot_widgets:
            return
        self.has_manual_zoom_or_pan = True
        first_plot = list(self.plot_widgets.values())[0]
        first_plot.setXRange(x_min, x_max, padding=0)
        self._record_current_view_ranges()

    def mark_manual_zoom_or_pan(self):
        """Marks that the user has manually zoomed or panned, and captures current view ranges."""
        if getattr(self, "_is_rebuilding", False):
            return
        self.has_manual_zoom_or_pan = True
        self._record_current_view_ranges()

    def _record_current_view_ranges(self):
        """Records current X and Y view ranges across active plot widgets."""
        if not self.plot_widgets:
            return
        first_plot = list(self.plot_widgets.values())[0]
        if hasattr(first_plot, "vb") and first_plot.vb is not None:
            self.saved_x_range = list(first_plot.vb.viewRange()[0])
        for ch, plot in self.plot_widgets.items():
            if hasattr(plot, "vb") and plot.vb is not None:
                self.saved_y_ranges[ch] = list(plot.vb.viewRange()[1])

    def _on_manual_range_change(self, mask=None):
        """Slot called when a ViewBox signals manual range change (pan, wheel, scale)."""
        if not getattr(self, "_is_rebuilding", False):
            self.mark_manual_zoom_or_pan()

    def cancel_drag_selection(self) -> bool:
        """Cancels any ongoing X-axis drag selection across all stacked plots."""
        canceled = False
        for plot in self.plot_widgets.values():
            if hasattr(plot, "vb") and hasattr(plot.vb, "cancel_drag"):
                if plot.vb.cancel_drag():
                    canceled = True
        self.hide_drag_selection()
        return canceled

    def eventFilter(self, watched, event):
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            if self.cancel_drag_selection():
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self.cancel_drag_selection():
                event.accept()
                return
        super().keyPressEvent(event)

    def set_sessions(self, sessions: Dict[str, Session]):
        self.sessions = sessions
        # Clean up stale custom lap labels for sessions that no longer exist
        stale_keys = [key for key in self.custom_lap_labels if key[0] not in sessions]
        for key in stale_keys:
            del self.custom_lap_labels[key]
        self.rebuild_plots()

    def set_selected_channels(self, channels: Set[str]):
        sorted_channels = sorted(list(channels))
        if sorted_channels != self.selected_channels:
            self.selected_channels = sorted_channels
            self.rebuild_plots()

    def set_selected_laps(self, laps_info: List[Tuple[str, int, str]]):
        if laps_info != self.selected_laps_info:
            self.selected_laps_info = laps_info
            self.rebuild_plots()

    def _on_x_axis_changed(self, idx: int):
        slug = self.x_axis_combo.itemData(idx)
        if slug and slug != self.x_axis_slug:
            self.x_axis_slug = slug
            self.has_manual_zoom_or_pan = False
            self.saved_x_range = None
            self.saved_y_ranges.clear()
            self.rebuild_plots()

    def _toggle_x_grid(self, checked: bool):
        self.show_x_grid = checked
        for plot in self.plot_widgets.values():
            plot.showGrid(x=self.show_x_grid, y=self.show_y_grid, alpha=0.3)

    def _toggle_y_grid(self, checked: bool):
        self.show_y_grid = checked
        for plot in self.plot_widgets.values():
            plot.showGrid(x=self.show_x_grid, y=self.show_y_grid, alpha=0.3)

    def _toggle_cursor_values(self, checked: bool):
        self.show_cursor_values = checked
        for v_line in self.v_lines:
            v_line.setVisible(self.show_cursor_values)
        for dot, _, _, _ in self.tracking_dots:
            dot.setVisible(self.show_cursor_values)
        if not self.show_cursor_values:
            title_color = "#E0E0E0" if self.is_dark else "#202020"
            for channel_name, plot in self.plot_widgets.items():
                display_label = channel_name
                if self.state_manager:
                    display_label = self.state_manager.get_label_by_slug(channel_name, channel_name)
                plot.setTitle(f"<span style='color:{title_color}; font-weight:bold; font-size:10pt;'>{display_label}</span>", justify='left')

    def _toggle_legend(self, checked: bool):
        self.show_legend = checked
        if self.legend:
            self.legend.setVisible(self.show_legend)

    def _on_autorange(self, *args, **kwargs):
        """Executes pyqtgraph's built-in 'View All' auto-range on every plot and master linked X-axis, resetting manual zoom state."""
        self.has_manual_zoom_or_pan = False
        self.saved_x_range = None
        self.saved_y_ranges.clear()

        if not self.plot_widgets:
            return

        plots = list(self.plot_widgets.values())
        for plot in plots:
            plot.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
            plot.autoRange()

        if plots:
            plots[0].enableAutoRange(axis=pg.ViewBox.XAxis, enable=True)
            plots[0].autoRange()

    def _on_rename_legend(self):
        """Opens dialog to customize legend labels specifying what the curve colors mean."""
        if not self.selected_laps_info:
            QMessageBox.information(
                self, "No Laps Selected",
                "Please select at least one lap from the left sidebar to customize its legend label."
            )
            return

        from ui.edit_dialogs import RenameLegendLabelsDialog
        dialog = RenameLegendLabelsDialog(
            self.selected_laps_info, self.sessions, self.custom_lap_labels, parent=self
        )
        if dialog.exec() == RenameLegendLabelsDialog.Accepted:
            self.custom_lap_labels.update(dialog.renamed_labels)
            self.rebuild_plots()

    def _on_export_plot(self):
        """Opens PyQtGraph's default built-in export dialog for exporting plots and data."""
        from pyqtgraph.GraphicsScene.exportDialog import ExportDialog
        if not hasattr(self, "_export_dialog") or self._export_dialog is None:
            self._export_dialog = ExportDialog(self.glw.scene())

        target_item = self.glw.ci if hasattr(self.glw, "ci") else (list(self.plot_widgets.values())[0] if self.plot_widgets else None)
        self._export_dialog.show(target_item)

    def rebuild_plots(self):
        self._is_rebuilding = True
        try:
            logger.debug("Rebuilding plots (channels: %s, selected laps: %d, X-axis slug: '%s')",
                         self.selected_channels, len(self.selected_laps_info), self.x_axis_slug)
            if self.has_manual_zoom_or_pan and self.plot_widgets:
                self._record_current_view_ranges()

            self.glw.scene().blockSignals(True)
            self.glw.clear()
            self.plot_widgets.clear()
            self.v_lines.clear()
            self.tracking_dots.clear()
            self.legend = None

            if not self.selected_channels or not self.selected_laps_info:
                label = pg.LabelItem(
                    text="Select laps and channels from the left sidebar to display graphs.",
                    size="12pt", color="#808080"
                )
                self.glw.addItem(label, row=0, col=0)
                return

            first_plot: Optional[pg.PlotItem] = None
            title_color = "#E0E0E0" if self.is_dark else "#202020"

            for row, channel_name in enumerate(self.selected_channels):
                vb = XZoomViewBox(graph_widget=self)
                vb.update_theme(self.is_dark)
                vb.sigRangeChangedManually.connect(self._on_manual_range_change)
                plot = self.glw.addPlot(row=row, col=0, viewBox=vb)
                plot.setMenuEnabled(False)
                plot.ctrlMenu = None

                display_label = channel_name
                if self.state_manager:
                    display_label = self.state_manager.get_label_by_slug(channel_name, channel_name)

                title_html = f"<span style='color:{title_color}; font-weight:bold; font-size:10pt;'>{display_label}</span>"
                plot.setTitle(title_html, justify='left')
                plot.setLabel("left", "")
                plot.showGrid(x=self.show_x_grid, y=self.show_y_grid, alpha=0.3)
                plot.getAxis('left').setWidth(65)

                if first_plot is None:
                    first_plot = plot
                    self.legend = pg.LegendItem(offset=(-10, 10))
                    self.legend.setParentItem(first_plot)
                    self.legend.setVisible(self.show_legend)
                    if self.is_dark:
                        self.legend.setBrush(pg.mkBrush(30, 33, 38, 220))
                        self.legend.setPen(pg.mkPen(80, 80, 80))
                    else:
                        self.legend.setBrush(pg.mkBrush(245, 245, 245, 220))
                        self.legend.setPen(pg.mkPen(200, 200, 200))

                    # Populate the shared legend for ALL selected laps across all loaded sessions
                    for session_id, lap_num, color in self.selected_laps_info:
                        session = self.sessions.get(session_id)
                        session_name = session.name if session else session_id
                        default_name = f"{session_name} L{lap_num}"
                        curve_name = self.custom_lap_labels.get((session_id, lap_num), default_name)
                        sample_curve = pg.PlotDataItem(pen=pg.mkPen(color=color, width=2.5))
                        self.legend.addItem(sample_curve, curve_name)
                else:
                    plot.setXLink(first_plot)

                if row == len(self.selected_channels) - 1:
                    plot.getAxis("bottom").setStyle(showValues=True)
                    plot.getAxis("bottom").setHeight(40)
                    plot.setLabel("bottom", f"{self.x_axis_channel}")
                else:
                    # Keep bottom axis active to render X grid lines, but without text numbers
                    plot.getAxis("bottom").setStyle(showValues=False, tickLength=0)
                    plot.getAxis("bottom").setHeight(0)

                # Synchronized vertical crosshair
                v_line = pg.InfiniteLine(
                    angle=90, movable=False,
                    pen=pg.mkPen(CROSSHAIR_LINE_COLOR, width=1, style=Qt.DashLine)
                )
                v_line.setVisible(self.show_cursor_values)
                plot.addItem(v_line, ignoreBounds=True)
                self.v_lines.append(v_line)

                self.plot_widgets[channel_name] = plot

                # Plot curves and create tracking dots for each selected lap
                for session_id, lap_num, color in self.selected_laps_info:
                    if session_id not in self.sessions:
                        continue
                    session = self.sessions[session_id]
                    lap = session.get_lap(lap_num)
                    if not lap:
                        continue

                    raw_x = lap.get_channel(self.x_axis_slug)
                    raw_y = lap.get_channel(channel_name)

                    if raw_x is not None and raw_y is not None and len(raw_x) > 0 and len(raw_y) > 0:
                        if np.isnan(raw_x[0]):
                            valid_x0_indices = np.where(~np.isnan(raw_x))[0]
                            if len(valid_x0_indices) == 0:
                                continue
                            x0 = raw_x[valid_x0_indices[0]]
                        else:
                            x0 = raw_x[0]
                        x_normalized = raw_x - x0
                        pen = pg.mkPen(color=color, width=1.8)

                        curve = plot.plot(x_normalized, raw_y, pen=pen)

                        # Create tracking dot for this curve
                        dot_pen = pg.mkPen("#FFFFFF" if self.is_dark else "#000000", width=1.2)
                        dot = pg.ScatterPlotItem(
                            size=8,
                            brush=pg.mkBrush(color),
                            pen=dot_pen,
                            symbol='o'
                        )
                        dot.setZValue(10)
                        dot.setVisible(self.show_cursor_values)
                        plot.addItem(dot, ignoreBounds=True)
                        self.tracking_dots.append((dot, session_id, lap_num, channel_name))

            self._update_row_heights()

            # Apply auto-range only if no manual zoom or pan has occurred
            if not self.has_manual_zoom_or_pan:
                self._on_autorange()
            else:
                # Restore preserved manual zoom / view ranges
                if self.saved_x_range is not None and first_plot is not None:
                    first_plot.setXRange(self.saved_x_range[0], self.saved_x_range[1], padding=0)
                for ch, plot in self.plot_widgets.items():
                    if ch in self.saved_y_ranges:
                        y_range = self.saved_y_ranges[ch]
                        plot.setYRange(y_range[0], y_range[1], padding=0)
                    else:
                        plot.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
                        plot.autoRange(axis=pg.ViewBox.YAxis)
        finally:
            self.glw.scene().blockSignals(False)
            self._is_rebuilding = False

    def _on_mouse_moved(self, evt):
        if getattr(self, "_is_rebuilding", False) or not self.plot_widgets or not self.show_cursor_values:
            return

        try:
            first_plot = list(self.plot_widgets.values())[0]
            if not first_plot or not hasattr(first_plot, "vb") or first_plot.vb is None:
                return
            mouse_point = first_plot.vb.mapSceneToView(evt)
            x_val = mouse_point.x()
        except Exception:
            return

        # Update crosshair position on all stacked plots
        for v_line in self.v_lines:
            try:
                v_line.setPos(x_val)
            except Exception:
                pass

        title_color = "#E0E0E0" if self.is_dark else "#202020"
        samples: Dict[Tuple[str, int, str], Optional[Tuple[float, float]]] = {}

        # Update tracking dots position on every curve (snapping directly to nearest actual curve vertex)
        for dot, session_id, lap_num, channel_name in self.tracking_dots:
            try:
                session = self.sessions.get(session_id)
                if not session:
                    dot.setData(x=[], y=[])
                    continue
                lap = session.get_lap(lap_num)
                if not lap:
                    dot.setData(x=[], y=[])
                    continue

                raw_x = lap.get_channel(self.x_axis_slug)
                raw_y = lap.get_channel(channel_name)

                sample = _get_nearest_channel_sample(raw_x, raw_y, x_val)
                samples[(session_id, lap_num, channel_name)] = sample
                if sample is not None:
                    actual_x, actual_y = sample
                    dot.setData(x=[actual_x], y=[actual_y])
                    dot.setVisible(True)
                else:
                    dot.setData(x=[], y=[])
            except Exception:
                pass

        # Update each plot's header directly with its current channel values using cached samples
        for channel_name, plot in self.plot_widgets.items():
            try:
                display_label = channel_name
                if self.state_manager:
                    display_label = self.state_manager.get_label_by_slug(channel_name, channel_name)
                title_parts = [f"<span style='color:{title_color}; font-weight:bold; font-size:10pt;'>{display_label}</span>"]

                for session_id, lap_num, color in self.selected_laps_info:
                    sample = samples.get((session_id, lap_num, channel_name))
                    if sample is not None:
                        _, actual_y = sample
                        title_parts.append(f"<span style='color:{color}; font-weight:bold; font-size:10pt;'>{actual_y:.2f}</span>")

                full_title = " &nbsp;&nbsp;|&nbsp;&nbsp; ".join(title_parts)
                plot.setTitle(full_title, justify='left')
            except Exception:
                pass

    def get_view_state(self) -> Dict[str, Any]:
        """Returns current graph view state dictionary for persistence, including zoom/pan states."""
        if self.has_manual_zoom_or_pan and self.plot_widgets:
            self._record_current_view_ranges()

        return {
            "show_x_grid": self.show_x_grid,
            "show_y_grid": self.show_y_grid,
            "show_cursor_values": self.show_cursor_values,
            "show_legend": self.show_legend,
            "x_axis_slug": self.x_axis_slug,
            "has_manual_zoom_or_pan": self.has_manual_zoom_or_pan,
            "saved_x_range": self.saved_x_range,
            "saved_y_ranges": self.saved_y_ranges,
        }

    def set_view_state(self, state: Dict[str, Any]):
        """Restores graph view settings and zoom states from persistent state."""
        if not state:
            return

        if "show_x_grid" in state:
            self.show_x_grid = bool(state["show_x_grid"])
            self.btn_x_grid.setChecked(self.show_x_grid)

        if "show_y_grid" in state:
            self.show_y_grid = bool(state["show_y_grid"])
            self.btn_y_grid.setChecked(self.show_y_grid)

        if "show_cursor_values" in state:
            self.show_cursor_values = bool(state["show_cursor_values"])
            self.btn_cursor.setChecked(self.show_cursor_values)

        if "show_legend" in state:
            self.show_legend = bool(state["show_legend"])
            self.btn_legend.setChecked(self.show_legend)

        if "x_axis_slug" in state:
            slug = state["x_axis_slug"]
            if slug in (STD_CH_LAP_TIME_SLUG, STD_CH_LAP_DIST_SLUG):
                self.x_axis_slug = slug
                for idx in range(self.x_axis_combo.count()):
                    if self.x_axis_combo.itemData(idx) == slug:
                        self.x_axis_combo.setCurrentIndex(idx)
                        break

        if "has_manual_zoom_or_pan" in state:
            self.has_manual_zoom_or_pan = bool(state["has_manual_zoom_or_pan"])

        if "saved_x_range" in state and isinstance(state["saved_x_range"], list):
            self.saved_x_range = [float(x) for x in state["saved_x_range"]]

        if "saved_y_ranges" in state and isinstance(state["saved_y_ranges"], dict):
            self.saved_y_ranges = {
                k: [float(v[0]), float(v[1])]
                for k, v in state["saved_y_ranges"].items()
                if isinstance(v, list) and len(v) >= 2
            }

        # Apply zoom ranges directly if plot widgets are already populated
        if self.has_manual_zoom_or_pan and self.plot_widgets:
            first_plot = list(self.plot_widgets.values())[0]
            if self.saved_x_range is not None and first_plot is not None:
                first_plot.setXRange(self.saved_x_range[0], self.saved_x_range[1], padding=0)
            for ch, plot in self.plot_widgets.items():
                if ch in self.saved_y_ranges:
                    y_range = self.saved_y_ranges[ch]
                    plot.setYRange(y_range[0], y_range[1], padding=0)

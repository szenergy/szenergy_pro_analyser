"""
PyQtGraph-based main view displaying vertically stacked, synchronized plots for selected channels.
Normalizes lap X-axis data for accurate lap overlay comparisons.
Features toolbar icon toggle buttons for X/Y grids, cursor values, legend labels, custom legend renaming, and auto-ranging.
Displays tracking dots on each curve at the cursor crosshair position.
Ensures equal viewbox heights across all stacked plots and full X-axis grid support on every plot.
"""

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
    STD_CHANNEL_TIME, STD_CHANNEL_DISTANCE,
    SLUG_TIME, SLUG_DISTANCE
)


def create_icon_x_grid(is_dark: bool) -> QIcon:
    """Draws a crisp vector icon representing vertical X-axis grid lines."""
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    fg = QColor("#E0E0E0" if is_dark else "#2A2E33")
    pen = QPen(fg, 1.4)
    painter.setPen(pen)
    painter.drawRoundedRect(3, 3, 18, 18, 2, 2)
    # Vertical grid lines
    pen.setStyle(Qt.DotLine)
    painter.setPen(pen)
    painter.drawLine(9, 4, 9, 20)
    painter.drawLine(15, 4, 15, 20)
    painter.end()
    return QIcon(pixmap)


def create_icon_y_grid(is_dark: bool) -> QIcon:
    """Draws a crisp vector icon representing horizontal Y-axis grid lines."""
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    fg = QColor("#E0E0E0" if is_dark else "#2A2E33")
    pen = QPen(fg, 1.4)
    painter.setPen(pen)
    painter.drawRoundedRect(3, 3, 18, 18, 2, 2)
    # Horizontal grid lines
    pen.setStyle(Qt.DotLine)
    painter.setPen(pen)
    painter.drawLine(4, 9, 20, 9)
    painter.drawLine(4, 15, 20, 15)
    painter.end()
    return QIcon(pixmap)


def create_icon_cursor(is_dark: bool) -> QIcon:
    """Draws a vector crosshair icon for cursor tracking and value displays."""
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    fg = QColor("#E0E0E0" if is_dark else "#2A2E33")
    pen = QPen(fg, 1.4)
    painter.setPen(pen)
    painter.drawEllipse(5, 5, 14, 14)
    painter.drawLine(12, 1, 12, 6)
    painter.drawLine(12, 18, 12, 23)
    painter.drawLine(1, 12, 6, 12)
    painter.drawLine(18, 12, 23, 12)
    painter.setBrush(fg)
    painter.drawEllipse(11, 11, 2, 2)
    painter.end()
    return QIcon(pixmap)


def create_icon_legend(is_dark: bool) -> QIcon:
    """Draws a vector legend list/label icon."""
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    fg = QColor("#E0E0E0" if is_dark else "#2A2E33")
    pen = QPen(fg, 1.5)
    painter.setPen(pen)
    painter.setBrush(fg)
    # 3 lines with bullet dots
    painter.drawEllipse(3, 4, 3, 3)
    painter.drawLine(9, 5, 21, 5)
    painter.drawEllipse(3, 11, 3, 3)
    painter.drawLine(9, 12, 21, 12)
    painter.drawEllipse(3, 18, 3, 3)
    painter.drawLine(9, 19, 21, 19)
    painter.end()
    return QIcon(pixmap)


def create_icon_rename_legend(is_dark: bool) -> QIcon:
    """Draws a vector tag icon for renaming curve/legend labels."""
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    fg = QColor("#E0E0E0" if is_dark else "#2A2E33")
    pen = QPen(fg, 1.5)
    painter.setPen(pen)
    tag = QPolygonF([
        QPointF(3, 12),
        QPointF(9, 4),
        QPointF(20, 4),
        QPointF(20, 20),
        QPointF(9, 20),
    ])
    painter.drawPolygon(tag)
    painter.drawEllipse(14, 10, 3, 3)
    painter.drawLine(6, 12, 10, 12)
    painter.end()
    return QIcon(pixmap)


def create_icon_autorange(is_dark: bool) -> QIcon:
    """Draws a vector expand/auto-range icon with 4 corner brackets."""
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    fg = QColor("#E0E0E0" if is_dark else "#2A2E33")
    pen = QPen(fg, 1.6)
    painter.setPen(pen)
    painter.drawLine(3, 8, 3, 3)
    painter.drawLine(3, 3, 8, 3)
    painter.drawLine(16, 3, 21, 3)
    painter.drawLine(21, 3, 21, 8)
    painter.drawLine(3, 16, 3, 21)
    painter.drawLine(3, 21, 8, 21)
    painter.drawLine(16, 21, 21, 21)
    painter.drawLine(21, 21, 21, 16)
    painter.end()
    return QIcon(pixmap)


def _get_nearest_channel_sample(
    raw_x: Optional[np.ndarray], raw_y: Optional[np.ndarray], x_val: float
) -> Optional[Tuple[float, float]]:
    """
    Finds the exact nearest recorded data point (actual_x, actual_y) on the plotted curve
    closest to x_val without any linear interpolation.
    """
    if raw_x is None or raw_y is None or len(raw_x) == 0 or len(raw_y) == 0:
        return None

    min_len = min(len(raw_x), len(raw_y))
    x_arr = np.asarray(raw_x[:min_len], dtype=float)
    y_arr = np.asarray(raw_y[:min_len], dtype=float)

    if np.isnan(x_arr[0]):
        valid_x0_indices = np.where(~np.isnan(x_arr))[0]
        if len(valid_x0_indices) == 0:
            return None
        x0 = x_arr[valid_x0_indices[0]]
    else:
        x0 = x_arr[0]

    x_norm = x_arr - x0

    valid_mask = ~(np.isnan(x_norm) | np.isnan(y_arr) | np.isinf(x_norm) | np.isinf(y_arr))
    if not np.any(valid_mask):
        return None

    valid_x = x_norm[valid_mask]
    valid_y = y_arr[valid_mask]

    # Bounds check: ensure cursor is within the lap's actual range
    if x_val < valid_x.min() or x_val > valid_x.max():
        return None

    # Snap to nearest actual recorded telemetry point on the curve
    nearest_idx = int(np.argmin(np.abs(valid_x - x_val)))
    return float(valid_x[nearest_idx]), float(valid_y[nearest_idx])


class XZoomViewBox(pg.ViewBox):
    """
    Custom PyQtGraph ViewBox providing 1D horizontal (X-axis) or vertical (Y-axis) click-and-drag selection zoom.
    Automatically detects whether user wants X or Y zoom based on dominant mouse drag delta.
    - X-axis zoom (dx >= dy): Synchronized full-height selection highlight across all stacked graphs; zooms X on release.
    - Y-axis zoom (dy > dx): Single-plot full-width selection highlight; zooms Y only on the active graph on release.
    Pressing Escape cancels the ongoing drag.
    """

    def __init__(self, graph_widget: Optional['GraphViewWidget'] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.graph_widget = graph_widget
        self._is_dragging: bool = False
        self._drag_canceled: bool = False
        self._setup_scale_box()

    def _setup_scale_box(self):
        is_dark = True
        if self.graph_widget is not None:
            is_dark = getattr(self.graph_widget, "is_dark", True)
        self.update_theme(is_dark)

    def update_theme(self, is_dark: bool):
        color_hex = "#00E676" if is_dark else "#00C853"
        fill_color = QColor(0, 230, 118, 45) if is_dark else QColor(0, 200, 83, 40)
        self.rbScaleBox.setPen(pg.mkPen(color_hex, width=1.5, style=Qt.DashLine))
        self.rbScaleBox.setBrush(pg.mkBrush(fill_color))

    def show_x_drag_box(self, x_min_data: float, x_max_data: float):
        """Updates and renders the X-axis selection rectangle across the full height of this ViewBox."""
        pt1 = self.mapFromView(QPointF(x_min_data, 0))
        pt2 = self.mapFromView(QPointF(x_max_data, 0))
        self.updateScaleBox(QPointF(pt1.x(), 0), QPointF(pt2.x(), self.height()))

    def show_y_drag_box(self, y1_px: float, y2_px: float):
        """Updates and renders the Y-axis selection rectangle across the full width of this ViewBox."""
        self.updateScaleBox(QPointF(0, y1_px), QPointF(self.width(), y2_px))

    def cancel_drag(self) -> bool:
        """Cancels an in-progress drag selection and hides the selection rectangle."""
        had_drag = self._is_dragging or self._drag_canceled
        self._drag_canceled = True
        self._is_dragging = False
        self.rbScaleBox.hide()
        return had_drag

    def mouseDragEvent(self, ev, axis=None):
        if ev.button() == Qt.MouseButton.LeftButton:
            ev.accept()
            p1 = ev.buttonDownPos()
            p2 = ev.pos()
            dx = abs(p2.x() - p1.x())
            dy = abs(p2.y() - p1.y())
            v1 = self.mapToView(p1)
            v2 = self.mapToView(p2)

            if ev.isFinish():
                was_canceled = self._drag_canceled
                self._is_dragging = False
                self._drag_canceled = False

                if self.graph_widget is not None:
                    self.graph_widget.hide_drag_selection()
                else:
                    self.rbScaleBox.hide()

                if was_canceled:
                    return

                if dx >= dy:
                    # X-axis zoom: applied to ALL stacked charts
                    x_min_data = min(v1.x(), v2.x())
                    x_max_data = max(v1.x(), v2.x())
                    if dx > 5 and (x_max_data - x_min_data) > 1e-6:
                        if not np.isnan(x_min_data) and not np.isnan(x_max_data) and not np.isinf(x_min_data) and not np.isinf(x_max_data):
                            if self.graph_widget is not None:
                                self.graph_widget.zoom_x_range(x_min_data, x_max_data)
                            else:
                                self.setXRange(x_min_data, x_max_data, padding=0)
                else:
                    # Y-axis zoom: applied ONLY to this specific chart
                    y_min_data = min(v1.y(), v2.y())
                    y_max_data = max(v1.y(), v2.y())
                    if dy > 5 and (y_max_data - y_min_data) > 1e-6:
                        if not np.isnan(y_min_data) and not np.isnan(y_max_data) and not np.isinf(y_min_data) and not np.isinf(y_max_data):
                            self.setYRange(y_min_data, y_max_data, padding=0)
                            if self.graph_widget is not None:
                                self.graph_widget.mark_manual_zoom_or_pan()
            else:
                if self._drag_canceled:
                    return
                self._is_dragging = True
                if dx >= dy:
                    # Show X selection across all stacked plots
                    x_min_data = min(v1.x(), v2.x())
                    x_max_data = max(v1.x(), v2.x())
                    if (x_max_data - x_min_data) > 0 and not np.isnan(x_min_data) and not np.isnan(x_max_data):
                        if self.graph_widget is not None:
                            self.graph_widget.show_drag_selection(x_min_data, x_max_data)
                        else:
                            self.show_x_drag_box(x_min_data, x_max_data)
                else:
                    # Show Y selection ONLY on this specific plot
                    if self.graph_widget is not None:
                        self.graph_widget.hide_drag_selection_except(self)
                    self.show_y_drag_box(p1.y(), p2.y())
        else:
            super().mouseDragEvent(ev, axis=axis)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape and (self._is_dragging or self._drag_canceled):
            if self.graph_widget is not None:
                self.graph_widget.cancel_drag_selection()
            else:
                self.cancel_drag()
            ev.accept()
            return
        super().keyPressEvent(ev)


class GraphViewWidget(QWidget):
    """Main plotting area with vertically stacked charts, toolbar toggles, and on-graph value readouts."""

    def __init__(self, parent=None, state_manager=None):
        super().__init__(parent)
        self.state_manager = state_manager
        self.sessions: Dict[str, Session] = {}
        self.selected_channels: List[str] = []
        self.selected_laps_info: List[Tuple[str, int, str]] = []
        self.custom_lap_labels: Dict[Tuple[str, int], str] = {}
        self.x_axis_slug: str = SLUG_TIME
        self.time_label: str = STD_CHANNEL_TIME
        self.dist_label: str = STD_CHANNEL_DISTANCE
        self.is_dark: bool = True

        # State tracking for zoom/pan preservation
        self.has_manual_zoom_or_pan: bool = False
        self.saved_x_range: Optional[List[float]] = None
        self.saved_y_ranges: Dict[str, List[float]] = {}

        # View and Display toggles
        self.show_x_grid: bool = False
        self.show_y_grid: bool = True
        self.show_cursor_values: bool = True
        self.show_legend: bool = True
        self._is_rebuilding: bool = False

        self.plot_widgets: Dict[str, pg.PlotItem] = {}
        self.v_lines: List[pg.InfiniteLine] = []
        self.tracking_dots: List[Tuple[pg.ScatterPlotItem, str, int, str]] = []
        self.legend: Optional[pg.LegendItem] = None

        self._init_ui()

    @property
    def x_axis_channel(self) -> str:
        """Returns the active display label for the selected X-axis slug."""
        return self.dist_label if self.x_axis_slug == SLUG_DISTANCE else self.time_label

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

        c_layout.addStretch()

        # 7. X-Axis Selector (Using immutable Slugs as userData)
        c_layout.addWidget(QLabel("<b>X-Axis:</b>"))
        self.x_axis_combo = QComboBox()
        self.x_axis_combo.addItem(self.time_label, userData=SLUG_TIME)
        self.x_axis_combo.addItem(self.dist_label, userData=SLUG_DISTANCE)
        self.x_axis_combo.currentIndexChanged.connect(self._on_x_axis_changed)
        c_layout.addWidget(self.x_axis_combo)

        layout.addWidget(self.control_bar)

        # PyQtGraph Layout Container
        self.glw = pg.GraphicsLayoutWidget()
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
        self.x_axis_combo.addItem(self.time_label, userData=SLUG_TIME)
        self.x_axis_combo.addItem(self.dist_label, userData=SLUG_DISTANCE)

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
        self.selected_channels = sorted(list(channels))
        self.rebuild_plots()

    def set_selected_laps(self, laps_info: List[Tuple[str, int, str]]):
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

    def rebuild_plots(self):
        self._is_rebuilding = True
        try:
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
                    pen=pg.mkPen("#FFD740", width=1, style=Qt.DashLine)
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
                        x_normalized = raw_x - raw_x[0]
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
                if sample is not None:
                    actual_x, actual_y = sample
                    dot.setData(x=[actual_x], y=[actual_y])
                    dot.setVisible(True)
                else:
                    dot.setData(x=[], y=[])
            except Exception:
                pass

        # Update each plot's header directly with its current channel values
        for channel_name, plot in list(self.plot_widgets.items()):
            try:
                display_label = channel_name
                if self.state_manager:
                    display_label = self.state_manager.get_label_by_slug(channel_name, channel_name)
                title_parts = [f"<span style='color:{title_color}; font-weight:bold; font-size:10pt;'>{display_label}</span>"]

                for session_id, lap_num, color in self.selected_laps_info:
                    session = self.sessions.get(session_id)
                    if not session:
                        continue
                    lap = session.get_lap(lap_num)
                    if not lap:
                        continue

                    raw_x = lap.get_channel(self.x_axis_slug)
                    raw_y = lap.get_channel(channel_name)

                    sample = _get_nearest_channel_sample(raw_x, raw_y, x_val)
                    if sample is not None:
                        _, actual_y = sample
                        title_parts.append(f"<span style='color:{color}; font-weight:bold; font-size:10pt;'>{actual_y:.2f}</span>")

                full_title = " &nbsp;&nbsp;|&nbsp;&nbsp; ".join(title_parts)
                plot.setTitle(full_title, justify='left')
            except Exception:
                pass

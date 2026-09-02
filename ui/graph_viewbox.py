"""
Custom PyQtGraph ViewBox supporting 1D X/Y selection zoom, Escape cancel, and nearest curve point sampling.
"""

import weakref
from typing import Optional, Tuple
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor


def _get_nearest_channel_sample(
    raw_x: Optional[np.ndarray], raw_y: Optional[np.ndarray], x_val: float
) -> Optional[Tuple[float, float]]:
    """
    Finds the exact nearest recorded data point (actual_x, actual_y) on the plotted curve
    closest to x_val without any linear interpolation.
    Uses high-performance O(log N) binary search for monotonic telemetry X-axis arrays.
    """
    if raw_x is None or raw_y is None or len(raw_x) == 0 or len(raw_y) == 0:
        return None

    min_len = min(len(raw_x), len(raw_y))
    if min_len == 0:
        return None

    x_arr = np.asarray(raw_x[:min_len], dtype=float)
    y_arr = np.asarray(raw_y[:min_len], dtype=float)

    x_first = x_arr[0]
    x_last = x_arr[-1]

    # Fast path: Monotonically increasing X data (standard lap time or distance)
    if x_last >= x_first:
        if x_val < x_first or x_val > x_last:
            return None

        idx = int(np.searchsorted(x_arr, x_val))
        if idx <= 0:
            best_idx = 0
        elif idx >= min_len:
            best_idx = min_len - 1
        else:
            if abs(x_arr[idx] - x_val) < abs(x_arr[idx - 1] - x_val):
                best_idx = idx
            else:
                best_idx = idx - 1

        val_x = float(x_arr[best_idx])
        val_y = float(y_arr[best_idx])

        # Validate non-nan/inf
        if np.isnan(val_x) or np.isnan(val_y) or np.isinf(val_x) or np.isinf(val_y):
            valid_mask = ~(np.isnan(x_arr) | np.isnan(y_arr) | np.isinf(x_arr) | np.isinf(y_arr))
            if not np.any(valid_mask):
                return None
            valid_x = x_arr[valid_mask]
            valid_y = y_arr[valid_mask]
            if len(valid_x) == 0 or x_val < valid_x[0] or x_val > valid_x[-1]:
                return None
            idx_v = int(np.searchsorted(valid_x, x_val))
            if idx_v <= 0:
                b_idx = 0
            elif idx_v >= len(valid_x):
                b_idx = len(valid_x) - 1
            else:
                b_idx = idx_v if abs(valid_x[idx_v] - x_val) < abs(valid_x[idx_v - 1] - x_val) else idx_v - 1
            return float(valid_x[b_idx]), float(valid_y[b_idx])

        return val_x, val_y
    else:
        # Fallback for non-monotonic or inverted series
        valid_mask = ~(np.isnan(x_arr) | np.isnan(y_arr) | np.isinf(x_arr) | np.isinf(y_arr))
        if not np.any(valid_mask):
            return None
        valid_x = x_arr[valid_mask]
        valid_y = y_arr[valid_mask]
        if len(valid_x) == 0 or x_val < valid_x.min() or x_val > valid_x.max():
            return None
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

    def __init__(self, graph_widget=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._graph_widget_ref = weakref.ref(graph_widget) if graph_widget is not None else None
        self.setMenuEnabled(False)
        self.menu = None
        self._is_dragging: bool = False
        self._drag_canceled: bool = False
        self._setup_scale_box()

    @property
    def graph_widget(self):
        return self._graph_widget_ref() if self._graph_widget_ref is not None else None

    @graph_widget.setter
    def graph_widget(self, val):
        self._graph_widget_ref = weakref.ref(val) if val is not None else None

    def mouseClickEvent(self, ev):
        if ev.button() == Qt.MouseButton.RightButton:
            ev.accept()
            return
        super().mouseClickEvent(ev)

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

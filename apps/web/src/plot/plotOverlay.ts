/**
 * Canvas2D overlay renderer for stacked telemetry plots:
 * - Nice engineering axis ticks & X/Y gridlines
 * - Plot header titles + colored above-graph cursor value readouts
 * - Synchronized vertical dashed crosshair + clamped bottom X-axis pill
 * - Collision-avoiding stacked on-graph tracking labels with right-edge flip
 * - X-axis (all plots) and Y-axis (single plot) green drag-zoom selection boxes
 */

export interface PlotLayoutBox {
  plotKey: string;
  displayLabel: string;
  channelSlug?: string;
  lapInfo?: { sessionId: string; lapNumber: number };
  ySuffix?: string;
  /** Outer box for this stacked row (CSS px) */
  rowTop: number;
  rowHeight: number;
  /** Actual WebGL plot viewport box inside margins (CSS px) */
  plotLeft: number;
  plotTop: number;
  plotWidth: number;
  plotHeight: number;
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
}

export interface OverlaySampleDot {
  seriesKey: string;
  color: string;
  actualX: number;
  actualY: number;
  plotY: number;
}

export interface OverlayDragBox {
  mode: 'x' | 'y';
  /** For mode 'y', the target plotKey; for 'x', applies across all plots */
  plotKey?: string;
  startPx: number;
  currPx: number;
}

export interface OverlayRenderParams {
  width: number;
  height: number;
  isDark: boolean;
  showXGrid: boolean;
  showYGrid: boolean;
  showCursorValues: boolean;
  showCursorOnGraph: boolean;
  showCursorAboveGraph: boolean;
  xAxisLabel: string;
  cursorX: number | null;
  plots: PlotLayoutBox[];
  samplesByPlot: Map<string, OverlaySampleDot[]>;
  dragBox: OverlayDragBox | null;
}

export const LEFT_AXIS_WIDTH = 65;
export const RIGHT_MARGIN = 14;
export const HEADER_HEIGHT = 24;
export const BOTTOM_AXIS_HEIGHT = 36;
export const ROW_GAP = 6;

export function computeNiceTicks(min: number, max: number, targetCount: number): number[] {
  const span = max - min;
  if (!Number.isFinite(span) || span <= 0 || targetCount <= 0) return [];
  const rawStep = span / targetCount;
  const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const norm = rawStep / mag;
  let stepMag: number;
  if (norm < 1.5) stepMag = 1;
  else if (norm < 3.5) stepMag = 2;
  else if (norm < 7.5) stepMag = 5;
  else stepMag = 10;
  const step = stepMag * mag;
  if (!Number.isFinite(step) || step <= 0) return [];

  const first = Math.ceil(min / step) * step;
  const ticks: number[] = [];
  for (let v = first; v <= max + step * 1e-9 && ticks.length < 64; v += step) {
    // Avoid -0
    ticks.push(Math.abs(v) < step * 1e-9 ? 0 : v);
  }
  return ticks;
}

export function formatTickValue(val: number, span: number): string {
  if (!Number.isFinite(val)) return '';
  if (Math.abs(val) < 1e-12) return '0';
  const abs = Math.abs(val);
  if (abs >= 1e5 || (abs > 0 && abs < 1e-3)) {
    return val.toExponential(2);
  }
  if (span < 0.1) return val.toFixed(3);
  if (span < 2) return val.toFixed(2);
  if (span < 50) return val.toFixed(1);
  return Math.round(val).toString();
}

export function renderPlotOverlay(canvas: HTMLCanvasElement, params: OverlayRenderParams) {
  const { width, height, isDark } = params;
  const dpr = window.devicePixelRatio || 1;
  const targetW = Math.max(1, Math.round(width * dpr));
  const targetH = Math.max(1, Math.round(height * dpr));
  if (canvas.width !== targetW || canvas.height !== targetH) {
    canvas.width = targetW;
    canvas.height = targetH;
  }

  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  ctx.save();
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, width, height);

  if (params.plots.length === 0) {
    ctx.fillStyle = '#808080';
    ctx.font = '14px system-ui, -apple-system, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('Select laps and channels from the left sidebar to display graphs.', width / 2, height / 2);
    ctx.restore();
    return;
  }

  const fgColor = isDark ? '#E0E0E0' : '#202020';
  const mutedColor = isDark ? '#9BA3AF' : '#5F6368';
  const borderColor = isDark ? '#3A3F47' : '#D0D5DD';
  const gridColor = isDark ? 'rgba(255,255,255,0.14)' : 'rgba(0,0,0,0.12)';
  const bgColor = isDark ? '#191B1F' : '#FFFFFF';
  const valueTextColor = isDark ? '#E0E0E0' : '#000000';

  const lastIdx = params.plots.length - 1;

  for (let i = 0; i < params.plots.length; i++) {
    const p = params.plots[i];
    const spanX = p.xMax - p.xMin;
    const spanY = p.yMax - p.yMin;
    const xTicks = computeNiceTicks(p.xMin, p.xMax, Math.max(3, Math.floor(p.plotWidth / 95)));
    const yTicks = computeNiceTicks(p.yMin, p.yMax, Math.max(2, Math.floor(p.plotHeight / 42)));

    // 1. Header title + above-graph cursor values
    ctx.save();
    ctx.beginPath();
    ctx.rect(p.plotLeft, p.rowTop, Math.max(0, width - p.plotLeft - RIGHT_MARGIN), HEADER_HEIGHT);
    ctx.clip();

    ctx.font = '600 12px system-ui, -apple-system, sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = fgColor;
    const titleY = p.rowTop + HEADER_HEIGHT * 0.5;
    let cursorTextX = p.plotLeft + 2;
    ctx.fillText(p.displayLabel, cursorTextX, titleY);
    cursorTextX += ctx.measureText(p.displayLabel).width + 14;

    if (params.showCursorValues && params.showCursorAboveGraph && params.cursorX !== null) {
      const dots = params.samplesByPlot.get(p.plotKey) || [];
      for (const dot of dots) {
        if (!Number.isFinite(dot.actualY)) continue;
        // Color bar ▌
        ctx.fillStyle = dot.color;
        ctx.fillRect(cursorTextX, titleY - 6, 4, 12);
        cursorTextX += 7;

        const valStr = dot.actualY.toFixed(2);
        ctx.font = '500 12px ui-monospace, SFMono-Regular, Menlo, monospace';
        ctx.fillStyle = valueTextColor;
        ctx.fillText(valStr, cursorTextX, titleY);
        cursorTextX += ctx.measureText(valStr).width + 12;
      }
    }
    ctx.restore();

    // 2. Gridlines clipped to plot viewport
    ctx.save();
    ctx.beginPath();
    ctx.rect(p.plotLeft, p.plotTop, p.plotWidth, p.plotHeight);
    ctx.clip();

    ctx.strokeStyle = gridColor;
    ctx.lineWidth = 1;

    if (params.showXGrid && spanX > 0) {
      ctx.beginPath();
      for (const tx of xTicks) {
        const px = Math.round(p.plotLeft + ((tx - p.xMin) / spanX) * p.plotWidth) + 0.5;
        ctx.moveTo(px, p.plotTop);
        ctx.lineTo(px, p.plotTop + p.plotHeight);
      }
      ctx.stroke();
    }

    if (params.showYGrid && spanY > 0) {
      ctx.beginPath();
      for (const ty of yTicks) {
        const py = Math.round(p.plotTop + p.plotHeight - ((ty - p.yMin) / spanY) * p.plotHeight) + 0.5;
        ctx.moveTo(p.plotLeft, py);
        ctx.lineTo(p.plotLeft + p.plotWidth, py);
      }
      ctx.stroke();
    }

    // 3. Synchronized vertical dashed crosshair inside plot
    if (params.showCursorValues && params.cursorX !== null && spanX > 0) {
      if (params.cursorX >= p.xMin && params.cursorX <= p.xMax) {
        const cxPx = Math.round(p.plotLeft + ((params.cursorX - p.xMin) / spanX) * p.plotWidth) + 0.5;
        ctx.save();
        ctx.strokeStyle = '#FFD740';
        ctx.lineWidth = 1;
        ctx.setLineDash([5, 4]);
        ctx.beginPath();
        ctx.moveTo(cxPx, p.plotTop);
        ctx.lineTo(cxPx, p.plotTop + p.plotHeight);
        ctx.stroke();
        ctx.restore();
      }
    }

    // 4. Collision-avoiding on-graph tracking labels
    if (params.showCursorValues && params.showCursorOnGraph && params.cursorX !== null && spanX > 0 && spanY > 0) {
      const dots = params.samplesByPlot.get(p.plotKey) || [];
      const visibleSamples = dots
        .filter((d) => Number.isFinite(d.actualX) && Number.isFinite(d.plotY) && d.actualX >= p.xMin && d.actualX <= p.xMax)
        .map((d) => ({
          ...d,
          px: p.plotLeft + ((d.actualX - p.xMin) / spanX) * p.plotWidth,
          py: p.plotTop + p.plotHeight - ((d.plotY - p.yMin) / spanY) * p.plotHeight,
        }))
        // Top-to-bottom in screen coords = ascending py (descending actualY)
        .sort((a, b) => b.plotY - a.plotY);

      if (visibleSamples.length > 0) {
        const topLimit = p.plotTop + 12;
        const bottomLimit = p.plotTop + p.plotHeight - 12;
        const totalAvail = Math.max(0, bottomLimit - topLimit);
        const minGap = 18;
        const effectiveGap =
          visibleSamples.length > 1 && (visibleSamples.length - 1) * minGap > totalAvail
            ? totalAvail / (visibleSamples.length - 1)
            : minGap;

        const placed: { layoutPy: number; px: number; actualY: number; color: string }[] = [];
        let prevPy: number | null = null;
        for (const s of visibleSamples) {
          const clampedOrigPy = Math.max(topLimit, Math.min(bottomLimit, s.py));
          const currPy: number = prevPy === null ? clampedOrigPy : Math.max(clampedOrigPy, prevPy + effectiveGap);
          placed.push({ layoutPy: currPy, px: s.px, actualY: s.actualY, color: s.color });
          prevPy = currPy;
        }

        const lowestPy = placed[placed.length - 1].layoutPy;
        if (lowestPy > bottomLimit) {
          const shiftUp = lowestPy - bottomLimit;
          for (const item of placed) {
            item.layoutPy = Math.max(topLimit, item.layoutPy - shiftUp);
          }
        }

        const rightFlipThreshold = p.plotLeft + p.plotWidth - 65;
        ctx.font = '700 11px ui-monospace, SFMono-Regular, Menlo, monospace';
        ctx.textBaseline = 'middle';

        for (const item of placed) {
          const labelText = item.actualY.toFixed(2);
          const flipLeft = item.px > rightFlipThreshold;
          ctx.textAlign = flipLeft ? 'right' : 'left';
          const tx = flipLeft ? item.px - 9 : item.px + 9;

          // Subtle halo for legibility over dense curves
          ctx.lineWidth = 3;
          ctx.strokeStyle = isDark ? 'rgba(25,27,31,0.85)' : 'rgba(255,255,255,0.85)';
          ctx.strokeText(labelText, tx, item.layoutPy);
          ctx.fillStyle = item.color;
          ctx.fillText(labelText, tx, item.layoutPy);
        }
      }
    }

    // 5. Drag zoom selection box
    if (params.dragBox) {
      const boxFill = isDark ? 'rgba(255, 200, 21, 0.18)' : 'rgba(255, 200, 21, 0.22)';
      const boxStroke = isDark ? '#FFC815' : '#D9A700';
      if (params.dragBox.mode === 'x') {
        const x1 = Math.max(p.plotLeft, Math.min(params.dragBox.startPx, params.dragBox.currPx));
        const x2 = Math.min(p.plotLeft + p.plotWidth, Math.max(params.dragBox.startPx, params.dragBox.currPx));
        if (x2 > x1) {
          ctx.fillStyle = boxFill;
          ctx.fillRect(x1, p.plotTop, x2 - x1, p.plotHeight);
          ctx.strokeStyle = boxStroke;
          ctx.lineWidth = 1.5;
          ctx.strokeRect(x1 + 0.5, p.plotTop + 0.5, x2 - x1 - 1, p.plotHeight - 1);
        }
      } else if (params.dragBox.mode === 'y' && params.dragBox.plotKey === p.plotKey) {
        const y1 = Math.max(p.plotTop, Math.min(params.dragBox.startPx, params.dragBox.currPx));
        const y2 = Math.min(p.plotTop + p.plotHeight, Math.max(params.dragBox.startPx, params.dragBox.currPx));
        if (y2 > y1) {
          ctx.fillStyle = boxFill;
          ctx.fillRect(p.plotLeft, y1, p.plotWidth, y2 - y1);
          ctx.strokeStyle = boxStroke;
          ctx.lineWidth = 1.5;
          ctx.strokeRect(p.plotLeft + 0.5, y1 + 0.5, p.plotWidth - 1, y2 - y1 - 1);
        }
      }
    }

    ctx.restore();

    // 6. Plot frame & Y-axis ticks
    ctx.strokeStyle = borderColor;
    ctx.lineWidth = 1;
    ctx.strokeRect(p.plotLeft + 0.5, p.plotTop + 0.5, p.plotWidth - 1, p.plotHeight - 1);

    ctx.font = '11px ui-monospace, SFMono-Regular, Menlo, monospace';
    ctx.fillStyle = mutedColor;
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';

    for (const ty of yTicks) {
      if (spanY <= 0) continue;
      const py = p.plotTop + p.plotHeight - ((ty - p.yMin) / spanY) * p.plotHeight;
      if (py < p.plotTop + 6 || py > p.plotTop + p.plotHeight - 6) continue;
      ctx.beginPath();
      ctx.moveTo(p.plotLeft - 4, Math.round(py) + 0.5);
      ctx.lineTo(p.plotLeft, Math.round(py) + 0.5);
      ctx.stroke();
      const tickText = p.ySuffix ? `${formatTickValue(ty, spanY)}${p.ySuffix}` : formatTickValue(ty, spanY);
      ctx.fillText(tickText, p.plotLeft - 7, py);
    }

    // 7. Bottom X-axis ticks + cursor X pill on bottom plot only
    if (i === lastIdx) {
      const axisY = p.plotTop + p.plotHeight;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      ctx.fillStyle = mutedColor;

      for (const tx of xTicks) {
        if (spanX <= 0) continue;
        const px = p.plotLeft + ((tx - p.xMin) / spanX) * p.plotWidth;
        if (px < p.plotLeft + 16 || px > p.plotLeft + p.plotWidth - 16) continue;
        ctx.beginPath();
        ctx.moveTo(Math.round(px) + 0.5, axisY);
        ctx.lineTo(Math.round(px) + 0.5, axisY + 4);
        ctx.stroke();
        ctx.fillText(formatTickValue(tx, spanX), px, axisY + 6);
      }

      // X-axis label
      ctx.font = '500 11px system-ui, -apple-system, sans-serif';
      ctx.fillStyle = mutedColor;
      ctx.fillText(params.xAxisLabel, p.plotLeft + p.plotWidth * 0.5, axisY + 21);

      // Cursor X tracking pill
      if (params.showCursorValues && params.cursorX !== null && spanX > 0) {
        if (params.cursorX >= p.xMin && params.cursorX <= p.xMax) {
          const text = ` ${params.cursorX.toFixed(2)} `;
          ctx.font = '600 11px ui-monospace, SFMono-Regular, Menlo, monospace';
          const tw = ctx.measureText(text).width + 6;
          const halfW = tw * 0.5;
          const rawX = p.plotLeft + ((params.cursorX - p.xMin) / spanX) * p.plotWidth;
          const clampedX = Math.max(p.plotLeft + halfW, Math.min(p.plotLeft + p.plotWidth - halfW, rawX));

          ctx.fillStyle = bgColor;
          ctx.fillRect(clampedX - halfW, axisY + 2, tw, 17);
          ctx.strokeStyle = '#FFD740';
          ctx.lineWidth = 1;
          ctx.strokeRect(clampedX - halfW + 0.5, axisY + 2.5, tw - 1, 16);
          ctx.fillStyle = fgColor;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(text, clampedX, axisY + 11);
        }
      }
    }
  }

  ctx.restore();
}

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Columns3,
  Crosshair,
  GitCommitHorizontal,
  GripVertical,
  List,
  Maximize2,
  Pencil,
  Percent,
  Rows3,
} from 'lucide-react';
import {
  BOTTOM_AXIS_HEIGHT,
  HEADER_HEIGHT,
  LEFT_AXIS_WIDTH,
  OverlayDragBox,
  OverlaySampleDot,
  PlotLayoutBox,
  renderPlotOverlay,
  RIGHT_MARGIN,
  ROW_GAP,
} from '@/plot/plotOverlay';
import { TrackMapCursorPoint } from '@/plot/trackMapRenderer';
import {
  CurveRenderInput,
  DotRenderInput,
  hexToRgba,
  WebGLCurveRenderer,
} from '@/plot/webglCurves';
import { stateManager } from '@/state/stateManager';
import {
  GraphViewSettings,
  GroupingMode,
  LAP_COLORS,
  SelectedLapInfo,
  SessionSummary,
  STD_CH_LAP_DIST_SLUG,
  STD_CH_LAP_TIME_SLUG,
} from '@/types/telemetry';
import { HoveredPlotBounds, PlotCurveData, PlotDataResponse } from '@/workers/protocol';
import { telemetryClient } from '@/workers/telemetryClient';
export interface GraphViewProps {
  isDark: boolean;
  sessions: SessionSummary[];
  selectedChannels: string[];
  selectedLaps: SelectedLapInfo[];
  channelColors: Record<string, string>;
  customLapLabels: Record<string, string>;
  customChannelLabels: Record<string, string>;
  settings: GraphViewSettings;
  channelsVersion: number;
  onUpdateSettings: (partial: Partial<GraphViewSettings>) => void;
  onOpenRenameLegend: () => void;
  onCursorMapPoints: (points: TrackMapCursorPoint[]) => void;
}
type ActiveInteraction =
  | {
      type: 'zoom';
      pointerId: number;
      startX: number;
      startY: number;
      targetPlot: PlotLayoutBox;
      mode: 'x' | 'y' | null;
    }
  | {
      type: 'pan';
      pointerId: number;
      startX: number;
      startY: number;
      targetPlot: PlotLayoutBox;
      initXMin: number;
      initXMax: number;
      initYMin: number;
      initYMax: number;
      xChanged: boolean;
    };

const TOP_PADDING = 4;

function padYRange(min: number, max: number): [number, number] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0, 1];
  const span = max - min;
  if (span <= 1e-12) {
    const pad = Math.abs(min) > 1 ? Math.abs(min) * 0.05 : 1;
    return [min - pad, max + pad];
  }
  const pad = span * 0.04;
  return [min - pad, max + pad];
}

function normalizeXRange(min: number, max: number): [number, number] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0, 1];
  if (max - min <= 1e-12) {
    const pad = Math.abs(min) > 1 ? Math.abs(min) * 0.05 : 1;
    return [min - pad, max + pad];
  }
  return [min, max];
}

interface PlotSeriesItem {
  plotKey: string;
  title: string;
  channelSlug?: string;
  lapInfo?: { sessionId: string; lapNumber: number };
  ySuffix?: string;
  defaultExtent?: [number, number];
}

function computePlotLayouts(
  width: number,
  height: number,
  items: PlotSeriesItem[],
  xRange: [number, number],
  manualYRanges: Record<string, [number, number]>,
): PlotLayoutBox[] {
  const n = items.length;
  if (n === 0) return [];

  const plotWidth = width - LEFT_AXIS_WIDTH - RIGHT_MARGIN;
  if (plotWidth < 20) return [];

  const reservedHeight =
    TOP_PADDING + BOTTOM_AXIS_HEIGHT + Math.max(0, n - 1) * ROW_GAP + n * HEADER_HEIGHT;
  const totalPlotHeights = height - reservedHeight;
  if (totalPlotHeights < n * 16) return [];

  const plotHeight = totalPlotHeights / n;
  const plots: PlotLayoutBox[] = [];

  for (let i = 0; i < n; i++) {
    const item = items[i];
    const rowTop = TOP_PADDING + i * (HEADER_HEIGHT + plotHeight + ROW_GAP);
    const plotTop = rowTop + HEADER_HEIGHT;
    const rowHeight = HEADER_HEIGHT + plotHeight + (i === n - 1 ? BOTTOM_AXIS_HEIGHT : 0);

    const manualY = manualYRanges[item.plotKey];
    let yMin: number;
    let yMax: number;
    if (manualY) {
      [yMin, yMax] = manualY;
    } else if (item.defaultExtent) {
      [yMin, yMax] = padYRange(item.defaultExtent[0], item.defaultExtent[1]);
    } else {
      yMin = 0;
      yMax = 1;
    }

    plots.push({
      plotKey: item.plotKey,
      displayLabel: item.title,
      channelSlug: item.channelSlug,
      lapInfo: item.lapInfo,
      ySuffix: item.ySuffix,
      rowTop,
      rowHeight,
      plotLeft: LEFT_AXIS_WIDTH,
      plotTop,
      plotWidth,
      plotHeight,
      xMin: xRange[0],
      xMax: xRange[1],
      yMin,
      yMax,
    });
  }

  return plots;
}
export const GraphView: React.FC<GraphViewProps> = ({
  isDark,
  sessions,
  selectedChannels,
  selectedLaps,
  channelColors,
  customLapLabels,
  customChannelLabels,
  settings,
  channelsVersion,
  onUpdateSettings,
  onOpenRenameLegend,
  onCursorMapPoints,
}) => {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const webglCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const overlayCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const legendRef = useRef<HTMLDivElement | null>(null);

  const glRendererRef = useRef<WebGLCurveRenderer | null>(null);
  const [webglError, setWebglError] = useState<string | null>(null);

  // Mutable high-frequency state stored in refs for 60fps canvas rendering
  const viewportSizeRef = useRef({ width: 0, height: 0 });
  const plotDataRef = useRef<PlotDataResponse | null>(null);
  const curvesByPlotRef = useRef<Map<string, PlotCurveData[]>>(new Map());
  const lapYExtentsRef = useRef<Record<string, [number, number]>>({});
  const fullXExtentRef = useRef<[number, number] | null>(null);
  const manualXRangeRef = useRef<[number, number] | null>(null);
  const manualChannelYRangesRef = useRef<Record<string, [number, number]>>({});
  const manualLapYRangesRef = useRef<Record<string, [number, number]>>({});
  const manualNormLapYRangesRef = useRef<Record<string, [number, number]>>({});
  const plotsRef = useRef<PlotLayoutBox[]>([]);

  const cursorXRef = useRef<number | null>(null);
  const cursorSamplesRef = useRef<Map<string, OverlaySampleDot[]>>(new Map());
  const dragBoxRef = useRef<OverlayDragBox | null>(null);
  const interactionRef = useRef<ActiveInteraction | null>(null);
  // Coalescing & sequencing refs
  const plotReqSeqRef = useRef(0);
  const fetchTimerRef = useRef<number | undefined>(undefined);
  const cursorSeqRef = useRef(0);
  const cursorRafRef = useRef<number | null>(null);
  const pendingCursorTargetRef = useRef<{
    targetX: number;
    hovered: HoveredPlotBounds | null;
  } | null>(null);
  const cursorInFlightRef = useRef(false);
  const unmountedRef = useRef(false);

  // Draggable Legend state (null = default top-right CSS anchor)
  const [legendPos, setLegendPos] = useState<{ x: number; y: number } | null>(null);
  const legendDragRef = useRef<{
    pointerId: number;
    offsetX: number;
    offsetY: number;
  } | null>(null);

  // Derived channel group metadata when channelsVersion or xAxisSlug changes
  const channelGroups = useMemo(() => {
    void channelsVersion;
    return stateManager.getChannelGroups();
  }, [channelsVersion]);

  const xAxisOptions = useMemo(() => {
    void channelsVersion;
    return [
      {
        slug: STD_CH_LAP_DIST_SLUG,
        label: stateManager.getDisplayNameByKey(STD_CH_LAP_DIST_SLUG),
      },
      {
        slug: STD_CH_LAP_TIME_SLUG,
        label: stateManager.getDisplayNameByKey(STD_CH_LAP_TIME_SLUG),
      },
    ];
  }, [channelsVersion]);

  const displayLabels = useMemo(() => {
    void channelsVersion;
    const map: Record<string, string> = {};
    for (const slug of selectedChannels) {
      map[slug] = customChannelLabels[slug] || stateManager.getDisplayNameByKey(slug);
    }
    return map;
  }, [selectedChannels, channelsVersion, customChannelLabels]);

  const xAxisLabel = useMemo(() => {
    void channelsVersion;
    return stateManager.getDisplayNameByKey(settings.xAxisSlug);
  }, [settings.xAxisSlug, channelsVersion]);
  const sessionMap = useMemo(() => {
    const map = new Map<string, SessionSummary>();
    for (const s of sessions) {
      map.set(s.id, s);
    }
    return map;
  }, [sessions]);

  const lapLabels = useMemo(() => {
    const map: Record<string, string> = {};
    for (const lap of selectedLaps) {
      const key = `${lap.sessionId}:${lap.lapNumber}`;
      const session = sessionMap.get(lap.sessionId);
      const defaultLabel = `${session ? session.name : lap.sessionId} Lap ${lap.lapNumber}`;
      map[key] = customLapLabels[key] || defaultLabel;
    }
    return map;
  }, [selectedLaps, sessionMap, customLapLabels]);

  // Keep latest props accessible in non-React event callbacks
  const latestPropsRef = useRef({
    isDark,
    sessions,
    selectedChannels,
    selectedLaps,
    channelColors,
    settings,
    channelGroups,
    displayLabels,
    lapLabels,
    xAxisLabel,
    onCursorMapPoints,
  });
  latestPropsRef.current = {
    isDark,
    sessions,
    selectedChannels,
    selectedLaps,
    channelColors,
    settings,
    channelGroups,
    displayLabels,
    lapLabels,
    xAxisLabel,
    onCursorMapPoints,
  };

  const getActiveManualYRanges = useCallback(
    (groupingMode: GroupingMode, normalizeY: boolean): Record<string, [number, number]> => {
      if (groupingMode === 'channel') return manualChannelYRangesRef.current;
      return normalizeY ? manualNormLapYRangesRef.current : manualLapYRangesRef.current;
    },
    [],
  );

  // Core synchronous WebGL2 + Canvas2D frame render
  const renderAll = useCallback(() => {
    const { width, height } = viewportSizeRef.current;
    if (width <= 0 || height <= 0) return;

    const props = latestPropsRef.current;
    const data = plotDataRef.current;
    const rawXExtent = manualXRangeRef.current ?? data?.xExtent ?? fullXExtentRef.current ?? [0, 1];
    const xRange = normalizeXRange(rawXExtent[0], rawXExtent[1]);
    const isByLap = props.settings.groupingMode === 'lap';
    const isNorm = isByLap && props.settings.normalizeY;

    const items: PlotSeriesItem[] = isByLap
      ? props.selectedLaps.map((lap) => {
          const lapKey = `${lap.sessionId}:${lap.lapNumber}`;
          return {
            plotKey: lapKey,
            title: props.lapLabels[lapKey] ?? lapKey,
            lapInfo: { sessionId: lap.sessionId, lapNumber: lap.lapNumber },
            ySuffix: isNorm ? '%' : undefined,
            defaultExtent: isNorm ? [0, 100] : lapYExtentsRef.current[lapKey],
          };
        })
      : props.selectedChannels.map((slug) => ({
          plotKey: slug,
          title: props.displayLabels[slug] ?? slug,
          channelSlug: slug,
          defaultExtent: data?.yExtents[slug],
        }));

    const manualYRanges = getActiveManualYRanges(props.settings.groupingMode, props.settings.normalizeY);
    const plots = computePlotLayouts(width, height, items, xRange, manualYRanges);
    plotsRef.current = plots;
    // 1. WebGL2 pass
    const gl = glRendererRef.current;
    if (gl) {
      const dpr = window.devicePixelRatio || 1;
      const clearColor: [number, number, number, number] = props.isDark
        ? [0x19 / 255, 0x1b / 255, 0x1f / 255, 1.0]
        : [1.0, 1.0, 1.0, 1.0];

      gl.beginFrame(width, height, dpr, clearColor);

      if (plots.length > 0 && data) {
        const dotBorder: [number, number, number, number] = props.isDark
          ? [1, 1, 1, 1]
          : [0, 0, 0, 1];

        for (const p of plots) {
          const chCurves = curvesByPlotRef.current.get(p.plotKey) ?? [];
          const glCurves: CurveRenderInput[] = chCurves.map((c) => ({
            x: c.x,
            y: c.y,
            color: hexToRgba(c.color, 1.0),
            lineWidth: 1.8,
          }));

          const glDots: DotRenderInput[] = [];
          if (props.settings.showCursorValues && cursorXRef.current !== null) {
            const dots = cursorSamplesRef.current.get(p.plotKey) ?? [];
            for (const d of dots) {
              if (
                Number.isFinite(d.actualX) &&
                Number.isFinite(d.plotY) &&
                d.actualX >= p.xMin &&
                d.actualX <= p.xMax
              ) {
                glDots.push({
                  x: d.actualX,
                  y: d.plotY,
                  fillColor: hexToRgba(d.color, 1.0),
                  borderColor: dotBorder,
                  radiusPx: 4.5,
                });
              }
            }
          }

          gl.drawPlot(
            {
              left: p.plotLeft,
              top: p.plotTop,
              width: p.plotWidth,
              height: p.plotHeight,
              xMin: p.xMin,
              xMax: p.xMax,
              yMin: p.yMin,
              yMax: p.yMax,
            },
            height,
            dpr,
            glCurves,
            glDots,
            props.settings.antialias,
          );
        }
      }
    }

    // 2. Canvas2D overlay pass
    const overlayCanvas = overlayCanvasRef.current;
    if (overlayCanvas) {
      renderPlotOverlay(overlayCanvas, {
        width,
        height,
        isDark: props.isDark,
        showXGrid: props.settings.showXGrid,
        showYGrid: props.settings.showYGrid,
        showCursorValues: props.settings.showCursorValues,
        showCursorOnGraph: props.settings.showCursorOnGraph,
        showCursorAboveGraph: props.settings.showCursorAboveGraph,
        xAxisLabel: props.xAxisLabel,
        cursorX: cursorXRef.current,
        plots,
        samplesByPlot: cursorSamplesRef.current,
        dragBox: interactionRef.current?.type === 'zoom' ? dragBoxRef.current : null,
      });
    }
  }, [getActiveManualYRanges]);

  const rebuildPlotSeries = useCallback(() => {
    const data = plotDataRef.current;
    const props = latestPropsRef.current;
    if (!data) {
      curvesByPlotRef.current = new Map();
      lapYExtentsRef.current = {};
      return;
    }

    const isByLap = props.settings.groupingMode === 'lap';
    const isNorm = isByLap && props.settings.normalizeY;
    const grouped = new Map<string, PlotCurveData[]>();
    const lapExtents: Record<string, [number, number]> = {};

    for (const curve of data.curves) {
      if (!isByLap) {
        let list = grouped.get(curve.channelSlug);
        if (!list) {
          list = [];
          grouped.set(curve.channelSlug, list);
        }
        list.push(curve);
        continue;
      }

      const lapKey = `${curve.sessionId}:${curve.lapNumber}`;
      const chColor = props.channelColors[curve.channelSlug] ?? LAP_COLORS[0];
      let yArr = curve.y;

      if (isNorm) {
        const ext = data.yExtents[curve.channelSlug];
        const normArr = new Float64Array(yArr.length);
        const span = ext ? ext[1] - ext[0] : 0;
        if (ext && span > 0 && Number.isFinite(span)) {
          const minV = ext[0];
          for (let i = 0; i < yArr.length; i++) {
            const v = yArr[i];
            normArr[i] = Number.isFinite(v) ? ((v - minV) / span) * 100 : v;
          }
        } else {
          for (let i = 0; i < yArr.length; i++) {
            const v = yArr[i];
            normArr[i] = Number.isFinite(v) ? 50 : v;
          }
        }
        yArr = normArr;
      } else {
        let minV = Infinity;
        let maxV = -Infinity;
        for (let i = 0; i < yArr.length; i++) {
          const v = yArr[i];
          if (Number.isFinite(v)) {
            if (v < minV) minV = v;
            if (v > maxV) maxV = v;
          }
        }
        if (Number.isFinite(minV) && Number.isFinite(maxV)) {
          const prev = lapExtents[lapKey];
          lapExtents[lapKey] = prev
            ? [Math.min(prev[0], minV), Math.max(prev[1], maxV)]
            : [minV, maxV];
        }
      }

      let list = grouped.get(lapKey);
      if (!list) {
        list = [];
        grouped.set(lapKey, list);
      }
      list.push({
        ...curve,
        color: chColor,
        y: yArr,
      });
    }

    curvesByPlotRef.current = grouped;
    lapYExtentsRef.current = lapExtents;
  }, []);
  // Worker plot data fetch with latest-request-wins sequence guard
  const fetchPlotData = useCallback(async () => {
    const props = latestPropsRef.current;
    if (
      props.sessions.length === 0 ||
      props.selectedChannels.length === 0 ||
      props.selectedLaps.length === 0
    ) {
      ++plotReqSeqRef.current;
      plotDataRef.current = null;
      curvesByPlotRef.current = new Map();
      lapYExtentsRef.current = {};
      fullXExtentRef.current = null;
      cursorSamplesRef.current = new Map();
      props.onCursorMapPoints([]);
      renderAll();
      return;
    }

    const seq = ++plotReqSeqRef.current;
    const xRange = manualXRangeRef.current;
    const plotWidth = Math.max(
      200,
      viewportSizeRef.current.width - LEFT_AXIS_WIDTH - RIGHT_MARGIN,
    );
    const maxBuckets = Math.max(800, Math.round(plotWidth * (window.devicePixelRatio || 1) * 1.5));

    try {
      const res = await telemetryClient.getPlotData({
        xAxisSlug: props.settings.xAxisSlug,
        channels: props.selectedChannels,
        selectedLaps: props.selectedLaps,
        xMin: xRange ? xRange[0] : null,
        xMax: xRange ? xRange[1] : null,
        maxBuckets,
        filterGaps: props.settings.filterGaps,
        channelGroups: props.channelGroups,
      });

      if (seq !== plotReqSeqRef.current || unmountedRef.current) return;

      plotDataRef.current = res;
      if (!xRange && res.xExtent) {
        fullXExtentRef.current = res.xExtent;
      }

      rebuildPlotSeries();
      renderAll();
    } catch (err) {
      if (seq !== plotReqSeqRef.current || unmountedRef.current) return;
      console.error('Failed to fetch plot data:', err);
    }
  }, [rebuildPlotSeries, renderAll]);

  const schedulePlotFetch = useCallback(
    (delayMs = 60) => {
      window.clearTimeout(fetchTimerRef.current);
      fetchTimerRef.current = window.setTimeout(() => {
        fetchTimerRef.current = undefined;
        void fetchPlotData();
      }, delayMs);
    },
    [fetchPlotData],
  );

  // Coalesced cursor query loop (at most one query in-flight to worker)
  const drainCursorQueries = useCallback(async () => {
    if (cursorInFlightRef.current) return;
    cursorInFlightRef.current = true;

    try {
      while (pendingCursorTargetRef.current !== null && !unmountedRef.current) {
        const { targetX, hovered } = pendingCursorTargetRef.current;
        pendingCursorTargetRef.current = null;

        const props = latestPropsRef.current;
        if (
          props.sessions.length === 0 ||
          props.selectedChannels.length === 0 ||
          props.selectedLaps.length === 0
        ) {
          cursorSamplesRef.current = new Map();
          props.onCursorMapPoints([]);
          renderAll();
          continue;
        }

        const seq = ++cursorSeqRef.current;
        const res = await telemetryClient.queryCursor({
          xAxisSlug: props.settings.xAxisSlug,
          channels: props.selectedChannels,
          selectedLaps: props.selectedLaps,
          targetX,
          hovered,
          channelGroups: props.channelGroups,
        });

        if (seq !== cursorSeqRef.current || unmountedRef.current) {
          continue;
        }

        if (pendingCursorTargetRef.current === null && Number.isFinite(res.snappedX)) {
          cursorXRef.current = res.snappedX;
        }

        const nextSamples = new Map<string, OverlaySampleDot[]>();
        const isByLap = props.settings.groupingMode === 'lap';
        const isNorm = isByLap && props.settings.normalizeY;
        const yExtents = plotDataRef.current?.yExtents;

        for (const slug of props.selectedChannels) {
          const items = res.samplesByChannel[slug];
          if (!items) continue;
          for (const item of items) {
            if (!isByLap) {
              let list = nextSamples.get(slug);
              if (!list) {
                list = [];
                nextSamples.set(slug, list);
              }
              list.push({
                seriesKey: item.lapKey,
                color: item.color,
                actualX: item.actualX,
                actualY: item.actualY,
                plotY: item.actualY,
              });
            } else {
              let plotY = item.actualY;
              if (isNorm) {
                const ext = yExtents?.[slug];
                const span = ext ? ext[1] - ext[0] : 0;
                plotY =
                  ext && span > 0 && Number.isFinite(span)
                    ? ((item.actualY - ext[0]) / span) * 100
                    : 50;
              }
              let list = nextSamples.get(item.lapKey);
              if (!list) {
                list = [];
                nextSamples.set(item.lapKey, list);
              }
              list.push({
                seriesKey: slug,
                color: props.channelColors[slug] ?? LAP_COLORS[0],
                actualX: item.actualX,
                actualY: item.actualY,
                plotY,
              });
            }
          }
        }
        cursorSamplesRef.current = nextSamples;
        if (isByLap) {
          const primaryColor = props.isDark ? '#FFC815' : '#D9A700';
          props.onCursorMapPoints(
            res.trackMapDots.map((d) => ({ distance: d.distance, color: primaryColor })),
          );
        } else {
          props.onCursorMapPoints(res.trackMapDots);
        }
        renderAll();
      }
    } catch (err) {
      console.error('Failed to query cursor:', err);
    } finally {
      cursorInFlightRef.current = false;
    }
  }, [renderAll]);

  const resetZoomToFull = useCallback(() => {
    manualXRangeRef.current = null;
    manualChannelYRangesRef.current = {};
    manualLapYRangesRef.current = {};
    manualNormLapYRangesRef.current = {};
    window.clearTimeout(fetchTimerRef.current);
    fetchTimerRef.current = undefined;
    renderAll();
    void fetchPlotData();
  }, [fetchPlotData, renderAll]);

  // Initialize WebGL2 renderer once
  useEffect(() => {
    unmountedRef.current = false;
    const glCanvas = webglCanvasRef.current;
    if (glCanvas) {
      try {
        glRendererRef.current = new WebGLCurveRenderer(glCanvas);
        setWebglError(null);
      } catch (err) {
        setWebglError(err instanceof Error ? err.message : 'WebGL2 initialization failed.');
      }
    }

    return () => {
      unmountedRef.current = true;
      window.clearTimeout(fetchTimerRef.current);
      fetchTimerRef.current = undefined;
      if (cursorRafRef.current !== null) {
        cancelAnimationFrame(cursorRafRef.current);
        cursorRafRef.current = null;
      }
      glRendererRef.current?.dispose();
      glRendererRef.current = null;
    };
  }, []);

  // Responsive viewport ResizeObserver
  useEffect(() => {
    const vp = viewportRef.current;
    if (!vp) return;

    let lastWidth = 0;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const w = Math.floor(entry.contentRect.width);
      const h = Math.floor(entry.contentRect.height);
      const widthChanged = Math.abs(w - lastWidth) > 32;
      lastWidth = w;
      viewportSizeRef.current = { width: w, height: h };
      renderAll();

      // Clamp legend position inside resized viewport if previously dragged
      setLegendPos((prev) => {
        if (!prev) return null;
        const legW = legendRef.current?.offsetWidth ?? 180;
        const legH = legendRef.current?.offsetHeight ?? 80;
        return {
          x: Math.max(4, Math.min(Math.max(4, w - legW - 4), prev.x)),
          y: Math.max(4, Math.min(Math.max(4, h - legH - 4), prev.y)),
        };
      });

      if (widthChanged && plotDataRef.current) {
        schedulePlotFetch(120);
      }
    });

    observer.observe(vp);
    return () => {
      observer.disconnect();
    };
  }, [renderAll, schedulePlotFetch]);

  // Reset zoom & cursor when switching X-axis
  const prevXAxisSlugRef = useRef(settings.xAxisSlug);
  useEffect(() => {
    if (prevXAxisSlugRef.current !== settings.xAxisSlug) {
      prevXAxisSlugRef.current = settings.xAxisSlug;
      manualXRangeRef.current = null;
      manualChannelYRangesRef.current = {};
      manualLapYRangesRef.current = {};
      manualNormLapYRangesRef.current = {};
      cursorXRef.current = null;
      pendingCursorTargetRef.current = null;
      ++cursorSeqRef.current;
      cursorSamplesRef.current = new Map();
      onCursorMapPoints([]);
    }
  }, [settings.xAxisSlug, onCursorMapPoints]);

  // Fetch plot data whenever inputs/settings/channelsVersion change
  useEffect(() => {
    window.clearTimeout(fetchTimerRef.current);
    fetchTimerRef.current = undefined;
    void fetchPlotData();
    // Refresh active cursor values if cursor is currently positioned
    if (cursorXRef.current !== null) {
      pendingCursorTargetRef.current = { targetX: cursorXRef.current, hovered: null };
      void drainCursorQueries();
    }
  }, [
    sessions,
    selectedChannels,
    selectedLaps,
    settings.xAxisSlug,
    settings.filterGaps,
    channelsVersion,
    channelGroups,
    fetchPlotData,
    drainCursorQueries,
  ]);

  // Rebuild series and redraw immediately when grouping, normalize, colors, visual settings, or labels change
  useEffect(() => {
    rebuildPlotSeries();
    if (cursorXRef.current !== null) {
      pendingCursorTargetRef.current = { targetX: cursorXRef.current, hovered: null };
      void drainCursorQueries();
    }
    renderAll();
  }, [
    isDark,
    settings.groupingMode,
    settings.normalizeY,
    settings.showXGrid,
    settings.showYGrid,
    settings.antialias,
    settings.showCursorValues,
    settings.showCursorOnGraph,
    settings.showCursorAboveGraph,
    channelColors,
    displayLabels,
    lapLabels,
    xAxisLabel,
    rebuildPlotSeries,
    drainCursorQueries,
    renderAll,
  ]);
  const cancelZoomDrag = useCallback(() => {
    const active = interactionRef.current;
    const hadZoom = active?.type === 'zoom' || dragBoxRef.current !== null;
    if (active?.type === 'zoom') {
      const canvas = overlayCanvasRef.current;
      if (canvas && canvas.hasPointerCapture(active.pointerId)) {
        canvas.releasePointerCapture(active.pointerId);
      }
      interactionRef.current = null;
    }
    if (dragBoxRef.current !== null) {
      dragBoxRef.current = null;
    }
    if (hadZoom) {
      renderAll();
      requestAnimationFrame(() => renderAll());
    }
    return hadZoom;
  }, [renderAll]);

  // Escape, right-click anywhere in window, or window blur cancels active drag zoom
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        cancelZoomDrag();
      }
    };
    const isZoomActive = () => interactionRef.current?.type === 'zoom' || dragBoxRef.current !== null;
    const onWindowPointerDown = (e: PointerEvent) => {
      if (e.button === 2 && isZoomActive()) {
        e.preventDefault();
        cancelZoomDrag();
      }
    };
    const onWindowPointerMove = (e: PointerEvent) => {
      if ((e.buttons & 2) !== 0 && isZoomActive()) {
        cancelZoomDrag();
      }
    };
    const onWindowMouseDown = (e: MouseEvent) => {
      if (e.button === 2 && isZoomActive()) {
        e.preventDefault();
        cancelZoomDrag();
      }
    };
    const onWindowMouseUp = (e: MouseEvent) => {
      if (e.button === 2 && isZoomActive()) {
        e.preventDefault();
        cancelZoomDrag();
      }
    };
    const onWindowAuxClick = (e: MouseEvent) => {
      if (e.button === 2 && isZoomActive()) {
        e.preventDefault();
        cancelZoomDrag();
      }
    };
    const onWindowContextMenu = (e: MouseEvent) => {
      if (isZoomActive()) {
        e.preventDefault();
        cancelZoomDrag();
      }
    };
    const onWindowBlur = () => {
      cancelZoomDrag();
    };
    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('pointerdown', onWindowPointerDown, true);
    window.addEventListener('pointermove', onWindowPointerMove, true);
    window.addEventListener('mousedown', onWindowMouseDown, true);
    window.addEventListener('mouseup', onWindowMouseUp, true);
    window.addEventListener('auxclick', onWindowAuxClick, true);
    window.addEventListener('contextmenu', onWindowContextMenu, true);
    window.addEventListener('blur', onWindowBlur);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('pointerdown', onWindowPointerDown, true);
      window.removeEventListener('pointermove', onWindowPointerMove, true);
      window.removeEventListener('mousedown', onWindowMouseDown, true);
      window.removeEventListener('mouseup', onWindowMouseUp, true);
      window.removeEventListener('auxclick', onWindowAuxClick, true);
      window.removeEventListener('contextmenu', onWindowContextMenu, true);
      window.removeEventListener('blur', onWindowBlur);
    };
  }, [cancelZoomDrag]);

  // Non-passive wheel listener for smooth X-zoom and left-strip Y-zoom
  useEffect(() => {
    const canvas = overlayCanvasRef.current;
    if (!canvas) return;

    const onWheel = (e: WheelEvent) => {
      const plots = plotsRef.current;
      if (plots.length === 0) return;

      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const localX = e.clientX - rect.left;
      const localY = e.clientY - rect.top;

      // Find hovered plot vertically (fallback to nearest/first)
      let targetPlot = plots.find(
        (p) => localY >= p.plotTop && localY <= p.plotTop + p.plotHeight,
      );
      if (!targetPlot) {
        targetPlot = plots.find((p) => localY >= p.rowTop && localY <= p.rowTop + p.rowHeight);
      }
      if (!targetPlot) {
        targetPlot = localY < plots[0].plotTop ? plots[0] : plots[plots.length - 1];
      }

      const clampedDelta = Math.max(-200, Math.min(200, e.deltaY));
      const zoomFactor = Math.exp(clampedDelta * 0.0015);

      if (localX < LEFT_AXIS_WIDTH) {
        // Hovering inside left Y-axis strip -> zoom Y of hovered plot
        const spanY = targetPlot.yMax - targetPlot.yMin;
        if (spanY <= 0 || !Number.isFinite(spanY)) return;
        const t = Math.max(
          0,
          Math.min(1, (targetPlot.plotTop + targetPlot.plotHeight - localY) / targetPlot.plotHeight),
        );
        const anchorY = targetPlot.yMin + t * spanY;
        const newSpanY = Math.max(1e-9, spanY * zoomFactor);
        const manualYRanges = getActiveManualYRanges(
          latestPropsRef.current.settings.groupingMode,
          latestPropsRef.current.settings.normalizeY,
        );
        manualYRanges[targetPlot.plotKey] = [
          anchorY - t * newSpanY,
          anchorY + (1 - t) * newSpanY,
        ];
        renderAll();
      } else {
        // Zoom X across all plots
        const spanX = targetPlot.xMax - targetPlot.xMin;
        if (spanX <= 0 || !Number.isFinite(spanX)) return;
        const t = Math.max(0, Math.min(1, (localX - targetPlot.plotLeft) / targetPlot.plotWidth));
        const anchorX = targetPlot.xMin + t * spanX;
        const newSpanX = Math.max(1e-9, spanX * zoomFactor);
        manualXRangeRef.current = [anchorX - t * newSpanX, anchorX + (1 - t) * newSpanX];
        renderAll();
        schedulePlotFetch(70);
      }
    };

    canvas.addEventListener('wheel', onWheel, { passive: false });
    return () => canvas.removeEventListener('wheel', onWheel);
  }, [renderAll, schedulePlotFetch]);

  // Helper: find plot containing (localX, localY)
  const findPlotForPointer = (localX: number, localY: number): PlotLayoutBox | null => {
    for (const p of plotsRef.current) {
      if (
        localX >= p.plotLeft &&
        localX <= p.plotLeft + p.plotWidth &&
        localY >= p.plotTop &&
        localY <= p.plotTop + p.plotHeight
      ) {
        return p;
      }
    }
    return null;
  };

  const handleCanvasPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = overlayCanvasRef.current;
    if (!canvas || plotsRef.current.length === 0) return;

    if (e.button === 2) {
      e.preventDefault();
      cancelZoomDrag();
      return;
    }

    const rect = canvas.getBoundingClientRect();
    const localX = e.clientX - rect.left;
    const localY = e.clientY - rect.top;
    if (e.button === 1 || (e.button === 0 && e.shiftKey)) {
      e.preventDefault();
      const targetPlot =
        findPlotForPointer(localX, localY) ??
        plotsRef.current.find((p) => localY >= p.rowTop && localY <= p.rowTop + p.rowHeight) ??
        null;
      if (!targetPlot) return;

      canvas.setPointerCapture(e.pointerId);
      interactionRef.current = {
        type: 'pan',
        pointerId: e.pointerId,
        startX: localX,
        startY: localY,
        targetPlot,
        initXMin: targetPlot.xMin,
        initXMax: targetPlot.xMax,
        initYMin: targetPlot.yMin,
        initYMax: targetPlot.yMax,
        xChanged: false,
      };
      return;
    }

    // Left-click -> Drag zoom (X across all plots or Y on active plot)
    if (e.button === 0) {
      const targetPlot = findPlotForPointer(localX, localY);
      if (!targetPlot) return;

      canvas.setPointerCapture(e.pointerId);
      interactionRef.current = {
        type: 'zoom',
        pointerId: e.pointerId,
        startX: localX,
        startY: localY,
        targetPlot,
        mode: null,
      };
      dragBoxRef.current = null;
    }
  };

  const handleCanvasPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = overlayCanvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const localX = e.clientX - rect.left;
    const localY = e.clientY - rect.top;

    const active = interactionRef.current;
    if (active) {
      if (active.type === 'zoom') {
        if ((e.buttons & 2) !== 0) {
          cancelZoomDrag();
          return;
        }
        const dx = localX - active.startX;
        const dy = localY - active.startY;
        if (active.mode === null && Math.hypot(dx, dy) >= 4) {
          active.mode = Math.abs(dx) >= Math.abs(dy) ? 'x' : 'y';
        }
        if (active.mode === 'x') {
          dragBoxRef.current = {
            mode: 'x',
            startPx: active.startX,
            currPx: localX,
          };
          renderAll();
        } else if (active.mode === 'y') {
          dragBoxRef.current = {
            mode: 'y',
            plotKey: active.targetPlot.plotKey,
            startPx: active.startY,
            currPx: localY,
          };
          renderAll();
        }
        return;
      }

      if (active.type === 'pan') {
        const dxPx = localX - active.startX;
        const dyPx = localY - active.startY;
        const p = active.targetPlot;
        const spanX = active.initXMax - active.initXMin;
        const spanY = active.initYMax - active.initYMin;

        if (spanX > 0 && p.plotWidth > 0) {
          const shiftX = (dxPx / p.plotWidth) * spanX;
          manualXRangeRef.current = [active.initXMin - shiftX, active.initXMax - shiftX];
          active.xChanged = true;
        }
        if (spanY > 0 && p.plotHeight > 0) {
          const shiftY = (dyPx / p.plotHeight) * spanY;
          const manualYRanges = getActiveManualYRanges(
            latestPropsRef.current.settings.groupingMode,
            latestPropsRef.current.settings.normalizeY,
          );
          manualYRanges[p.plotKey] = [
            active.initYMin + shiftY,
            active.initYMax + shiftY,
          ];
        }

        renderAll();
        if (active.xChanged) {
          schedulePlotFetch(60);
        }
        return;
      }
    }

    // Standard cursor tracking (throttled via requestAnimationFrame)
    const plots = plotsRef.current;
    if (plots.length === 0) return;

    const refPlot = plots[0];
    const inPlotX = localX >= refPlot.plotLeft && localX <= refPlot.plotLeft + refPlot.plotWidth;
    const inPlotStackY =
      localY >= plots[0].plotTop &&
      localY <= plots[plots.length - 1].plotTop + plots[plots.length - 1].plotHeight;

    if (!inPlotX || !inPlotStackY) {
      if (cursorXRef.current !== null) {
        cursorXRef.current = null;
        pendingCursorTargetRef.current = null;
        ++cursorSeqRef.current;
        cursorSamplesRef.current = new Map();
        onCursorMapPoints([]);
        renderAll();
      }
      return;
    }

    const hoveredPlot = plots.find(
      (p) => localY >= p.plotTop && localY <= p.plotTop + p.plotHeight,
    );
    let hovered: HoveredPlotBounds | null = null;
    if (hoveredPlot && hoveredPlot.plotWidth > 0 && hoveredPlot.plotHeight > 0) {
      const spanY = hoveredPlot.yMax - hoveredPlot.yMin;
      const targetY =
        hoveredPlot.yMin +
        ((hoveredPlot.plotTop + hoveredPlot.plotHeight - localY) / hoveredPlot.plotHeight) * spanY;
      const isByLap = latestPropsRef.current.settings.groupingMode === 'lap';
      hovered = {
        channelSlug: hoveredPlot.channelSlug ?? '',
        hoveredLap: isByLap ? hoveredPlot.lapInfo ?? null : null,
        normalizeY: isByLap ? latestPropsRef.current.settings.normalizeY : false,
        channelExtents: isByLap ? plotDataRef.current?.yExtents : undefined,
        targetY,
        xMin: hoveredPlot.xMin,
        xMax: hoveredPlot.xMax,
        yMin: hoveredPlot.yMin,
        yMax: hoveredPlot.yMax,
        plotWidth: hoveredPlot.plotWidth,
        plotHeight: hoveredPlot.plotHeight,
      };
    }

    const spanX = refPlot.xMax - refPlot.xMin;
    if (spanX <= 0 || !Number.isFinite(spanX)) return;
    const targetX =
      refPlot.xMin + ((localX - refPlot.plotLeft) / refPlot.plotWidth) * spanX;
    cursorXRef.current = targetX;
    pendingCursorTargetRef.current = { targetX, hovered };
    if (cursorRafRef.current === null) {
      cursorRafRef.current = requestAnimationFrame(() => {
        cursorRafRef.current = null;
        renderAll();
        void drainCursorQueries();
      });
    }
  };

  const finishInteraction = (e: React.PointerEvent<HTMLCanvasElement>, cancelled: boolean) => {
    const canvas = overlayCanvasRef.current;
    const active = interactionRef.current;
    if (!active) {
      if (dragBoxRef.current !== null) {
        dragBoxRef.current = null;
        renderAll();
      }
      return;
    }

    if (canvas && canvas.hasPointerCapture(active.pointerId)) {
      canvas.releasePointerCapture(active.pointerId);
    }

    const isRightButton = e.button === 2 || (e.buttons & 2) !== 0;
    const rect = canvas?.getBoundingClientRect();
    const localX = rect ? e.clientX - rect.left : active.startX;
    const localY = rect ? e.clientY - rect.top : active.startY;

    if (!cancelled && !isRightButton && active.type === 'zoom' && dragBoxRef.current) {
      const box = dragBoxRef.current;
      const p = active.targetPlot;
      if (box.mode === 'x') {
        const px1 = Math.max(p.plotLeft, Math.min(box.startPx, localX));
        const px2 = Math.min(p.plotLeft + p.plotWidth, Math.max(box.startPx, localX));
        if (px2 - px1 >= 4 && p.plotWidth > 0) {
          const spanX = p.xMax - p.xMin;
          const newXMin = p.xMin + ((px1 - p.plotLeft) / p.plotWidth) * spanX;
          const newXMax = p.xMin + ((px2 - p.plotLeft) / p.plotWidth) * spanX;
          if (newXMax - newXMin > 1e-9) {
            manualXRangeRef.current = [newXMin, newXMax];
            window.clearTimeout(fetchTimerRef.current);
            fetchTimerRef.current = undefined;
            renderAll();
            void fetchPlotData();
          }
        }
      } else if (box.mode === 'y') {
        const py1 = Math.max(p.plotTop, Math.min(box.startPx, localY));
        const py2 = Math.min(p.plotTop + p.plotHeight, Math.max(box.startPx, localY));
        if (py2 - py1 >= 4 && p.plotHeight > 0) {
          const spanY = p.yMax - p.yMin;
          const newYMax = p.yMin + ((p.plotTop + p.plotHeight - py1) / p.plotHeight) * spanY;
          const newYMin = p.yMin + ((p.plotTop + p.plotHeight - py2) / p.plotHeight) * spanY;
          if (newYMax - newYMin > 1e-9) {
            const manualYRanges = getActiveManualYRanges(
              latestPropsRef.current.settings.groupingMode,
              latestPropsRef.current.settings.normalizeY,
            );
            manualYRanges[p.plotKey] = [newYMin, newYMax];
          }
        }
      }
    } else if (active.type === 'pan' && active.xChanged) {
      window.clearTimeout(fetchTimerRef.current);
      fetchTimerRef.current = undefined;
      void fetchPlotData();
    }
    interactionRef.current = null;
    dragBoxRef.current = null;
    renderAll();
  };

  const handleCanvasPointerLeave = () => {
    if (interactionRef.current) return;
    if (cursorRafRef.current !== null) {
      cancelAnimationFrame(cursorRafRef.current);
      cursorRafRef.current = null;
    }
    if (cursorXRef.current !== null) {
      cursorXRef.current = null;
      pendingCursorTargetRef.current = null;
      ++cursorSeqRef.current;
      cursorSamplesRef.current = new Map();
      onCursorMapPoints([]);
      renderAll();
    }
  };

  // Legend dragging handlers
  const handleLegendPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.stopPropagation();
    if (e.button !== 0) return;
    const legendEl = legendRef.current;
    const vpEl = viewportRef.current;
    if (!legendEl || !vpEl) return;

    const legRect = legendEl.getBoundingClientRect();
    const vpRect = vpEl.getBoundingClientRect();
    const currentX = legRect.left - vpRect.left;
    const currentY = legRect.top - vpRect.top;

    setLegendPos({ x: currentX, y: currentY });
    legendEl.setPointerCapture(e.pointerId);
    legendDragRef.current = {
      pointerId: e.pointerId,
      offsetX: e.clientX - legRect.left,
      offsetY: e.clientY - legRect.top,
    };
  };

  const handleLegendPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    e.stopPropagation();
    const drag = legendDragRef.current;
    const legendEl = legendRef.current;
    const vpEl = viewportRef.current;
    if (!drag || !legendEl || !vpEl) return;

    const vpRect = vpEl.getBoundingClientRect();
    const legW = legendEl.offsetWidth;
    const legH = legendEl.offsetHeight;

    const rawX = e.clientX - vpRect.left - drag.offsetX;
    const rawY = e.clientY - vpRect.top - drag.offsetY;

    const clampedX = Math.max(4, Math.min(Math.max(4, vpRect.width - legW - 4), rawX));
    const clampedY = Math.max(4, Math.min(Math.max(4, vpRect.height - legH - 4), rawY));
    setLegendPos({ x: clampedX, y: clampedY });
  };

  const handleLegendPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    e.stopPropagation();
    const drag = legendDragRef.current;
    if (!drag) return;
    const legendEl = legendRef.current;
    if (legendEl && legendEl.hasPointerCapture(drag.pointerId)) {
      legendEl.releasePointerCapture(drag.pointerId);
    }
    legendDragRef.current = null;
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        width: '100%',
        height: '100%',
        minWidth: 0,
        minHeight: 0,
        background: 'var(--bg-app)',
      }}
    >
      {/* Top Toolbar */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          padding: '6px 10px',
          background: 'var(--bg-panel)',
          borderBottom: '1px solid var(--border-subtle)',
          flexShrink: 0,
          overflowX: 'auto',
        }}
      >
        <ToolbarActionButton
          onClick={resetZoomToFull}
          title="Auto-Range All Axes (Double-click plot)"
          icon={<Maximize2 size={14} />}
          label="Auto-Range"
        />

        <ToolbarToggleButton
          active={settings.showXGrid}
          onClick={() => onUpdateSettings({ showXGrid: !settings.showXGrid })}
          title="Toggle X Gridlines"
          icon={<Columns3 size={14} />}
          label="X Grid"
        />

        <ToolbarToggleButton
          active={settings.showYGrid}
          onClick={() => onUpdateSettings({ showYGrid: !settings.showYGrid })}
          title="Toggle Y Gridlines"
          icon={<Rows3 size={14} />}
          label="Y Grid"
        />

        <ToolbarToggleButton
          active={settings.showCursorValues}
          onClick={() => onUpdateSettings({ showCursorValues: !settings.showCursorValues })}
          title="Toggle Cursor Values"
          icon={<Crosshair size={14} />}
          label="Cursor"
        />

        <ToolbarToggleButton
          active={settings.filterGaps}
          onClick={() => onUpdateSettings({ filterGaps: !settings.filterGaps })}
          title="Show or bridge data gaps across missing segments"
          icon={<GitCommitHorizontal size={14} />}
          label="Show Gaps"
        />

        <ToolbarToggleButton
          active={settings.showLegend}
          onClick={() => onUpdateSettings({ showLegend: !settings.showLegend })}
          title="Toggle Floating Legend"
          icon={<List size={14} />}
          label="Legend"
        />

        <ToolbarActionButton
          onClick={onOpenRenameLegend}
          title="Rename Legend Labels"
          icon={<Pencil size={14} />}
          label="Rename Legend"
        />

        {settings.groupingMode === 'lap' && (
          <ToolbarToggleButton
            active={settings.normalizeY}
            onClick={() => onUpdateSettings({ normalizeY: !settings.normalizeY })}
            title="Normalize all channels (0–100%) on shared Y-axis"
            icon={<Percent size={14} />}
            label="Normalize Y"
          />
        )}

        <div style={{ flex: 1, minWidth: '8px' }} />
        <label
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            fontSize: '12px',
            color: 'var(--text-muted)',
            flexShrink: 0,
          }}
        >
          <span>X-Axis:</span>
          <select
            aria-label="X-Axis channel"
            value={settings.xAxisSlug}
            onChange={(e) => onUpdateSettings({ xAxisSlug: e.target.value })}
            style={{
              height: '28px',
              padding: '0 8px',
              borderRadius: '4px',
              border: '1px solid var(--border-strong)',
              background: 'var(--bg-input)',
              color: 'var(--text-primary)',
              fontSize: '12px',
            }}
          >
            {xAxisOptions.map((opt) => (
              <option key={opt.slug} value={opt.slug}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {/* Plot Viewport */}
      <div
        ref={viewportRef}
        style={{
          position: 'relative',
          flex: 1,
          minHeight: 0,
          overflow: 'hidden',
          background: 'var(--bg-canvas)',
        }}
      >
        {/* WebGL2 Curve Layer */}
        <canvas
          ref={webglCanvasRef}
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            display: 'block',
            pointerEvents: 'none',
          }}
        />

        {/* Canvas2D Overlay + Interaction Layer */}
        <canvas
          ref={overlayCanvasRef}
          onPointerDown={handleCanvasPointerDown}
          onPointerMove={handleCanvasPointerMove}
          onPointerUp={(e) => finishInteraction(e, false)}
          onPointerCancel={(e) => finishInteraction(e, true)}
          onLostPointerCapture={() => cancelZoomDrag()}
          onPointerLeave={handleCanvasPointerLeave}
          onDoubleClick={resetZoomToFull}
          onContextMenu={(e) => {
            e.preventDefault();
            cancelZoomDrag();
          }}
          onAuxClick={(e) => {
            if (e.button === 2) {
              e.preventDefault();
              cancelZoomDrag();
            }
          }}
          onMouseDown={(e) => {
            if (e.button === 1) e.preventDefault();
            if (e.button === 2) {
              e.preventDefault();
              cancelZoomDrag();
            }
          }}
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            display: 'block',
            cursor: 'crosshair',
            touchAction: 'none',
          }}
        />

        {webglError && (
          <div
            style={{
              position: 'absolute',
              bottom: '12px',
              left: '50%',
              transform: 'translateX(-50%)',
              padding: '6px 12px',
              borderRadius: '6px',
              background: 'var(--danger-bg)',
              border: '1px solid var(--danger)',
              color: 'var(--danger)',
              fontSize: '12px',
              pointerEvents: 'none',
            }}
          >
            {webglError}
          </div>
        )}

        {/* Draggable Floating Legend */}
        {settings.showLegend && (
          <div
            ref={legendRef}
            onPointerDown={handleLegendPointerDown}
            onPointerMove={handleLegendPointerMove}
            onPointerUp={handleLegendPointerUp}
            onPointerCancel={handleLegendPointerUp}
            onWheel={(e) => e.stopPropagation()}
            onDoubleClick={(e) => e.stopPropagation()}
            style={{
              position: 'absolute',
              ...(legendPos
                ? { left: `${legendPos.x}px`, top: `${legendPos.y}px` }
                : { top: '28px', right: '22px' }),
              minWidth: '160px',
              maxWidth: '280px',
              maxHeight: '60%',
              overflowY: 'auto',
              padding: '8px 10px',
              borderRadius: '6px',
              background: isDark ? 'rgba(25, 27, 31, 0.9)' : 'rgba(255, 255, 255, 0.92)',
              backdropFilter: 'blur(6px)',
              border: '1px solid var(--border-strong)',
              boxShadow: '0 4px 14px rgba(0, 0, 0, 0.28)',
              cursor: 'grab',
              userSelect: 'none',
              touchAction: 'none',
              zIndex: 10,
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                marginBottom: '6px',
                paddingBottom: '4px',
                borderBottom: '1px solid var(--border-subtle)',
                fontSize: '11px',
                fontWeight: 600,
                color: 'var(--text-muted)',
              }}
            >
              <GripVertical size={12} />
              <span>Legend</span>
            </div>
            {settings.groupingMode === 'lap' ? (
              selectedChannels.length === 0 ? (
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>No channels selected</div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                  {selectedChannels.map((slug) => {
                    const label = displayLabels[slug] ?? slug;
                    const color = channelColors[slug] ?? LAP_COLORS[0];

                    return (
                      <div
                        key={slug}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px',
                          fontSize: '12px',
                          color: 'var(--text-primary)',
                        }}
                      >
                        <span
                          style={{
                            width: '12px',
                            height: '4px',
                            borderRadius: '2px',
                            background: color,
                            flexShrink: 0,
                          }}
                        />
                        <span
                          style={{
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                          title={label}
                        >
                          {label}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )
            ) : selectedLaps.length === 0 ? (
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>No laps selected</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                {selectedLaps.map((lap) => {
                  const key = `${lap.sessionId}:${lap.lapNumber}`;
                  const label = lapLabels[key] ?? key;

                  return (
                    <div
                      key={key}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        fontSize: '12px',
                        color: 'var(--text-primary)',
                      }}
                    >
                      <span
                        style={{
                          width: '12px',
                          height: '4px',
                          borderRadius: '2px',
                          background: lap.color,
                          flexShrink: 0,
                        }}
                      />
                      <span
                        style={{
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                        title={label}
                      >
                        {label}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

interface ToolbarButtonProps {
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
  title: string;
  icon: React.ReactNode;
  label: string;
}

const ToolbarToggleButton: React.FC<ToolbarButtonProps> = ({
  active = false,
  disabled = false,
  onClick,
  title,
  icon,
  label,
}) => (
  <button
    type="button"
    disabled={disabled}
    onClick={onClick}
    title={title}
    aria-pressed={active}
    style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '5px',
      height: '28px',
      padding: '0 8px',
      borderRadius: '4px',
      border: `1px solid ${active && !disabled ? 'var(--accent-border)' : 'var(--border-subtle)'}`,
      background: active && !disabled ? 'var(--accent-subtle)' : 'var(--bg-button)',
      color: disabled ? 'var(--text-muted)' : active ? 'var(--accent-fg)' : 'var(--text-primary)',
      opacity: disabled ? 0.45 : 1,
      fontSize: '12px',
      fontWeight: active && !disabled ? 600 : 500,
      cursor: disabled ? 'not-allowed' : 'pointer',
      flexShrink: 0,
      whiteSpace: 'nowrap',
    }}
  >
    {icon}
    <span>{label}</span>
  </button>
);

const ToolbarActionButton: React.FC<Omit<ToolbarButtonProps, 'active'>> = ({
  onClick,
  title,
  icon,
  label,
}) => (
  <button
    type="button"
    onClick={onClick}
    title={title}
    style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '5px',
      height: '28px',
      padding: '0 8px',
      borderRadius: '4px',
      border: '1px solid var(--border-subtle)',
      background: 'var(--bg-button)',
      color: 'var(--text-primary)',
      fontSize: '12px',
      fontWeight: 500,
      cursor: 'pointer',
      flexShrink: 0,
      whiteSpace: 'nowrap',
    }}
  >
    {icon}
    <span>{label}</span>
  </button>
);

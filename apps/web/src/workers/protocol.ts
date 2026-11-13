import {
  ChannelDef,
  ParseSessionConfig,
  SelectedLapInfo,
} from '@/types/telemetry';
export interface PlotCurveData {
  channelSlug: string;
  sessionId: string;
  lapNumber: number;
  color: string;
  x: Float64Array;
  y: Float64Array;
}

export interface PlotDataResponse {
  curves: PlotCurveData[];
  xExtent: [number, number] | null;
  yExtents: Record<string, [number, number]>;
}

export interface CursorSampleItem {
  lapKey: string;
  sessionId: string;
  lapNumber: number;
  color: string;
  actualX: number;
  actualY: number;
}

export interface HoveredLapInput {
  sessionId: string;
  lapNumber: number;
}

export interface HoveredPlotBounds {
  channelSlug: string;
  hoveredLap?: HoveredLapInput | null;
  normalizeY?: boolean;
  channelExtents?: Record<string, [number, number]>;
  targetY: number;
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
  plotWidth: number;
  plotHeight: number;
}

export interface CursorQueryResponse {
  snappedX: number;
  samplesByChannel: Record<string, CursorSampleItem[]>;
  trackMapDots: Array<{ distance: number; color: string }>;
}

export interface FormulaValidationResult {
  valid: boolean;
  message: string;
  variables: string[];
}

export type WorkerRequest =
  | { id: number; type: 'init' }
  | { id: number; type: 'inspectFile'; fileName: string; buffer: ArrayBuffer }
  | { id: number; type: 'discardPendingFile'; fileToken: string }
  | { id: number; type: 'importSession'; fileToken: string; config: ParseSessionConfig }
  | { id: number; type: 'reparseSession'; sessionId: string; config: ParseSessionConfig }
  | { id: number; type: 'removeSession'; sessionId: string }
  | { id: number; type: 'clearSessions' }
  | { id: number; type: 'clearCalculatedCache'; calcSlugs: string[] }
  | { id: number; type: 'validateFormula'; formula: string; expectedVars?: string[] }
  | { id: number; type: 'parseTrackMapColumns'; fileName: string; buffer: ArrayBuffer }
  | {
      id: number;
      type: 'loadTrackMapData';
      mapToken: string;
      fileName: string;
      xCol: string;
      yCol: string;
      distCol: string | null;
    }
  | { id: number; type: 'discardMapToken'; mapToken: string }
  | {
      id: number;
      type: 'getPlotData';
      xAxisSlug: string;
      channels: string[];
      selectedLaps: SelectedLapInfo[];
      xMin: number | null;
      xMax: number | null;
      maxBuckets: number;
      filterGaps: boolean;
      globalCalcs: ChannelDef[];
    }
  | {
      id: number;
      type: 'queryCursor';
      xAxisSlug: string;
      channels: string[];
      selectedLaps: SelectedLapInfo[];
      targetX: number;
      hovered?: HoveredPlotBounds | null;
      globalCalcs: ChannelDef[];
    };

export type WorkerResponse =
  | { id: number; ok: true; result: unknown }
  | { id: number; ok: false; error: string };

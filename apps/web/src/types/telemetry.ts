export const APP_NAME = 'SZenergy Pro Analyser';
export const APP_VERSION = '2.0.0';

export const STD_CH_LAP_NUM = 'Lap Number';
export const STD_CH_LAP_TIME = 'Lap Time';
export const STD_CH_LAP_DIST = 'Lap Distance';

export const STD_CH_LAP_NUM_SLUG = 'lap_num';
export const STD_CH_LAP_TIME_SLUG = 'lap_time';
export const STD_CH_LAP_DIST_SLUG = 'lap_dist';
export const REQUIRED_CHANNEL_GROUP_IDS = [
  STD_CH_LAP_NUM_SLUG,
  STD_CH_LAP_TIME_SLUG,
  STD_CH_LAP_DIST_SLUG,
] as const;

export function isRequiredChannelGroupId(id: string): boolean {
  return (
    id === STD_CH_LAP_NUM_SLUG ||
    id === STD_CH_LAP_TIME_SLUG ||
    id === STD_CH_LAP_DIST_SLUG
  );
}

export const MAX_STACKED_PLOTS = 6;
export const MAX_SELECTED_CHANNELS = MAX_STACKED_PLOTS;
export const MAX_RECENT_FILES = 15;

export const CROSSHAIR_LINE_COLOR = '#FFD740';

export const DEFAULT_GAP_TIME_THRESHOLD = 1.0; // seconds
export const DEFAULT_GAP_DIST_THRESHOLD = 50.0; // meters

export const LAP_COLORS: readonly string[] = [
  '#FF0000',
  '#00FF00',
  '#0000FF',
  '#FFFF00',
  '#00FFFF',
  '#FF00FF',
  '#FF9600',
  '#FF0096',
  '#00FF96',
  '#96FF00',
  '#9600FF',
  '#0096FF',
] as const;

export interface ChannelTransform {
  factor: number;
  offset: number;
}

export interface GroupChannelOverride {
  channel: string;
  factor: number;
  offset: number;
}

export interface ChannelGroupDef {
  id: string;
  name: string;
  unit: string;
  channels: string[];
  transforms?: Record<string, ChannelTransform>;
}

export interface SystemRoleAliases {
  lap: string[];
  time: string[];
  dist: string[];
}

export interface FileImportConfig {
  sheet_name: string | null;
  lap_col: string;
  time_col: string | null;
  dist_col: string | null;
  gap_time_threshold?: number | null;
  gap_dist_threshold?: number | null;
  group_overrides?: Record<string, GroupChannelOverride>;
}

export interface TrackMapDef {
  name: string;
  slug: string;
  rotation: number;
  color: string;
  x: number[];
  y: number[];
  distance: number[] | null;
}

export interface MapData {
  x: number[];
  y: number[];
  distance: number[] | null;
}

export interface LapSummary {
  lap_number: number;
  duration: number;
  distance: number;
  sample_count: number;
}

export interface SessionSummary {
  id: string;
  name: string;
  sheet_name: string | null;
  channels: string[];
  skipped_channels: string[];
  available_columns: string[];
  lap_col: string;
  time_col: string | null;
  dist_col: string | null;
  has_time: boolean;
  has_dist: boolean;
  laps: LapSummary[];
  gap_time_threshold: number | null;
  gap_dist_threshold: number | null;
  group_overrides?: Record<string, GroupChannelOverride>;
}

export interface ParseSessionConfig {
  session_id: string;
  file_name: string;
  sheet_name: string | null;
  lap_col: string;
  time_col: string | null;
  dist_col: string | null;
  gap_time_threshold: number | null;
  gap_dist_threshold: number | null;
  group_overrides?: Record<string, GroupChannelOverride>;
}

export interface FilePreview {
  columns: string[];
  rows: string[][];
  sheets?: string[];
  selectedSheet?: string;
  finiteCounts: number[];
  totalRows: number;
}

export interface SelectedLapInfo {
  sessionId: string;
  lapNumber: number;
  color: string;
}

export type ThemeMode = 'auto' | 'dark' | 'light';
export type GroupingMode = 'channel' | 'lap';

export interface GraphViewSettings {
  showXGrid: boolean;
  showYGrid: boolean;
  showCursorValues: boolean;
  showCursorOnGraph: boolean;
  showCursorAboveGraph: boolean;
  showLegend: boolean;
  antialias: boolean;
  filterGaps: boolean;
  xAxisSlug: string;
  groupingMode: GroupingMode;
  normalizeY: boolean;
}

export const DEFAULT_GRAPH_VIEW_SETTINGS: GraphViewSettings = {
  showXGrid: true,
  showYGrid: true,
  showCursorValues: true,
  showCursorOnGraph: true,
  showCursorAboveGraph: true,
  showLegend: false,
  antialias: true,
  filterGaps: false,
  xAxisSlug: STD_CH_LAP_DIST_SLUG,
  groupingMode: 'channel',
  normalizeY: false,
};

export interface AppSettings {
  themeMode: ThemeMode;
  graph: GraphViewSettings;
  sidebarBottomTabIndex: number;
  selectedMapSlug: string | null;
  sidebarWidth?: number;
  sidebarSplitRatio?: number;
}

export const DEFAULT_APP_SETTINGS: AppSettings = {
  themeMode: 'auto',
  graph: { ...DEFAULT_GRAPH_VIEW_SETTINGS },
  sidebarBottomTabIndex: 0,
  selectedMapSlug: null,
};

export interface RecentFileEntry {
  id: string;
  name: string;
  size: number;
  lastModified: number;
  lastOpenedAt: number;
  handle?: FileSystemFileHandle;
}

export interface ConfigExportEnvelope {
  schema_version: 2;
  type: 'szenergypro_config_export';
  data: {
    channelGroups: ChannelGroupDef[];
    systemAliases: SystemRoleAliases;
  };
}

export interface TrackMapExportEnvelope {
  schema_version: 1;
  data: TrackMapDef;
}

import {
  clearRecentFiles as dbClearRecentFiles,
  deleteMapBySlug as dbDeleteMapBySlug,
  deleteRecentFile as dbDeleteRecentFile,
  getAllMaps as dbGetAllMaps,
  getRecentFiles as dbGetRecentFiles,
  kvGet,
  kvSet,
  putMap as dbPutMap,
  upsertRecentFile as dbUpsertRecentFile,
} from '@/state/db';
import {
  AppSettings,
  ChannelGroupDef,
  ChannelTransform,
  ConfigExportEnvelope,
  DEFAULT_APP_SETTINGS,
  DEFAULT_GRAPH_VIEW_SETTINGS,
  FileImportConfig,
  GraphViewSettings,
  GroupChannelOverride,
  isRequiredChannelGroupId,
  LAP_COLORS,
  RecentFileEntry,
  REQUIRED_CHANNEL_GROUP_IDS,
  STD_CH_LAP_DIST,
  STD_CH_LAP_DIST_SLUG,
  STD_CH_LAP_NUM,
  STD_CH_LAP_NUM_SLUG,
  STD_CH_LAP_TIME,
  STD_CH_LAP_TIME_SLUG,
  SystemRoleAliases,
  ThemeMode,
  TrackMapDef,
  TrackMapExportEnvelope,
} from '@/types/telemetry';

const KV_CHANNEL_GROUPS = 'channel_groups';
const KV_SYSTEM_ALIASES = 'system_aliases';
const KV_FILE_IMPORTS = 'file_imports';
const KV_SETTINGS = 'settings';

const DEFAULT_SYSTEM_ALIASES: SystemRoleAliases = {
  lap: ['Lap Number', 'Lap_Number', 'lap_num', 'Lap', 'lap'],
  time: ['Lap Time', 'Lap_Time', 'Lap_Time_[s]', 'Time_s', 'lap_time', 'Time', 'time'],
  dist: [
    'Lap Distance',
    'Lap_Distance',
    'Lap_Distance_[m]',
    'Distance_m',
    'Distance_[m]',
    'lap_dist',
    'Distance',
    'distance',
    'Dist',
  ],
};

export function generateSlug(label: string): string {
  const slug = label
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, '_')
    .replace(/^_+|_+$/g, '');
  return slug || 'group';
}

export function generateUniqueSlug(label: string, existingSlugs: Iterable<string>): string {
  const taken = new Set(existingSlugs);
  const baseSlug = generateSlug(label);
  let slug = baseSlug;
  let counter = 1;
  while (taken.has(slug)) {
    slug = `${baseSlug}_${counter}`;
    counter += 1;
  }
  return slug;
}

export function formatChannelDisplay(label: string, unit = ''): string {
  if (!label) {
    return '';
  }
  const unitStr = (unit ?? '').trim();
  if (!unitStr) {
    return label;
  }
  if (label.endsWith(`[${unitStr}]`) || label.endsWith(`(${unitStr})`)) {
    return label;
  }
  return `${label} [${unitStr}]`;
}

function fnv1aHex(input: string): string {
  let h1 = 0x811c9dc5;
  let h2 = 0x811c9dc5 ^ 0x9e3779b9;
  for (let i = 0; i < input.length; i += 1) {
    const ch = input.charCodeAt(i);
    h1 ^= ch & 0xff;
    h1 = Math.imul(h1, 0x01000193);
    h2 ^= (ch >> 8) ^ (ch & 0xff);
    h2 = Math.imul(h2, 0x01000193);
  }
  return (h1 >>> 0).toString(16).padStart(8, '0') + (h2 >>> 0).toString(16).padStart(8, '0');
}

export async function computeFileSignature(
  fileName: string,
  rawColumns: string[],
  sheetName?: string | null,
): Promise<string> {
  const cleanName = fileName.trim();
  const payload = JSON.stringify({
    fileName: cleanName,
    sheetName: sheetName ?? null,
    columns: rawColumns,
  });

  if (typeof globalThis.crypto !== 'undefined' && globalThis.crypto.subtle) {
    const encoded = new TextEncoder().encode(payload);
    const digest = await globalThis.crypto.subtle.digest('SHA-256', encoded);
    const bytes = new Uint8Array(digest);
    let hex = '';
    for (let i = 0; i < bytes.length; i += 1) {
      hex += bytes[i].toString(16).padStart(2, '0');
    }
    return `${cleanName}::${hex}`;
  }

  return `${cleanName}::fnv1a_${fnv1aHex(payload)}`;
}

function isPlainObject(val: unknown): val is Record<string, unknown> {
  return typeof val === 'object' && val !== null && !Array.isArray(val);
}

function cloneTransforms(
  transforms?: Record<string, ChannelTransform>,
): Record<string, ChannelTransform> | undefined {
  if (!transforms) return undefined;
  const out: Record<string, ChannelTransform> = {};
  for (const [k, v] of Object.entries(transforms)) {
    if (!v || typeof v !== 'object') continue;
    const factor = typeof v.factor === 'number' && Number.isFinite(v.factor) ? v.factor : 1;
    const offset = typeof v.offset === 'number' && Number.isFinite(v.offset) ? v.offset : 0;
    if (factor !== 1 || offset !== 0) {
      out[k] = { factor, offset };
    }
  }
  return Object.keys(out).length > 0 ? out : undefined;
}

function cloneGroupOverrides(
  overrides?: Record<string, GroupChannelOverride>,
): Record<string, GroupChannelOverride> | undefined {
  if (!overrides) return undefined;
  const out: Record<string, GroupChannelOverride> = {};
  for (const [gid, ov] of Object.entries(overrides)) {
    if (!ov || typeof ov !== 'object' || typeof ov.channel !== 'string' || !ov.channel.trim()) {
      continue;
    }
    out[gid] = {
      channel: ov.channel.trim(),
      factor: typeof ov.factor === 'number' && Number.isFinite(ov.factor) ? ov.factor : 1,
      offset: typeof ov.offset === 'number' && Number.isFinite(ov.offset) ? ov.offset : 0,
    };
  }
  return Object.keys(out).length > 0 ? out : undefined;
}

function cloneGroup(g: ChannelGroupDef): ChannelGroupDef {
  const transforms = cloneTransforms(g.transforms);
  return {
    id: g.id,
    name: g.name,
    unit: g.unit ?? '',
    channels: [...g.channels],
    ...(transforms ? { transforms } : {}),
  };
}

function cloneFileImport(cfg: FileImportConfig): FileImportConfig {
  const group_overrides = cloneGroupOverrides(cfg.group_overrides);
  return {
    sheet_name: cfg.sheet_name ?? null,
    lap_col: cfg.lap_col,
    time_col: cfg.time_col ?? null,
    dist_col: cfg.dist_col ?? null,
    gap_time_threshold: cfg.gap_time_threshold ?? null,
    gap_dist_threshold: cfg.gap_dist_threshold ?? null,
    ...(group_overrides ? { group_overrides } : {}),
  };
}

function normalizeColName(col: string): string {
  return col.trim().toLowerCase().replace(/\s+/g, '_');
}

function stripUnitSuffix(col: string): string {
  return col
    .trim()
    .replace(/[\s_]*(\[[^\]]*\]|\([^)]*\))\s*$/, '')
    .trim();
}

function mergeUniqueStrings(primary: string[], fallback: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const s of [...primary, ...fallback]) {
    const clean = s.trim();
    if (!clean) continue;
    const key = clean.toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      out.push(clean);
    }
  }
  return out;
}

export class StateManager {
  private channelGroups: ChannelGroupDef[] = [];
  private systemAliases: SystemRoleAliases = {
    lap: [...DEFAULT_SYSTEM_ALIASES.lap],
    time: [...DEFAULT_SYSTEM_ALIASES.time],
    dist: [...DEFAULT_SYSTEM_ALIASES.dist],
  };
  private fileImports: Record<string, FileImportConfig> = {};
  private settings: AppSettings = {
    ...DEFAULT_APP_SETTINGS,
    graph: { ...DEFAULT_GRAPH_VIEW_SETTINGS },
  };
  private maps: TrackMapDef[] = [];
  private recentFiles: RecentFileEntry[] = [];
  private initialized = false;
  private initPromise: Promise<void> | null = null;

  async init(): Promise<void> {
    if (this.initialized) {
      return;
    }
    if (this.initPromise) {
      return this.initPromise;
    }

    this.initPromise = (async () => {
      const [rawGroups, rawAliases, rawFileImports, rawSettings, maps, recentFiles] =
        await Promise.all([
          kvGet<unknown>(KV_CHANNEL_GROUPS),
          kvGet<unknown>(KV_SYSTEM_ALIASES),
          kvGet<unknown>(KV_FILE_IMPORTS),
          kvGet<unknown>(KV_SETTINGS),
          dbGetAllMaps(),
          dbGetRecentFiles(),
        ]);

      if (Array.isArray(rawGroups)) {
        this.channelGroups = this.parseStoredGroups(rawGroups);
      }

      if (isPlainObject(rawAliases)) {
        const lap = Array.isArray(rawAliases.lap)
          ? rawAliases.lap.filter((s): s is string => typeof s === 'string')
          : [];
        const time = Array.isArray(rawAliases.time)
          ? rawAliases.time.filter((s): s is string => typeof s === 'string')
          : [];
        const dist = Array.isArray(rawAliases.dist)
          ? rawAliases.dist.filter((s): s is string => typeof s === 'string')
          : [];
        this.systemAliases = {
          lap: mergeUniqueStrings(lap, DEFAULT_SYSTEM_ALIASES.lap),
          time: mergeUniqueStrings(time, DEFAULT_SYSTEM_ALIASES.time),
          dist: mergeUniqueStrings(dist, DEFAULT_SYSTEM_ALIASES.dist),
        };
      }

      const groupsChanged = this.ensureRequiredGroupsInMemory();
      if (groupsChanged) {
        await kvSet(KV_CHANNEL_GROUPS, this.channelGroups);
      }
      if (isPlainObject(rawFileImports)) {
        const loaded: Record<string, FileImportConfig> = {};
        for (const [sig, val] of Object.entries(rawFileImports)) {
          if (isPlainObject(val) && typeof val.lap_col === 'string' && val.lap_col.trim()) {
            const group_overrides = isPlainObject(val.group_overrides)
              ? cloneGroupOverrides(val.group_overrides as Record<string, GroupChannelOverride>)
              : undefined;
            loaded[sig] = {
              sheet_name: typeof val.sheet_name === 'string' ? val.sheet_name : null,
              lap_col: val.lap_col,
              time_col: typeof val.time_col === 'string' && val.time_col ? val.time_col : null,
              dist_col: typeof val.dist_col === 'string' && val.dist_col ? val.dist_col : null,
              gap_time_threshold:
                typeof val.gap_time_threshold === 'number' ? val.gap_time_threshold : null,
              gap_dist_threshold:
                typeof val.gap_dist_threshold === 'number' ? val.gap_dist_threshold : null,
              ...(group_overrides ? { group_overrides } : {}),
            };
          }
        }
        this.fileImports = loaded;
      }

      if (isPlainObject(rawSettings)) {
        const rawGraph = isPlainObject(rawSettings.graph) ? rawSettings.graph : {};
        const themeMode: ThemeMode =
          rawSettings.themeMode === 'dark' ||
          rawSettings.themeMode === 'light' ||
          rawSettings.themeMode === 'auto'
            ? rawSettings.themeMode
            : DEFAULT_APP_SETTINGS.themeMode;

        this.settings = {
          themeMode,
          graph: {
            showXGrid:
              typeof rawGraph.showXGrid === 'boolean'
                ? rawGraph.showXGrid
                : DEFAULT_GRAPH_VIEW_SETTINGS.showXGrid,
            showYGrid:
              typeof rawGraph.showYGrid === 'boolean'
                ? rawGraph.showYGrid
                : DEFAULT_GRAPH_VIEW_SETTINGS.showYGrid,
            showCursorValues:
              typeof rawGraph.showCursorValues === 'boolean'
                ? rawGraph.showCursorValues
                : DEFAULT_GRAPH_VIEW_SETTINGS.showCursorValues,
            showCursorOnGraph:
              typeof rawGraph.showCursorOnGraph === 'boolean'
                ? rawGraph.showCursorOnGraph
                : DEFAULT_GRAPH_VIEW_SETTINGS.showCursorOnGraph,
            showCursorAboveGraph:
              typeof rawGraph.showCursorAboveGraph === 'boolean'
                ? rawGraph.showCursorAboveGraph
                : DEFAULT_GRAPH_VIEW_SETTINGS.showCursorAboveGraph,
            showLegend:
              typeof rawGraph.showLegend === 'boolean'
                ? rawGraph.showLegend
                : DEFAULT_GRAPH_VIEW_SETTINGS.showLegend,
            antialias:
              typeof rawGraph.antialias === 'boolean'
                ? rawGraph.antialias
                : DEFAULT_GRAPH_VIEW_SETTINGS.antialias,
            filterGaps:
              typeof rawGraph.filterGaps === 'boolean'
                ? rawGraph.filterGaps
                : DEFAULT_GRAPH_VIEW_SETTINGS.filterGaps,
            xAxisSlug:
              typeof rawGraph.xAxisSlug === 'string' && rawGraph.xAxisSlug
                ? rawGraph.xAxisSlug
                : DEFAULT_GRAPH_VIEW_SETTINGS.xAxisSlug,
            groupingMode:
              rawGraph.groupingMode === 'lap' || rawGraph.groupingMode === 'channel'
                ? rawGraph.groupingMode
                : DEFAULT_GRAPH_VIEW_SETTINGS.groupingMode,
            normalizeY:
              typeof rawGraph.normalizeY === 'boolean'
                ? rawGraph.normalizeY
                : DEFAULT_GRAPH_VIEW_SETTINGS.normalizeY,
          },
          sidebarBottomTabIndex:
            typeof rawSettings.sidebarBottomTabIndex === 'number'
              ? rawSettings.sidebarBottomTabIndex
              : DEFAULT_APP_SETTINGS.sidebarBottomTabIndex,
          selectedMapSlug:
            typeof rawSettings.selectedMapSlug === 'string' ? rawSettings.selectedMapSlug : null,
          sidebarWidth:
            typeof rawSettings.sidebarWidth === 'number' ? rawSettings.sidebarWidth : undefined,
          sidebarSplitRatio:
            typeof rawSettings.sidebarSplitRatio === 'number'
              ? rawSettings.sidebarSplitRatio
              : undefined,
        };
      }

      this.maps = maps;
      this.recentFiles = recentFiles;
      this.initialized = true;
    })();

    return this.initPromise;
  }

  private parseStoredGroups(data: unknown[]): ChannelGroupDef[] {
    const out: ChannelGroupDef[] = [];
    const seenIds = new Set<string>();
    for (const item of data) {
      if (!isPlainObject(item) || typeof item.name !== 'string') continue;
      const name = item.name.trim();
      if (!name) continue;
      const rawId = typeof item.id === 'string' && item.id.trim() ? item.id.trim() : `grp_${generateSlug(name)}`;
      const id = seenIds.has(rawId) ? generateUniqueSlug(rawId, seenIds) : rawId;
      seenIds.add(id);
      const unit = typeof item.unit === 'string' ? item.unit.trim() : '';
      const channels = Array.isArray(item.channels)
        ? mergeUniqueStrings(
            item.channels.filter((c): c is string => typeof c === 'string'),
            [],
          )
        : [];
      const transforms = isPlainObject(item.transforms)
        ? cloneTransforms(item.transforms as Record<string, ChannelTransform>)
        : undefined;
      out.push({ id, name, unit, channels, ...(transforms ? { transforms } : {}) });
    }
    return out;
  }
  private getRequiredGroupMeta(id: string): { name: string; unit: string; defaultAliases: string[] } | null {
    if (id === STD_CH_LAP_NUM_SLUG) {
      return { name: STD_CH_LAP_NUM, unit: '', defaultAliases: this.systemAliases.lap };
    }
    if (id === STD_CH_LAP_TIME_SLUG) {
      return { name: STD_CH_LAP_TIME, unit: 's', defaultAliases: this.systemAliases.time };
    }
    if (id === STD_CH_LAP_DIST_SLUG) {
      return { name: STD_CH_LAP_DIST, unit: 'm', defaultAliases: this.systemAliases.dist };
    }
    return null;
  }

  private ensureRequiredGroupsInMemory(): boolean {
    const byId = new Map<string, ChannelGroupDef>();
    const customGroups: ChannelGroupDef[] = [];
    const claimedByCustom = new Set<string>();

    for (const g of this.channelGroups) {
      if (isRequiredChannelGroupId(g.id)) {
        byId.set(g.id, cloneGroup(g));
      } else {
        const cloned = cloneGroup(g);
        customGroups.push(cloned);
        for (const ch of cloned.channels) {
          claimedByCustom.add(ch.toLowerCase());
        }
      }
    }

    const requiredGroups: ChannelGroupDef[] = [];
    for (const reqId of REQUIRED_CHANNEL_GROUP_IDS) {
      const meta = this.getRequiredGroupMeta(reqId)!;
      const existing = byId.get(reqId);
      if (existing) {
        const channels =
          existing.channels.length > 0
            ? existing.channels
            : meta.defaultAliases.filter((c) => !claimedByCustom.has(c.toLowerCase()));
        const transforms = cloneTransforms(existing.transforms);
        requiredGroups.push({
          id: reqId,
          name: meta.name,
          unit: meta.unit,
          channels: [...channels],
          ...(transforms ? { transforms } : {}),
        });
      } else {
        requiredGroups.push({
          id: reqId,
          name: meta.name,
          unit: meta.unit,
          channels: meta.defaultAliases.filter((c) => !claimedByCustom.has(c.toLowerCase())),
        });
      }
    }

    const next = [...requiredGroups, ...customGroups];
    const changed = JSON.stringify(next) !== JSON.stringify(this.channelGroups);
    this.channelGroups = next;
    this.syncSystemAliasesFromRequiredGroups();
    return changed;
  }

  private syncSystemAliasesFromRequiredGroups(): void {
    const lapGrp = this.channelGroups.find((g) => g.id === STD_CH_LAP_NUM_SLUG);
    const timeGrp = this.channelGroups.find((g) => g.id === STD_CH_LAP_TIME_SLUG);
    const distGrp = this.channelGroups.find((g) => g.id === STD_CH_LAP_DIST_SLUG);
    this.systemAliases = {
      lap: lapGrp && lapGrp.channels.length > 0 ? [...lapGrp.channels] : [...this.systemAliases.lap],
      time: timeGrp && timeGrp.channels.length > 0 ? [...timeGrp.channels] : [...this.systemAliases.time],
      dist: distGrp && distGrp.channels.length > 0 ? [...distGrp.channels] : [...this.systemAliases.dist],
    };
  }

  // -------------------------------------------------------------------------
  // Channel Groups
  // -------------------------------------------------------------------------

  getChannelGroups(): ChannelGroupDef[] {
    return this.channelGroups.map(cloneGroup);
  }

  async saveChannelGroups(groups: ChannelGroupDef[]): Promise<void> {
    this.channelGroups = groups.map(cloneGroup);
    this.ensureRequiredGroupsInMemory();
    await kvSet(KV_CHANNEL_GROUPS, this.channelGroups);
    await kvSet(KV_SYSTEM_ALIASES, this.systemAliases);
  }

  getGroupById(groupId: string): ChannelGroupDef | null {
    const found = this.channelGroups.find((g) => g.id === groupId);
    return found ? cloneGroup(found) : null;
  }

  getGroupForRawChannel(rawChannel: string): ChannelGroupDef | null {
    const found = this.channelGroups.find((g) => g.channels.includes(rawChannel));
    return found ? cloneGroup(found) : null;
  }

  async upsertChannelGroup(params: {
    id?: string;
    name: string;
    unit?: string;
    channels: string[];
  }): Promise<ChannelGroupDef> {
    const cleanName = params.name.trim();
    const cleanUnit = (params.unit ?? '').trim();
    const cleanChannels = mergeUniqueStrings(params.channels, []);
    const memberSet = new Set(cleanChannels);

    // Ensure a raw channel only belongs to one group at a time
    const nextGroups = this.channelGroups.map((g) => {
      if (params.id && g.id === params.id) {
        return cloneGroup(g);
      }
      return {
        ...cloneGroup(g),
        channels: g.channels.filter((c) => !memberSet.has(c)),
      };
    });

    if (params.id) {
      const reqMeta = this.getRequiredGroupMeta(params.id);
      const idx = nextGroups.findIndex((g) => g.id === params.id);
      if (idx >= 0) {
        const transforms = cloneTransforms(nextGroups[idx].transforms);
        const updated: ChannelGroupDef = {
          id: params.id,
          name: reqMeta ? reqMeta.name : cleanName,
          unit: reqMeta ? reqMeta.unit : cleanUnit,
          channels: cleanChannels,
          ...(transforms ? { transforms } : {}),
        };
        nextGroups[idx] = updated;
        await this.saveChannelGroups(nextGroups);
        return cloneGroup(this.getGroupById(params.id) ?? updated);
      }
    }

    const existingIds = nextGroups.map((g) => g.id);
    const id = generateUniqueSlug(`grp_${cleanName}`, existingIds);
    const created: ChannelGroupDef = {
      id,
      name: cleanName,
      unit: cleanUnit,
      channels: cleanChannels,
    };
    nextGroups.push(created);
    await this.saveChannelGroups(nextGroups);
    return cloneGroup(created);
  }
  async addChannelsToGroup(groupId: string, rawChannels: string[]): Promise<void> {
    const group = this.getGroupById(groupId);
    if (!group) return;
    await this.upsertChannelGroup({
      id: group.id,
      name: group.name,
      unit: group.unit,
      channels: [...group.channels, ...rawChannels],
    });
  }

  async deleteChannelGroup(groupId: string): Promise<void> {
    if (isRequiredChannelGroupId(groupId)) {
      return;
    }
    const filtered = this.channelGroups.filter((g) => g.id !== groupId);
    if (filtered.length !== this.channelGroups.length) {
      await this.saveChannelGroups(filtered);
    }
  }

  getDisplayNameByKey(keyOrGroupId: string): string {
    if (keyOrGroupId === STD_CH_LAP_NUM_SLUG) return STD_CH_LAP_NUM;
    if (keyOrGroupId === STD_CH_LAP_TIME_SLUG) return formatChannelDisplay(STD_CH_LAP_TIME, 's');
    if (keyOrGroupId === STD_CH_LAP_DIST_SLUG) return formatChannelDisplay(STD_CH_LAP_DIST, 'm');

    const grp = this.channelGroups.find((g) => g.id === keyOrGroupId);
    if (grp) {
      return formatChannelDisplay(grp.name, grp.unit);
    }
    return keyOrGroupId;
  }

  // -------------------------------------------------------------------------
  // System Role Aliases & Auto-Detection
  // -------------------------------------------------------------------------

  getSystemAliases(): SystemRoleAliases {
    return {
      lap: [...this.systemAliases.lap],
      time: [...this.systemAliases.time],
      dist: [...this.systemAliases.dist],
    };
  }

  async recordSystemAliases(
    lapCol: string,
    timeCol: string | null,
    distCol: string | null,
  ): Promise<void> {
    const appendMissing = (existing: string[], col: string | null): string[] => {
      if (!col || !col.trim()) return existing;
      const clean = col.trim();
      if (existing.some((c) => c.toLowerCase() === clean.toLowerCase())) {
        return existing;
      }
      return [clean, ...existing];
    };

    this.systemAliases = {
      lap: appendMissing(this.systemAliases.lap, lapCol),
      time: appendMissing(this.systemAliases.time, timeCol),
      dist: appendMissing(this.systemAliases.dist, distCol),
    };
    await kvSet(KV_SYSTEM_ALIASES, this.systemAliases);

    const addToRequiredGroup = async (groupId: string, col: string | null) => {
      if (!col || !col.trim()) return;
      const clean = col.trim();
      const grp = this.getGroupById(groupId);
      if (!grp) return;
      if (grp.channels.some((c) => c.toLowerCase() === clean.toLowerCase())) {
        return;
      }
      await this.upsertChannelGroup({
        id: grp.id,
        name: grp.name,
        unit: grp.unit,
        channels: [clean, ...grp.channels],
      });
    };

    await addToRequiredGroup(STD_CH_LAP_NUM_SLUG, lapCol);
    await addToRequiredGroup(STD_CH_LAP_TIME_SLUG, timeCol);
    await addToRequiredGroup(STD_CH_LAP_DIST_SLUG, distCol);
  }

  autoDetectImportRoles(
    columns: string[],
    finiteCounts?: number[],
  ): { lapCol: string | null; timeCol: string | null; distCol: string | null } {
    const isNumericCandidate = (idx: number): boolean => {
      if (!finiteCounts || idx >= finiteCounts.length) return true;
      return finiteCounts[idx] >= 1;
    };

    const matchAlias = (aliases: string[], excludeCols: Set<string>): string | null => {
      for (const alias of aliases) {
        const idx = columns.findIndex(
          (c, i) => !excludeCols.has(c) && c === alias && isNumericCandidate(i),
        );
        if (idx >= 0) return columns[idx];
      }
      for (const alias of aliases) {
        const normAlias = normalizeColName(alias);
        const idx = columns.findIndex(
          (c, i) => !excludeCols.has(c) && normalizeColName(c) === normAlias && isNumericCandidate(i),
        );
        if (idx >= 0) return columns[idx];
      }
      for (const alias of aliases) {
        const normAlias = normalizeColName(stripUnitSuffix(alias));
        if (!normAlias) continue;
        const idx = columns.findIndex(
          (c, i) =>
            !excludeCols.has(c) &&
            normalizeColName(stripUnitSuffix(c)) === normAlias &&
            isNumericCandidate(i),
        );
        if (idx >= 0) return columns[idx];
      }
      return null;
    };

    const used = new Set<string>();
    const lapCol = matchAlias(this.systemAliases.lap, used);
    if (lapCol) used.add(lapCol);
    const timeCol = matchAlias(this.systemAliases.time, used);
    if (timeCol) used.add(timeCol);
    const distCol = matchAlias(this.systemAliases.dist, used);

    return { lapCol, timeCol, distCol };
  }

  // -------------------------------------------------------------------------
  // Per-File Import Memory
  // -------------------------------------------------------------------------

  async computeFileSignature(
    fileName: string,
    rawColumns: string[],
    sheetName?: string | null,
  ): Promise<string> {
    return computeFileSignature(fileName, rawColumns, sheetName);
  }

  getFileImportConfig(signature: string): FileImportConfig | null {
    const entry = this.fileImports[signature];
    return entry ? cloneFileImport(entry) : null;
  }

  getAllFileImports(): Record<string, FileImportConfig> {
    const res: Record<string, FileImportConfig> = {};
    for (const [sig, cfg] of Object.entries(this.fileImports)) {
      res[sig] = cloneFileImport(cfg);
    }
    return res;
  }

  async saveFileImportConfig(signature: string, config: FileImportConfig): Promise<void> {
    this.fileImports[signature] = cloneFileImport(config);
    await kvSet(KV_FILE_IMPORTS, this.fileImports);
  }

  async removeFileImportConfig(signature: string): Promise<void> {
    if (signature in this.fileImports) {
      delete this.fileImports[signature];
      await kvSet(KV_FILE_IMPORTS, this.fileImports);
    }
  }

  async clearFileImports(): Promise<void> {
    this.fileImports = {};
    await kvSet(KV_FILE_IMPORTS, this.fileImports);
  }

  async replaceAllFileImports(nextImports: Record<string, FileImportConfig>): Promise<void> {
    const cleaned: Record<string, FileImportConfig> = {};
    for (const [sig, cfg] of Object.entries(nextImports)) {
      cleaned[sig] = cloneFileImport(cfg);
    }
    this.fileImports = cleaned;
    await kvSet(KV_FILE_IMPORTS, this.fileImports);
  }

  isFileImportValidForColumns(config: FileImportConfig, rawColumns: string[]): boolean {
    const rawSet = new Set(rawColumns);
    if (!config.lap_col || !rawSet.has(config.lap_col)) {
      return false;
    }
    const hasTime = Boolean(config.time_col && rawSet.has(config.time_col));
    const hasDist = Boolean(config.dist_col && rawSet.has(config.dist_col));
    if (config.time_col && !hasTime) return false;
    if (config.dist_col && !hasDist) return false;
    return hasTime || hasDist;
  }

  // -------------------------------------------------------------------------
  // Settings
  // -------------------------------------------------------------------------

  getSettings(): AppSettings {
    return {
      ...this.settings,
      graph: { ...this.settings.graph },
    };
  }

  async saveSettings(next: Partial<AppSettings>): Promise<AppSettings> {
    this.settings = {
      ...this.settings,
      ...next,
      graph: {
        ...this.settings.graph,
        ...(next.graph ?? {}),
      },
    };
    await kvSet(KV_SETTINGS, this.settings);
    return this.getSettings();
  }

  getGraphSettings(): GraphViewSettings {
    return { ...this.settings.graph };
  }

  async updateGraphSettings(partial: Partial<GraphViewSettings>): Promise<GraphViewSettings> {
    const updated = await this.saveSettings({
      graph: {
        ...this.settings.graph,
        ...partial,
      },
    });
    return updated.graph;
  }

  // -------------------------------------------------------------------------
  // Config Export / Import
  // -------------------------------------------------------------------------

  exportConfig(): ConfigExportEnvelope {
    return {
      schema_version: 2,
      type: 'szenergypro_config_export',
      data: {
        channelGroups: this.getChannelGroups(),
        systemAliases: this.getSystemAliases(),
      },
    };
  }

  exportConfigJson(): string {
    return JSON.stringify(this.exportConfig(), null, 4);
  }

  async importConfigJson(
    jsonText: string,
  ): Promise<{ groupsImported: number; aliasesImported: number }> {
    let raw: unknown;
    try {
      raw = JSON.parse(jsonText);
    } catch (err) {
      throw new Error(
        `Could not parse configuration file as JSON: ${err instanceof Error ? err.message : String(err)}`,
      );
    }

    if (!isPlainObject(raw) || raw.type !== 'szenergypro_config_export' || !isPlainObject(raw.data)) {
      throw new Error('Invalid configuration file format.');
    }

    let groupsImported = 0;
    let aliasesImported = 0;

    if (Array.isArray(raw.data.channelGroups)) {
      const imported = this.parseStoredGroups(raw.data.channelGroups);
      const byId = new Map<string, ChannelGroupDef>();
      for (const g of this.channelGroups) {
        byId.set(g.id, cloneGroup(g));
      }
      for (const g of imported) {
        byId.set(g.id, g);
        groupsImported += 1;
      }
      await this.saveChannelGroups(Array.from(byId.values()));
    }

    if (isPlainObject(raw.data.systemAliases)) {
      const sa = raw.data.systemAliases;
      const nextLap = Array.isArray(sa.lap)
        ? sa.lap.filter((s): s is string => typeof s === 'string')
        : [];
      const nextTime = Array.isArray(sa.time)
        ? sa.time.filter((s): s is string => typeof s === 'string')
        : [];
      const nextDist = Array.isArray(sa.dist)
        ? sa.dist.filter((s): s is string => typeof s === 'string')
        : [];
      aliasesImported = nextLap.length + nextTime.length + nextDist.length;
      this.systemAliases = {
        lap: mergeUniqueStrings(nextLap, this.systemAliases.lap),
        time: mergeUniqueStrings(nextTime, this.systemAliases.time),
        dist: mergeUniqueStrings(nextDist, this.systemAliases.dist),
      };
      await kvSet(KV_SYSTEM_ALIASES, this.systemAliases);
      if (this.ensureRequiredGroupsInMemory()) {
        await kvSet(KV_CHANNEL_GROUPS, this.channelGroups);
      }
    }
    return { groupsImported, aliasesImported };
  }

  // -------------------------------------------------------------------------
  // Track Maps Management
  // -------------------------------------------------------------------------

  loadMaps(): TrackMapDef[] {
    return this.maps.map((m) => ({
      ...m,
      x: [...m.x],
      y: [...m.y],
      distance: m.distance ? [...m.distance] : null,
    }));
  }

  getMap(slugOrName: string): TrackMapDef | null {
    const target = slugOrName.trim().toLowerCase();
    const found = this.maps.find(
      (m) => m.slug.toLowerCase() === target || m.name.trim().toLowerCase() === target,
    );
    if (!found) {
      return null;
    }
    return {
      ...found,
      x: [...found.x],
      y: [...found.y],
      distance: found.distance ? [...found.distance] : null,
    };
  }

  async saveMap(params: {
    name: string;
    x: ArrayLike<number>;
    y: ArrayLike<number>;
    distance?: ArrayLike<number> | null;
    rotation?: number;
    color?: string | null;
    oldNameOrSlug?: string | null;
  }): Promise<TrackMapDef> {
    const cleanName = params.name.trim();
    const slug = generateSlug(cleanName) || 'track_map';

    if (params.oldNameOrSlug) {
      const oldTarget = params.oldNameOrSlug.trim().toLowerCase();
      const oldMap = this.maps.find(
        (m) => m.slug.toLowerCase() === oldTarget || m.name.trim().toLowerCase() === oldTarget,
      );
      if (oldMap && oldMap.slug !== slug) {
        await dbDeleteMapBySlug(oldMap.slug);
        this.maps = this.maps.filter((m) => m.slug !== oldMap.slug);
      }
    }

    const xArr = Array.from(params.x, Number);
    const yArr = Array.from(params.y, Number);
    const distArr = params.distance != null ? Array.from(params.distance, Number) : null;
    const rotation =
      typeof params.rotation === 'number' && Number.isFinite(params.rotation)
        ? params.rotation
        : 0.0;
    const chosenColor =
      params.color && params.color.trim() ? params.color.trim() : LAP_COLORS[1];

    const mapDef: TrackMapDef = {
      name: cleanName,
      slug,
      rotation,
      color: chosenColor,
      x: xArr,
      y: yArr,
      distance: distArr,
    };

    await dbPutMap(mapDef);
    const existingIdx = this.maps.findIndex((m) => m.slug === slug);
    if (existingIdx >= 0) {
      this.maps[existingIdx] = mapDef;
    } else {
      this.maps.push(mapDef);
    }
    this.maps.sort((a, b) => a.name.localeCompare(b.name));
    return mapDef;
  }

  async saveMapRotation(slugOrName: string, rotation: number): Promise<boolean> {
    const existing = this.getMap(slugOrName);
    if (!existing) {
      return false;
    }
    await this.saveMap({
      name: existing.name,
      x: existing.x,
      y: existing.y,
      distance: existing.distance,
      rotation,
      color: existing.color,
    });
    return true;
  }

  async saveMapColor(slugOrName: string, color: string): Promise<boolean> {
    const existing = this.getMap(slugOrName);
    if (!existing) {
      return false;
    }
    await this.saveMap({
      name: existing.name,
      x: existing.x,
      y: existing.y,
      distance: existing.distance,
      rotation: existing.rotation,
      color,
    });
    return true;
  }

  async deleteMap(slugOrName: string): Promise<boolean> {
    const target = slugOrName.trim().toLowerCase();
    const existing = this.maps.find(
      (m) => m.slug.toLowerCase() === target || m.name.trim().toLowerCase() === target,
    );
    if (!existing) {
      return false;
    }
    await dbDeleteMapBySlug(existing.slug);
    this.maps = this.maps.filter((m) => m.slug !== existing.slug);
    return true;
  }

  async replaceAllMaps(nextMaps: TrackMapDef[]): Promise<void> {
    const existingSlugs = new Set(this.maps.map((m) => m.slug));
    const nextSlugs = new Set(nextMaps.map((m) => m.slug));
    for (const slug of existingSlugs) {
      if (!nextSlugs.has(slug)) {
        await dbDeleteMapBySlug(slug);
      }
    }
    const cloned: TrackMapDef[] = [];
    for (const m of nextMaps) {
      const copy: TrackMapDef = {
        ...m,
        x: [...m.x],
        y: [...m.y],
        distance: m.distance ? [...m.distance] : null,
      };
      await dbPutMap(copy);
      cloned.push(copy);
    }
    cloned.sort((a, b) => a.name.localeCompare(b.name));
    this.maps = cloned;
  }

  exportTrackMapJson(slugOrName: string): string | null {
    const mapDef = this.getMap(slugOrName);
    if (!mapDef) {
      return null;
    }
    const envelope: TrackMapExportEnvelope = {
      schema_version: 1,
      data: mapDef,
    };
    return JSON.stringify(envelope, null, 4);
  }

  parseTrackMapJson(jsonText: string): TrackMapDef {
    let raw: unknown;
    try {
      raw = JSON.parse(jsonText);
    } catch (err) {
      throw new Error(
        `Could not parse track map JSON: ${err instanceof Error ? err.message : String(err)}`,
      );
    }

    if (!isPlainObject(raw)) {
      throw new Error('Invalid track map format: root must be a JSON object.');
    }

    const data = isPlainObject(raw.data) ? raw.data : raw;

    if (typeof data.name !== 'string' || !data.name.trim()) {
      throw new Error("Invalid track map format: missing non-empty 'name'.");
    }
    if (!Array.isArray(data.x) || !Array.isArray(data.y)) {
      throw new Error("Invalid track map format: 'x' and 'y' coordinate arrays are required.");
    }
    if (data.x.length < 2 || data.x.length !== data.y.length) {
      throw new Error(
        "Invalid track map format: 'x' and 'y' must have equal length of at least 2 points.",
      );
    }

    const xArr = data.x.map(Number);
    const yArr = data.y.map(Number);
    if (xArr.some((v) => !Number.isFinite(v)) || yArr.some((v) => !Number.isFinite(v))) {
      throw new Error('Invalid track map format: coordinates must be finite numbers.');
    }

    let distArr: number[] | null = null;
    if (Array.isArray(data.distance)) {
      if (data.distance.length !== xArr.length) {
        throw new Error(
          "Invalid track map format: 'distance' array length must match 'x' and 'y'.",
        );
      }
      const parsedDist = data.distance.map(Number);
      if (parsedDist.some((v) => !Number.isFinite(v))) {
        throw new Error('Invalid track map format: distance values must be finite numbers.');
      }
      distArr = parsedDist;
    }

    const cleanName = data.name.trim();
    const slug =
      typeof data.slug === 'string' && data.slug.trim()
        ? generateSlug(data.slug)
        : generateSlug(cleanName) || 'track_map';
    const rotation =
      typeof data.rotation === 'number' && Number.isFinite(data.rotation) ? data.rotation : 0.0;
    const color =
      typeof data.color === 'string' && data.color.trim() ? data.color.trim() : LAP_COLORS[1];

    return {
      name: cleanName,
      slug,
      rotation,
      color,
      x: xArr,
      y: yArr,
      distance: distArr,
    };
  }

  async importTrackMapJson(jsonText: string): Promise<TrackMapDef> {
    const mapDef = this.parseTrackMapJson(jsonText);
    await dbPutMap(mapDef);
    const existingIdx = this.maps.findIndex((m) => m.slug === mapDef.slug);
    if (existingIdx >= 0) {
      this.maps[existingIdx] = mapDef;
    } else {
      this.maps.push(mapDef);
    }
    this.maps.sort((a, b) => a.name.localeCompare(b.name));
    return mapDef;
  }

  // -------------------------------------------------------------------------
  // Recent Files
  // -------------------------------------------------------------------------

  getRecentFiles(): RecentFileEntry[] {
    return [...this.recentFiles];
  }

  async addRecentFile(entry: RecentFileEntry): Promise<RecentFileEntry[]> {
    this.recentFiles = await dbUpsertRecentFile(entry);
    return this.getRecentFiles();
  }

  async removeRecentFile(id: string): Promise<RecentFileEntry[]> {
    await dbDeleteRecentFile(id);
    this.recentFiles = this.recentFiles.filter((f) => f.id !== id);
    return this.getRecentFiles();
  }

  async clearRecentFiles(): Promise<void> {
    await dbClearRecentFiles();
    this.recentFiles = [];
  }
}

export const stateManager = new StateManager();

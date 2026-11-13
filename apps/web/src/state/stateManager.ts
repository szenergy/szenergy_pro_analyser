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
  ChannelDef,
  ChannelType,
  ConfigExportEnvelope,
  DEFAULT_APP_SETTINGS,
  DEFAULT_CHANNEL_DEFS,
  DEFAULT_GRAPH_VIEW_SETTINGS,
  FileMappingConfig,
  GraphViewSettings,
  LAP_COLORS,
  LocalCalcDef,
  PresetDef,
  PresetMatchStats,
  RecentFileEntry,
  STD_CH_LAP_DIST,
  STD_CH_LAP_DIST_SLUG,
  STD_CH_LAP_NUM,
  STD_CH_LAP_NUM_SLUG,
  STD_CH_LAP_TIME,
  STD_CH_LAP_TIME_SLUG,
  SYSTEM_CHANNEL_SLUGS,
  ThemeMode,
  TrackMapDef,
  TrackMapExportEnvelope,
} from '@/types/telemetry';

const KV_PRESETS = 'presets';
const KV_CHANNELS = 'channels';
const KV_FILE_MAPPINGS = 'file_mappings';
const KV_SETTINGS = 'settings';

export function generateSlug(label: string): string {
  const slug = label
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, '_')
    .replace(/^_+|_+$/g, '');
  return slug || 'channel';
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

export async function computeFileSignature(fileName: string, rawColumns: string[]): Promise<string> {
  const cleanName = fileName.trim();
  const payload = JSON.stringify({ fileName: cleanName, columns: rawColumns });

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

function normalizeChannelType(slug: string, rawType: unknown): ChannelType {
  if (SYSTEM_CHANNEL_SLUGS.includes(slug)) {
    return 'system';
  }
  if (rawType === 'calculated') {
    return 'calculated';
  }
  if (rawType === 'system') {
    return 'system';
  }
  // Desktop legacy JSON uses 'normal'; map it to 'custom'
  return 'custom';
}

function normalizeLocalCalc(raw: unknown): LocalCalcDef | null {
  if (!isPlainObject(raw)) {
    return null;
  }
  const formula = typeof raw.formula === 'string' ? raw.formula : '';
  const targetSlug = typeof raw.target_slug === 'string' ? raw.target_slug : '';
  if (!formula || !targetSlug) {
    return null;
  }
  const targetLabel =
    typeof raw.target_label === 'string' && raw.target_label ? raw.target_label : targetSlug;
  const name = typeof raw.name === 'string' && raw.name ? raw.name : targetLabel;
  const inputs: Record<string, string> = {};
  if (isPlainObject(raw.inputs)) {
    for (const [k, v] of Object.entries(raw.inputs)) {
      if (typeof v === 'string') {
        inputs[k] = v;
      }
    }
  }
  return {
    name,
    target_slug: targetSlug,
    target_label: targetLabel,
    formula,
    inputs,
  };
}

function stripCalcTargetsFromMapping(
  mapping: Record<string, string>,
  localCalcs: LocalCalcDef[],
): Record<string, string> {
  if (localCalcs.length === 0) {
    return { ...mapping };
  }
  const calcTargets = new Set<string>();
  for (const c of localCalcs) {
    if (c.target_slug) calcTargets.add(c.target_slug);
    if (c.name) calcTargets.add(c.name);
    if (c.target_label) calcTargets.add(c.target_label);
  }
  const cleaned: Record<string, string> = {};
  for (const [k, v] of Object.entries(mapping)) {
    if (!calcTargets.has(k)) {
      cleaned[k] = v;
    }
  }
  return cleaned;
}

function normalizePresetItem(raw: unknown): PresetDef | null {
  if (!isPlainObject(raw)) {
    return null;
  }
  if (typeof raw.name !== 'string' || !isPlainObject(raw.mapping)) {
    return null;
  }
  const slug =
    typeof raw.slug === 'string' && raw.slug.trim() ? raw.slug.trim() : generateSlug(raw.name);

  const rawMapping: Record<string, string> = {};
  for (const [k, v] of Object.entries(raw.mapping)) {
    if (typeof v === 'string') {
      rawMapping[k] = v;
    }
  }

  const localCalcs: LocalCalcDef[] = [];
  if (Array.isArray(raw.local_calculated_channels)) {
    for (const item of raw.local_calculated_channels) {
      const normalized = normalizeLocalCalc(item);
      if (normalized) {
        localCalcs.push(normalized);
      }
    }
  }

  const preset: PresetDef = {
    slug,
    name: raw.name,
    mapping: stripCalcTargetsFromMapping(rawMapping, localCalcs),
    local_calculated_channels: localCalcs,
  };

  if (typeof raw.gap_time_threshold === 'number' && Number.isFinite(raw.gap_time_threshold)) {
    preset.gap_time_threshold = raw.gap_time_threshold;
  }
  if (typeof raw.gap_dist_threshold === 'number' && Number.isFinite(raw.gap_dist_threshold)) {
    preset.gap_dist_threshold = raw.gap_dist_threshold;
  }

  return preset;
}

function isBetterPresetRank(
  candidate: [number, number, number],
  currentBest: [number, number, number],
): boolean {
  if (candidate[0] !== currentBest[0]) return candidate[0] > currentBest[0];
  if (candidate[1] !== currentBest[1]) return candidate[1] > currentBest[1];
  return candidate[2] > currentBest[2];
}

function cloneChannelDef(ch: ChannelDef): ChannelDef {
  return {
    ...ch,
    inputs: ch.inputs ? { ...ch.inputs } : undefined,
  };
}

function clonePresetDef(p: PresetDef): PresetDef {
  return {
    ...p,
    mapping: { ...p.mapping },
    local_calculated_channels: p.local_calculated_channels.map((c) => ({
      ...c,
      inputs: { ...c.inputs },
    })),
  };
}

function cloneFileMapping(cfg: FileMappingConfig): FileMappingConfig {
  return {
    preset_slug: cfg.preset_slug ?? null,
    mapping: { ...cfg.mapping },
    local_calculated_channels: cfg.local_calculated_channels.map((c) => ({
      ...c,
      inputs: { ...c.inputs },
    })),
    gap_time_threshold: cfg.gap_time_threshold ?? null,
    gap_dist_threshold: cfg.gap_dist_threshold ?? null,
  };
}

export class StateManager {
  private presets: PresetDef[] = [];
  private channels: ChannelDef[] = DEFAULT_CHANNEL_DEFS.map(cloneChannelDef);
  private fileMappings: Record<string, FileMappingConfig> = {};
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
      const [rawPresets, rawChannels, rawFileMappings, rawSettings, maps, recentFiles] =
        await Promise.all([
          kvGet<unknown>(KV_PRESETS),
          kvGet<unknown>(KV_CHANNELS),
          kvGet<unknown>(KV_FILE_MAPPINGS),
          kvGet<unknown>(KV_SETTINGS),
          dbGetAllMaps(),
          dbGetRecentFiles(),
        ]);

      this.presets = this.parseStoredPresets(rawPresets);

      if (Array.isArray(rawChannels) && rawChannels.length > 0) {
        const parsed = this.parseStoredChannels(rawChannels);
        this.channels =
          parsed.length > 0 ? parsed : DEFAULT_CHANNEL_DEFS.map(cloneChannelDef);
      } else {
        this.channels = DEFAULT_CHANNEL_DEFS.map(cloneChannelDef);
        await kvSet(KV_CHANNELS, this.channels);
      }

      if (isPlainObject(rawFileMappings)) {
        const loadedMappings: Record<string, FileMappingConfig> = {};
        for (const [sig, val] of Object.entries(rawFileMappings)) {
          if (isPlainObject(val) && isPlainObject(val.mapping)) {
            const mapping: Record<string, string> = {};
            for (const [k, v] of Object.entries(val.mapping)) {
              if (typeof v === 'string') {
                mapping[k] = v;
              }
            }
            const calcs: LocalCalcDef[] = [];
            if (Array.isArray(val.local_calculated_channels)) {
              for (const item of val.local_calculated_channels) {
                const c = normalizeLocalCalc(item);
                if (c) calcs.push(c);
              }
            }
            loadedMappings[sig] = {
              preset_slug: typeof val.preset_slug === 'string' ? val.preset_slug : null,
              mapping,
              local_calculated_channels: calcs,
              gap_time_threshold:
                typeof val.gap_time_threshold === 'number' ? val.gap_time_threshold : null,
              gap_dist_threshold:
                typeof val.gap_dist_threshold === 'number' ? val.gap_dist_threshold : null,
            };
          }
        }
        this.fileMappings = loadedMappings;
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

  private parseStoredPresets(data: unknown): PresetDef[] {
    if (!data) {
      return [];
    }
    if (Array.isArray(data)) {
      const list: PresetDef[] = [];
      for (const item of data) {
        const p = normalizePresetItem(item);
        if (p) list.push(p);
      }
      return list;
    }
    if (isPlainObject(data)) {
      const migrated: PresetDef[] = [];
      for (const [name, mapping] of Object.entries(data)) {
        if (isPlainObject(mapping)) {
          const cleanMap: Record<string, string> = {};
          for (const [k, v] of Object.entries(mapping)) {
            if (typeof v === 'string') cleanMap[k] = v;
          }
          migrated.push({
            slug: generateSlug(name),
            name,
            mapping: cleanMap,
            local_calculated_channels: [],
          });
        }
      }
      return migrated;
    }
    return [];
  }

  private parseStoredChannels(data: unknown[]): ChannelDef[] {
    const converted: ChannelDef[] = [];
    for (const item of data) {
      if (isPlainObject(item) && typeof item.label === 'string' && typeof item.slug === 'string') {
        const slug = item.slug;
        const type = normalizeChannelType(slug, item.type);
        const unit = typeof item.unit === 'string' ? item.unit : '';
        const ch: ChannelDef = { label: item.label, slug, type, unit };
        if (typeof item.formula === 'string') {
          ch.formula = item.formula;
        }
        if (isPlainObject(item.inputs)) {
          const inputs: Record<string, string> = {};
          for (const [k, v] of Object.entries(item.inputs)) {
            if (typeof v === 'string') inputs[k] = v;
          }
          ch.inputs = inputs;
        }
        converted.push(ch);
      } else if (typeof item === 'string') {
        const slug = generateSlug(item);
        converted.push({
          label: item,
          slug,
          type: normalizeChannelType(slug, undefined),
          unit: '',
        });
      } else if (isPlainObject(item) && typeof item.label === 'string') {
        const slug = generateSlug(item.label);
        converted.push({
          label: item.label,
          slug,
          type: normalizeChannelType(slug, item.type),
          unit: typeof item.unit === 'string' ? item.unit : '',
        });
      }
    }
    return converted;
  }

  // -------------------------------------------------------------------------
  // Slug & Display Helpers
  // -------------------------------------------------------------------------

  generateSlug(label: string): string {
    return generateSlug(label);
  }

  generateUniqueSlug(label: string, existingSlugs?: Iterable<string>): string {
    const slugs = existingSlugs ?? this.channels.map((ch) => ch.slug);
    return generateUniqueSlug(label, slugs);
  }

  formatChannelDisplay(label: string, unit = ''): string {
    return formatChannelDisplay(label, unit);
  }

  // -------------------------------------------------------------------------
  // Channel Definitions
  // -------------------------------------------------------------------------

  getChannelDefs(): ChannelDef[] {
    return this.channels.map(cloneChannelDef);
  }

  async saveChannelDefs(channels: ChannelDef[]): Promise<void> {
    this.channels = channels.map((ch) => ({
      label: ch.label,
      slug: ch.slug,
      type: normalizeChannelType(ch.slug, ch.type),
      unit: ch.unit ?? '',
      ...(ch.formula !== undefined ? { formula: ch.formula } : {}),
      ...(ch.inputs !== undefined ? { inputs: { ...ch.inputs } } : {}),
    }));
    await kvSet(KV_CHANNELS, this.channels);
  }

  async saveNewCustomChannels(labels: string[]): Promise<boolean> {
    const existingDefs = this.getChannelDefs();
    const existingLabels = new Set<string>();
    for (const ch of existingDefs) {
      existingLabels.add(ch.label);
      existingLabels.add(formatChannelDisplay(ch.label, ch.unit));
    }
    const existingSlugs = existingDefs.map((ch) => ch.slug);

    let updated = false;
    for (const rawLabel of labels) {
      const labelClean = rawLabel.trim();
      if (
        labelClean &&
        labelClean !== '-- Skip --' &&
        !existingLabels.has(labelClean) &&
        this.getSlugByLabel(labelClean) === null
      ) {
        const slug = generateUniqueSlug(labelClean, existingSlugs);
        existingDefs.push({
          label: labelClean,
          slug,
          type: 'custom',
          unit: '',
        });
        existingLabels.add(labelClean);
        existingSlugs.push(slug);
        updated = true;
      }
    }

    if (updated) {
      await this.saveChannelDefs(existingDefs);
    }
    return updated;
  }

  getChannelLabels(): string[] {
    return this.channels.map((ch) => ch.label);
  }

  getChannelDefsBySlug(): Record<string, ChannelDef> {
    const res: Record<string, ChannelDef> = {};
    for (const ch of this.channels) {
      res[ch.slug] = cloneChannelDef(ch);
    }
    return res;
  }

  getCalculatedChannelDefs(): ChannelDef[] {
    return this.channels.filter((ch) => ch.type === 'calculated').map(cloneChannelDef);
  }

  getCalculatedChannelSlugs(): Set<string> {
    return new Set(this.channels.filter((ch) => ch.type === 'calculated').map((ch) => ch.slug));
  }

  getChannelDisplayNames(): string[] {
    return this.channels.map((ch) => formatChannelDisplay(ch.label, ch.unit));
  }

  labelToSlugMapping(): Record<string, string> {
    const res: Record<string, string> = {};
    for (const ch of this.channels) {
      if (ch.label && ch.slug) {
        res[ch.label] = ch.slug;
        const disp = formatChannelDisplay(ch.label, ch.unit);
        if (disp) {
          res[disp] = ch.slug;
        }
      }
    }
    return res;
  }

  getSlugByLabel(label: string): string | null {
    const mapping = this.labelToSlugMapping();
    if (label in mapping) {
      return mapping[label];
    }
    const targetLower = label.trim().toLowerCase();
    for (const [k, v] of Object.entries(mapping)) {
      if (k.toLowerCase() === targetLower) {
        return v;
      }
    }
    return null;
  }

  getUnitBySlug(slug: string, defaultUnit = ''): string {
    const found = this.channels.find((ch) => ch.slug === slug);
    return found ? found.unit ?? defaultUnit : defaultUnit;
  }

  getLabelBySlug(slug: string, defaultLabel?: string): string {
    const found = this.channels.find((ch) => ch.slug === slug);
    if (found) {
      return found.label;
    }
    if (defaultLabel !== undefined) {
      return defaultLabel;
    }
    if (slug === STD_CH_LAP_NUM_SLUG) return STD_CH_LAP_NUM;
    if (slug === STD_CH_LAP_TIME_SLUG) return STD_CH_LAP_TIME;
    if (slug === STD_CH_LAP_DIST_SLUG) return STD_CH_LAP_DIST;
    return slug;
  }

  getDisplayNameBySlug(slug: string, defaultLabel?: string): string {
    const found = this.channels.find((ch) => ch.slug === slug);
    if (found) {
      return formatChannelDisplay(found.label || slug, found.unit);
    }
    const label = this.getLabelBySlug(slug, defaultLabel);
    const unit = this.getUnitBySlug(slug, '');
    return formatChannelDisplay(label, unit);
  }

  getLapLabel(): string {
    return this.getLabelBySlug(STD_CH_LAP_NUM_SLUG, STD_CH_LAP_NUM);
  }

  getTimeLabel(): string {
    return this.getLabelBySlug(STD_CH_LAP_TIME_SLUG, STD_CH_LAP_TIME);
  }

  getDistanceLabel(): string {
    return this.getLabelBySlug(STD_CH_LAP_DIST_SLUG, STD_CH_LAP_DIST);
  }

  // -------------------------------------------------------------------------
  // Presets CRUD & Best-Fit Matching
  // -------------------------------------------------------------------------

  loadPresets(): PresetDef[] {
    return this.presets.map(clonePresetDef);
  }

  async savePresets(presets: PresetDef[]): Promise<void> {
    this.presets = presets.map(clonePresetDef);
    await kvSet(KV_PRESETS, this.presets);
  }

  getPresetBySlug(slug: string): PresetDef | null {
    const found = this.presets.find((p) => p.slug === slug);
    return found ? clonePresetDef(found) : null;
  }

  getPresetByName(name: string): PresetDef | null {
    const found = this.presets.find((p) => p.name === name);
    return found ? clonePresetDef(found) : null;
  }

  getPresetNameBySlug(slug: string, fallback?: string): string {
    const preset = this.getPresetBySlug(slug);
    if (preset?.name) {
      return preset.name;
    }
    return fallback !== undefined ? fallback : slug;
  }

  getPresetSlugByName(name: string): string | null {
    const preset = this.getPresetByName(name);
    return preset?.slug ?? null;
  }

  async savePreset(
    presetName: string,
    mapping: Record<string, string>,
    options: {
      slug?: string | null;
      localCalculatedChannels?: LocalCalcDef[];
      gapTimeThreshold?: number | null;
      gapDistThreshold?: number | null;
    } = {},
  ): Promise<string> {
    const presets = this.loadPresets();
    const existingSlugs = presets.map((p) => p.slug);

    const {
      slug = null,
      localCalculatedChannels,
      gapTimeThreshold,
      gapDistThreshold,
    } = options;

    let targetPreset: PresetDef | undefined;
    if (slug) {
      targetPreset = presets.find((p) => p.slug === slug);
    }
    if (!targetPreset) {
      targetPreset = presets.find((p) => p.name === presetName);
    }

    const calcsCopy = localCalculatedChannels
      ? localCalculatedChannels.map((c) => ({ ...c, inputs: { ...c.inputs } }))
      : undefined;
    const cleanMapping = stripCalcTargetsFromMapping(
      mapping,
      calcsCopy ?? targetPreset?.local_calculated_channels ?? [],
    );

    let savedSlug: string;
    if (targetPreset) {
      targetPreset.name = presetName;
      targetPreset.mapping = cleanMapping;
      if (calcsCopy !== undefined) {
        targetPreset.local_calculated_channels = calcsCopy;
      } else if (!targetPreset.local_calculated_channels) {
        targetPreset.local_calculated_channels = [];
      }
      if (gapTimeThreshold !== undefined && gapTimeThreshold !== null) {
        targetPreset.gap_time_threshold = Number(gapTimeThreshold);
      }
      if (gapDistThreshold !== undefined && gapDistThreshold !== null) {
        targetPreset.gap_dist_threshold = Number(gapDistThreshold);
      }
      savedSlug = targetPreset.slug;
    } else {
      savedSlug = generateUniqueSlug(slug || presetName, existingSlugs);
      const newPreset: PresetDef = {
        slug: savedSlug,
        name: presetName,
        mapping: cleanMapping,
        local_calculated_channels: calcsCopy ?? [],
      };
      if (gapTimeThreshold !== undefined && gapTimeThreshold !== null) {
        newPreset.gap_time_threshold = Number(gapTimeThreshold);
      }
      if (gapDistThreshold !== undefined && gapDistThreshold !== null) {
        newPreset.gap_dist_threshold = Number(gapDistThreshold);
      }
      presets.push(newPreset);
    }

    await this.savePresets(presets);
    return savedSlug;
  }

  async deletePreset(slugOrName: string): Promise<void> {
    const filtered = this.presets.filter(
      (p) => p.slug !== slugOrName && p.name !== slugOrName,
    );
    if (filtered.length !== this.presets.length) {
      await this.savePresets(filtered);
    }
  }

  getPresetMatchStats(slugOrName: string, rawColumns: string[]): PresetMatchStats {
    const preset = this.getPresetBySlug(slugOrName) ?? this.getPresetByName(slugOrName);
    const mapping = preset?.mapping ?? {};
    const localCalcs = preset?.local_calculated_channels ?? [];

    const rawSet = new Set(rawColumns);
    const presetCols = Object.keys(mapping);
    const presetColSet = new Set(presetCols);

    for (const calc of localCalcs) {
      for (const inp of Object.values(calc.inputs ?? {})) {
        if (!presetColSet.has(inp)) {
          presetColSet.add(inp);
          presetCols.push(inp);
        }
      }
    }

    const matchedChannels = presetCols.filter((c) => rawSet.has(c));
    const missingChannels = presetCols.filter((c) => !rawSet.has(c));
    const unmappedChannels = rawColumns.filter((c) => !presetColSet.has(c));

    const matchedCount = matchedChannels.length;
    const presetTotal = presetCols.length;
    const matchRatio = presetTotal > 0 ? matchedCount / presetTotal : 0.0;

    return {
      matched_count: matchedCount,
      preset_total: presetTotal,
      missing_in_file_count: missingChannels.length,
      unmapped_in_file_count: unmappedChannels.length,
      match_ratio: matchRatio,
      matched_channels: matchedChannels,
      missing_channels: missingChannels,
      unmapped_channels: unmappedChannels,
    };
  }

  findMatchingPreset(rawColumns: string[]): string | null {
    const rawSet = new Set(rawColumns);
    let bestPresetSlug: string | null = null;
    let bestRank: [number, number, number] = [-1, -1.0, -1];

    for (const preset of this.presets) {
      const mapping = preset.mapping ?? {};
      const localCalcs = preset.local_calculated_channels ?? [];
      if (Object.keys(mapping).length === 0 && localCalcs.length === 0) {
        continue;
      }

      const presetCols = new Set(Object.keys(mapping));
      for (const calc of localCalcs) {
        for (const inp of Object.values(calc.inputs ?? {})) {
          presetCols.add(inp);
        }
      }

      let matchedCount = 0;
      for (const col of presetCols) {
        if (rawSet.has(col)) {
          matchedCount += 1;
        }
      }

      const presetTotal = presetCols.size;
      const matchRatio = presetTotal > 0 ? matchedCount / presetTotal : 0.0;

      // Threshold check: works for full matches or partial matches with >=40% overlap
      const isValidMatch =
        presetTotal <= 2
          ? matchedCount === presetTotal
          : matchedCount >= 2 && matchRatio >= 0.4;

      if (isValidMatch) {
        const rank: [number, number, number] = [matchedCount, matchRatio, presetTotal];
        if (isBetterPresetRank(rank, bestRank)) {
          bestRank = rank;
          bestPresetSlug = preset.slug;
        }
      }
    }

    return bestPresetSlug;
  }

  // -------------------------------------------------------------------------
  // Per-File Mapping Memory (Keyed by File Signature)
  // -------------------------------------------------------------------------

  async computeFileSignature(fileName: string, rawColumns: string[]): Promise<string> {
    return computeFileSignature(fileName, rawColumns);
  }

  getFileMappingConfig(signature: string): FileMappingConfig | null {
    const entry = this.fileMappings[signature];
    return entry ? cloneFileMapping(entry) : null;
  }

  getAllFileMappings(): Record<string, FileMappingConfig> {
    const res: Record<string, FileMappingConfig> = {};
    for (const [sig, cfg] of Object.entries(this.fileMappings)) {
      res[sig] = cloneFileMapping(cfg);
    }
    return res;
  }

  async saveFileMappingConfig(signature: string, config: FileMappingConfig): Promise<void> {
    this.fileMappings[signature] = cloneFileMapping(config);
    await kvSet(KV_FILE_MAPPINGS, this.fileMappings);
  }

  async removeFileMappingConfig(signature: string): Promise<void> {
    if (signature in this.fileMappings) {
      delete this.fileMappings[signature];
      await kvSet(KV_FILE_MAPPINGS, this.fileMappings);
    }
  }

  async clearFileMappings(): Promise<void> {
    this.fileMappings = {};
    await kvSet(KV_FILE_MAPPINGS, this.fileMappings);
  }

  isFileMappingValidForColumns(config: FileMappingConfig, rawColumns: string[]): boolean {
    const rawSet = new Set(rawColumns);
    for (const rawCol of Object.keys(config.mapping)) {
      if (!rawSet.has(rawCol)) {
        return false;
      }
    }
    for (const calc of config.local_calculated_channels) {
      for (const inpCol of Object.values(calc.inputs)) {
        if (!rawSet.has(inpCol)) {
          return false;
        }
      }
    }
    return true;
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
  // Config Export / Import (Desktop szenergy_config.json compatible)
  // -------------------------------------------------------------------------

  exportConfig(): ConfigExportEnvelope {
    return {
      schema_version: 1,
      type: 'szenergypro_config_export',
      data: {
        presets: this.loadPresets(),
        channels: this.getChannelDefs(),
      },
    };
  }

  exportConfigJson(): string {
    return JSON.stringify(this.exportConfig(), null, 4);
  }

  async importConfigJson(
    jsonText: string,
  ): Promise<{ presetsImported: number; channelsImported: number }> {
    let raw: unknown;
    try {
      raw = JSON.parse(jsonText);
    } catch (err) {
      throw new Error(
        `Could not parse JSON configuration: ${err instanceof Error ? err.message : String(err)}`,
      );
    }

    if (!isPlainObject(raw)) {
      throw new Error('Invalid configuration format: root must be a JSON object.');
    }

    const schemaVersion = typeof raw.schema_version === 'number' ? raw.schema_version : 0;
    const payload = isPlainObject(raw.data) ? raw.data : raw;

    const importedPresets = payload.presets;
    const importedChannels = payload.channels ?? payload.custom_channels;

    if (importedPresets === undefined && importedChannels === undefined) {
      throw new Error("Invalid configuration file: neither 'presets' nor 'channels' found.");
    }

    let channelsImported = 0;
    if (importedChannels !== undefined) {
      if (!Array.isArray(importedChannels)) {
        throw new Error("'channels' in configuration must be a list of channel definitions.");
      }

      const existingChannels = this.getChannelDefs();
      const channelsBySlug = new Map<string, ChannelDef>();
      for (const ch of existingChannels) {
        if (ch.slug) {
          channelsBySlug.set(ch.slug, ch);
        }
      }
      const existingSlugs = Array.from(channelsBySlug.keys());

      for (const ch of importedChannels) {
        if (isPlainObject(ch) && typeof ch.label === 'string') {
          const label = ch.label.trim();
          const rawSlug = typeof ch.slug === 'string' && ch.slug.trim() ? ch.slug.trim() : null;
          const unit = typeof ch.unit === 'string' ? ch.unit : '';
          const formula = typeof ch.formula === 'string' ? ch.formula : undefined;
          let inputs: Record<string, string> | undefined;
          if (isPlainObject(ch.inputs)) {
            inputs = {};
            for (const [k, v] of Object.entries(ch.inputs)) {
              if (typeof v === 'string') inputs[k] = v;
            }
          }

          if (rawSlug) {
            const existing = channelsBySlug.get(rawSlug);
            if (existing) {
              existing.label = label;
              if (typeof ch.unit === 'string') existing.unit = unit;
              if (ch.type !== undefined) {
                existing.type = normalizeChannelType(rawSlug, ch.type);
              }
              if (formula !== undefined) existing.formula = formula;
              if (inputs !== undefined) existing.inputs = inputs;
            } else {
              const newCh: ChannelDef = {
                label,
                slug: rawSlug,
                type: normalizeChannelType(rawSlug, ch.type),
                unit,
                ...(formula !== undefined ? { formula } : {}),
                ...(inputs !== undefined ? { inputs } : {}),
              };
              channelsBySlug.set(rawSlug, newCh);
              existingSlugs.push(rawSlug);
            }
            channelsImported += 1;
          } else if (label) {
            const slug = generateUniqueSlug(label, existingSlugs);
            const newCh: ChannelDef = {
              label,
              slug,
              type: normalizeChannelType(slug, ch.type),
              unit,
              ...(formula !== undefined ? { formula } : {}),
              ...(inputs !== undefined ? { inputs } : {}),
            };
            channelsBySlug.set(slug, newCh);
            existingSlugs.push(slug);
            channelsImported += 1;
          }
        } else if (typeof ch === 'string') {
          const label = ch.trim();
          if (label) {
            const slug = generateUniqueSlug(label, existingSlugs);
            channelsBySlug.set(slug, {
              label,
              slug,
              type: normalizeChannelType(slug, undefined),
              unit: '',
            });
            existingSlugs.push(slug);
            channelsImported += 1;
          }
        }
      }

      // Ensure all system-required channel slugs exist
      const requiredSystemChannels: Array<[string, string, string]> = [
        [STD_CH_LAP_NUM_SLUG, STD_CH_LAP_NUM, ''],
        [STD_CH_LAP_TIME_SLUG, STD_CH_LAP_TIME, 's'],
        [STD_CH_LAP_DIST_SLUG, STD_CH_LAP_DIST, 'm'],
      ];
      for (const [reqSlug, reqDefaultLabel, reqUnit] of requiredSystemChannels) {
        if (!channelsBySlug.has(reqSlug)) {
          channelsBySlug.set(reqSlug, {
            label: reqDefaultLabel,
            slug: reqSlug,
            type: 'system',
            unit: reqUnit,
          });
        }
      }

      await this.saveChannelDefs(Array.from(channelsBySlug.values()));
    }

    let presetsImported = 0;
    if (importedPresets !== undefined) {
      if (!Array.isArray(importedPresets) && !isPlainObject(importedPresets)) {
        throw new Error("'presets' in configuration must be a list or object.");
      }

      const existingPresets = this.loadPresets();
      const presetsBySlug = new Map<string, PresetDef>();
      const presetsByName = new Map<string, PresetDef>();
      for (const p of existingPresets) {
        presetsBySlug.set(p.slug, p);
        presetsByName.set(p.name, p);
      }

      const presetItems: PresetDef[] = [];
      if (Array.isArray(importedPresets)) {
        for (const item of importedPresets) {
          const p = normalizePresetItem(item);
          if (p) presetItems.push(p);
        }
      } else if (isPlainObject(importedPresets)) {
        const labelMap = this.labelToSlugMapping();
        for (const [name, rawMapping] of Object.entries(importedPresets)) {
          if (isPlainObject(rawMapping)) {
            const mapping: Record<string, string> = {};
            for (const [rawCol, target] of Object.entries(rawMapping)) {
              if (typeof target === 'string') {
                if (schemaVersion === 0 && target in labelMap) {
                  mapping[rawCol] = labelMap[target];
                } else {
                  mapping[rawCol] = target;
                }
              }
            }
            presetItems.push({
              slug: generateSlug(name),
              name,
              mapping,
              local_calculated_channels: [],
            });
          }
        }
      }

      for (const p of presetItems) {
        const bySlug = presetsBySlug.get(p.slug);
        const byName = presetsByName.get(p.name);
        if (bySlug) {
          bySlug.name = p.name;
          bySlug.mapping = p.mapping;
          bySlug.local_calculated_channels = p.local_calculated_channels;
          if (p.gap_time_threshold !== undefined) bySlug.gap_time_threshold = p.gap_time_threshold;
          if (p.gap_dist_threshold !== undefined) bySlug.gap_dist_threshold = p.gap_dist_threshold;
        } else if (byName) {
          byName.mapping = p.mapping;
          byName.local_calculated_channels = p.local_calculated_channels;
          if (p.gap_time_threshold !== undefined) byName.gap_time_threshold = p.gap_time_threshold;
          if (p.gap_dist_threshold !== undefined) byName.gap_dist_threshold = p.gap_dist_threshold;
        } else {
          presetsBySlug.set(p.slug, p);
          presetsByName.set(p.name, p);
        }
        presetsImported += 1;
      }

      await this.savePresets(Array.from(presetsBySlug.values()));
    }

    return { presetsImported, channelsImported };
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

  async importTrackMapJson(jsonText: string): Promise<TrackMapDef> {
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

    const mapDef: TrackMapDef = {
      name: cleanName,
      slug,
      rotation,
      color,
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

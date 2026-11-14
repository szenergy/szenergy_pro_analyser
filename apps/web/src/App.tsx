import React, { useCallback, useEffect, useRef, useState } from 'react';
import { TrackMapCursorPoint } from '@/plot/trackMapRenderer';
import { computeFileSignature, stateManager } from '@/state/stateManager';
import {
  DEFAULT_APP_SETTINGS,
  DEFAULT_GAP_DIST_THRESHOLD,
  DEFAULT_GAP_TIME_THRESHOLD,
  FilePreview,
  GroupChannelOverride,
  GroupingMode,
  isRequiredChannelGroupId,
  LAP_COLORS,
  MAX_STACKED_PLOTS,
  RecentFileEntry,
  SelectedLapInfo,
  SessionSummary,
  STD_CH_LAP_DIST_SLUG,
  STD_CH_LAP_TIME_SLUG,
  ThemeMode,
} from '@/types/telemetry';
import { telemetryClient } from '@/workers/telemetryClient';
import { GraphView } from '@/components/GraphView';
import { ImportWizardModal, ImportWizardSubmitResult } from '@/components/ImportWizardModal';
import {
  ChannelGroupManagerModal,
  RememberedImportsModal,
  TrackMapManagerModal,
  WelcomeStartupModal,
} from '@/components/ManagerModals';
import { RenameLegendModal } from '@/components/RenameLegendModal';
import { Sidebar } from '@/components/Sidebar';
import { TrackMapTab } from '@/components/TrackMapTab';

interface WizardJob {
  mode: 'import' | 'edit';
  fileToken?: string;
  sessionId?: string;
  fileName: string;
  fileSignature: string;
  preview: FilePreview;
  initialSheetName: string | null;
  initialLapCol: string | null;
  initialTimeCol: string | null;
  initialDistCol: string | null;
  initialGapTime: number | null;
  initialGapDist: number | null;
  initialGroupOverrides?: Record<string, GroupChannelOverride>;
  initialRemember: boolean;
  fileEntry?: {
    size: number;
    lastModified: number;
    handle?: FileSystemFileHandle;
  };
}

interface QueuedFile {
  file: File;
  handle?: FileSystemFileHandle;
}

function makeSessionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `sess_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

function getSystemDark(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches;
}

export const App: React.FC = () => {
  const [ready, setReady] = useState(false);
  const [systemDark, setSystemDark] = useState<boolean>(getSystemDark);
  const [themeMode, setThemeMode] = useState<ThemeMode>(DEFAULT_APP_SETTINGS.themeMode);
  const [graphSettings, setGraphSettings] = useState(DEFAULT_APP_SETTINGS.graph);
  const [bottomTabIndex, setBottomTabIndex] = useState(0);
  const [selectedMapSlug, setSelectedMapSlug] = useState<string | null>(null);
  const [sidebarWidth, setSidebarWidth] = useState<number>(300);
  const [sidebarSplitRatio, setSidebarSplitRatio] = useState<number>(0.5);

  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selectedLaps, setSelectedLaps] = useState<SelectedLapInfo[]>([]);
  const [selectedChannels, setSelectedChannels] = useState<string[]>([]);
  const [channelColors, setChannelColors] = useState<Record<string, string>>({});
  const [customLapLabels, setCustomLapLabels] = useState<Record<string, string>>({});
  const [customChannelLabels, setCustomChannelLabels] = useState<Record<string, string>>({});
  const [recentFiles, setRecentFiles] = useState<RecentFileEntry[]>([]);
  const [cursorMapPoints, setCursorMapPoints] = useState<TrackMapCursorPoint[]>([]);

  const [channelsVersion, setChannelsVersion] = useState(0);
  const [mapRefreshVersion, setMapRefreshVersion] = useState(0);

  const [wizardJob, setWizardJob] = useState<WizardJob | null>(null);
  const [fileQueue, setFileQueue] = useState<QueuedFile[]>([]);
  const [busyMessage, setBusyMessage] = useState<string | null>(null);
  const [toast, setToast] = useState<{ kind: 'info' | 'warning' | 'error'; text: string } | null>(
    null,
  );
  const [isDragOver, setIsDragOver] = useState(false);

  // Modals
  const [groupModal, setGroupModal] = useState<{
    open: boolean;
    focusGroupId: string | null;
    draftChannels: string[] | null;
  }>({ open: false, focusGroupId: null, draftChannels: null });
  const [rememberedImportsOpen, setRememberedImportsOpen] = useState(false);
  const [mapsOpen, setMapsOpen] = useState(false);
  const [renameLegendOpen, setRenameLegendOpen] = useState(false);
  const [welcomeOpen, setWelcomeOpen] = useState(true);

  const fallbackFileInputRef = useRef<HTMLInputElement | null>(null);
  const reloadFileInputRef = useRef<HTMLInputElement | null>(null);
  const importConfigInputRef = useRef<HTMLInputElement | null>(null);
  const reloadSessionTargetRef = useRef<string | null>(null);
  const resizingRef = useRef(false);
  const loadedFilesRef = useRef<
    Map<
      string,
      {
        name: string;
        size?: number;
        lastModified?: number;
        signature: string;
        handle?: FileSystemFileHandle;
      }
    >
  >(new Map());

  const isDark = themeMode === 'dark' ? true : themeMode === 'light' ? false : systemDark;

  const showToast = useCallback((kind: 'info' | 'warning' | 'error', text: string) => {
    setToast({ kind, text });
  }, []);

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), 5000);
    return () => window.clearTimeout(t);
  }, [toast]);

  // Listen to OS dark mode changes
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (ev: MediaQueryListEvent) => setSystemDark(ev.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  // Apply data-theme attribute to root element
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
  }, [isDark]);

  // Initialize IndexedDB state & WASM worker
  useEffect(() => {
    let cancelled = false;
    (async () => {
      await Promise.all([stateManager.init(), telemetryClient.init()]);
      if (cancelled) return;
      const settings = stateManager.getSettings();
      setThemeMode(settings.themeMode);
      setGraphSettings(settings.graph);
      setBottomTabIndex(settings.sidebarBottomTabIndex);
      setSelectedMapSlug(settings.selectedMapSlug);
      if (settings.sidebarWidth && settings.sidebarWidth >= 220 && settings.sidebarWidth <= 560) {
        setSidebarWidth(settings.sidebarWidth);
      }
      if (
        settings.sidebarSplitRatio &&
        settings.sidebarSplitRatio >= 0.18 &&
        settings.sidebarSplitRatio <= 0.82
      ) {
        setSidebarSplitRatio(settings.sidebarSplitRatio);
      }
      setRecentFiles(stateManager.getRecentFiles());
      setChannelsVersion((v) => v + 1);
      setReady(true);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleUpdateGraphSettings = useCallback(
    async (partial: Partial<typeof graphSettings>) => {
      const updated = await stateManager.updateGraphSettings(partial);
      setGraphSettings(updated);
    },
    [],
  );

  const ensureValidXAxis = useCallback(
    (nextSessions: SessionSummary[]) => {
      if (nextSessions.length === 0) return;
      const anyHasDist = nextSessions.some((s) => s.has_dist);
      const anyHasTime = nextSessions.some((s) => s.has_time);
      if (graphSettings.xAxisSlug === STD_CH_LAP_DIST_SLUG && !anyHasDist && anyHasTime) {
        void handleUpdateGraphSettings({ xAxisSlug: STD_CH_LAP_TIME_SLUG });
      } else if (graphSettings.xAxisSlug === STD_CH_LAP_TIME_SLUG && !anyHasTime && anyHasDist) {
        void handleUpdateGraphSettings({ xAxisSlug: STD_CH_LAP_DIST_SLUG });
      }
    },
    [graphSettings.xAxisSlug, handleUpdateGraphSettings],
  );

  const checkGroupCollisions = useCallback((_targetSessions: SessionSummary[]): boolean => {
    return false;
  }, []);

  // Process next queued file when wizard is idle
  useEffect(() => {
    if (!ready || wizardJob !== null || fileQueue.length === 0) return;

    const [nextItem, ...rest] = fileQueue;
    setFileQueue(rest);

    (async () => {
      const { file, handle } = nextItem;
      setBusyMessage(`Inspecting ${file.name}...`);
      try {
        const inspected = await telemetryClient.inspectFile(file);
        const { fileToken } = inspected;
        let preview = inspected.preview;

        const alreadyLoaded = Array.from(loadedFilesRef.current.values()).some(
          (meta) =>
            meta.name === file.name &&
            meta.size === file.size &&
            meta.lastModified === file.lastModified,
        );
        if (alreadyLoaded) {
          await telemetryClient.discardPendingFile(fileToken);
          setBusyMessage(null);
          showToast('info', `'${file.name}' is already loaded.`);
          return;
        }

        const defaultSignature = await computeFileSignature(
          file.name,
          preview.columns,
          preview.selectedSheet ?? null,
        );
        let signature = defaultSignature;
        let remembered = stateManager.getFileImportConfig(defaultSignature);

        // If a remembered config exists for another worksheet of this workbook, check sheets
        if (!remembered && preview.sheets && preview.sheets.length > 1) {
          const allImports = stateManager.getAllFileImports();
          const candidateEntry = Object.entries(allImports).find(
            ([sig, cfg]) =>
              sig.startsWith(`${file.name.trim()}::`) &&
              cfg.sheet_name &&
              preview.sheets!.includes(cfg.sheet_name),
          );
          if (candidateEntry) {
            const [candSig, candCfg] = candidateEntry;
            const sheetRes = await telemetryClient.inspectExcelSheet(
              fileToken,
              candCfg.sheet_name!,
            );
            const sheetSig = await computeFileSignature(
              file.name,
              sheetRes.preview.columns,
              sheetRes.preview.selectedSheet ?? null,
            );
            if (sheetSig === candSig) {
              preview = sheetRes.preview;
              signature = sheetSig;
              remembered = candCfg;
            }
          }
        }

        // Auto-import 1: Remembered file import config
        if (remembered && stateManager.isFileImportValidForColumns(remembered, preview.columns)) {
          setBusyMessage(`Importing ${file.name}...`);
          const sessionId = makeSessionId();
          const summary = await telemetryClient.importSession(fileToken, {
            session_id: sessionId,
            file_name: file.name,
            sheet_name: remembered.sheet_name,
            lap_col: remembered.lap_col,
            time_col: remembered.time_col,
            dist_col: remembered.dist_col,
            gap_time_threshold: remembered.gap_time_threshold ?? DEFAULT_GAP_TIME_THRESHOLD,
            gap_dist_threshold: remembered.gap_dist_threshold ?? DEFAULT_GAP_DIST_THRESHOLD,
            group_overrides: remembered.group_overrides,
          });
          loadedFilesRef.current.set(sessionId, {
            name: file.name,
            size: file.size,
            lastModified: file.lastModified,
            signature,
            ...(handle ? { handle } : {}),
          });
          setSessions((prev) => {
            const next = [...prev, summary];
            ensureValidXAxis(next);
            return next;
          });
          const updatedRecent = await stateManager.addRecentFile({
            id: signature,
            name: file.name,
            size: file.size,
            lastModified: file.lastModified,
            lastOpenedAt: Date.now(),
            ...(handle ? { handle } : {}),
          });
          setRecentFiles(updatedRecent);
          setBusyMessage(null);
          checkGroupCollisions([summary]);
          return;
        }

        // Pre-detect required roles for the Import Wizard when file is not remembered
        const detected = stateManager.autoDetectImportRoles(preview.columns, preview.finiteCounts);
        setBusyMessage(null);
        setWizardJob({
          mode: 'import',
          fileToken,
          fileName: file.name,
          fileSignature: signature,
          preview,
          initialSheetName: remembered?.sheet_name ?? preview.selectedSheet ?? null,
          initialLapCol: remembered?.lap_col ?? detected.lapCol,
          initialTimeCol: remembered?.time_col ?? detected.timeCol,
          initialDistCol: remembered?.dist_col ?? detected.distCol,
          initialGapTime: remembered?.gap_time_threshold ?? null,
          initialGapDist: remembered?.gap_dist_threshold ?? null,
          initialGroupOverrides: remembered?.group_overrides,
          initialRemember: true,
          fileEntry: {
            size: file.size,
            lastModified: file.lastModified,
            handle,
          },
        });
      } catch (err) {
        setBusyMessage(null);
        showToast(
          'error',
          `Failed to load '${file.name}': ${err instanceof Error ? err.message : String(err)}`,
        );
      }
    })();
  }, [ready, wizardJob, fileQueue, showToast, checkGroupCollisions, ensureValidXAxis]);

  const enqueueFiles = useCallback(
    (items: QueuedFile[]) => {
      const supported = items.filter((item) => {
        const ext = item.file.name.split('.').pop()?.toLowerCase() ?? '';
        return ext === 'csv' || ext === 'xlsx' || ext === 'xls' || ext === 'tdms';
      });
      if (supported.length === 0) {
        showToast('error', 'Unsupported file format. Supported: .csv, .xlsx, .xls, .tdms');
        return;
      }

      const unique: QueuedFile[] = [];
      const seenBatch = new Set<string>();
      let skippedDuplicateName: string | null = null;
      for (const item of supported) {
        const f = item.file;
        const batchKey = `${f.name}::${f.size}::${f.lastModified}`;
        const matchesLoaded = Array.from(loadedFilesRef.current.values()).some(
          (m) => m.name === f.name && m.size === f.size && m.lastModified === f.lastModified,
        );
        const matchesWizard =
          wizardJob?.mode === 'import' &&
          wizardJob.fileName === f.name &&
          wizardJob.fileEntry?.size === f.size &&
          wizardJob.fileEntry?.lastModified === f.lastModified;
        const matchesQueued = fileQueue.some(
          (q) =>
            q.file.name === f.name &&
            q.file.size === f.size &&
            q.file.lastModified === f.lastModified,
        );
        if (seenBatch.has(batchKey) || matchesLoaded || matchesWizard || matchesQueued) {
          skippedDuplicateName = f.name;
          continue;
        }
        seenBatch.add(batchKey);
        unique.push(item);
      }

      if (skippedDuplicateName) {
        showToast('info', `'${skippedDuplicateName}' is already loaded.`);
      }
      if (unique.length > 0) {
        setWelcomeOpen(false);
        setFileQueue((prev) => [...prev, ...unique]);
      }
    },
    [fileQueue, showToast, wizardJob],
  );

  const handleOpenFiles = useCallback(async () => {
    const win = window as Window & {
      showOpenFilePicker?: (opts?: unknown) => Promise<FileSystemFileHandle[]>;
    };
    if (typeof win.showOpenFilePicker === 'function') {
      try {
        const handles = await win.showOpenFilePicker({
          multiple: true,
          types: [
            {
              description: 'Telemetry Logs',
              accept: {
                'text/csv': ['.csv'],
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
                'application/vnd.ms-excel': ['.xls'],
                'application/octet-stream': ['.tdms'],
              },
            },
          ],
        });
        const items: QueuedFile[] = await Promise.all(
          handles.map(async (handle) => ({
            file: await handle.getFile(),
            handle,
          })),
        );
        enqueueFiles(items);
        return;
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          return;
        }
      }
    }
    fallbackFileInputRef.current?.click();
  }, [enqueueFiles]);

  // Ctrl+O shortcut
  useEffect(() => {
    const onKeyDown = (ev: KeyboardEvent) => {
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'o') {
        ev.preventDefault();
        void handleOpenFiles();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [handleOpenFiles]);

  const handleOpenRecentFile = useCallback(
    async (entry: RecentFileEntry) => {
      if (!entry.handle) {
        showToast(
          'info',
          `Browser security requires re-selecting '${entry.name}' from disk.`,
        );
        await handleOpenFiles();
        return;
      }
      try {
        const handleWithPerm = entry.handle as FileSystemFileHandle & {
          queryPermission?: (desc: { mode: 'read' }) => Promise<PermissionState>;
          requestPermission?: (desc: { mode: 'read' }) => Promise<PermissionState>;
        };
        let perm: PermissionState = 'granted';
        if (typeof handleWithPerm.queryPermission === 'function') {
          perm = await handleWithPerm.queryPermission({ mode: 'read' });
          if (perm !== 'granted' && typeof handleWithPerm.requestPermission === 'function') {
            perm = await handleWithPerm.requestPermission({ mode: 'read' });
          }
        }
        if (perm !== 'granted') {
          showToast('error', `Permission denied to reopen '${entry.name}'.`);
          return;
        }
        const file = await entry.handle.getFile();
        enqueueFiles([{ file, handle: entry.handle }]);
      } catch (err) {
        showToast(
          'error',
          `Could not reopen '${entry.name}': ${err instanceof Error ? err.message : String(err)}`,
        );
      }
    },
    [enqueueFiles, handleOpenFiles, showToast],
  );

  const handleWizardSubmit = async (result: ImportWizardSubmitResult) => {
    if (!wizardJob) return;
    const job = wizardJob;
    setWizardJob(null);

    await stateManager.recordSystemAliases(result.lapCol, result.timeCol, result.distCol);
    setChannelsVersion((v) => v + 1);
    try {
      if (job.mode === 'import' && job.fileToken) {
        setBusyMessage(`Parsing ${job.fileName}...`);
        const isReplacing = Boolean(job.sessionId);
        const sessionId = job.sessionId ?? makeSessionId();
        const summary = await telemetryClient.importSession(job.fileToken, {
          session_id: sessionId,
          file_name: job.fileName,
          sheet_name: result.sheetName,
          lap_col: result.lapCol,
          time_col: result.timeCol,
          dist_col: result.distCol,
          gap_time_threshold: result.gapTimeThreshold,
          gap_dist_threshold: result.gapDistThreshold,
          group_overrides: result.groupOverrides,
        });

        const finalSig = await computeFileSignature(
          job.fileName,
          summary.available_columns,
          summary.sheet_name,
        );
        if (result.rememberForFile) {
          await stateManager.saveFileImportConfig(finalSig, {
            sheet_name: result.sheetName,
            lap_col: result.lapCol,
            time_col: result.timeCol,
            dist_col: result.distCol,
            gap_time_threshold: result.gapTimeThreshold,
            gap_dist_threshold: result.gapDistThreshold,
            group_overrides: result.groupOverrides,
          });
        } else {
          await stateManager.removeFileImportConfig(finalSig);
        }
        loadedFilesRef.current.set(sessionId, {
          name: job.fileName,
          size: job.fileEntry?.size,
          lastModified: job.fileEntry?.lastModified,
          signature: finalSig,
          ...(job.fileEntry?.handle ? { handle: job.fileEntry.handle } : {}),
        });
        if (isReplacing) {
          setSessions((prev) => {
            const next = prev.map((s) => (s.id === summary.id ? summary : s));
            ensureValidXAxis(next);
            return next;
          });
          const validLapNums = new Set(summary.laps.map((l) => l.lap_number));
          setSelectedLaps((prev) =>
            prev.filter((l) => l.sessionId !== summary.id || validLapNums.has(l.lapNumber)),
          );
        } else {
          setSessions((prev) => {
            const next = [...prev, summary];
            ensureValidXAxis(next);
            return next;
          });
        }
        if (job.fileEntry) {
          const updatedRecent = await stateManager.addRecentFile({
            id: finalSig,
            name: job.fileName,
            size: job.fileEntry.size,
            lastModified: job.fileEntry.lastModified,
            lastOpenedAt: Date.now(),
            ...(job.fileEntry.handle ? { handle: job.fileEntry.handle } : {}),
          });
          setRecentFiles(updatedRecent);
        }
        checkGroupCollisions([summary]);
      } else if (job.mode === 'edit' && job.sessionId) {
        setBusyMessage(`Updating ${job.fileName}...`);
        const summary = await telemetryClient.reparseSession(job.sessionId, {
          session_id: job.sessionId,
          file_name: job.fileName,
          sheet_name: result.sheetName,
          lap_col: result.lapCol,
          time_col: result.timeCol,
          dist_col: result.distCol,
          gap_time_threshold: result.gapTimeThreshold,
          gap_dist_threshold: result.gapDistThreshold,
          group_overrides: result.groupOverrides,
        });

        const finalSig = await computeFileSignature(
          job.fileName,
          summary.available_columns,
          summary.sheet_name,
        );
        if (result.rememberForFile) {
          await stateManager.saveFileImportConfig(finalSig, {
            sheet_name: result.sheetName,
            lap_col: result.lapCol,
            time_col: result.timeCol,
            dist_col: result.distCol,
            gap_time_threshold: result.gapTimeThreshold,
            gap_dist_threshold: result.gapDistThreshold,
            group_overrides: result.groupOverrides,
          });
        } else {
          await stateManager.removeFileImportConfig(finalSig);
        }
        setSessions((prev) => {
          const next = prev.map((s) => (s.id === summary.id ? summary : s));
          ensureValidXAxis(next);
          return next;
        });
        const validLapNums = new Set(summary.laps.map((l) => l.lap_number));
        setSelectedLaps((prev) =>
          prev.filter((l) => l.sessionId !== summary.id || validLapNums.has(l.lapNumber)),
        );
        checkGroupCollisions([summary]);
      }
    } catch (err) {
      showToast(
        'error',
        `Failed to parse '${job.fileName}': ${err instanceof Error ? err.message : String(err)}`,
      );
    } finally {
      setBusyMessage(null);
    }
  };

  const handleWizardCancel = async () => {
    if (wizardJob?.mode === 'import' && wizardJob.fileToken) {
      await telemetryClient.discardPendingFile(wizardJob.fileToken);
    }
    setWizardJob(null);
  };

  const handleEditSessionImport = async (sessionId: string) => {
    const session = sessions.find((s) => s.id === sessionId);
    if (!session) return;
    try {
      const preview = await telemetryClient.getSessionSheetPreview(
        session.id,
        session.sheet_name ?? undefined,
      );
      const sig = await computeFileSignature(
        session.name,
        preview.columns,
        preview.selectedSheet ?? session.sheet_name,
      );
      const remembered = stateManager.getFileImportConfig(sig) !== null;
      setWizardJob({
        mode: 'edit',
        sessionId: session.id,
        fileName: session.name,
        fileSignature: sig,
        preview,
        initialSheetName: session.sheet_name,
        initialLapCol: session.lap_col,
        initialTimeCol: session.time_col,
        initialDistCol: session.dist_col,
        initialGapTime: session.gap_time_threshold,
        initialGapDist: session.gap_dist_threshold,
        initialGroupOverrides: session.group_overrides,
        initialRemember: remembered,
      });
    } catch (err) {
      showToast(
        'error',
        `Could not open import settings: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  };

  const handleRemoveSession = async (sessionId: string) => {
    await telemetryClient.removeSession(sessionId);
    loadedFilesRef.current.delete(sessionId);
    setSessions((prev) => {
      const next = prev.filter((s) => s.id !== sessionId);
      ensureValidXAxis(next);
      return next;
    });
    setSelectedLaps((prev) => prev.filter((l) => l.sessionId !== sessionId));
  };

  const reloadSessionFromFile = async (
    sessionId: string,
    freshFile: File,
    handle?: FileSystemFileHandle,
  ) => {
    const session = sessions.find((s) => s.id === sessionId);
    if (!session) return;

    setBusyMessage(`Reloading ${freshFile.name}...`);
    try {
      const inspected = await telemetryClient.inspectFile(freshFile);
      const { fileToken } = inspected;
      let preview = inspected.preview;

      if (
        session.sheet_name &&
        preview.sheets &&
        preview.sheets.includes(session.sheet_name) &&
        preview.selectedSheet !== session.sheet_name
      ) {
        const sheetRes = await telemetryClient.inspectExcelSheet(fileToken, session.sheet_name);
        preview = sheetRes.preview;
      }

      const signature = await computeFileSignature(
        freshFile.name,
        preview.columns,
        preview.selectedSheet ?? session.sheet_name,
      );
      const cfg = {
        sheet_name: session.sheet_name,
        lap_col: session.lap_col,
        time_col: session.time_col,
        dist_col: session.dist_col,
        gap_time_threshold: session.gap_time_threshold,
        gap_dist_threshold: session.gap_dist_threshold,
      };

      if (stateManager.isFileImportValidForColumns(cfg, preview.columns)) {
        const summary = await telemetryClient.importSession(fileToken, {
          session_id: sessionId,
          file_name: freshFile.name,
          sheet_name: session.sheet_name,
          lap_col: session.lap_col,
          time_col: session.time_col,
          dist_col: session.dist_col,
          gap_time_threshold: session.gap_time_threshold ?? DEFAULT_GAP_TIME_THRESHOLD,
          gap_dist_threshold: session.gap_dist_threshold ?? DEFAULT_GAP_DIST_THRESHOLD,
          group_overrides: session.group_overrides,
        });
        loadedFilesRef.current.set(sessionId, {
          name: freshFile.name,
          size: freshFile.size,
          lastModified: freshFile.lastModified,
          signature,
          ...(handle ? { handle } : {}),
        });
        setSessions((prev) => {
          const next = prev.map((s) => (s.id === summary.id ? summary : s));
          ensureValidXAxis(next);
          return next;
        });
        const validLapNums = new Set(summary.laps.map((l) => l.lap_number));
        setSelectedLaps((prev) =>
          prev.filter((l) => l.sessionId !== summary.id || validLapNums.has(l.lapNumber)),
        );
        const updatedRecent = await stateManager.addRecentFile({
          id: signature,
          name: freshFile.name,
          size: freshFile.size,
          lastModified: freshFile.lastModified,
          lastOpenedAt: Date.now(),
          ...(handle ? { handle } : {}),
        });
        setRecentFiles(updatedRecent);
        if (!checkGroupCollisions([summary])) {
          showToast('info', `Reloaded '${freshFile.name}' (${summary.laps.length} laps).`);
        }
      } else {
        setWizardJob({
          mode: 'import',
          fileToken,
          sessionId,
          fileName: freshFile.name,
          fileSignature: signature,
          preview,
          initialSheetName: session.sheet_name,
          initialLapCol: session.lap_col,
          initialTimeCol: session.time_col,
          initialDistCol: session.dist_col,
          initialGapTime: session.gap_time_threshold,
          initialGapDist: session.gap_dist_threshold,
          initialGroupOverrides: session.group_overrides,
          initialRemember: true,
          fileEntry: {
            size: freshFile.size,
            lastModified: freshFile.lastModified,
            handle,
          },
        });
      }
    } catch (err) {
      showToast(
        'error',
        `Failed to reload '${freshFile.name}': ${err instanceof Error ? err.message : String(err)}`,
      );
    } finally {
      setBusyMessage(null);
    }
  };

  const handleReloadSession = async (sessionId: string) => {
    const session = sessions.find((s) => s.id === sessionId);
    if (!session) return;
    const meta = loadedFilesRef.current.get(sessionId);
    const handle =
      meta?.handle ??
      recentFiles.find((r) => r.id === meta?.signature || r.name === session.name)?.handle;

    if (handle) {
      try {
        const handleWithPerm = handle as FileSystemFileHandle & {
          queryPermission?: (desc: { mode: 'read' }) => Promise<PermissionState>;
          requestPermission?: (desc: { mode: 'read' }) => Promise<PermissionState>;
        };
        let perm: PermissionState = 'granted';
        if (typeof handleWithPerm.queryPermission === 'function') {
          perm = await handleWithPerm.queryPermission({ mode: 'read' });
          if (perm !== 'granted' && typeof handleWithPerm.requestPermission === 'function') {
            perm = await handleWithPerm.requestPermission({ mode: 'read' });
          }
        }
        if (perm !== 'granted') {
          showToast('error', `Permission denied to reload '${session.name}'.`);
          return;
        }
        const freshFile = await handle.getFile();
        await reloadSessionFromFile(sessionId, freshFile, handle);
        return;
      } catch (err) {
        showToast(
          'error',
          `Could not reload '${session.name}': ${err instanceof Error ? err.message : String(err)}`,
        );
        return;
      }
    }

    const win = window as Window & {
      showOpenFilePicker?: (opts?: unknown) => Promise<FileSystemFileHandle[]>;
    };
    if (typeof win.showOpenFilePicker === 'function') {
      try {
        const [pickedHandle] = await win.showOpenFilePicker({
          multiple: false,
          types: [
            {
              description: 'Telemetry Logs',
              accept: {
                'text/csv': ['.csv'],
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
                'application/vnd.ms-excel': ['.xls'],
                'application/octet-stream': ['.tdms'],
              },
            },
          ],
        });
        if (pickedHandle) {
          const freshFile = await pickedHandle.getFile();
          await reloadSessionFromFile(sessionId, freshFile, pickedHandle);
        }
        return;
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return;
      }
    }

    showToast('info', `Browser security requires re-selecting '${session.name}' from disk.`);
    reloadSessionTargetRef.current = sessionId;
    reloadFileInputRef.current?.click();
  };

  const handleClearWorkspace = async () => {
    await telemetryClient.clearSessions();
    loadedFilesRef.current.clear();
    setSessions([]);
    setSelectedLaps([]);
    setSelectedChannels([]);
    setChannelColors({});
    setCustomLapLabels({});
    setCustomChannelLabels({});
    setCursorMapPoints([]);
  };

  const handleSetThemeMode = async (mode: ThemeMode) => {
    setThemeMode(mode);
    await stateManager.saveSettings({ themeMode: mode });
  };

  const handleChangeSelectedChannels = (nextChannels: string[]) => {
    setChannelColors((prev) => {
      const used = new Set<string>();
      for (const slug of nextChannels) {
        if (prev[slug]) used.add(prev[slug]);
      }
      let changed = false;
      const next = { ...prev };
      for (const slug of nextChannels) {
        if (!next[slug]) {
          const pick =
            LAP_COLORS.find((c) => !used.has(c)) ?? LAP_COLORS[used.size % LAP_COLORS.length];
          next[slug] = pick;
          used.add(pick);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
    setSelectedChannels(nextChannels);
  };

  const handleChangeGroupingMode = async (mode: GroupingMode) => {
    if (mode === graphSettings.groupingMode) return;
    if (mode === 'lap') {
      if (selectedLaps.length > MAX_STACKED_PLOTS) {
        setSelectedLaps((prev) => prev.slice(0, MAX_STACKED_PLOTS));
        showToast(
          'info',
          `By Lap mode supports up to ${MAX_STACKED_PLOTS} stacked laps; trimmed selection.`,
        );
      }
      handleChangeSelectedChannels(selectedChannels);
    } else if (selectedChannels.length > MAX_STACKED_PLOTS) {
      setSelectedChannels((prev) => prev.slice(0, MAX_STACKED_PLOTS));
      showToast(
        'info',
        `By Channel mode supports up to ${MAX_STACKED_PLOTS} stacked channels; trimmed selection.`,
      );
    }
    await handleUpdateGraphSettings({ groupingMode: mode });
  };

  const reconcileSelectionWithGroups = useCallback(() => {
    const groups = stateManager.getChannelGroups();
    const groupIds = new Set(groups.map((g) => g.id));
    setSelectedChannels((prev) => {
      const next: string[] = [];
      const seen = new Set<string>();
      for (const key of prev) {
        if (groupIds.has(key)) {
          if (!seen.has(key)) {
            seen.add(key);
            next.push(key);
          }
          continue;
        }
        const grp = stateManager.getGroupForRawChannel(key);
        const resolved = grp ? grp.id : key;
        if (!seen.has(resolved)) {
          seen.add(resolved);
          next.push(resolved);
        }
      }
      return next;
    });
  }, []);

  const handleGroupsUpdated = useCallback(() => {
    setChannelsVersion((v) => v + 1);
    reconcileSelectionWithGroups();
    checkGroupCollisions(sessions);
  }, [checkGroupCollisions, reconcileSelectionWithGroups, sessions]);

  const handleQuickAddToGroup = async (groupId: string, rawChannels: string[]) => {
    await stateManager.addChannelsToGroup(groupId, rawChannels);
    handleGroupsUpdated();
  };

  const handleDeleteChannelGroup = async (groupId: string) => {
    if (isRequiredChannelGroupId(groupId)) return;
    await stateManager.deleteChannelGroup(groupId);
    setSelectedChannels((prev) => prev.filter((c) => c !== groupId));
    setChannelsVersion((v) => v + 1);
  };

  const handleExportConfig = () => {
    const json = stateManager.exportConfigJson();
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'szenergy_config.json';
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImportConfigFile = async (file: File) => {
    try {
      const text = await file.text();
      const { groupsImported, aliasesImported } = await stateManager.importConfigJson(text);
      handleGroupsUpdated();
      showToast(
        'info',
        `Imported ${groupsImported} channel group(s) and ${aliasesImported} role alias(es).`,
      );
    } catch (err) {
      showToast(
        'error',
        `Config import failed: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  };

  // Sidebar resize handle
  const startResize = (ev: React.MouseEvent) => {
    ev.preventDefault();
    resizingRef.current = true;
    const onMove = (moveEv: MouseEvent) => {
      if (!resizingRef.current) return;
      const clamped = Math.max(220, Math.min(540, moveEv.clientX));
      setSidebarWidth(clamped);
    };
    const onUp = (upEv: MouseEvent) => {
      if (!resizingRef.current) return;
      resizingRef.current = false;
      const clamped = Math.max(220, Math.min(540, upEv.clientX));
      void stateManager.saveSettings({ sidebarWidth: clamped });
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  // Window-wide drag & drop
  const handleDragOver = (ev: React.DragEvent) => {
    if (ev.dataTransfer.types.includes('Files')) {
      ev.preventDefault();
      setIsDragOver(true);
    }
  };

  const handleDragLeave = (ev: React.DragEvent) => {
    if (ev.currentTarget.contains(ev.relatedTarget as Node)) return;
    setIsDragOver(false);
  };

  const handleDrop = (ev: React.DragEvent) => {
    ev.preventDefault();
    setIsDragOver(false);
    const files = Array.from(ev.dataTransfer.files);
    if (files.length > 0) {
      enqueueFiles(files.map((file) => ({ file })));
    }
  };

  return (
    <div
      style={{
        display: 'flex',
        width: '100vw',
        height: '100vh',
        overflow: 'hidden',
        backgroundColor: 'var(--bg-app)',
        color: 'var(--text-primary)',
        position: 'relative',
      }}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Hidden fallback file inputs */}
      <input
        ref={fallbackFileInputRef}
        type="file"
        multiple
        accept=".csv,.xlsx,.xls,.tdms"
        style={{ display: 'none' }}
        onChange={(ev) => {
          const files = Array.from(ev.target.files ?? []);
          ev.target.value = '';
          if (files.length > 0) {
            enqueueFiles(files.map((file) => ({ file })));
          }
        }}
      />
      <input
        ref={reloadFileInputRef}
        type="file"
        accept=".csv,.xlsx,.xls,.tdms"
        style={{ display: 'none' }}
        onChange={(ev) => {
          const file = ev.target.files?.[0];
          const targetSid = reloadSessionTargetRef.current;
          reloadSessionTargetRef.current = null;
          ev.target.value = '';
          if (file && targetSid) {
            void reloadSessionFromFile(targetSid, file);
          }
        }}
      />
      <input
        ref={importConfigInputRef}
        type="file"
        accept=".json"
        style={{ display: 'none' }}
        onChange={(ev) => {
          const file = ev.target.files?.[0];
          ev.target.value = '';
          if (file) {
            void handleImportConfigFile(file);
          }
        }}
      />

      {/* Left Sidebar */}
      <div
        style={{
          width: sidebarWidth,
          minWidth: 220,
          maxWidth: 540,
          height: '100%',
          flexShrink: 0,
          position: 'relative',
          zIndex: 30,
        }}
      >
        <Sidebar
          isDark={isDark}
          themeMode={themeMode}
          graphSettings={graphSettings}
          sessions={sessions}
          selectedLaps={selectedLaps}
          selectedChannels={selectedChannels}
          channelColors={channelColors}
          recentFiles={recentFiles}
          bottomTabIndex={bottomTabIndex}
          channelsVersion={channelsVersion}
          splitRatio={sidebarSplitRatio}
          onSplitRatioChange={(ratio) => {
            setSidebarSplitRatio(ratio);
            void stateManager.saveSettings({ sidebarSplitRatio: ratio });
          }}
          trackMapSlot={
            <TrackMapTab
              isDark={isDark}
              cursorPoints={cursorMapPoints}
              selectedMapSlug={selectedMapSlug}
              mapRefreshVersion={mapRefreshVersion}
              onSelectMap={(slug) => {
                setSelectedMapSlug(slug);
                void stateManager.saveSettings({ selectedMapSlug: slug });
              }}
              onOpenMapManager={() => setMapsOpen(true)}
            />
          }
          onOpenFiles={() => void handleOpenFiles()}
          onOpenRecentFile={(entry) => void handleOpenRecentFile(entry)}
          onClearRecentFiles={() => {
            void stateManager.clearRecentFiles().then(() => setRecentFiles([]));
          }}
          onClearWorkspace={() => void handleClearWorkspace()}
          onImportConfig={() => importConfigInputRef.current?.click()}
          onExportConfig={handleExportConfig}
          onOpenManageChannelGroups={(opts) =>
            setGroupModal({
              open: true,
              focusGroupId: opts?.focusGroupId ?? null,
              draftChannels: opts?.draftChannels ?? null,
            })
          }
          onOpenManageRememberedImports={() => setRememberedImportsOpen(true)}
          onQuickAddToGroup={(gid, chs) => void handleQuickAddToGroup(gid, chs)}
          onDeleteChannelGroup={(gid) => void handleDeleteChannelGroup(gid)}
          onOpenManageMaps={() => setMapsOpen(true)}
          onSetThemeMode={(mode) => void handleSetThemeMode(mode)}
          onUpdateGraphSettings={(partial) => void handleUpdateGraphSettings(partial)}
          onChangeGroupingMode={(mode) => void handleChangeGroupingMode(mode)}
          onChangeSelectedLaps={setSelectedLaps}
          onChangeSelectedChannels={handleChangeSelectedChannels}
          onChangeChannelColor={(slug, color) =>
            setChannelColors((prev) => ({ ...prev, [slug]: color }))
          }
          onEditSessionMapping={(id) => void handleEditSessionImport(id)}
          onReloadSession={(id) => void handleReloadSession(id)}
          onRemoveSession={(id) => void handleRemoveSession(id)}
          onBottomTabChange={(idx) => {
            setBottomTabIndex(idx);
            void stateManager.saveSettings({ sidebarBottomTabIndex: idx });
          }}
        />
      </div>

      {/* Splitter */}
      <div
        onMouseDown={startResize}
        style={{
          width: 4,
          cursor: 'col-resize',
          backgroundColor: 'var(--border-subtle)',
          flexShrink: 0,
        }}
        title="Drag to resize sidebar"
      />

      {/* Main Graph Area */}
      <div style={{ flex: 1, minWidth: 0, height: '100%' }}>
        <GraphView
          isDark={isDark}
          sessions={sessions}
          selectedChannels={selectedChannels}
          selectedLaps={selectedLaps}
          channelColors={channelColors}
          customLapLabels={customLapLabels}
          customChannelLabels={customChannelLabels}
          settings={graphSettings}
          channelsVersion={channelsVersion}
          onUpdateSettings={(partial) => void handleUpdateGraphSettings(partial)}
          onOpenRenameLegend={() => setRenameLegendOpen(true)}
          onCursorMapPoints={setCursorMapPoints}
        />
      </div>

      {/* Drop Zone Overlay */}
      {isDragOver && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 1500,
            backgroundColor: 'var(--accent-subtle)',
            border: '3px dashed var(--accent)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            pointerEvents: 'none',
          }}
        >
          <div
            style={{
              backgroundColor: 'var(--bg-panel)',
              border: '1px solid var(--accent)',
              padding: '18px 28px',
              borderRadius: 8,
              fontSize: 16,
              fontWeight: 600,
            }}
          >
            Drop telemetry files (.csv, .xlsx, .xls, .tdms) to import
          </div>
        </div>
      )}

      {/* Loading Busy Overlay */}
      {busyMessage && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 1600,
            backgroundColor: 'rgba(0, 0, 0, 0.45)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <div
            style={{
              backgroundColor: 'var(--bg-panel)',
              border: '1px solid var(--border-strong)',
              borderRadius: 8,
              padding: '16px 24px',
              fontSize: 13,
              fontWeight: 500,
              boxShadow: '0 8px 24px rgba(0,0,0,0.35)',
            }}
          >
            {busyMessage}
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div
          role="status"
          style={{
            position: 'fixed',
            bottom: 18,
            right: 18,
            zIndex: 1700,
            padding: '10px 14px',
            borderRadius: 6,
            backgroundColor:
              toast.kind === 'error'
                ? 'var(--danger)'
                : toast.kind === 'warning'
                  ? 'var(--bg-elevated)'
                  : 'var(--bg-elevated)',
            color:
              toast.kind === 'error'
                ? '#FFFFFF'
                : toast.kind === 'warning'
                  ? 'var(--warning)'
                  : 'var(--text-primary)',
            border:
              toast.kind === 'warning'
                ? '1px solid var(--warning)'
                : '1px solid var(--border-strong)',
            fontSize: 13,
            maxWidth: 460,
            boxShadow: '0 6px 20px rgba(0,0,0,0.35)',
          }}
        >
          {toast.text}
        </div>
      )}

      {/* Modals */}
      {wizardJob && (
        <ImportWizardModal
          isOpen
          mode={wizardJob.mode}
          fileName={wizardJob.fileName}
          fileToken={wizardJob.fileToken}
          sessionId={wizardJob.sessionId}
          preview={wizardJob.preview}
          initialSheetName={wizardJob.initialSheetName}
          initialLapCol={wizardJob.initialLapCol}
          initialTimeCol={wizardJob.initialTimeCol}
          initialDistCol={wizardJob.initialDistCol}
          initialGapTime={wizardJob.initialGapTime}
          initialGapDist={wizardJob.initialGapDist}
          initialGroupOverrides={wizardJob.initialGroupOverrides}
          initialRemember={wizardJob.initialRemember}
          onSubmit={(res) => void handleWizardSubmit(res)}
          onCancel={() => void handleWizardCancel()}
        />
      )}
      <ChannelGroupManagerModal
        isOpen={groupModal.open}
        sessions={sessions}
        initialFocusGroupId={groupModal.focusGroupId}
        initialDraftChannels={groupModal.draftChannels}
        onClose={() => setGroupModal({ open: false, focusGroupId: null, draftChannels: null })}
        onGroupsUpdated={() => handleGroupsUpdated()}
      />

      <RememberedImportsModal
        isOpen={rememberedImportsOpen}
        onClose={() => setRememberedImportsOpen(false)}
      />

      <TrackMapManagerModal
        isOpen={mapsOpen}
        onClose={() => setMapsOpen(false)}
        onMapsUpdated={() => setMapRefreshVersion((v) => v + 1)}
      />

      <RenameLegendModal
        isOpen={renameLegendOpen}
        selectedLaps={selectedLaps}
        selectedChannels={selectedChannels}
        sessions={sessions}
        channelColors={channelColors}
        customLapLabels={customLapLabels}
        customChannelLabels={customChannelLabels}
        onSave={(nextLaps, nextChannels) => {
          setCustomLapLabels(nextLaps);
          setCustomChannelLabels(nextChannels);
        }}
        onClose={() => setRenameLegendOpen(false)}
      />

      <WelcomeStartupModal
        isOpen={ready && welcomeOpen && sessions.length === 0 && wizardJob === null && !busyMessage}
        recentFiles={recentFiles}
        onOpenFiles={() => void handleOpenFiles()}
        onOpenRecentFile={(entry) => void handleOpenRecentFile(entry)}
        onClose={() => setWelcomeOpen(false)}
      />
    </div>
  );
};

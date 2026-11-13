import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Check,
  ChevronDown,
  ChevronRight,
  FolderOpen,
  ListX,
  MoreVertical,
  RotateCw,
  Search,
  Trash2,
} from 'lucide-react';
import {
  GraphViewSettings,
  GroupingMode,
  LAP_COLORS,
  MAX_STACKED_PLOTS,
  RecentFileEntry,
  SelectedLapInfo,
  SessionSummary,
  ThemeMode,
} from '@/types/telemetry';
import { stateManager } from '@/state/stateManager';

export interface SidebarProps {
  isDark: boolean;
  themeMode: ThemeMode;
  graphSettings: GraphViewSettings;
  sessions: SessionSummary[];
  selectedLaps: SelectedLapInfo[];
  selectedChannels: string[];
  channelColors: Record<string, string>;
  recentFiles: RecentFileEntry[];
  bottomTabIndex: number;
  channelsVersion: number;
  splitRatio: number;
  onSplitRatioChange: (ratio: number) => void;
  trackMapSlot: React.ReactNode;
  onOpenFiles: () => void;
  onOpenRecentFile: (entry: RecentFileEntry) => void;
  onClearRecentFiles: () => void;
  onClearWorkspace: () => void;
  onImportConfig: () => void;
  onExportConfig: () => void;
  onOpenManagePresets: () => void;
  onOpenManageChannels: () => void;
  onOpenManageFileMappings: () => void;
  onOpenManageMaps: () => void;
  onSetThemeMode: (mode: ThemeMode) => void;
  onUpdateGraphSettings: (partial: Partial<GraphViewSettings>) => void;
  onChangeGroupingMode: (mode: GroupingMode) => void;
  onChangeSelectedLaps: (laps: SelectedLapInfo[]) => void;
  onChangeSelectedChannels: (channels: string[]) => void;
  onChangeChannelColor: (slug: string, color: string) => void;
  onEditSessionMapping: (sessionId: string) => void;
  onReloadSession: (sessionId: string) => void;
  onRemoveSession: (sessionId: string) => void;
  onBottomTabChange: (idx: number) => void;
}

type MenuKey = 'file' | 'edit' | 'view' | null;

interface LapKey {
  sessionId: string;
  lapNumber: number;
}

function formatLapTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '0.000 s';
  return `${seconds.toFixed(3)} s`;
}

function sameLap(a: LapKey, b: LapKey): boolean {
  return a.sessionId === b.sessionId && a.lapNumber === b.lapNumber;
}

function allocateColor(usedColors: Set<string>): string {
  for (const c of LAP_COLORS) {
    if (!usedColors.has(c)) return c;
  }
  return LAP_COLORS[usedColors.size % LAP_COLORS.length];
}

export const Sidebar: React.FC<SidebarProps> = ({
  themeMode,
  graphSettings,
  sessions,
  selectedLaps,
  selectedChannels,
  channelColors,
  recentFiles,
  bottomTabIndex,
  channelsVersion,
  splitRatio,
  onSplitRatioChange,
  trackMapSlot,
  onOpenFiles,
  onOpenRecentFile,
  onClearRecentFiles,
  onClearWorkspace,
  onImportConfig,
  onExportConfig,
  onOpenManagePresets,
  onOpenManageChannels,
  onOpenManageFileMappings,
  onOpenManageMaps,
  onSetThemeMode,
  onUpdateGraphSettings,
  onChangeGroupingMode,
  onChangeSelectedLaps,
  onChangeSelectedChannels,
  onChangeChannelColor,
  onEditSessionMapping,
  onRemoveSession,
  onReloadSession,
  onBottomTabChange,
}) => {
  const [openMenu, setOpenMenu] = useState<MenuKey>(null);
  const [recentSubmenuOpen, setRecentSubmenuOpen] = useState(false);
  const [expandedSessions, setExpandedSessions] = useState<Record<string, boolean>>({});
  const [contextMenu, setContextMenu] = useState<{
    sessionId: string;
    x: number;
    y: number;
  } | null>(null);
  const [colorPickerTarget, setColorPickerTarget] = useState<
    | { kind: 'lap'; sessionId: string; lapNumber: number; x: number; y: number }
    | { kind: 'channel'; slug: string; x: number; y: number }
    | null
  >(null);

  const [channelSearch, setChannelSearch] = useState('');
  const [channelLimitNotice, setChannelLimitNotice] = useState(false);
  const [lapLimitNotice, setLapLimitNotice] = useState(false);

  const isByLap = graphSettings.groupingMode === 'lap';
  const maxLapsAllowed = isByLap ? MAX_STACKED_PLOTS : LAP_COLORS.length;
  const maxChannelsAllowed = isByLap ? LAP_COLORS.length : MAX_STACKED_PLOTS;
  const anchorLapRef = useRef<LapKey | null>(null);
  const dragStartLapRef = useRef<LapKey | null>(null);
  const isDraggingLapsRef = useRef(false);
  const anchorChannelRef = useRef<string | null>(null);
  const dragStartChannelRef = useRef<string | null>(null);
  const isDraggingChannelsRef = useRef(false);
  const menuBarRef = useRef<HTMLDivElement | null>(null);
  const sidebarContentRef = useRef<HTMLDivElement | null>(null);
  const [localSplitRatio, setLocalSplitRatio] = useState(splitRatio);

  useEffect(() => {
    setLocalSplitRatio(splitRatio);
  }, [splitRatio]);

  const startVerticalSplitDrag = (e: React.MouseEvent) => {
    e.preventDefault();
    const container = sidebarContentRef.current;
    if (!container) return;
    const computeRatio = (clientY: number) => {
      const rect = container.getBoundingClientRect();
      if (rect.height <= 0) return localSplitRatio;
      const rel = (clientY - rect.top) / rect.height;
      return Math.max(0.18, Math.min(0.82, rel));
    };
    let latestRatio = localSplitRatio;
    const onMove = (moveEv: MouseEvent) => {
      latestRatio = computeRatio(moveEv.clientY);
      setLocalSplitRatio(latestRatio);
    };
    const onUp = (upEv: MouseEvent) => {
      latestRatio = computeRatio(upEv.clientY);
      setLocalSplitRatio(latestRatio);
      onSplitRatioChange(latestRatio);
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };
  // Auto-expand newly added sessions
  useEffect(() => {
    setExpandedSessions((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const s of sessions) {
        if (next[s.id] === undefined) {
          next[s.id] = true;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [sessions]);

  // Global click-outside & Escape handler for menus, context menu, and color picker
  useEffect(() => {
    const handlePointerDown = (e: MouseEvent) => {
      const target = e.target as HTMLElement | null;
      if (openMenu && menuBarRef.current && !menuBarRef.current.contains(target)) {
        setOpenMenu(null);
        setRecentSubmenuOpen(false);
      }
      if (contextMenu && !target?.closest('[data-sidebar-context-menu="true"]')) {
        setContextMenu(null);
      }
      if (colorPickerTarget && !target?.closest('[data-lap-color-picker="true"]')) {
        setColorPickerTarget(null);
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpenMenu(null);
        setRecentSubmenuOpen(false);
        setContextMenu(null);
        setColorPickerTarget(null);
      }
    };
    const handlePointerUp = () => {
      isDraggingLapsRef.current = false;
      dragStartLapRef.current = null;
      isDraggingChannelsRef.current = false;
      dragStartChannelRef.current = null;
    };

    window.addEventListener('mousedown', handlePointerDown);
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('pointerup', handlePointerUp);
    return () => {
      window.removeEventListener('mousedown', handlePointerDown);
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('pointerup', handlePointerUp);
    };
  }, [openMenu, contextMenu, colorPickerTarget]);

  // Flat list of all laps in display order for Shift+Click & drag range selection
  const flatLaps = useMemo<LapKey[]>(() => {
    const list: LapKey[] = [];
    for (const s of sessions) {
      for (const lap of s.laps) {
        list.push({ sessionId: s.id, lapNumber: lap.lap_number });
      }
    }
    return list;
  }, [sessions]);

  const selectedLapMap = useMemo(() => {
    const map = new Map<string, SelectedLapInfo>();
    for (const item of selectedLaps) {
      map.set(`${item.sessionId}::${item.lapNumber}`, item);
    }
    return map;
  }, [selectedLaps]);

  const triggerLapLimitNotice = () => {
    setLapLimitNotice(true);
    window.setTimeout(() => setLapLimitNotice(false), 2500);
  };

  const selectRange = (from: LapKey, to: LapKey) => {
    const idxA = flatLaps.findIndex((l) => sameLap(l, from));
    const idxB = flatLaps.findIndex((l) => sameLap(l, to));
    if (idxA === -1 || idxB === -1) return;
    const start = Math.min(idxA, idxB);
    const end = Math.max(idxA, idxB);
    const rawSlice = flatLaps.slice(start, end + 1);
    if (rawSlice.length > maxLapsAllowed) {
      triggerLapLimitNotice();
    }
    const slice = rawSlice.slice(0, maxLapsAllowed);

    const usedColors = new Set<string>();
    const next: SelectedLapInfo[] = [];
    for (const l of slice) {
      const existing = selectedLapMap.get(`${l.sessionId}::${l.lapNumber}`);
      const color = existing ? existing.color : allocateColor(usedColors);
      usedColors.add(color);
      next.push({ sessionId: l.sessionId, lapNumber: l.lapNumber, color });
    }
    onChangeSelectedLaps(next);
  };

  const handleLapPointerDown = (e: React.PointerEvent, lap: LapKey) => {
    if (e.button !== 0) return;
    if ((e.target as HTMLElement).closest('[data-lap-swatch="true"]')) return;

    if (e.shiftKey && anchorLapRef.current) {
      selectRange(anchorLapRef.current, lap);
      return;
    }

    if (e.ctrlKey || e.metaKey) {
      const key = `${lap.sessionId}::${lap.lapNumber}`;
      const existing = selectedLapMap.get(key);
      if (existing) {
        onChangeSelectedLaps(
          selectedLaps.filter((item) => !sameLap(item, lap)),
        );
        setLapLimitNotice(false);
      } else if (selectedLaps.length < maxLapsAllowed) {
        const usedColors = new Set(selectedLaps.map((l) => l.color));
        const color = allocateColor(usedColors);
        onChangeSelectedLaps([...selectedLaps, { ...lap, color }]);
        setLapLimitNotice(false);
      } else {
        triggerLapLimitNotice();
      }
      anchorLapRef.current = lap;
      return;
    }

    // Plain click: toggle if it's the only selected lap, otherwise select only this lap
    isDraggingLapsRef.current = true;
    dragStartLapRef.current = lap;
    anchorLapRef.current = lap;

    if (selectedLaps.length === 1 && sameLap(selectedLaps[0], lap)) {
      onChangeSelectedLaps([]);
    } else {
      const existing = selectedLapMap.get(`${lap.sessionId}::${lap.lapNumber}`);
      const color = existing ? existing.color : LAP_COLORS[0];
      onChangeSelectedLaps([{ ...lap, color }]);
    }
  };

  const handleLapPointerEnter = (lap: LapKey) => {
    if (!isDraggingLapsRef.current || !dragStartLapRef.current) return;
    if (sameLap(dragStartLapRef.current, lap)) return;
    selectRange(dragStartLapRef.current, lap);
  };

  const handleSelectAllSessionLaps = (sessionId: string) => {
    const session = sessions.find((s) => s.id === sessionId);
    if (!session) return;
    const usedColors = new Set(selectedLaps.map((l) => l.color));
    const next = [...selectedLaps];
    let hitLimit = false;
    for (const lap of session.laps) {
      if (next.length >= maxLapsAllowed) {
        hitLimit = true;
        break;
      }
      const key = `${sessionId}::${lap.lap_number}`;
      if (!selectedLapMap.has(key)) {
        const color = allocateColor(usedColors);
        usedColors.add(color);
        next.push({ sessionId, lapNumber: lap.lap_number, color });
      }
    }
    if (hitLimit) triggerLapLimitNotice();
    onChangeSelectedLaps(next);
    setContextMenu(null);
  };

  const handleDeselectAllSessionLaps = (sessionId: string) => {
    onChangeSelectedLaps(selectedLaps.filter((l) => l.sessionId !== sessionId));
    setContextMenu(null);
  };

  // Available channels across loaded sessions + global calculated channels whose dependencies are available
  const availableChannels = useMemo(() => {
    const rawSet = new Set<string>();
    for (const s of sessions) {
      for (const ch of s.channels) {
        rawSet.add(ch);
      }
    }
    const defs = stateManager.getChannelDefs();
    let changed = true;
    while (changed) {
      changed = false;
      for (const def of defs) {
        if (def.type === 'calculated' && def.slug && !rawSet.has(def.slug)) {
          const deps = Object.values(def.inputs ?? {});
          if (deps.length > 0 && deps.every((d) => rawSet.has(d))) {
            rawSet.add(def.slug);
            changed = true;
          }
        }
      }
    }
    const list = Array.from(rawSet);
    list.sort((a, b) =>
      stateManager.getDisplayNameBySlug(a).localeCompare(stateManager.getDisplayNameBySlug(b)),
    );
    return list;
  }, [sessions, channelsVersion]);

  const filteredChannels = useMemo(() => {
    const q = channelSearch.trim().toLowerCase();
    if (!q) return availableChannels;
    return availableChannels.filter((slug) => {
      const display = stateManager.getDisplayNameBySlug(slug).toLowerCase();
      return display.includes(q) || slug.toLowerCase().includes(q);
    });
  }, [availableChannels, channelSearch]);

  const triggerChannelLimitNotice = () => {
    setChannelLimitNotice(true);
    window.setTimeout(() => setChannelLimitNotice(false), 2500);
  };

  const handleToggleChannel = (slug: string) => {
    if (selectedChannels.includes(slug)) {
      onChangeSelectedChannels(selectedChannels.filter((c) => c !== slug));
      setChannelLimitNotice(false);
    } else {
      if (selectedChannels.length >= maxChannelsAllowed) {
        triggerChannelLimitNotice();
        return;
      }
      onChangeSelectedChannels([...selectedChannels, slug]);
    }
  };

  const selectChannelRange = (fromSlug: string, toSlug: string) => {
    const idxA = filteredChannels.indexOf(fromSlug);
    const idxB = filteredChannels.indexOf(toSlug);
    if (idxA === -1 || idxB === -1) return;
    const start = Math.min(idxA, idxB);
    const end = Math.max(idxA, idxB);
    const rawSlice = filteredChannels.slice(start, end + 1);
    if (rawSlice.length > maxChannelsAllowed) {
      triggerChannelLimitNotice();
    } else {
      setChannelLimitNotice(false);
    }
    onChangeSelectedChannels(rawSlice.slice(0, maxChannelsAllowed));
  };

  const handleChannelPointerDown = (e: React.PointerEvent, slug: string) => {
    if (e.button !== 0) return;
    const target = e.target as HTMLElement;
    if (target.closest('[data-channel-swatch="true"]') || target.closest('.channel-solo-btn')) {
      return;
    }

    if (e.shiftKey && anchorChannelRef.current) {
      selectChannelRange(anchorChannelRef.current, slug);
      return;
    }

    if (e.ctrlKey || e.metaKey) {
      handleToggleChannel(slug);
      anchorChannelRef.current = slug;
      return;
    }

    isDraggingChannelsRef.current = true;
    dragStartChannelRef.current = slug;
    anchorChannelRef.current = slug;
    handleToggleChannel(slug);
  };

  const handleChannelPointerEnter = (slug: string) => {
    if (!isDraggingChannelsRef.current || !dragStartChannelRef.current) return;
    if (dragStartChannelRef.current === slug) return;
    selectChannelRange(dragStartChannelRef.current, slug);
  };

  const menuBtnStyle = (active: boolean): React.CSSProperties => ({
    background: active ? 'var(--bg-button-hover)' : 'transparent',
    color: 'var(--text-primary)',
    border: 'none',
    borderRadius: 4,
    padding: '3px 8px',
    fontSize: 12,
    cursor: 'pointer',
  });

  const dropdownStyle: React.CSSProperties = {
    position: 'absolute',
    top: '100%',
    left: 0,
    minWidth: 220,
    background: 'var(--bg-menu)',
    border: '1px solid var(--border-strong)',
    borderRadius: 6,
    boxShadow: '0 6px 20px rgba(0,0,0,0.35)',
    padding: '4px 0',
    zIndex: 1000,
  };

  const menuItemStyle = (disabled = false): React.CSSProperties => ({
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
    width: '100%',
    padding: '6px 12px',
    background: 'transparent',
    border: 'none',
    color: disabled ? 'var(--text-muted)' : 'var(--text-primary)',
    fontSize: 12,
    textAlign: 'left',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.6 : 1,
  });

  return (
    <aside
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        width: '100%',
        background: 'var(--bg-panel)',
        color: 'var(--text-primary)',
        borderRight: '1px solid var(--border-subtle)',
        userSelect: 'none',
        position: 'relative',
        overflow: 'visible',
      }}
    >
      {/* 1. Compact Top Menu Bar */}
      <div
        ref={menuBarRef}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 2,
          padding: '4px 6px',
          borderBottom: '1px solid var(--border-subtle)',
          background: 'var(--bg-surface)',
          position: 'relative',
          zIndex: 40,
          flexShrink: 0,
        }}
      >
        {/* File Menu */}
        <div style={{ position: 'relative' }}>
          <button
            type="button"
            style={menuBtnStyle(openMenu === 'file')}
            onClick={() => {
              setOpenMenu(openMenu === 'file' ? null : 'file');
              setRecentSubmenuOpen(false);
            }}
            onMouseEnter={() => openMenu && setOpenMenu('file')}
          >
            File
          </button>
          {openMenu === 'file' && (
            <div style={dropdownStyle}>
              <button
                type="button"
                style={menuItemStyle()}
                onClick={() => {
                  setOpenMenu(null);
                  onOpenFiles();
                }}
              >
                <span>Open Log File...</span>
                <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>Ctrl+O</span>
              </button>

              {/* Recent Files Submenu */}
              <div
                style={{ position: 'relative' }}
                onMouseEnter={() => setRecentSubmenuOpen(true)}
                onMouseLeave={() => setRecentSubmenuOpen(false)}
              >
                <button
                  type="button"
                  style={menuItemStyle()}
                  onClick={() => setRecentSubmenuOpen((v) => !v)}
                >
                  <span>Recent Files</span>
                  <ChevronRight size={13} />
                </button>
                {recentSubmenuOpen && (
                  <div
                    style={{
                      ...dropdownStyle,
                      top: 0,
                      left: '100%',
                      minWidth: 240,
                      maxHeight: 320,
                      overflowY: 'auto',
                    }}
                  >
                    {recentFiles.length === 0 ? (
                      <div style={{ padding: '6px 12px', fontSize: 12, color: 'var(--text-muted)' }}>
                        (No recent files)
                      </div>
                    ) : (
                      recentFiles.map((entry) => {
                        const hasHandle = Boolean(entry.handle);
                        return (
                          <button
                            key={entry.id}
                            type="button"
                            disabled={!hasHandle}
                            title={
                              hasHandle
                                ? entry.name
                                : 'Browser requires re-selecting file on non-Chromium'
                            }
                            style={menuItemStyle(!hasHandle)}
                            onClick={() => {
                              if (!hasHandle) return;
                              setOpenMenu(null);
                              setRecentSubmenuOpen(false);
                              onOpenRecentFile(entry);
                            }}
                          >
                            <span
                              style={{
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap',
                              }}
                            >
                              {entry.name}
                            </span>
                          </button>
                        );
                      })
                    )}
                    <div
                      style={{
                        height: 1,
                        background: 'var(--border-subtle)',
                        margin: '4px 0',
                      }}
                    />
                    <button
                      type="button"
                      disabled={recentFiles.length === 0}
                      style={menuItemStyle(recentFiles.length === 0)}
                      onClick={() => {
                        setOpenMenu(null);
                        setRecentSubmenuOpen(false);
                        onClearRecentFiles();
                      }}
                    >
                      <span>Clear Recent</span>
                    </button>
                  </div>
                )}
              </div>

              <div style={{ height: 1, background: 'var(--border-subtle)', margin: '4px 0' }} />
              <button
                type="button"
                style={menuItemStyle()}
                onClick={() => {
                  setOpenMenu(null);
                  onClearWorkspace();
                }}
              >
                <span>Clear Workspace</span>
              </button>
              <div style={{ height: 1, background: 'var(--border-subtle)', margin: '4px 0' }} />
              <button
                type="button"
                style={menuItemStyle()}
                onClick={() => {
                  setOpenMenu(null);
                  onImportConfig();
                }}
              >
                <span>Import Configuration...</span>
              </button>
              <button
                type="button"
                style={menuItemStyle()}
                onClick={() => {
                  setOpenMenu(null);
                  onExportConfig();
                }}
              >
                <span>Export Configuration...</span>
              </button>
            </div>
          )}
        </div>

        {/* Edit Menu */}
        <div style={{ position: 'relative' }}>
          <button
            type="button"
            style={menuBtnStyle(openMenu === 'edit')}
            onClick={() => setOpenMenu(openMenu === 'edit' ? null : 'edit')}
            onMouseEnter={() => openMenu && setOpenMenu('edit')}
          >
            Edit
          </button>
          {openMenu === 'edit' && (
            <div style={dropdownStyle}>
              <button
                type="button"
                style={menuItemStyle()}
                onClick={() => {
                  setOpenMenu(null);
                  onOpenManagePresets();
                }}
              >
                <span>Manage Presets...</span>
              </button>
              <button
                type="button"
                style={menuItemStyle()}
                onClick={() => {
                  setOpenMenu(null);
                  onOpenManageChannels();
                }}
              >
                <span>Manage Global Channels...</span>
              </button>
              <button
                type="button"
                style={menuItemStyle()}
                onClick={() => {
                  setOpenMenu(null);
                  onOpenManageFileMappings();
                }}
              >
                <span>Manage File Mappings...</span>
              </button>
              <button
                type="button"
                style={menuItemStyle()}
                onClick={() => {
                  setOpenMenu(null);
                  onOpenManageMaps();
                }}
              >
                <span>Manage Track Maps...</span>
              </button>
            </div>
          )}
        </div>

        {/* View Menu */}
        <div style={{ position: 'relative' }}>
          <button
            type="button"
            style={menuBtnStyle(openMenu === 'view')}
            onClick={() => setOpenMenu(openMenu === 'view' ? null : 'view')}
            onMouseEnter={() => openMenu && setOpenMenu('view')}
          >
            View
          </button>
          {openMenu === 'view' && (
            <div style={dropdownStyle}>
              <div
                style={{
                  padding: '4px 12px',
                  fontSize: 11,
                  color: 'var(--text-muted)',
                  fontWeight: 600,
                }}
              >
                Theme
              </div>
              {(['auto', 'dark', 'light'] as ThemeMode[]).map((mode) => {
                const label =
                  mode === 'auto' ? 'Auto (System)' : mode === 'dark' ? 'Dark' : 'Light';
                const checked = themeMode === mode;
                return (
                  <button
                    key={mode}
                    type="button"
                    style={menuItemStyle()}
                    onClick={() => {
                      onSetThemeMode(mode);
                      setOpenMenu(null);
                    }}
                  >
                    <span>{label}</span>
                    {checked && <Check size={13} />}
                  </button>
                );
              })}
              <div style={{ height: 1, background: 'var(--border-subtle)', margin: '4px 0' }} />
              <div
                style={{
                  padding: '4px 12px',
                  fontSize: 11,
                  color: 'var(--text-muted)',
                  fontWeight: 600,
                }}
              >
                Cursor Values
              </div>
              <button
                type="button"
                style={menuItemStyle()}
                onClick={() =>
                  onUpdateGraphSettings({ showCursorOnGraph: !graphSettings.showCursorOnGraph })
                }
              >
                <span>On Graph</span>
                {graphSettings.showCursorOnGraph && <Check size={13} />}
              </button>
              <button
                type="button"
                style={menuItemStyle()}
                onClick={() =>
                  onUpdateGraphSettings({
                    showCursorAboveGraph: !graphSettings.showCursorAboveGraph,
                  })
                }
              >
                <span>Above Graph</span>
                {graphSettings.showCursorAboveGraph && <Check size={13} />}
              </button>
              <div style={{ height: 1, background: 'var(--border-subtle)', margin: '4px 0' }} />
              <button
                type="button"
                style={menuItemStyle()}
                onClick={() => onUpdateGraphSettings({ antialias: !graphSettings.antialias })}
              >
                <span>Anti-Aliasing</span>
                {graphSettings.antialias && <Check size={13} />}
              </button>
              <button
                type="button"
                style={menuItemStyle()}
                onClick={() => onUpdateGraphSettings({ filterGaps: !graphSettings.filterGaps })}
              >
                <span>Filter Data Gaps</span>
                {graphSettings.filterGaps && <Check size={13} />}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Split Container for Top & Bottom Sections */}
      <div
        ref={sidebarContentRef}
        style={{
          display: 'flex',
          flexDirection: 'column',
          flex: 1,
          minHeight: 0,
        }}
      >
      {/* 2. Sessions & Laps Panel */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          flex: `0 0 calc(${(localSplitRatio * 100).toFixed(2)}% - 2px)`,
          minHeight: 0,
          padding: 6,
          gap: 6,
        }}
      >
        {/* Grouping Mode Toggle (By Channel | By Lap) */}
        <div
          role="group"
          aria-label="Plot grouping"
          style={{
            display: 'flex',
            gap: 4,
            flexShrink: 0,
          }}
        >
          {(
            [
              { mode: 'channel' as const, label: 'By Channel' },
              { mode: 'lap' as const, label: 'By Lap' },
            ]
          ).map(({ mode, label }) => {
            const active = graphSettings.groupingMode === mode;
            return (
              <button
                key={mode}
                type="button"
                aria-pressed={active}
                onClick={() => onChangeGroupingMode(mode)}
                style={{
                  flex: 1,
                  height: 26,
                  padding: '0 8px',
                  fontSize: 11,
                  fontWeight: active ? 600 : 500,
                  borderRadius: 5,
                  border: active
                    ? '1px solid var(--accent-border)'
                    : '1px solid var(--border-subtle)',
                  background: active ? 'var(--accent-subtle)' : 'var(--bg-button)',
                  color: active ? 'var(--accent-fg)' : 'var(--text-muted)',
                  cursor: 'pointer',
                }}
              >
                {label}
              </button>
            );
          })}
        </div>

        {lapLimitNotice && (
          <div
            style={{
              fontSize: 11,
              padding: '4px 8px',
              borderRadius: 4,
              background: 'var(--danger-bg)',
              color: 'var(--warning)',
              flexShrink: 0,
            }}
          >
            Maximum {maxLapsAllowed} laps can be selected.
          </div>
        )}


        <div
          style={{
            flex: 1,
            minHeight: 0,
            overflowY: 'auto',
            border: '1px solid var(--border-subtle)',
            borderRadius: 6,
            background: 'var(--bg-surface)',
          }}
        >
          {sessions.length === 0 ? (
            <div
              style={{
                padding: 16,
                textAlign: 'center',
                fontSize: 12,
                color: 'var(--text-muted)',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <FolderOpen size={20} style={{ opacity: 0.6 }} />
              <span>No sessions loaded.</span>
            </div>
          ) : (
            sessions.map((session) => {
              const isExpanded = expandedSessions[session.id] ?? true;
              const selectedCount = selectedLaps.filter((l) => l.sessionId === session.id).length;
              return (
                <div key={session.id}>
                  {/* Session Header Row */}
                  <div
                    onClick={() =>
                      setExpandedSessions((prev) => ({ ...prev, [session.id]: !isExpanded }))
                    }
                    onContextMenu={(e) => {
                      e.preventDefault();
                      setContextMenu({ sessionId: session.id, x: e.clientX, y: e.clientY });
                    }}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 4,
                      padding: '5px 6px',
                      background: 'var(--bg-elevated)',
                      borderBottom: '1px solid var(--border-subtle)',
                      fontSize: 12,
                      fontWeight: 600,
                      cursor: 'pointer',
                    }}
                  >
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setExpandedSessions((prev) => ({ ...prev, [session.id]: !isExpanded }));
                      }}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: 'var(--text-muted)',
                        padding: 0,
                        display: 'flex',
                        alignItems: 'center',
                        cursor: 'pointer',
                      }}
                    >
                      {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </button>
                    <span
                      title={session.name}
                      style={{
                        flex: 1,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        color: 'var(--text-strong)',
                      }}
                    >
                      {session.name}
                    </span>
                    <span
                      className="tabular-nums"
                      style={{ fontSize: 11, color: 'var(--text-muted)', flexShrink: 0 }}
                    >
                      {selectedCount}/{session.laps.length}
                    </span>
                    <button
                      type="button"
                      title="Session Actions"
                      onClick={(e) => {
                        e.stopPropagation();
                        const rect = e.currentTarget.getBoundingClientRect();
                        setContextMenu({ sessionId: session.id, x: rect.right, y: rect.bottom });
                      }}
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: 'var(--text-muted)',
                        padding: 2,
                        display: 'flex',
                        alignItems: 'center',
                        cursor: 'pointer',
                      }}
                    >
                      <MoreVertical size={13} />
                    </button>
                  </div>

                  {/* Lap Rows (all when expanded, only selected when collapsed) */}
                  {session.laps
                    .filter(
                      (lap) =>
                        isExpanded || selectedLapMap.has(`${session.id}::${lap.lap_number}`),
                    )
                    .map((lap) => {
                      const lapKey: LapKey = { sessionId: session.id, lapNumber: lap.lap_number };
                      const sel = selectedLapMap.get(`${session.id}::${lap.lap_number}`);
                      return (
                        <div
                          key={lap.lap_number}
                          onPointerDown={(e) => handleLapPointerDown(e, lapKey)}
                          onPointerEnter={() => handleLapPointerEnter(lapKey)}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 6,
                            padding: '4px 8px 4px 20px',
                            fontSize: 12,
                            cursor: 'pointer',
                            background: sel ? 'var(--accent-subtle)' : 'transparent',
                            borderBottom: '1px solid var(--border-subtle)',
                          }}
                        >
                          {isByLap ? (
                            <input
                              type="checkbox"
                              readOnly
                              checked={Boolean(sel)}
                              tabIndex={-1}
                              style={{
                                margin: 0,
                                pointerEvents: 'none',
                                accentColor: 'var(--accent)',
                                flexShrink: 0,
                              }}
                            />
                          ) : (
                            <button
                              type="button"
                              data-lap-swatch="true"
                              title={sel ? 'Change lap color' : 'Not selected'}
                              onClick={(e) => {
                                e.stopPropagation();
                                if (!sel) return;
                                const rect = e.currentTarget.getBoundingClientRect();
                                setColorPickerTarget({
                                  kind: 'lap',
                                  sessionId: session.id,
                                  lapNumber: lap.lap_number,
                                  x: rect.left,
                                  y: rect.bottom + 4,
                                });
                              }}
                              style={{
                                width: 12,
                                height: 12,
                                borderRadius: 3,
                                border: sel
                                  ? '1px solid rgba(255,255,255,0.4)'
                                  : '1px solid var(--border-strong)',
                                background: sel ? sel.color : 'transparent',
                                padding: 0,
                                cursor: sel ? 'pointer' : 'default',
                                flexShrink: 0,
                              }}
                            />
                          )}
                          <span style={{ flex: 1, color: 'var(--text-primary)' }}>
                            Lap {lap.lap_number}
                          </span>
                          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                            {Math.round(lap.distance)} m
                          </span>
                          <span
                            style={{
                              fontSize: 11,
                              fontVariantNumeric: 'tabular-nums',
                              color: 'var(--text-muted)',
                              minWidth: 62,
                              textAlign: 'right',
                            }}
                          >
                            {formatLapTime(lap.duration)}
                          </span>
                        </div>
                      );
                    })}
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Adjustable Vertical Divider */}
      <div
        onMouseDown={startVerticalSplitDrag}
        title="Drag to resize Sessions & Channels sections"
        style={{
          height: 4,
          cursor: 'row-resize',
          background: 'var(--border-strong)',
          flexShrink: 0,
        }}
      />

      {/* 3. Bottom Tab Widget (Channels | Track Map) */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          flex: 1,
          minHeight: 0,
        }}
      >
        <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
          {bottomTabIndex === 0 ? (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                flex: 1,
                minHeight: 0,
                padding: 6,
                gap: 6,
              }}
            >
              {/* Search & Counter Row */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                <div
                  style={{
                    flex: 1,
                    height: 28,
                    boxSizing: 'border-box',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '0 8px',
                    background: 'var(--bg-input)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 5,
                  }}
                >
                  <Search size={13} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
                  <input
                    type="text"
                    value={channelSearch}
                    onChange={(e) => setChannelSearch(e.target.value)}
                    placeholder="Filter channels..."
                    style={{
                      flex: 1,
                      background: 'transparent',
                      border: 'none',
                      outline: 'none',
                      color: 'var(--text-primary)',
                      fontSize: 12,
                      minWidth: 0,
                    }}
                  />
                </div>
                <span
                  className="tabular-nums"
                  style={{
                    height: 28,
                    boxSizing: 'border-box',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 11,
                    fontWeight: 600,
                    padding: '0 8px',
                    borderRadius: 5,
                    background: 'var(--badge-bg)',
                    border: '1px solid var(--border-subtle)',
                    color:
                      selectedChannels.length >= maxChannelsAllowed
                        ? 'var(--warning)'
                        : 'var(--text-muted)',
                    flexShrink: 0,
                  }}
                >
                  {selectedChannels.length}/{maxChannelsAllowed}
                </span>
                <button
                  type="button"
                  onClick={() => onChangeSelectedChannels([])}
                  disabled={selectedChannels.length === 0}
                  title="Clear channel selection"
                  aria-label="Clear channel selection"
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: 28,
                    height: 28,
                    boxSizing: 'border-box',
                    padding: 0,
                    borderRadius: 5,
                    border: '1px solid var(--border-subtle)',
                    background: 'var(--bg-button)',
                    color: selectedChannels.length === 0 ? 'var(--text-muted)' : 'var(--text-primary)',
                    opacity: selectedChannels.length === 0 ? 0.5 : 1,
                    cursor: selectedChannels.length === 0 ? 'default' : 'pointer',
                    flexShrink: 0,
                  }}
                >
                  <ListX size={13} />
                </button>
              </div>

              {channelLimitNotice && (
                <div
                  style={{
                    fontSize: 11,
                    padding: '4px 8px',
                    borderRadius: 4,
                    background: 'var(--danger-bg)',
                    color: 'var(--warning)',
                    flexShrink: 0,
                  }}
                >
                  Maximum {maxChannelsAllowed} channels can be selected.
                </div>
              )}

              {/* Channel List */}
              <div
                style={{
                  flex: 1,
                  minHeight: 0,
                  overflowY: 'auto',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 6,
                  background: 'var(--bg-surface)',
                }}
              >
                {filteredChannels.length === 0 ? (
                  <div
                    style={{
                      padding: 12,
                      fontSize: 12,
                      color: 'var(--text-muted)',
                      textAlign: 'center',
                    }}
                  >
                    {availableChannels.length === 0
                      ? 'No channels available.'
                      : 'No matching channels.'}
                  </div>
                ) : (
                  filteredChannels.map((slug) => {
                    const checked = selectedChannels.includes(slug);
                    const label = stateManager.getDisplayNameBySlug(slug);
                    const chColor = channelColors[slug] ?? LAP_COLORS[0];
                    return (
                      <div
                        key={slug}
                        role="checkbox"
                        aria-checked={checked}
                        tabIndex={0}
                        className="channel-row"
                        onPointerDown={(e) => handleChannelPointerDown(e, slug)}
                        onPointerEnter={() => handleChannelPointerEnter(slug)}
                        onKeyDown={(e) => {
                          if (e.key === ' ' || e.key === 'Enter') {
                            e.preventDefault();
                            handleToggleChannel(slug);
                          }
                        }}
                        style={{
                          display: 'flex',
                          alignItems: 'stretch',
                          gap: 8,
                          paddingLeft: 8,
                          paddingRight: 0,
                          minHeight: 28,
                          fontSize: 12,
                          cursor: 'pointer',
                          borderBottom: '1px solid var(--border-subtle)',
                          background: checked ? 'var(--accent-subtle)' : 'transparent',
                        }}
                      >
                        {isByLap ? (
                          <button
                            type="button"
                            data-channel-swatch="true"
                            title={checked ? 'Change channel color' : 'Not selected'}
                            onPointerDown={(e) => e.stopPropagation()}
                            onClick={(e) => {
                              e.stopPropagation();
                              if (!checked) return;
                              const rect = e.currentTarget.getBoundingClientRect();
                              setColorPickerTarget({
                                kind: 'channel',
                                slug,
                                x: rect.left,
                                y: rect.bottom + 4,
                              });
                            }}
                            style={{
                              width: 12,
                              height: 12,
                              alignSelf: 'center',
                              borderRadius: 3,
                              border: checked
                                ? '1px solid rgba(255,255,255,0.4)'
                                : '1px solid var(--border-strong)',
                              background: checked ? chColor : 'transparent',
                              padding: 0,
                              cursor: checked ? 'pointer' : 'default',
                              flexShrink: 0,
                            }}
                          />
                        ) : (
                          <input
                            type="checkbox"
                            readOnly
                            checked={checked}
                            tabIndex={-1}
                            style={{
                              cursor: 'pointer',
                              pointerEvents: 'none',
                              accentColor: 'var(--accent)',
                              flexShrink: 0,
                              alignSelf: 'center',
                              margin: '6px 0',
                            }}
                          />
                        )}
                        <span
                          title={label}
                          style={{
                            flex: 1,
                            minWidth: 0,
                            alignSelf: 'center',
                            padding: '4px 0',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            color: 'var(--text-primary)',
                          }}
                        >
                          {label}
                        </span>
                        <button
                          type="button"
                          className="channel-solo-btn"
                          title="Select only this channel"
                          aria-label={`Select only ${label}`}
                          onPointerDown={(e) => e.stopPropagation()}
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            onChangeSelectedChannels([slug]);
                          }}
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            width: 26,
                            padding: 0,
                            border: 'none',
                            borderRadius: 0,
                            background: 'var(--bg-button)',
                            color: 'var(--text-muted)',
                            cursor: 'pointer',
                            flexShrink: 0,
                          }}
                        >
                          <ChevronRight size={14} />
                        </button>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          ) : (
            <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>{trackMapSlot}</div>
          )}
        </div>

        {/* Bottom Tab Selector */}
        <div
          style={{
            display: 'flex',
            borderTop: '1px solid var(--border-subtle)',
            background: 'var(--bg-surface)',
            flexShrink: 0,
          }}
        >
          {['Channels', 'Track Map'].map((tabLabel, idx) => {
            const active = bottomTabIndex === idx;
            return (
              <button
                key={tabLabel}
                type="button"
                onClick={() => onBottomTabChange(idx)}
                style={{
                  flex: 1,
                  padding: '6px 8px',
                  fontSize: 12,
                  fontWeight: active ? 600 : 400,
                  background: active ? 'var(--bg-panel)' : 'transparent',
                  color: active ? 'var(--accent-fg)' : 'var(--text-muted)',
                  border: 'none',
                  borderTop: active ? '2px solid var(--accent)' : '2px solid transparent',
                  cursor: 'pointer',
                }}
              >
                {tabLabel}
              </button>
            );
          })}
        </div>
      </div>
      </div>

      {/* Session Context Menu */}
      {contextMenu && (
        <div
          data-sidebar-context-menu="true"
          style={{
            position: 'fixed',
            top: contextMenu.y,
            left: contextMenu.x,
            minWidth: 185,
            background: 'var(--bg-menu)',
            border: '1px solid var(--border-strong)',
            borderRadius: 6,
            boxShadow: '0 6px 20px rgba(0,0,0,0.4)',
            padding: '4px 0',
            zIndex: 1200,
          }}
        >
          <button
            type="button"
            style={menuItemStyle()}
            onClick={() => handleSelectAllSessionLaps(contextMenu.sessionId)}
          >
            <span>Select All Laps</span>
          </button>
          <button
            type="button"
            style={menuItemStyle()}
            onClick={() => handleDeselectAllSessionLaps(contextMenu.sessionId)}
          >
            <span>Deselect All Laps</span>
          </button>
          <div style={{ height: 1, background: 'var(--border-subtle)', margin: '4px 0' }} />
          <button
            type="button"
            style={menuItemStyle()}
            onClick={() => {
              const sid = contextMenu.sessionId;
              setContextMenu(null);
              onReloadSession(sid);
            }}
          >
            <span>Reload</span>
            <RotateCw size={13} />
          </button>
          <button
            type="button"
            style={menuItemStyle()}
            onClick={() => {
              const sid = contextMenu.sessionId;
              setContextMenu(null);
              onEditSessionMapping(sid);
            }}
          >
            <span>Edit Channel Mapping...</span>
          </button>
          <button
            type="button"
            style={{ ...menuItemStyle(), color: 'var(--danger)' }}
            onClick={() => {
              const sid = contextMenu.sessionId;
              setContextMenu(null);
              onRemoveSession(sid);
            }}
          >
            <span>Remove Session</span>
            <Trash2 size={13} />
          </button>
        </div>
      )}

      {/* Lap Color Picker Popover */}
      {colorPickerTarget && (
        <div
          data-lap-color-picker="true"
          style={{
            position: 'fixed',
            top: colorPickerTarget.y,
            left: colorPickerTarget.x,
            display: 'grid',
            gridTemplateColumns: 'repeat(4, 22px)',
            gap: 6,
            padding: 8,
            background: 'var(--bg-menu)',
            border: '1px solid var(--border-strong)',
            borderRadius: 6,
            boxShadow: '0 6px 20px rgba(0,0,0,0.4)',
            zIndex: 1200,
          }}
        >
          {LAP_COLORS.map((color) => (
            <button
              key={color}
              type="button"
              title={color}
              onClick={() => {
                if (colorPickerTarget.kind === 'lap') {
                  onChangeSelectedLaps(
                    selectedLaps.map((l) =>
                      sameLap(l, colorPickerTarget) ? { ...l, color } : l,
                    ),
                  );
                } else {
                  onChangeChannelColor(colorPickerTarget.slug, color);
                }
                setColorPickerTarget(null);
              }}
              style={{
                width: 22,
                height: 22,
                borderRadius: 4,
                background: color,
                border: '1px solid rgba(255,255,255,0.35)',
                cursor: 'pointer',
                padding: 0,
              }}
            />
          ))}
        </div>
      )}
    </aside>
  );
};

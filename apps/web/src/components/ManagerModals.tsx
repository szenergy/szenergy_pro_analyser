import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Check,
  Clock,
  Database,
  Download,
  FileSpreadsheet,
  FolderOpen,
  GripVertical,
  Layers,
  Map as MapIcon,
  Plus,
  Search,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import {
  generateUniqueSlug,
  stateManager,
} from '@/state/stateManager';
import {
  ChannelGroupDef,
  FileImportConfig,
  isRequiredChannelGroupId,
  LAP_COLORS,
  RecentFileEntry,
  SessionSummary,
  TrackMapDef,
} from '@/types/telemetry';
import { telemetryClient } from '@/workers/telemetryClient';

// ---------------------------------------------------------------------------
// Shared Modal Shell & Styles
// ---------------------------------------------------------------------------

const overlayStyle: React.CSSProperties = {
  position: 'fixed',
  inset: 0,
  zIndex: 1000,
  backgroundColor: 'rgba(0, 0, 0, 0.6)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  padding: 16,
};

const modalStyle: React.CSSProperties = {
  backgroundColor: 'var(--bg-panel)',
  border: '1px solid var(--border-strong)',
  borderRadius: 8,
  width: '100%',
  maxWidth: 860,
  maxHeight: '88vh',
  display: 'flex',
  flexDirection: 'column',
  color: 'var(--text-primary)',
  boxShadow: '0 12px 32px rgba(0, 0, 0, 0.45)',
};

const headerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '12px 16px',
  borderBottom: '1px solid var(--border-subtle)',
};

const inputStyle: React.CSSProperties = {
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border-strong)',
  borderRadius: 4,
  padding: '6px 8px',
  color: 'var(--text-primary)',
  fontSize: 13,
  outline: 'none',
  width: '100%',
  boxSizing: 'border-box',
};

const btnStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  padding: '6px 10px',
  borderRadius: 4,
  border: '1px solid var(--border-strong)',
  backgroundColor: 'var(--bg-button)',
  color: 'var(--text-primary)',
  fontSize: 12,
  cursor: 'pointer',
};

const primaryBtnStyle: React.CSSProperties = {
  ...btnStyle,
  border: '1px solid var(--accent-border)',
  backgroundColor: 'var(--accent)',
  color: 'var(--accent-text)',
  fontWeight: 600,
};

const dangerBtnStyle: React.CSSProperties = {
  ...btnStyle,
  border: '1px solid var(--danger)',
  backgroundColor: 'var(--danger-bg)',
  color: 'var(--danger)',
};

// ---------------------------------------------------------------------------
// 1. ChannelGroupManagerModal
// ---------------------------------------------------------------------------

export interface ChannelGroupManagerModalProps {
  isOpen: boolean;
  sessions: SessionSummary[];
  initialFocusGroupId?: string | null;
  initialDraftChannels?: string[] | null;
  onClose: () => void;
  onGroupsUpdated: () => Promise<void> | void;
}

export const ChannelGroupManagerModal: React.FC<ChannelGroupManagerModalProps> = ({
  isOpen,
  sessions,
  initialFocusGroupId,
  initialDraftChannels,
  onClose,
  onGroupsUpdated,
}) => {
  const [draftGroups, setDraftGroups] = useState<ChannelGroupDef[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draggedMember, setDraggedMember] = useState<string | null>(null);
  const [dragOverMember, setDragOverMember] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    if (!isOpen) return;
    setErrorMsg('');
    setSearch('');
    const loaded = stateManager.getChannelGroups();

    if (initialDraftChannels && initialDraftChannels.length > 0) {
      const cleanDraft = Array.from(new Set(initialDraftChannels));
      const draftSet = new Set(cleanDraft);
      const cleanedLoaded = loaded.map((g) => ({
        ...g,
        channels: g.channels.filter((c) => !draftSet.has(c)),
      }));
      const newId = generateUniqueSlug(
        `grp_${cleanDraft[0]}`,
        cleanedLoaded.map((g) => g.id),
      );
      const draftGroup: ChannelGroupDef = {
        id: newId,
        name: cleanDraft[0],
        unit: '',
        channels: cleanDraft,
      };
      setDraftGroups([...cleanedLoaded, draftGroup]);
      setSelectedId(newId);
      return;
    }

    setDraftGroups(loaded);
    if (initialFocusGroupId && loaded.some((g) => g.id === initialFocusGroupId)) {
      setSelectedId(initialFocusGroupId);
    } else if (loaded.length > 0) {
      setSelectedId(loaded[0].id);
    } else {
      setSelectedId(null);
    }
  }, [isOpen, initialFocusGroupId, initialDraftChannels]);

  const selectedGroup = useMemo(
    () => draftGroups.find((g) => g.id === selectedId) ?? null,
    [draftGroups, selectedId],
  );

  const editMembers = useMemo(
    () => selectedGroup?.channels ?? [],
    [selectedGroup],
  );

  const allRawChannels = useMemo(() => {
    const sessionMap = new Map<string, string[]>();
    for (const s of sessions) {
      const seenInSession = new Set<string>();
      for (const ch of s.channels) {
        seenInSession.add(ch);
      }
      if (s.lap_col) seenInSession.add(s.lap_col);
      if (s.time_col) seenInSession.add(s.time_col);
      if (s.dist_col) seenInSession.add(s.dist_col);
      for (const ch of seenInSession) {
        const list = sessionMap.get(ch) ?? [];
        list.push(s.name);
        sessionMap.set(ch, list);
      }
    }
    for (const g of draftGroups) {
      for (const ch of g.channels) {
        if (!sessionMap.has(ch)) {
          sessionMap.set(ch, []);
        }
      }
    }
    return Array.from(sessionMap.entries())
      .map(([name, sessionNames]) => ({ name, sessionNames }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [sessions, draftGroups]);

  const unselectedChannels = useMemo(() => {
    const memberSet = new Set(editMembers);
    const q = search.trim().toLowerCase();
    return allRawChannels.filter((c) => {
      if (memberSet.has(c.name)) return false;
      if (!q) return true;
      return c.name.toLowerCase().includes(q);
    });
  }, [allRawChannels, editMembers, search]);

  const filteredSelectedMembers = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return editMembers;
    return editMembers.filter((m) => m.toLowerCase().includes(q));
  }, [editMembers, search]);

  const channelSessionCounts = useMemo(() => {
    const map = new Map<string, number>();
    for (const c of allRawChannels) {
      map.set(c.name, c.sessionNames.length);
    }
    return map;
  }, [allRawChannels]);

  const draftGroupForChannel = useMemo(() => {
    const map = new Map<string, ChannelGroupDef>();
    for (const g of draftGroups) {
      for (const ch of g.channels) {
        map.set(ch, g);
      }
    }
    return map;
  }, [draftGroups]);

  if (!isOpen) return null;

  const updateSelectedGroup = (updater: (grp: ChannelGroupDef) => ChannelGroupDef) => {
    if (!selectedId) return;
    setErrorMsg('');
    setDraftGroups((prev) =>
      prev.map((g) => (g.id === selectedId ? updater(g) : g)),
    );
  };

  const reorderMember = (fromName: string, toName: string) => {
    if (fromName === toName) return;
    updateSelectedGroup((grp) => {
      const fromIdx = grp.channels.indexOf(fromName);
      const toIdx = grp.channels.indexOf(toName);
      if (fromIdx < 0 || toIdx < 0) return grp;
      const next = [...grp.channels];
      const [moved] = next.splice(fromIdx, 1);
      next.splice(toIdx, 0, moved);
      return { ...grp, channels: next };
    });
  };

  const handleSelectGroup = (grp: ChannelGroupDef) => {
    setErrorMsg('');
    setSelectedId(grp.id);
  };

  const handleStartNew = () => {
    setErrorMsg('');
    const newId = generateUniqueSlug(
      'grp_new_group',
      draftGroups.map((g) => g.id),
    );
    const newGroup: ChannelGroupDef = {
      id: newId,
      name: 'New Group',
      unit: '',
      channels: [],
    };
    setDraftGroups((prev) => [...prev, newGroup]);
    setSelectedId(newId);
  };

  const handleToggleMember = (chName: string) => {
    if (!selectedId) return;
    setErrorMsg('');
    setDraftGroups((prev) => {
      const target = prev.find((g) => g.id === selectedId);
      if (!target) return prev;
      const isRemoving = target.channels.includes(chName);
      if (isRemoving) {
        return prev.map((g) => {
          if (g.id !== selectedId) return g;
          const nextTransforms = g.transforms ? { ...g.transforms } : undefined;
          if (nextTransforms) delete nextTransforms[chName];
          return {
            ...g,
            channels: g.channels.filter((c) => c !== chName),
            transforms: nextTransforms,
          };
        });
      }
      return prev.map((g) => {
        if (g.id === selectedId) {
          return { ...g, channels: [...g.channels, chName] };
        }
        const nextTransforms = g.transforms ? { ...g.transforms } : undefined;
        if (nextTransforms) delete nextTransforms[chName];
        return {
          ...g,
          channels: g.channels.filter((c) => c !== chName),
          transforms: nextTransforms,
        };
      });
    });
  };

  const handleTransformChange = (chName: string, field: 'factor' | 'offset', rawValue: string) => {
    const num = Number(rawValue);
    const val = Number.isFinite(num) ? num : field === 'factor' ? 1 : 0;
    updateSelectedGroup((grp) => {
      const current = grp.transforms?.[chName] ?? { factor: 1, offset: 0 };
      const next = {
        factor: field === 'factor' ? val : current.factor,
        offset: field === 'offset' ? val : current.offset,
      };
      const nextTransforms = { ...(grp.transforms ?? {}) };
      if (next.factor === 1 && next.offset === 0) {
        delete nextTransforms[chName];
      } else {
        nextTransforms[chName] = next;
      }
      return {
        ...grp,
        transforms: Object.keys(nextTransforms).length > 0 ? nextTransforms : undefined,
      };
    });
  };

  const handleDelete = (id: string) => {
    if (isRequiredChannelGroupId(id)) return;
    setErrorMsg('');
    setDraftGroups((prev) => {
      const next = prev.filter((g) => g.id !== id);
      if (selectedId === id) {
        setSelectedId(next[0]?.id ?? null);
      }
      return next;
    });
  };

  const handleSaveAll = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setErrorMsg('');
    for (const g of draftGroups) {
      const cleanName = g.name.trim();
      if (!cleanName) {
        setSelectedId(g.id);
        setErrorMsg('Every group must have a non-empty name.');
        return;
      }
      if (!isRequiredChannelGroupId(g.id) && g.channels.length === 0) {
        setSelectedId(g.id);
        setErrorMsg(`Group "${cleanName}" must include at least one channel.`);
        return;
      }
    }

    const cleaned = draftGroups.map((g) => ({
      ...g,
      name: g.name.trim(),
      unit: g.unit.trim(),
      channels: [...g.channels],
      ...(g.transforms ? { transforms: { ...g.transforms } } : {}),
    }));
    await stateManager.saveChannelGroups(cleaned);
    await onGroupsUpdated();
    onClose();
  };

  return (
    <div style={overlayStyle} onClick={onClose}>
      <form
        onSubmit={(e) => void handleSaveAll(e)}
        style={modalStyle}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={headerStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, color: 'var(--text-strong)' }}>
            <Layers size={16} style={{ color: 'var(--accent)' }} />
            <span>Channel Group Manager</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
          >
            <X size={18} />
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', flex: 1, minHeight: 400, overflow: 'hidden' }}>
          {/* Left: Group List */}
          <div style={{ borderRight: '1px solid var(--border-subtle)', overflowY: 'auto', padding: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
            {draftGroups.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: 16, textAlign: 'center' }}>
                No channel groups yet. Create one to combine channels with different names across logs.
              </div>
            ) : (
              draftGroups.map((g) => {
                const isSelected = g.id === selectedId;
                const isRequired = isRequiredChannelGroupId(g.id);
                return (
                  <div
                    key={g.id}
                    onClick={() => handleSelectGroup(g)}
                    style={{
                      padding: '8px 10px',
                      borderRadius: 6,
                      cursor: 'pointer',
                      backgroundColor: isSelected ? 'var(--accent-subtle)' : 'var(--bg-surface)',
                      border: `1px solid ${isSelected ? 'var(--accent-border)' : 'var(--border-subtle)'}`,
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
                      <span style={{ fontWeight: 600, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {g.name || 'Untitled'}
                        {g.unit ? ` [${g.unit}]` : ''}
                      </span>
                      {isRequired ? (
                        <span
                          style={{
                            fontSize: 10,
                            fontWeight: 600,
                            padding: '2px 5px',
                            borderRadius: 4,
                            backgroundColor: 'var(--badge-bg)',
                            color: 'var(--text-muted)',
                            flexShrink: 0,
                          }}
                        >
                          Required
                        </span>
                      ) : (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDelete(g.id);
                          }}
                          style={{ ...dangerBtnStyle, padding: '3px 6px' }}
                          title="Delete Group"
                        >
                          <Trash2 size={12} />
                        </button>
                      )}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                      {g.channels.length} channel{g.channels.length === 1 ? '' : 's'}
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* Right: Group Editor */}
          <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, padding: 16, gap: 12 }}>
            {!selectedGroup ? (
              <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', paddingTop: 40 }}>
                Select a group or click "New Group".
              </div>
            ) : (
              <>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 140px', gap: 10 }}>
                  <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
                    <span>Group Name</span>
                    <input
                      type="text"
                      placeholder="e.g. Vehicle Speed"
                      value={selectedGroup.name}
                      disabled={isRequiredChannelGroupId(selectedGroup.id)}
                      onChange={(e) =>
                        updateSelectedGroup((g) => ({ ...g, name: e.target.value }))
                      }
                      style={{
                        ...inputStyle,
                        opacity: isRequiredChannelGroupId(selectedGroup.id) ? 0.7 : 1,
                      }}
                    />
                  </label>
                  <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
                    <span>Unit (optional)</span>
                    <input
                      type="text"
                      placeholder="e.g. km/h"
                      value={selectedGroup.unit}
                      disabled={isRequiredChannelGroupId(selectedGroup.id)}
                      onChange={(e) =>
                        updateSelectedGroup((g) => ({ ...g, unit: e.target.value }))
                      }
                      style={{
                        ...inputStyle,
                        opacity: isRequiredChannelGroupId(selectedGroup.id) ? 0.7 : 1,
                      }}
                    />
                  </label>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                  <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-strong)' }}>
                    Member Channels ({editMembers.length} selected — drag to set priority, top = highest)
                  </span>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      padding: '4px 8px',
                      backgroundColor: 'var(--bg-input)',
                      border: '1px solid var(--border-strong)',
                      borderRadius: 4,
                      width: 220,
                    }}
                  >
                    <Search size={12} style={{ color: 'var(--text-muted)' }} />
                    <input
                      type="text"
                      placeholder="Filter channels..."
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      style={{
                        flex: 1,
                        background: 'transparent',
                        border: 'none',
                        outline: 'none',
                        color: 'var(--text-primary)',
                        fontSize: 12,
                      }}
                    />
                  </div>
                </div>

                <div
                  style={{
                    flex: 1,
                    minHeight: 0,
                    overflowY: 'auto',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 6,
                    backgroundColor: 'var(--bg-surface)',
                  }}
                >
                  {filteredSelectedMembers.length === 0 && unselectedChannels.length === 0 ? (
                    <div style={{ padding: 16, fontSize: 12, color: 'var(--text-muted)', textAlign: 'center' }}>
                      {allRawChannels.length === 0 && editMembers.length === 0
                        ? 'Load telemetry files to pick channels.'
                        : 'No channels match your filter.'}
                    </div>
                  ) : (
                    <>
                      {filteredSelectedMembers.map((chName) => {
                        const priorityIdx = editMembers.indexOf(chName) + 1;
                        const fileCount = channelSessionCounts.get(chName) ?? 0;
                        const isDragTarget = dragOverMember === chName && draggedMember !== chName;
                        const tr = selectedGroup.transforms?.[chName];
                        const factorVal = tr?.factor ?? 1;
                        const offsetVal = tr?.offset ?? 0;
                        return (
                          <div
                            key={`sel:${chName}`}
                            draggable
                            onDragStart={(e) => {
                              setDraggedMember(chName);
                              e.dataTransfer.effectAllowed = 'move';
                            }}
                            onDragOver={(e) => {
                              e.preventDefault();
                              if (draggedMember && dragOverMember !== chName) {
                                setDragOverMember(chName);
                              }
                            }}
                            onDrop={(e) => {
                              e.preventDefault();
                              if (draggedMember) {
                                reorderMember(draggedMember, chName);
                              }
                              setDraggedMember(null);
                              setDragOverMember(null);
                            }}
                            onDragEnd={() => {
                              setDraggedMember(null);
                              setDragOverMember(null);
                            }}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: 8,
                              padding: '6px 10px',
                              borderBottom: '1px solid var(--border-subtle)',
                              borderTop: isDragTarget ? '2px solid var(--accent)' : undefined,
                              fontSize: 12,
                              backgroundColor: 'var(--accent-subtle)',
                              opacity: draggedMember === chName ? 0.5 : 1,
                              cursor: 'grab',
                            }}
                          >
                            <GripVertical size={13} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
                            <span
                              className="tabular-nums"
                              style={{
                                fontSize: 10,
                                fontWeight: 600,
                                color: 'var(--accent)',
                                minWidth: 18,
                              }}
                            >
                              #{priorityIdx}
                            </span>
                            <input
                              type="checkbox"
                              checked
                              onChange={() => handleToggleMember(chName)}
                              style={{ accentColor: 'var(--accent)', cursor: 'pointer' }}
                            />
                            <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontFamily: 'monospace', fontSize: 12 }}>
                              {chName}
                            </span>
                            {!isRequiredChannelGroupId(selectedGroup.id) && (
                              <div
                                draggable={false}
                                onPointerDown={(e) => e.stopPropagation()}
                                onDragStart={(e) => e.preventDefault()}
                                style={{ display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0 }}
                              >
                                <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>×</span>
                                <input
                                  type="number"
                                  step="any"
                                  aria-label={`Factor for ${chName}`}
                                  title="Multiplier factor: (raw * factor) + offset"
                                  value={factorVal}
                                  onChange={(e) => handleTransformChange(chName, 'factor', e.target.value)}
                                  style={{
                                    ...inputStyle,
                                    width: 60,
                                    padding: '2px 5px',
                                    fontSize: 11,
                                  }}
                                />
                                <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>+</span>
                                <input
                                  type="number"
                                  step="any"
                                  aria-label={`Offset for ${chName}`}
                                  title="Offset: (raw * factor) + offset"
                                  value={offsetVal}
                                  onChange={(e) => handleTransformChange(chName, 'offset', e.target.value)}
                                  style={{
                                    ...inputStyle,
                                    width: 60,
                                    padding: '2px 5px',
                                    fontSize: 11,
                                  }}
                                />
                              </div>
                            )}
                            {fileCount > 0 && (
                              <span style={{ fontSize: 10, color: 'var(--text-muted)', flexShrink: 0 }}>
                                {fileCount} file{fileCount === 1 ? '' : 's'}
                              </span>
                            )}
                          </div>
                        );
                      })}
                      {unselectedChannels.map((ch) => {
                        const otherGroup = draftGroupForChannel.get(ch.name);
                        const inOtherGroup =
                          otherGroup && otherGroup.id !== selectedId ? otherGroup.name : null;
                        return (
                          <label
                            key={ch.name}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: 8,
                              padding: '6px 10px',
                              borderBottom: '1px solid var(--border-subtle)',
                              fontSize: 12,
                              cursor: 'pointer',
                            }}
                          >
                            <input
                              type="checkbox"
                              checked={false}
                              onChange={() => handleToggleMember(ch.name)}
                              style={{ accentColor: 'var(--accent)' }}
                            />
                            <span style={{ flex: 1, fontFamily: 'monospace', fontSize: 12 }}>
                              {ch.name}
                            </span>
                            {inOtherGroup && (
                              <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                                in {inOtherGroup}
                              </span>
                            )}
                            {ch.sessionNames.length > 0 && (
                              <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                                {ch.sessionNames.length} file{ch.sessionNames.length === 1 ? '' : 's'}
                              </span>
                            )}
                          </label>
                        );
                      })}
                    </>
                  )}
                </div>

                {errorMsg && (
                  <div style={{ color: 'var(--danger)', fontSize: 12 }}>{errorMsg}</div>
                )}
              </>
            )}
          </div>
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '10px 16px',
            borderTop: '1px solid var(--border-subtle)',
            backgroundColor: 'var(--bg-surface)',
            borderBottomLeftRadius: 8,
            borderBottomRightRadius: 8,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 8,
          }}
        >
          <button type="button" onClick={handleStartNew} style={btnStyle}>
            <Plus size={13} />
            New Group
          </button>
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" onClick={onClose} style={btnStyle}>
              Cancel
            </button>
            <button type="submit" style={primaryBtnStyle}>
              <Check size={14} />
              <span>Save</span>
            </button>
          </div>
        </div>
      </form>
    </div>
  );
};

// ---------------------------------------------------------------------------
// 2. RememberedImportsModal
// ---------------------------------------------------------------------------

export interface RememberedImportsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const RememberedImportsModal: React.FC<RememberedImportsModalProps> = ({
  isOpen,
  onClose,
}) => {
  const [draftImports, setDraftImports] = useState<Record<string, FileImportConfig>>({});
  const [selectedSig, setSelectedSig] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    const all = stateManager.getAllFileImports();
    setDraftImports(all);
    const keys = Object.keys(all);
    setSelectedSig(keys.length > 0 ? keys[0] : null);
  }, [isOpen]);

  if (!isOpen) return null;

  const entries = Object.entries(draftImports);
  const selected = selectedSig ? draftImports[selectedSig] : null;

  const handleDelete = (sig: string) => {
    setDraftImports((prev) => {
      const next = { ...prev };
      delete next[sig];
      if (selectedSig === sig) {
        const remaining = Object.keys(next);
        setSelectedSig(remaining[0] ?? null);
      }
      return next;
    });
  };

  const handleClearAll = () => {
    setDraftImports({});
    setSelectedSig(null);
  };

  const handleSave = async () => {
    await stateManager.replaceAllFileImports(draftImports);
    onClose();
  };

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={modalStyle} onClick={(e) => e.stopPropagation()}>
        <div style={headerStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, color: 'var(--text-strong)' }}>
            <Database size={16} style={{ color: 'var(--accent)' }} />
            <span>Remembered File Imports</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
          >
            <X size={18} />
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', flex: 1, minHeight: 340, overflow: 'hidden' }}>
          <div style={{ borderRight: '1px solid var(--border-subtle)', overflowY: 'auto', padding: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
            {entries.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', fontSize: 13, padding: 16, textAlign: 'center' }}>
                No remembered file imports.
              </div>
            ) : (
              entries.map(([sig, cfg]) => {
                const isSelected = sig === selectedSig;
                const displayName = sig.split('::')[0] || sig;
                return (
                  <div
                    key={sig}
                    onClick={() => setSelectedSig(sig)}
                    style={{
                      padding: '8px 10px',
                      borderRadius: 6,
                      cursor: 'pointer',
                      backgroundColor: isSelected ? 'var(--accent-subtle)' : 'var(--bg-surface)',
                      border: `1px solid ${isSelected ? 'var(--accent-border)' : 'var(--border-subtle)'}`,
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
                      <span style={{ fontWeight: 600, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={sig}>
                        {displayName}
                      </span>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDelete(sig);
                        }}
                        style={{ ...dangerBtnStyle, padding: '3px 6px' }}
                        title="Delete"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                      {cfg.sheet_name ? `Sheet: ${cfg.sheet_name} · ` : ''}
                      Lap: {cfg.lap_col}
                    </div>
                  </div>
                );
              })
            )}
          </div>

          <div style={{ overflowY: 'auto', padding: 16 }}>
            {!selected || !selectedSig ? (
              <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', paddingTop: 40 }}>
                Select a remembered import to inspect.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, fontSize: 12 }}>
                <div style={{ color: 'var(--text-muted)', wordBreak: 'break-all' }}>
                  Signature: <code style={{ color: 'var(--text-primary)' }}>{selectedSig}</code>
                </div>
                {selected.sheet_name && (
                  <div>
                    Worksheet: <strong>{selected.sheet_name}</strong>
                  </div>
                )}
                <div>
                  Lap Number: <code>{selected.lap_col}</code>
                </div>
                <div>
                  Lap Time: <code>{selected.time_col ?? '—'}</code>
                </div>
                <div>
                  Lap Distance: <code>{selected.dist_col ?? '—'}</code>
                </div>
                {selected.group_overrides && Object.keys(selected.group_overrides).length > 0 && (
                  <div>
                    Group Overrides:{' '}
                    <code>
                      {Object.entries(selected.group_overrides)
                        .map(([gid, ov]) => `${stateManager.getDisplayNameByKey(gid)} -> ${ov.channel} (×${ov.factor} + ${ov.offset})`)
                        .join('; ')}
                    </code>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '10px 16px',
            borderTop: '1px solid var(--border-subtle)',
            backgroundColor: 'var(--bg-surface)',
            borderBottomLeftRadius: 8,
            borderBottomRightRadius: 8,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 8,
          }}
        >
          <div>
            {entries.length > 0 && (
              <button type="button" onClick={handleClearAll} style={dangerBtnStyle}>
                <Trash2 size={12} />
                Clear All
              </button>
            )}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" onClick={onClose} style={btnStyle}>
              Cancel
            </button>
            <button type="button" onClick={() => void handleSave()} style={primaryBtnStyle}>
              <Check size={14} />
              <span>Save</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// 3. TrackMapManagerModal
// ---------------------------------------------------------------------------

export interface TrackMapManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onMapsUpdated?: () => void;
}

interface PendingMapImport {
  mapToken: string;
  fileName: string;
  columns: string[];
  xCol: string;
  yCol: string;
  distCol: string;
  name: string;
  color: string;
}

export const TrackMapManagerModal: React.FC<TrackMapManagerModalProps> = ({
  isOpen,
  onClose,
  onMapsUpdated,
}) => {
  const [draftMaps, setDraftMaps] = useState<TrackMapDef[]>([]);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [pendingImport, setPendingImport] = useState<PendingMapImport | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const jsonInputRef = useRef<HTMLInputElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (isOpen) {
      setErrorMsg(null);
      const loaded = stateManager.loadMaps();
      setDraftMaps(loaded);
      setSelectedSlug(loaded[0]?.slug ?? null);
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen && pendingImport) {
      void telemetryClient.discardMapToken(pendingImport.mapToken);
      setPendingImport(null);
    }
  }, [isOpen, pendingImport]);

  const selectedMap = useMemo(
    () => draftMaps.find((m) => m.slug === selectedSlug) ?? null,
    [draftMaps, selectedSlug],
  );

  if (!isOpen) return null;

  const updateSelectedMap = (updater: (m: TrackMapDef) => TrackMapDef) => {
    if (!selectedSlug) return;
    setDraftMaps((prev) =>
      prev.map((m) => (m.slug === selectedSlug ? updater(m) : m)),
    );
  };

  const handleDeleteMap = (slug: string) => {
    setDraftMaps((prev) => {
      const next = prev.filter((m) => m.slug !== slug);
      if (selectedSlug === slug) {
        setSelectedSlug(next[0]?.slug ?? null);
      }
      return next;
    });
  };

  const handleExportJson = (map: TrackMapDef) => {
    const json = JSON.stringify({ schema_version: 1, data: map }, null, 4);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${map.slug}.trackmap.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImportJsonFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    try {
      setErrorMsg(null);
      const text = await file.text();
      const imported = stateManager.parseTrackMapJson(text);
      setDraftMaps((prev) => {
        const idx = prev.findIndex((m) => m.slug === imported.slug);
        const next = idx >= 0 ? prev.map((m, i) => (i === idx ? imported : m)) : [...prev, imported];
        return next.sort((a, b) => a.name.localeCompare(b.name));
      });
      setSelectedSlug(imported.slug);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to import Track Map JSON');
    }
  };

  const handleSelectRawMapFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    try {
      setErrorMsg(null);
      setIsBusy(true);
      const { mapToken, columns } = await telemetryClient.parseTrackMapColumns(file);
      const baseName = file.name.replace(/\.[^.]+$/, '');
      setPendingImport({
        mapToken,
        fileName: file.name,
        columns,
        xCol: columns[0] ?? '',
        yCol: columns[1] ?? columns[0] ?? '',
        distCol: '',
        name: baseName,
        color: LAP_COLORS[draftMaps.length % LAP_COLORS.length],
      });
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to parse map file columns');
    } finally {
      setIsBusy(false);
    }
  };

  const handleCancelImport = async () => {
    if (pendingImport) {
      await telemetryClient.discardMapToken(pendingImport.mapToken);
      setPendingImport(null);
    }
  };

  const handleConfirmImport = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pendingImport) return;
    try {
      setErrorMsg(null);
      setIsBusy(true);
      const data = await telemetryClient.loadTrackMapData(
        pendingImport.mapToken,
        pendingImport.fileName,
        pendingImport.xCol,
        pendingImport.yCol,
        pendingImport.distCol || null,
      );
      const slug = generateUniqueSlug(pendingImport.name, draftMaps.map((m) => m.slug));
      const newMap: TrackMapDef = {
        name: pendingImport.name.trim() || slug,
        slug,
        rotation: 0,
        color: pendingImport.color,
        x: data.x,
        y: data.y,
        distance: data.distance,
      };
      setDraftMaps((prev) => [...prev, newMap].sort((a, b) => a.name.localeCompare(b.name)));
      setPendingImport(null);
      setSelectedSlug(newMap.slug);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to load track map data');
    } finally {
      setIsBusy(false);
    }
  };

  const handleSaveAll = async () => {
    const cleaned = draftMaps.map((m) => ({
      ...m,
      name: m.name.trim() || m.slug,
      rotation: Number.isFinite(m.rotation) ? m.rotation : 0,
    }));
    await stateManager.replaceAllMaps(cleaned);
    onMapsUpdated?.();
    onClose();
  };

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={modalStyle} onClick={(e) => e.stopPropagation()}>
        <div style={headerStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, color: 'var(--text-strong)' }}>
            <MapIcon size={16} style={{ color: 'var(--accent)' }} />
            <span>Track Map Manager</span>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>
            <X size={18} />
          </button>
        </div>
        <input ref={jsonInputRef} type="file" accept=".json,application/json" onChange={handleImportJsonFile} style={{ display: 'none' }} />
        <input ref={fileInputRef} type="file" accept=".csv,.xlsx,.xls" onChange={handleSelectRawMapFile} style={{ display: 'none' }} />

        {errorMsg && (
          <div style={{ padding: '8px 16px', backgroundColor: 'var(--danger-bg)', color: 'var(--danger)', fontSize: 12, borderBottom: '1px solid var(--border-subtle)' }}>
            {errorMsg}
          </div>
        )}

        {pendingImport ? (
          <form onSubmit={handleConfirmImport} style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto' }}>
            <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-strong)' }}>
              Configure Track Map Import: {pendingImport.fileName}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
                Map Name
                <input
                  type="text"
                  value={pendingImport.name}
                  onChange={(e) => setPendingImport({ ...pendingImport, name: e.target.value })}
                  style={inputStyle}
                  required
                />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
                X Coordinate Column
                <select
                  value={pendingImport.xCol}
                  onChange={(e) => setPendingImport({ ...pendingImport, xCol: e.target.value })}
                  style={inputStyle}
                >
                  {pendingImport.columns.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
                Y Coordinate Column
                <select
                  value={pendingImport.yCol}
                  onChange={(e) => setPendingImport({ ...pendingImport, yCol: e.target.value })}
                  style={inputStyle}
                >
                  {pendingImport.columns.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
                Distance Column (optional)
                <select
                  value={pendingImport.distCol}
                  onChange={(e) => setPendingImport({ ...pendingImport, distCol: e.target.value })}
                  style={inputStyle}
                >
                  <option value="">None</option>
                  {pendingImport.columns.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </label>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12 }}>
              <span>Color</span>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {LAP_COLORS.map((c) => (
                  <button
                    key={c}
                    type="button"
                    onClick={() => setPendingImport({ ...pendingImport, color: c })}
                    style={{
                      width: 22,
                      height: 22,
                      borderRadius: '50%',
                      backgroundColor: c,
                      border: pendingImport.color === c ? '2px solid #FFFFFF' : '1px solid var(--border-strong)',
                      cursor: 'pointer',
                    }}
                  />
                ))}
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
              <button type="button" onClick={() => void handleCancelImport()} style={btnStyle} disabled={isBusy}>
                Back
              </button>
              <button type="submit" style={primaryBtnStyle} disabled={isBusy}>
                {isBusy ? 'Importing...' : 'Add to Draft'}
              </button>
            </div>
          </form>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', flex: 1, minHeight: 360, overflow: 'hidden' }}>
            <div style={{ borderRight: '1px solid var(--border-subtle)', overflowY: 'auto', padding: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
              {draftMaps.length === 0 ? (
                <div style={{ color: 'var(--text-muted)', fontSize: 13, padding: 16, textAlign: 'center' }}>
                  No saved track maps.
                </div>
              ) : (
                draftMaps.map((m) => {
                  const isSelected = m.slug === selectedSlug;
                  return (
                    <div
                      key={m.slug}
                      onClick={() => setSelectedSlug(m.slug)}
                      style={{
                        padding: '8px 10px',
                        borderRadius: 6,
                        cursor: 'pointer',
                        backgroundColor: isSelected ? 'var(--accent-subtle)' : 'var(--bg-surface)',
                        border: `1px solid ${isSelected ? 'var(--accent-border)' : 'var(--border-subtle)'}`,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: 8,
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                        <span style={{ width: 10, height: 10, borderRadius: '50%', backgroundColor: m.color, flexShrink: 0 }} />
                        <span style={{ fontWeight: 600, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {m.name}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteMap(m.slug);
                        }}
                        style={{ ...dangerBtnStyle, padding: '3px 6px' }}
                        title="Delete"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  );
                })
              )}
            </div>

            <div style={{ overflowY: 'auto', padding: 16 }}>
              {!selectedMap ? (
                <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', paddingTop: 40 }}>
                  Select a track map to edit or export.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 120px', gap: 12 }}>
                    <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
                      Map Name
                      <input
                        type="text"
                        value={selectedMap.name}
                        onChange={(e) => updateSelectedMap((m) => ({ ...m, name: e.target.value }))}
                        style={inputStyle}
                      />
                    </label>
                    <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
                      Rotation (deg)
                      <input
                        type="number"
                        step="1"
                        value={selectedMap.rotation}
                        onChange={(e) => updateSelectedMap((m) => ({ ...m, rotation: Number(e.target.value) }))}
                        style={inputStyle}
                      />
                    </label>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12 }}>
                    <span>Color</span>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                      {LAP_COLORS.map((c) => (
                        <button
                          key={c}
                          type="button"
                          onClick={() => updateSelectedMap((m) => ({ ...m, color: c }))}
                          style={{
                            width: 22,
                            height: 22,
                            borderRadius: '50%',
                            backgroundColor: c,
                            border: selectedMap.color === c ? '2px solid #FFFFFF' : '1px solid var(--border-strong)',
                            cursor: 'pointer',
                          }}
                        />
                      ))}
                    </div>
                  </div>

                  <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                    Points: <strong style={{ color: 'var(--text-primary)' }}>{selectedMap.x.length}</strong> · Distance data:{' '}
                    <strong style={{ color: 'var(--text-primary)' }}>{selectedMap.distance ? 'Yes' : 'No'}</strong>
                  </div>

                  <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                    <button type="button" onClick={() => handleExportJson(selectedMap)} style={btnStyle}>
                      <Download size={13} />
                      Export JSON
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Footer */}
        <div
          style={{
            padding: '10px 16px',
            borderTop: '1px solid var(--border-subtle)',
            backgroundColor: 'var(--bg-surface)',
            borderBottomLeftRadius: 8,
            borderBottomRightRadius: 8,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 8,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <button type="button" onClick={() => jsonInputRef.current?.click()} style={btnStyle} disabled={isBusy}>
              <Upload size={13} />
              Import JSON
            </button>
            <button type="button" onClick={() => fileInputRef.current?.click()} style={btnStyle} disabled={isBusy}>
              <FileSpreadsheet size={13} />
              Import CSV / Excel
            </button>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" onClick={onClose} style={btnStyle}>
              Cancel
            </button>
            <button type="button" onClick={() => void handleSaveAll()} style={primaryBtnStyle} disabled={isBusy}>
              <Check size={14} />
              <span>Save</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// 4. WelcomeStartupModal
// ---------------------------------------------------------------------------

export interface WelcomeStartupModalProps {
  isOpen: boolean;
  recentFiles: RecentFileEntry[];
  onOpenFiles: () => void;
  onOpenRecentFile: (entry: RecentFileEntry) => void;
  onClose: () => void;
}

export const WelcomeStartupModal: React.FC<WelcomeStartupModalProps> = ({
  isOpen,
  recentFiles,
  onOpenFiles,
  onOpenRecentFile,
  onClose,
}) => {
  if (!isOpen) return null;

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div
        style={{
          ...modalStyle,
          maxWidth: 520,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={headerStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, color: 'var(--text-strong)' }}>
            <FolderOpen size={16} style={{ color: 'var(--accent)' }} />
            <span>Open Telemetry</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
          >
            <X size={18} />
          </button>
        </div>

        <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12, flex: 1, minHeight: 0, overflowY: 'auto' }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
            <Clock size={13} />
            <span>Recently Used Files</span>
          </div>

          <div
            style={{
              border: '1px solid var(--border-subtle)',
              borderRadius: 6,
              backgroundColor: 'var(--bg-surface)',
              maxHeight: 260,
              overflowY: 'auto',
            }}
          >
            {recentFiles.length === 0 ? (
              <div style={{ padding: 20, fontSize: 12, color: 'var(--text-muted)', textAlign: 'center' }}>
                No recently opened files.
              </div>
            ) : (
              recentFiles.map((entry) => (
                <button
                  key={entry.id}
                  type="button"
                  onClick={() => {
                    onClose();
                    onOpenRecentFile(entry);
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: 10,
                    width: '100%',
                    padding: '9px 12px',
                    border: 'none',
                    borderBottom: '1px solid var(--border-subtle)',
                    background: 'transparent',
                    color: 'var(--text-primary)',
                    fontSize: 12,
                    textAlign: 'left',
                    cursor: 'pointer',
                  }}
                >
                  <span style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {entry.name}
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)', flexShrink: 0 }}>
                    {new Date(entry.lastOpenedAt).toLocaleDateString()}
                  </span>
                </button>
              ))
            )}
          </div>
        </div>

        <div
          style={{
            padding: '10px 16px',
            borderTop: '1px solid var(--border-subtle)',
            backgroundColor: 'var(--bg-surface)',
            borderBottomLeftRadius: 8,
            borderBottomRightRadius: 8,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 8,
          }}
        >
          <button
            type="button"
            onClick={() => {
              onClose();
              onOpenFiles();
            }}
            style={primaryBtnStyle}
          >
            <FolderOpen size={14} />
            <span>Import File...</span>
          </button>
          <button type="button" onClick={onClose} style={btnStyle}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

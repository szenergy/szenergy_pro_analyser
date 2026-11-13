import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Check,
  Database,
  Download,
  Edit2,
  FileSpreadsheet,
  Layers,
  Map as MapIcon,
  Plus,
  Sliders,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import {
  generateUniqueSlug,
  stateManager,
} from '@/state/stateManager';
import {
  ChannelDef,
  FileMappingConfig,
  LAP_COLORS,
  PresetDef,
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
  maxWidth: 820,
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
// 1. PresetManagerModal
// ---------------------------------------------------------------------------

export interface PresetManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onPresetsChanged?: () => void;
}

export const PresetManagerModal: React.FC<PresetManagerModalProps> = ({
  isOpen,
  onClose,
  onPresetsChanged,
}) => {
  const [presets, setPresets] = useState<PresetDef[]>([]);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [renamingSlug, setRenamingSlug] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState('');

  const reload = useCallback(() => {
    const list = stateManager.loadPresets();
    setPresets(list);
    if (list.length > 0 && !list.some((p) => p.slug === selectedSlug)) {
      setSelectedSlug(list[0].slug);
    } else if (list.length === 0) {
      setSelectedSlug(null);
    }
  }, [selectedSlug]);

  useEffect(() => {
    if (isOpen) {
      reload();
      setRenamingSlug(null);
    }
  }, [isOpen, reload]);

  if (!isOpen) return null;

  const selected = presets.find((p) => p.slug === selectedSlug) ?? null;

  const handleStartRename = (preset: PresetDef) => {
    setRenamingSlug(preset.slug);
    setRenameValue(preset.name);
  };

  const handleConfirmRename = async (preset: PresetDef) => {
    const trimmed = renameValue.trim();
    if (trimmed && trimmed !== preset.name) {
      await stateManager.savePreset(trimmed, preset.mapping, {
        slug: preset.slug,
        localCalculatedChannels: preset.local_calculated_channels,
        gapTimeThreshold: preset.gap_time_threshold,
        gapDistThreshold: preset.gap_dist_threshold,
      });
      onPresetsChanged?.();
      reload();
    }
    setRenamingSlug(null);
  };

  const handleDelete = (slug: string) => {
    stateManager.deletePreset(slug);
    onPresetsChanged?.();
    reload();
  };

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={modalStyle} onClick={(e) => e.stopPropagation()}>
        <div style={headerStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, color: 'var(--text-strong)' }}>
            <Sliders size={16} style={{ color: 'var(--accent)' }} />
            <span>Preset Manager</span>
          </div>
          <button type="button" onClick={onClose} style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>
            <X size={18} />
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', flex: 1, minHeight: 360, overflow: 'hidden' }}>
          <div style={{ borderRight: '1px solid var(--border-subtle)', overflowY: 'auto', padding: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
            {presets.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', fontSize: 13, padding: 16, textAlign: 'center' }}>
                No saved presets.
              </div>
            ) : (
              presets.map((p) => {
                const isSelected = p.slug === selectedSlug;
                return (
                  <div
                    key={p.slug}
                    onClick={() => setSelectedSlug(p.slug)}
                    style={{
                      padding: '8px 10px',
                      borderRadius: 6,
                      cursor: 'pointer',
                      backgroundColor: isSelected ? 'var(--accent-subtle)' : 'var(--bg-surface)',
                      border: `1px solid ${isSelected ? 'var(--accent-border)' : 'var(--border-subtle)'}`,
                    }}
                  >
                    {renamingSlug === p.slug ? (
                      <div style={{ display: 'flex', gap: 4 }} onClick={(e) => e.stopPropagation()}>
                        <input
                          type="text"
                          value={renameValue}
                          onChange={(e) => setRenameValue(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') handleConfirmRename(p);
                            if (e.key === 'Escape') setRenamingSlug(null);
                          }}
                          style={{ ...inputStyle, padding: '3px 6px', fontSize: 12 }}
                          autoFocus
                        />
                        <button type="button" onClick={() => handleConfirmRename(p)} style={{ ...primaryBtnStyle, padding: '3px 6px' }}>
                          <Check size={12} />
                        </button>
                      </div>
                    ) : (
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
                        <span style={{ fontWeight: 600, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {p.name}
                        </span>
                        <div style={{ display: 'flex', gap: 4 }} onClick={(e) => e.stopPropagation()}>
                          <button type="button" onClick={() => handleStartRename(p)} title="Rename" style={{ ...btnStyle, padding: '3px 6px' }}>
                            <Edit2 size={12} />
                          </button>
                          <button type="button" onClick={() => handleDelete(p.slug)} title="Delete" style={{ ...dangerBtnStyle, padding: '3px 6px' }}>
                            <Trash2 size={12} />
                          </button>
                        </div>
                      </div>
                    )}
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                      {Object.keys(p.mapping).length} channels · {p.local_calculated_channels.length} local calcs
                    </div>
                  </div>
                );
              })
            )}
          </div>

          <div style={{ overflowY: 'auto', padding: 16 }}>
            {!selected ? (
              <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', paddingTop: 40 }}>
                Select a preset to inspect its mapping.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, fontSize: 12, color: 'var(--text-muted)' }}>
                  <span>Slug: <strong style={{ color: 'var(--text-primary)' }}>{selected.slug}</strong></span>
                  <span>Gap Time: <strong style={{ color: 'var(--text-primary)' }}>{selected.gap_time_threshold ?? 'default'} s</strong></span>
                  <span>Gap Dist: <strong style={{ color: 'var(--text-primary)' }}>{selected.gap_dist_threshold ?? 'default'} m</strong></span>
                </div>

                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--text-strong)' }}>
                    Column Mapping ({Object.keys(selected.mapping).length})
                  </div>
                  <div style={{ border: '1px solid var(--border-subtle)', borderRadius: 6, overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                      <thead>
                        <tr style={{ backgroundColor: 'var(--bg-surface)', textAlign: 'left', color: 'var(--text-muted)' }}>
                          <th style={{ padding: '6px 10px', borderBottom: '1px solid var(--border-subtle)' }}>Raw Column</th>
                          <th style={{ padding: '6px 10px', borderBottom: '1px solid var(--border-subtle)' }}>Target Channel</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(selected.mapping).map(([rawCol, targetSlug]) => (
                          <tr key={rawCol} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                            <td style={{ padding: '6px 10px', fontFamily: 'monospace' }}>{rawCol}</td>
                            <td style={{ padding: '6px 10px' }}>
                              {stateManager.getDisplayNameBySlug(targetSlug)} <span style={{ color: 'var(--text-muted)' }}>({targetSlug})</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {selected.local_calculated_channels.length > 0 && (
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: 'var(--text-strong)' }}>
                      Local Calculated Channels ({selected.local_calculated_channels.length})
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {selected.local_calculated_channels.map((lc) => (
                        <div key={lc.target_slug} style={{ padding: '6px 10px', backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', borderRadius: 4, fontSize: 12 }}>
                          <strong>{lc.name}</strong> → <code>{lc.formula}</code>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// 2. ChannelManagerModal
// ---------------------------------------------------------------------------

export interface ChannelManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onChannelsUpdated: () => void;
  onOpenGlobalCalc?: (editing?: ChannelDef) => void;
}

export const ChannelManagerModal: React.FC<ChannelManagerModalProps> = ({
  isOpen,
  onClose,
  onChannelsUpdated,
  onOpenGlobalCalc,
}) => {
  const [channels, setChannels] = useState<ChannelDef[]>([]);
  const [newLabel, setNewLabel] = useState('');
  const [newUnit, setNewUnit] = useState('');
  const [editingSlug, setEditingSlug] = useState<string | null>(null);
  const [editLabel, setEditLabel] = useState('');
  const [editUnit, setEditUnit] = useState('');

  const reload = useCallback(() => {
    setChannels(stateManager.getChannelDefs());
  }, []);

  useEffect(() => {
    if (isOpen) {
      reload();
      setEditingSlug(null);
      setNewLabel('');
      setNewUnit('');
    }
  }, [isOpen, reload]);

  if (!isOpen) return null;

  const handleAddCustom = (e: React.FormEvent) => {
    e.preventDefault();
    const label = newLabel.trim();
    if (!label) return;
    const existingSlugs = channels.map((c) => c.slug);
    const slug = generateUniqueSlug(label, existingSlugs);
    const updated: ChannelDef[] = [
      ...channels,
      { label, slug, type: 'custom', unit: newUnit.trim() },
    ];
    stateManager.saveChannelDefs(updated);
    setNewLabel('');
    setNewUnit('');
    reload();
    onChannelsUpdated();
  };

  const handleStartEdit = (ch: ChannelDef) => {
    setEditingSlug(ch.slug);
    setEditLabel(ch.label);
    setEditUnit(ch.unit);
  };

  const handleSaveEdit = (ch: ChannelDef) => {
    const label = editLabel.trim();
    if (!label) return;
    const updated = channels.map((c) =>
      c.slug === ch.slug ? { ...c, label, unit: editUnit.trim() } : c,
    );
    stateManager.saveChannelDefs(updated);
    setEditingSlug(null);
    reload();
    onChannelsUpdated();
  };

  const handleDelete = (slug: string) => {
    const updated = channels.filter((c) => c.slug !== slug || c.type === 'system');
    stateManager.saveChannelDefs(updated);
    reload();
    onChannelsUpdated();
  };

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={modalStyle} onClick={(e) => e.stopPropagation()}>
        <div style={headerStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, color: 'var(--text-strong)' }}>
            <Layers size={16} style={{ color: 'var(--accent)' }} />
            <span>Channel Manager</span>
          </div>
          <button type="button" onClick={onClose} style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>
            <X size={18} />
          </button>
        </div>

        <div style={{ padding: 16, borderBottom: '1px solid var(--border-subtle)', display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', justifyContent: 'space-between' }}>
          <form onSubmit={handleAddCustom} style={{ display: 'flex', gap: 8, alignItems: 'center', flex: 1, minWidth: 320 }}>
            <input
              type="text"
              placeholder="New custom channel label..."
              value={newLabel}
              onChange={(e) => setNewLabel(e.target.value)}
              style={{ ...inputStyle, flex: 2 }}
            />
            <input
              type="text"
              placeholder="Unit (e.g. km/h)"
              value={newUnit}
              onChange={(e) => setNewUnit(e.target.value)}
              style={{ ...inputStyle, flex: 1, maxWidth: 130 }}
            />
            <button type="submit" style={primaryBtnStyle}>
              <Plus size={14} />
              Add Custom
            </button>
          </form>

          {onOpenGlobalCalc && (
            <button type="button" onClick={() => onOpenGlobalCalc(undefined)} style={btnStyle}>
              <Plus size={14} />
              New Calculated Channel
            </button>
          )}
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: 16 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ textAlign: 'left', color: 'var(--text-muted)', borderBottom: '1px solid var(--border-subtle)' }}>
                <th style={{ padding: '6px 8px' }}>Label</th>
                <th style={{ padding: '6px 8px' }}>Unit</th>
                <th style={{ padding: '6px 8px' }}>Slug</th>
                <th style={{ padding: '6px 8px' }}>Type</th>
                <th style={{ padding: '6px 8px', textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {channels.map((ch) => {
                const isEditing = editingSlug === ch.slug;
                return (
                  <tr key={ch.slug} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                    <td style={{ padding: '8px' }}>
                      {isEditing ? (
                        <input
                          type="text"
                          value={editLabel}
                          onChange={(e) => setEditLabel(e.target.value)}
                          style={inputStyle}
                        />
                      ) : (
                        <span style={{ fontWeight: 500 }}>{ch.label}</span>
                      )}
                    </td>
                    <td style={{ padding: '8px', width: 110 }}>
                      {isEditing ? (
                        <input
                          type="text"
                          value={editUnit}
                          onChange={(e) => setEditUnit(e.target.value)}
                          style={inputStyle}
                        />
                      ) : (
                        <span style={{ color: 'var(--text-muted)' }}>{ch.unit || '—'}</span>
                      )}
                    </td>
                    <td style={{ padding: '8px', fontFamily: 'monospace', fontSize: 12, color: 'var(--text-muted)' }}>
                      {ch.slug}
                    </td>
                    <td style={{ padding: '8px' }}>
                      <span
                        style={{
                          fontSize: 11,
                          padding: '2px 6px',
                          borderRadius: 4,
                          backgroundColor: 'var(--badge-bg)',
                          color: ch.type === 'system' ? 'var(--info)' : ch.type === 'calculated' ? 'var(--warning)' : 'var(--accent)',
                        }}
                      >
                        {ch.type}
                      </span>
                    </td>
                    <td style={{ padding: '8px', textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', gap: 4 }}>
                        {isEditing ? (
                          <>
                            <button type="button" onClick={() => handleSaveEdit(ch)} style={primaryBtnStyle}>
                              <Check size={12} />
                            </button>
                            <button type="button" onClick={() => setEditingSlug(null)} style={btnStyle}>
                              <X size={12} />
                            </button>
                          </>
                        ) : (
                          <>
                            {ch.type === 'calculated' && onOpenGlobalCalc && (
                              <button
                                type="button"
                                onClick={() => onOpenGlobalCalc(ch)}
                                title="Edit Formula"
                                style={btnStyle}
                              >
                                Formula
                              </button>
                            )}
                            <button type="button" onClick={() => handleStartEdit(ch)} title="Edit Label/Unit" style={btnStyle}>
                              <Edit2 size={12} />
                            </button>
                            {ch.type !== 'system' && (
                              <button type="button" onClick={() => handleDelete(ch.slug)} title="Delete" style={dangerBtnStyle}>
                                <Trash2 size={12} />
                              </button>
                            )}
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// 3. FileMappingManagerModal
// ---------------------------------------------------------------------------

export interface FileMappingManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const FileMappingManagerModal: React.FC<FileMappingManagerModalProps> = ({
  isOpen,
  onClose,
}) => {
  const [mappings, setMappings] = useState<Record<string, FileMappingConfig>>({});
  const [selectedSig, setSelectedSig] = useState<string | null>(null);

  const reload = useCallback(() => {
    const all = stateManager.getAllFileMappings();
    setMappings(all);
    const keys = Object.keys(all);
    if (keys.length > 0 && (!selectedSig || !all[selectedSig])) {
      setSelectedSig(keys[0]);
    } else if (keys.length === 0) {
      setSelectedSig(null);
    }
  }, [selectedSig]);

  useEffect(() => {
    if (isOpen) {
      reload();
    }
  }, [isOpen, reload]);

  if (!isOpen) return null;

  const entries = Object.entries(mappings);
  const selected = selectedSig ? mappings[selectedSig] : null;

  const handleDelete = (sig: string) => {
    stateManager.removeFileMappingConfig(sig);
    reload();
  };

  const handleClearAll = () => {
    stateManager.clearFileMappings();
    reload();
  };

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={modalStyle} onClick={(e) => e.stopPropagation()}>
        <div style={headerStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, color: 'var(--text-strong)' }}>
            <Database size={16} style={{ color: 'var(--accent)' }} />
            <span>Remembered File Mappings</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {entries.length > 0 && (
              <button type="button" onClick={handleClearAll} style={dangerBtnStyle}>
                <Trash2 size={12} />
                Clear All
              </button>
            )}
            <button type="button" onClick={onClose} style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>
              <X size={18} />
            </button>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', flex: 1, minHeight: 360, overflow: 'hidden' }}>
          <div style={{ borderRight: '1px solid var(--border-subtle)', overflowY: 'auto', padding: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
            {entries.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', fontSize: 13, padding: 16, textAlign: 'center' }}>
                No remembered file mappings.
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
                      Preset: {cfg.preset_slug ?? 'none'} · {Object.keys(cfg.mapping).length} mapped · {cfg.local_calculated_channels.length} calcs
                    </div>
                  </div>
                );
              })
            )}
          </div>

          <div style={{ overflowY: 'auto', padding: 16 }}>
            {!selected || !selectedSig ? (
              <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', paddingTop: 40 }}>
                Select a file mapping entry to inspect.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', wordBreak: 'break-all' }}>
                  Signature: <code style={{ color: 'var(--text-primary)' }}>{selectedSig}</code>
                </div>
                <div style={{ border: '1px solid var(--border-subtle)', borderRadius: 6, overflow: 'hidden' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                    <thead>
                      <tr style={{ backgroundColor: 'var(--bg-surface)', textAlign: 'left', color: 'var(--text-muted)' }}>
                        <th style={{ padding: '6px 10px', borderBottom: '1px solid var(--border-subtle)' }}>Raw Column</th>
                        <th style={{ padding: '6px 10px', borderBottom: '1px solid var(--border-subtle)' }}>Target Channel</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(selected.mapping).map(([rawCol, targetSlug]) => (
                        <tr key={rawCol} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                          <td style={{ padding: '6px 10px', fontFamily: 'monospace' }}>{rawCol}</td>
                          <td style={{ padding: '6px 10px' }}>{stateManager.getDisplayNameBySlug(targetSlug)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// 4. TrackMapManagerModal
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
  const [maps, setMaps] = useState<TrackMapDef[]>([]);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editColor, setEditColor] = useState<string>(LAP_COLORS[0]);
  const [editRotation, setEditRotation] = useState<number>(0);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [pendingImport, setPendingImport] = useState<PendingMapImport | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const jsonInputRef = useRef<HTMLInputElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const reload = useCallback(async () => {
    const loaded = await stateManager.loadMaps();
    setMaps(loaded);
    if (loaded.length > 0 && !loaded.some((m) => m.slug === selectedSlug)) {
      setSelectedSlug(loaded[0].slug);
    } else if (loaded.length === 0) {
      setSelectedSlug(null);
    }
  }, [selectedSlug]);

  useEffect(() => {
    if (isOpen) {
      setErrorMsg(null);
      void reload();
    } else if (pendingImport) {
      void telemetryClient.discardMapToken(pendingImport.mapToken);
      setPendingImport(null);
    }
  }, [isOpen, reload, pendingImport]);

  const selectedMap = maps.find((m) => m.slug === selectedSlug) ?? null;

  useEffect(() => {
    if (selectedMap) {
      setEditName(selectedMap.name);
      setEditColor(selectedMap.color);
      setEditRotation(selectedMap.rotation);
    }
  }, [selectedMap]);

  if (!isOpen) return null;

  const handleSaveMapEdits = async () => {
    if (!selectedMap) return;
    const trimmed = editName.trim() || selectedMap.name;
    await stateManager.saveMap({
      ...selectedMap,
      name: trimmed,
      color: editColor,
      rotation: Number.isFinite(editRotation) ? editRotation : 0,
    });
    await reload();
    onMapsUpdated?.();
  };

  const handleDeleteMap = async (slug: string) => {
    await stateManager.deleteMap(slug);
    await reload();
    onMapsUpdated?.();
  };

  const handleExportJson = (map: TrackMapDef) => {
    const json = stateManager.exportTrackMapJson(map.slug);
    if (!json) return;
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
      const imported = await stateManager.importTrackMapJson(text);
      await reload();
      setSelectedSlug(imported.slug);
      onMapsUpdated?.();
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
        color: LAP_COLORS[maps.length % LAP_COLORS.length],
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
      const slug = generateUniqueSlug(pendingImport.name, maps.map((m) => m.slug));
      const newMap: TrackMapDef = {
        name: pendingImport.name.trim() || slug,
        slug,
        rotation: 0,
        color: pendingImport.color,
        x: data.x,
        y: data.y,
        distance: data.distance,
      };
      await stateManager.saveMap(newMap);
      setPendingImport(null);
      await reload();
      setSelectedSlug(newMap.slug);
      onMapsUpdated?.();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to load track map data');
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={modalStyle} onClick={(e) => e.stopPropagation()}>
        <div style={headerStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, color: 'var(--text-strong)' }}>
            <MapIcon size={16} style={{ color: 'var(--accent)' }} />
            <span>Track Map Manager</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input ref={jsonInputRef} type="file" accept=".json,application/json" onChange={handleImportJsonFile} style={{ display: 'none' }} />
            <input ref={fileInputRef} type="file" accept=".csv,.xlsx,.xls" onChange={handleSelectRawMapFile} style={{ display: 'none' }} />
            <button type="button" onClick={() => jsonInputRef.current?.click()} style={btnStyle} disabled={isBusy}>
              <Upload size={13} />
              Import JSON
            </button>
            <button type="button" onClick={() => fileInputRef.current?.click()} style={primaryBtnStyle} disabled={isBusy}>
              <FileSpreadsheet size={13} />
              Import CSV / Excel
            </button>
            <button type="button" onClick={onClose} style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>
              <X size={18} />
            </button>
          </div>
        </div>

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
                Cancel
              </button>
              <button type="submit" style={primaryBtnStyle} disabled={isBusy}>
                {isBusy ? 'Importing...' : 'Save Track Map'}
              </button>
            </div>
          </form>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', flex: 1, minHeight: 360, overflow: 'hidden' }}>
            <div style={{ borderRight: '1px solid var(--border-subtle)', overflowY: 'auto', padding: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
              {maps.length === 0 ? (
                <div style={{ color: 'var(--text-muted)', fontSize: 13, padding: 16, textAlign: 'center' }}>
                  No saved track maps.
                </div>
              ) : (
                maps.map((m) => {
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
                          void handleDeleteMap(m.slug);
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
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        style={inputStyle}
                      />
                    </label>
                    <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
                      Rotation (deg)
                      <input
                        type="number"
                        step="1"
                        value={editRotation}
                        onChange={(e) => setEditRotation(Number(e.target.value))}
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
                          onClick={() => setEditColor(c)}
                          style={{
                            width: 22,
                            height: 22,
                            borderRadius: '50%',
                            backgroundColor: c,
                            border: editColor === c ? '2px solid #FFFFFF' : '1px solid var(--border-strong)',
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

                  <div style={{ display: 'flex', gap: 8, justifyContent: 'space-between', marginTop: 4 }}>
                    <button type="button" onClick={() => handleExportJson(selectedMap)} style={btnStyle}>
                      <Download size={13} />
                      Export JSON
                    </button>
                    <button type="button" onClick={() => void handleSaveMapEdits()} style={primaryBtnStyle}>
                      <Check size={13} />
                      Save Changes
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

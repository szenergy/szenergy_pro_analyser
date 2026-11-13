import React, { useEffect, useState } from 'react';
import { RotateCcw, Tag, X } from 'lucide-react';
import { LAP_COLORS, SelectedLapInfo, SessionSummary } from '@/types/telemetry';
import { stateManager } from '@/state/stateManager';

export interface RenameLegendModalProps {
  isOpen: boolean;
  selectedLaps: SelectedLapInfo[];
  selectedChannels: string[];
  sessions: SessionSummary[];
  channelColors: Record<string, string>;
  customLapLabels: Record<string, string>;
  customChannelLabels: Record<string, string>;
  onSave: (updatedLaps: Record<string, string>, updatedChannels: Record<string, string>) => void;
  onClose: () => void;
}

export function getLapLegendKey(sessionId: string, lapNumber: number): string {
  return `${sessionId}:${lapNumber}`;
}

export const RenameLegendModal: React.FC<RenameLegendModalProps> = ({
  isOpen,
  selectedLaps,
  selectedChannels,
  sessions,
  channelColors,
  customLapLabels,
  customChannelLabels,
  onSave,
  onClose,
}) => {
  const [lapDraft, setLapDraft] = useState<Record<string, string>>({});
  const [channelDraft, setChannelDraft] = useState<Record<string, string>>({});

  useEffect(() => {
    if (isOpen) {
      setLapDraft({ ...customLapLabels });
      setChannelDraft({ ...customChannelLabels });
    }
  }, [isOpen, customLapLabels, customChannelLabels]);

  if (!isOpen) {
    return null;
  }

  const sessionById = new Map(sessions.map((s) => [s.id, s]));

  const handleResetAll = () => {
    setLapDraft({});
    setChannelDraft({});
  };

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    const cleanedLaps: Record<string, string> = {};
    for (const [k, v] of Object.entries(lapDraft)) {
      const trimmed = v.trim();
      if (trimmed.length > 0) cleanedLaps[k] = trimmed;
    }
    const cleanedChannels: Record<string, string> = {};
    for (const [k, v] of Object.entries(channelDraft)) {
      const trimmed = v.trim();
      if (trimmed.length > 0) cleanedChannels[k] = trimmed;
    }
    onSave(cleanedLaps, cleanedChannels);
    onClose();
  };
  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1000,
        backgroundColor: 'rgba(0, 0, 0, 0.6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
      }}
      onClick={onClose}
    >
      <div
        style={{
          backgroundColor: 'var(--bg-panel)',
          border: '1px solid var(--border-strong)',
          borderRadius: 8,
          width: '100%',
          maxWidth: 540,
          maxHeight: '85vh',
          display: 'flex',
          flexDirection: 'column',
          color: 'var(--text-primary)',
          boxShadow: '0 12px 32px rgba(0, 0, 0, 0.45)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '12px 16px',
            borderBottom: '1px solid var(--border-subtle)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 600, color: 'var(--text-strong)' }}>
            <Tag size={16} style={{ color: 'var(--accent)' }} />
            <span>Rename Legend Labels</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              padding: 4,
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
          <div style={{ padding: 16, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 14 }}>
            {selectedLaps.length === 0 && selectedChannels.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', padding: '24px 0' }}>
                No laps or channels are currently selected.
              </div>
            ) : (
              <>
                {selectedLaps.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                      Laps
                    </div>
                    {selectedLaps.map((lap) => {
                      const key = getLapLegendKey(lap.sessionId, lap.lapNumber);
                      const session = sessionById.get(lap.sessionId);
                      const defaultName = `${session?.name ?? lap.sessionId} Lap ${lap.lapNumber}`;
                      const value = lapDraft[key] ?? '';

                      return (
                        <div
                          key={key}
                          style={{
                            display: 'grid',
                            gridTemplateColumns: '16px 1fr 1.2fr',
                            alignItems: 'center',
                            gap: 10,
                            padding: '8px 10px',
                            backgroundColor: 'var(--bg-surface)',
                            border: '1px solid var(--border-subtle)',
                            borderRadius: 6,
                          }}
                        >
                          <span
                            style={{
                              width: 12,
                              height: 12,
                              borderRadius: '50%',
                              backgroundColor: lap.color,
                              display: 'inline-block',
                              border: '1px solid rgba(255,255,255,0.2)',
                            }}
                          />
                          <div
                            style={{
                              fontSize: 12,
                              color: 'var(--text-muted)',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                            title={defaultName}
                          >
                            {defaultName}
                          </div>
                          <input
                            type="text"
                            value={value}
                            onChange={(e) => setLapDraft((prev) => ({ ...prev, [key]: e.target.value }))}
                            placeholder={defaultName}
                            style={{
                              backgroundColor: 'var(--bg-input)',
                              border: '1px solid var(--border-strong)',
                              borderRadius: 4,
                              padding: '6px 8px',
                              color: 'var(--text-primary)',
                              fontSize: 13,
                              outline: 'none',
                              width: '100%',
                              boxSizing: 'border-box',
                            }}
                          />
                        </div>
                      );
                    })}
                  </div>
                )}

                {selectedChannels.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                      Channels
                    </div>
                    {selectedChannels.map((slug) => {
                      const defaultName = stateManager.getDisplayNameBySlug(slug);
                      const value = channelDraft[slug] ?? '';
                      const color = channelColors[slug] ?? LAP_COLORS[0];

                      return (
                        <div
                          key={slug}
                          style={{
                            display: 'grid',
                            gridTemplateColumns: '16px 1fr 1.2fr',
                            alignItems: 'center',
                            gap: 10,
                            padding: '8px 10px',
                            backgroundColor: 'var(--bg-surface)',
                            border: '1px solid var(--border-subtle)',
                            borderRadius: 6,
                          }}
                        >
                          <span
                            style={{
                              width: 12,
                              height: 12,
                              borderRadius: '50%',
                              backgroundColor: color,
                              display: 'inline-block',
                              border: '1px solid rgba(255,255,255,0.2)',
                            }}
                          />
                          <div
                            style={{
                              fontSize: 12,
                              color: 'var(--text-muted)',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                            title={defaultName}
                          >
                            {defaultName}
                          </div>
                          <input
                            type="text"
                            value={value}
                            onChange={(e) => setChannelDraft((prev) => ({ ...prev, [slug]: e.target.value }))}
                            placeholder={defaultName}
                            style={{
                              backgroundColor: 'var(--bg-input)',
                              border: '1px solid var(--border-strong)',
                              borderRadius: 4,
                              padding: '6px 8px',
                              color: 'var(--text-primary)',
                              fontSize: 13,
                              outline: 'none',
                              width: '100%',
                              boxSizing: 'border-box',
                            }}
                          />
                        </div>
                      );
                    })}
                  </div>
                )}
              </>
            )}
          </div>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '12px 16px',
              borderTop: '1px solid var(--border-subtle)',
              backgroundColor: 'var(--bg-surface)',
              borderBottomLeftRadius: 8,
              borderBottomRightRadius: 8,
            }}
          >
            <button
              type="button"
              onClick={handleResetAll}
              disabled={selectedLaps.length === 0 && selectedChannels.length === 0}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                padding: '6px 12px',
                borderRadius: 4,
                border: '1px solid var(--border-strong)',
                backgroundColor: 'var(--bg-button)',
                color: 'var(--text-primary)',
                fontSize: 13,
                cursor: selectedLaps.length === 0 && selectedChannels.length === 0 ? 'not-allowed' : 'pointer',
                opacity: selectedLaps.length === 0 && selectedChannels.length === 0 ? 0.5 : 1,
              }}
            >
              <RotateCcw size={14} />
              Reset All
            </button>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                type="button"
                onClick={onClose}
                style={{
                  padding: '6px 14px',
                  borderRadius: 4,
                  border: '1px solid var(--border-strong)',
                  backgroundColor: 'var(--bg-button)',
                  color: 'var(--text-primary)',
                  fontSize: 13,
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                type="submit"
                style={{
                  padding: '6px 14px',
                  borderRadius: 4,
                  border: '1px solid var(--accent-border)',
                  backgroundColor: 'var(--accent)',
                  color: 'var(--accent-text)',
                  fontWeight: 600,
                  fontSize: 13,
                  cursor: 'pointer',
                }}
              >
                Save
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
};

import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Check, FileSpreadsheet, X } from 'lucide-react';
import { stateManager } from '@/state/stateManager';
import {
  DEFAULT_GAP_DIST_THRESHOLD,
  DEFAULT_GAP_TIME_THRESHOLD,
  FilePreview,
  GroupChannelOverride,
  isRequiredChannelGroupId,
} from '@/types/telemetry';
import { telemetryClient } from '@/workers/telemetryClient';

export interface ImportWizardSubmitResult {
  sheetName: string | null;
  lapCol: string;
  timeCol: string | null;
  distCol: string | null;
  gapTimeThreshold: number;
  gapDistThreshold: number;
  groupOverrides: Record<string, GroupChannelOverride>;
  rememberForFile: boolean;
}

export interface ImportWizardModalProps {
  isOpen: boolean;
  mode: 'import' | 'edit';
  fileName: string;
  fileToken?: string;
  sessionId?: string;
  preview: FilePreview;
  initialSheetName: string | null;
  initialLapCol: string | null;
  initialTimeCol: string | null;
  initialDistCol: string | null;
  initialGapTime: number | null;
  initialGapDist: number | null;
  initialGroupOverrides?: Record<string, GroupChannelOverride>;
  initialRemember: boolean;
  onSubmit: (result: ImportWizardSubmitResult) => Promise<void> | void;
  onCancel: () => void;
}

export const ImportWizardModal: React.FC<ImportWizardModalProps> = ({
  isOpen,
  mode,
  fileName,
  fileToken,
  sessionId,
  preview: initialPreview,
  initialSheetName,
  initialLapCol,
  initialTimeCol,
  initialDistCol,
  initialGapTime,
  initialGapDist,
  initialGroupOverrides,
  initialRemember,
  onSubmit,
  onCancel,
}) => {
  const [preview, setPreview] = useState<FilePreview>(initialPreview);
  const [selectedSheet, setSelectedSheet] = useState<string>(
    initialSheetName ?? initialPreview.selectedSheet ?? initialPreview.sheets?.[0] ?? '',
  );
  const [lapCol, setLapCol] = useState<string>('');
  const [timeCol, setTimeCol] = useState<string>('');
  const [distCol, setDistCol] = useState<string>('');
  const [gapTime, setGapTime] = useState<string>(String(DEFAULT_GAP_TIME_THRESHOLD));
  const [gapDist, setGapDist] = useState<string>(String(DEFAULT_GAP_DIST_THRESHOLD));
  const [groupOverrides, setGroupOverrides] = useState<Record<string, GroupChannelOverride>>({});
  const [rememberForFile, setRememberForFile] = useState(true);
  const [showSkippedList, setShowSkippedList] = useState(false);
  const [sheetLoading, setSheetLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    if (!isOpen) return;
    setPreview(initialPreview);
    setSelectedSheet(
      initialSheetName ?? initialPreview.selectedSheet ?? initialPreview.sheets?.[0] ?? '',
    );
    const detected = stateManager.autoDetectImportRoles(
      initialPreview.columns,
      initialPreview.finiteCounts,
    );
    setLapCol(initialLapCol ?? detected.lapCol ?? '');
    setTimeCol(initialTimeCol ?? detected.timeCol ?? '');
    setDistCol(initialDistCol ?? detected.distCol ?? '');
    setGapTime(String(initialGapTime ?? DEFAULT_GAP_TIME_THRESHOLD));
    setGapDist(String(initialGapDist ?? DEFAULT_GAP_DIST_THRESHOLD));
    setGroupOverrides(initialGroupOverrides ? { ...initialGroupOverrides } : {});
    setRememberForFile(initialRemember);
    setShowSkippedList(false);
    setSheetLoading(false);
    setSubmitting(false);
    setErrorMsg('');
  }, [
    isOpen,
    initialPreview,
    initialSheetName,
    initialLapCol,
    initialTimeCol,
    initialDistCol,
    initialGapTime,
    initialGapDist,
    initialGroupOverrides,
    initialRemember,
  ]);

  const isTabular = useMemo(() => {
    const ext = fileName.split('.').pop()?.toLowerCase() ?? '';
    return ext !== 'tdms';
  }, [fileName]);

  const channelSummary = useMemo(() => {
    const cols = preview.columns;
    const counts = preview.finiteCounts ?? [];
    const lapIdx = lapCol ? cols.indexOf(lapCol) : -1;
    const refCount = lapIdx >= 0 && lapIdx < counts.length ? counts[lapIdx] : 0;

    const loaded: string[] = [];
    const skipped: Array<{ name: string; count: number }> = [];

    for (let i = 0; i < cols.length; i += 1) {
      const col = cols[i];
      if (col === lapCol) continue;
      const c = i < counts.length ? counts[i] : 0;
      const enough = isTabular
        ? c >= 2 && (refCount < 4 || c * 2 >= refCount)
        : c >= 2;
      if (enough) {
        loaded.push(col);
      } else {
        skipped.push({ name: col, count: c });
      }
    }
    return { loaded, skipped, refCount };
  }, [preview, lapCol, isTabular]);

  const customGroups = useMemo(
    () => stateManager.getChannelGroups().filter((g) => !isRequiredChannelGroupId(g.id)),
    [isOpen],
  );

  if (!isOpen) return null;

  const handleSheetChange = async (nextSheet: string) => {
    setSelectedSheet(nextSheet);
    setErrorMsg('');
    setSheetLoading(true);
    try {
      let nextPreview: FilePreview;
      if (mode === 'import' && fileToken) {
        const res = await telemetryClient.inspectExcelSheet(fileToken, nextSheet);
        nextPreview = res.preview;
      } else if (mode === 'edit' && sessionId) {
        nextPreview = await telemetryClient.getSessionSheetPreview(sessionId, nextSheet);
      } else {
        return;
      }
      setPreview(nextPreview);
      const detected = stateManager.autoDetectImportRoles(
        nextPreview.columns,
        nextPreview.finiteCounts,
      );
      setLapCol(detected.lapCol ?? '');
      setTimeCol(detected.timeCol ?? '');
      setDistCol(detected.distCol ?? '');
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setSheetLoading(false);
    }
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setErrorMsg('');
    if (!lapCol) {
      setErrorMsg('Select a Lap Number column.');
      return;
    }
    if (!timeCol && !distCol) {
      setErrorMsg('Select at least a Lap Time or Lap Distance column.');
      return;
    }
    if (timeCol && timeCol === lapCol) {
      setErrorMsg('Lap Time cannot be the same column as Lap Number.');
      return;
    }
    if (distCol && distCol === lapCol) {
      setErrorMsg('Lap Distance cannot be the same column as Lap Number.');
      return;
    }

    const parsedGapTime = Number(gapTime);
    const parsedGapDist = Number(gapDist);

    setSubmitting(true);
    try {
      await onSubmit({
        sheetName: preview.sheets && preview.sheets.length > 0 ? selectedSheet || preview.sheets[0] : null,
        lapCol,
        timeCol: timeCol || null,
        distCol: distCol || null,
        gapTimeThreshold:
          Number.isFinite(parsedGapTime) && parsedGapTime > 0
            ? parsedGapTime
            : DEFAULT_GAP_TIME_THRESHOLD,
        gapDistThreshold:
          Number.isFinite(parsedGapDist) && parsedGapDist > 0
            ? parsedGapDist
            : DEFAULT_GAP_DIST_THRESHOLD,
        groupOverrides,
        rememberForFile,
      });
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  };

  const formatCount = (idx: number): string => {
    const c = preview.finiteCounts?.[idx];
    if (typeof c !== 'number') return '';
    return ` (${c.toLocaleString()} pts)`;
  };

  const hasSheets = Boolean(preview.sheets && preview.sheets.length > 0);
  const canSubmit = Boolean(lapCol && (timeCol || distCol) && !sheetLoading && !submitting);

  return (
    <div style={overlayStyle} onClick={onCancel}>
      <form
        onSubmit={(e) => void handleSubmit(e)}
        style={modalStyle}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={headerStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
            <FileSpreadsheet size={16} style={{ color: 'var(--accent)', flexShrink: 0 }} />
            <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-strong)' }}>
              {mode === 'edit' ? 'Edit Import Settings' : 'Import Telemetry'}
            </span>
            <span
              style={{
                fontSize: 12,
                color: 'var(--text-muted)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
              title={fileName}
            >
              — {fileName}
            </span>
          </div>
          <button
            type="button"
            onClick={onCancel}
            aria-label="Close"
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              padding: 4,
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: 16, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 14, flex: 1 }}>
          {/* Excel Worksheet Selector */}
          {hasSheets && (
            <div
              style={{
                padding: '10px 12px',
                borderRadius: 6,
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border-subtle)',
                display: 'flex',
                alignItems: 'center',
                gap: 12,
              }}
            >
              <label
                htmlFor="import-sheet-select"
                style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-strong)', minWidth: 110 }}
              >
                Worksheet
              </label>
              <select
                id="import-sheet-select"
                value={selectedSheet}
                disabled={sheetLoading}
                onChange={(e) => void handleSheetChange(e.target.value)}
                style={{ ...selectStyle, flex: 1 }}
              >
                {preview.sheets!.map((sheet) => (
                  <option key={sheet} value={sheet}>
                    {sheet}
                  </option>
                ))}
              </select>
              {sheetLoading && (
                <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Loading sheet…</span>
              )}
            </div>
          )}

          {/* Required Role Selectors */}
          <div
            style={{
              padding: 12,
              borderRadius: 6,
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              display: 'flex',
              flexDirection: 'column',
              gap: 10,
            }}
          >
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-strong)' }}>
              Required Channels
              <span style={{ fontWeight: 400, color: 'var(--text-muted)', marginLeft: 8 }}>
                Select Lap Number and at least Lap Time or Lap Distance
              </span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 10 }}>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, minWidth: 0 }}>
                <span>
                  Lap Number <span style={{ color: 'var(--danger)' }}>*</span>
                </span>
                <select
                  aria-label="Lap Number column"
                  value={lapCol}
                  onChange={(e) => setLapCol(e.target.value)}
                  style={{ ...selectStyle, width: '100%', minWidth: 0, textOverflow: 'ellipsis' }}
                >
                  <option value="">-- Select column --</option>
                  {preview.columns.map((col, idx) => (
                    <option key={col} value={col}>
                      {col}
                      {formatCount(idx)}
                    </option>
                  ))}
                </select>
              </label>

              <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, minWidth: 0 }}>
                <span>Lap Time (s)</span>
                <select
                  aria-label="Lap Time column"
                  value={timeCol}
                  onChange={(e) => setTimeCol(e.target.value)}
                  style={{ ...selectStyle, width: '100%', minWidth: 0, textOverflow: 'ellipsis' }}
                >
                  <option value="">-- None --</option>
                  {preview.columns.map((col, idx) => (
                    <option key={col} value={col}>
                      {col}
                      {formatCount(idx)}
                    </option>
                  ))}
                </select>
              </label>

              <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, minWidth: 0 }}>
                <span>Lap Distance (m)</span>
                <select
                  aria-label="Lap Distance column"
                  value={distCol}
                  onChange={(e) => setDistCol(e.target.value)}
                  style={{ ...selectStyle, width: '100%', minWidth: 0, textOverflow: 'ellipsis' }}
                >
                  <option value="">-- None --</option>
                  {preview.columns.map((col, idx) => (
                    <option key={col} value={col}>
                      {col}
                      {formatCount(idx)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>

          {/* Loaded Channels Summary */}
          <div
            style={{
              padding: '8px 12px',
              borderRadius: 6,
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              fontSize: 12,
              display: 'flex',
              flexDirection: 'column',
              gap: 6,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
              <span>
                <strong style={{ color: 'var(--text-strong)' }}>{channelSummary.loaded.length}</strong>{' '}
                telemetry channel{channelSummary.loaded.length === 1 ? '' : 's'} will be loaded
                {preview.totalRows > 0 && (
                  <span style={{ color: 'var(--text-muted)' }}>
                    {' '}
                    ({preview.totalRows.toLocaleString()} rows)
                  </span>
                )}
              </span>
              {channelSummary.skipped.length > 0 && (
                <button
                  type="button"
                  onClick={() => setShowSkippedList((v) => !v)}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--text-muted)',
                    fontSize: 11,
                    cursor: 'pointer',
                    textDecoration: 'underline',
                  }}
                >
                  {channelSummary.skipped.length} non-telemetry/sparse skipped
                </button>
              )}
            </div>
            {showSkippedList && channelSummary.skipped.length > 0 && (
              <div style={{ fontSize: 11, color: 'var(--text-muted)', display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {channelSummary.skipped.map((s) => (
                  <span
                    key={s.name}
                    style={{
                      padding: '2px 6px',
                      borderRadius: 4,
                      backgroundColor: 'var(--bg-input)',
                      border: '1px solid var(--border-subtle)',
                    }}
                  >
                    {s.name} ({s.count})
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Gap Thresholds */}
          <div
            style={{
              padding: 10,
              borderRadius: 6,
              backgroundColor: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              display: 'flex',
              flexWrap: 'wrap',
              gap: 14,
              alignItems: 'center',
            }}
          >
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
              <span>Max Time Gap (s):</span>
              <input
                type="number"
                step="any"
                min="0.01"
                value={gapTime}
                onChange={(e) => setGapTime(e.target.value)}
                style={{ ...selectStyle, width: 80 }}
              />
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
              <span>Max Dist Gap (m):</span>
              <input
                type="number"
                step="any"
                min="0.1"
                value={gapDist}
                onChange={(e) => setGapDist(e.target.value)}
                style={{ ...selectStyle, width: 80 }}
              />
            </label>
          </div>

          {/* Local Channel Group Overrides */}
          {customGroups.length > 0 && (
            <div
              style={{
                padding: 10,
                borderRadius: 6,
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border-subtle)',
                display: 'flex',
                flexDirection: 'column',
                gap: 8,
              }}
            >
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-strong)' }}>
                Channel Group Overrides
                <span style={{ fontWeight: 400, color: 'var(--text-muted)', marginLeft: 8 }}>
                  Optional per-file channel & transform overrides
                </span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 170, overflowY: 'auto' }}>
                {customGroups.map((grp) => {
                  const ov = groupOverrides[grp.id];
                  const selectedCol = ov?.channel ?? '';
                  const factorVal = ov?.factor ?? 1;
                  const offsetVal = ov?.offset ?? 0;
                  return (
                    <div
                      key={grp.id}
                      style={{
                        display: 'grid',
                        gridTemplateColumns: 'minmax(110px, 1fr) minmax(130px, 1.4fr) 70px 70px',
                        alignItems: 'center',
                        gap: 6,
                        fontSize: 11,
                      }}
                    >
                      <span
                        style={{
                          fontWeight: 500,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                        title={grp.unit ? `${grp.name} [${grp.unit}]` : grp.name}
                      >
                        {grp.name}
                        {grp.unit ? ` [${grp.unit}]` : ''}
                      </span>
                      <select
                        aria-label={`Override for ${grp.name}`}
                        value={selectedCol}
                        onChange={(e) => {
                          const ch = e.target.value;
                          setGroupOverrides((prev) => {
                            const next = { ...prev };
                            if (!ch) {
                              delete next[grp.id];
                            } else {
                              const grpTr = grp.transforms?.[ch];
                              next[grp.id] = {
                                channel: ch,
                                factor: prev[grp.id]?.factor ?? grpTr?.factor ?? 1,
                                offset: prev[grp.id]?.offset ?? grpTr?.offset ?? 0,
                              };
                            }
                            return next;
                          });
                        }}
                        style={{ ...selectStyle, padding: '4px 6px', fontSize: 11, width: '100%', minWidth: 0, textOverflow: 'ellipsis' }}
                      >
                        <option value="">Default ({grp.channels[0] ?? 'auto'})</option>
                        {channelSummary.loaded.map((col) => (
                          <option key={col} value={col}>
                            {col}
                          </option>
                        ))}
                      </select>
                      <input
                        type="number"
                        step="any"
                        disabled={!selectedCol}
                        aria-label={`Override factor for ${grp.name}`}
                        title="Factor: (raw * factor) + offset"
                        value={factorVal}
                        onChange={(e) => {
                          const num = Number(e.target.value);
                          const factor = Number.isFinite(num) ? num : 1;
                          setGroupOverrides((prev) =>
                            prev[grp.id]
                              ? { ...prev, [grp.id]: { ...prev[grp.id], factor } }
                              : prev,
                          );
                        }}
                        style={{
                          ...selectStyle,
                          padding: '4px 6px',
                          fontSize: 11,
                          width: '100%',
                          opacity: selectedCol ? 1 : 0.45,
                        }}
                      />
                      <input
                        type="number"
                        step="any"
                        disabled={!selectedCol}
                        aria-label={`Override offset for ${grp.name}`}
                        title="Offset: (raw * factor) + offset"
                        value={offsetVal}
                        onChange={(e) => {
                          const num = Number(e.target.value);
                          const offset = Number.isFinite(num) ? num : 0;
                          setGroupOverrides((prev) =>
                            prev[grp.id]
                              ? { ...prev, [grp.id]: { ...prev[grp.id], offset } }
                              : prev,
                          );
                        }}
                        style={{
                          ...selectStyle,
                          padding: '4px 6px',
                          fontSize: 11,
                          width: '100%',
                          opacity: selectedCol ? 1 : 0.45,
                        }}
                      />
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {errorMsg && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '8px 10px',
                borderRadius: 6,
                backgroundColor: 'var(--danger-bg)',
                color: 'var(--danger)',
                fontSize: 12,
              }}
            >
              <AlertTriangle size={14} style={{ flexShrink: 0 }} />
              <span>{errorMsg}</span>
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '10px 16px',
            borderTop: '1px solid var(--border-subtle)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 10,
          }}
        >
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, cursor: 'pointer', color: 'var(--text-muted)' }}>
            <input
              type="checkbox"
              checked={rememberForFile}
              onChange={(e) => setRememberForFile(e.target.checked)}
              style={{ accentColor: 'var(--accent)' }}
            />
            <span>Remember for this file</span>
          </label>

          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" onClick={onCancel} style={btnStyle}>
              Cancel
            </button>
            <button
              type="submit"
              disabled={!canSubmit}
              style={{
                ...primaryBtnStyle,
                opacity: canSubmit ? 1 : 0.5,
                cursor: canSubmit ? 'pointer' : 'not-allowed',
              }}
            >
              <Check size={14} />
              <span>{submitting ? 'Loading…' : mode === 'edit' ? 'Apply Changes' : 'Import'}</span>
            </button>
          </div>
        </div>
      </form>
    </div>
  );
};

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
  maxWidth: 760,
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

const selectStyle: React.CSSProperties = {
  backgroundColor: 'var(--bg-input)',
  border: '1px solid var(--border-strong)',
  borderRadius: 4,
  padding: '6px 8px',
  color: 'var(--text-primary)',
  fontSize: 12,
  outline: 'none',
};

const btnStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
  padding: '6px 12px',
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

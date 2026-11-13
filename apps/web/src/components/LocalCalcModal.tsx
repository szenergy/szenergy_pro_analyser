import React, { useEffect, useMemo, useState } from 'react';
import { AlertCircle, CheckCircle2, Plus, Trash2, X } from 'lucide-react';
import {
  formatChannelDisplay,
  generateUniqueSlug,
  stateManager,
} from '@/state/stateManager';
import { ChannelDef, LocalCalcDef } from '@/types/telemetry';
import { telemetryClient } from '@/workers/telemetryClient';

export interface LocalCalcModalProps {
  isOpen: boolean;
  rawColumns: string[];
  existingNames: string[];
  initialCalc?: LocalCalcDef | null;
  onSave: (calc: LocalCalcDef) => void;
  onClose: () => void;
}

interface VarRow {
  letter: string;
  column: string;
}

const NEW_CHANNEL_OPTION = '__new_channel__';

function nextVarLetter(rows: VarRow[]): string {
  const used = new Set(rows.map((r) => r.letter));
  for (let i = 0; i < 26; i += 1) {
    const ch = String.fromCharCode(65 + i);
    if (!used.has(ch)) return ch;
  }
  return `V${rows.length + 1}`;
}

export const LocalCalcModal: React.FC<LocalCalcModalProps> = ({
  isOpen,
  rawColumns,
  existingNames,
  initialCalc,
  onSave,
  onClose,
}) => {
  const [channels, setChannels] = useState<ChannelDef[]>([]);
  const [targetSlug, setTargetSlug] = useState<string>('');
  const [isNewChannel, setIsNewChannel] = useState(false);
  const [newChannelName, setNewChannelName] = useState('');
  const [newChannelUnit, setNewChannelUnit] = useState('');
  const [calcName, setCalcName] = useState('');
  const [varRows, setVarRows] = useState<VarRow[]>([]);
  const [formula, setFormula] = useState('');
  const [validation, setValidation] = useState<{
    status: 'idle' | 'checking' | 'valid' | 'invalid';
    message: string;
  }>({ status: 'idle', message: '' });
  const [formError, setFormError] = useState('');

  useEffect(() => {
    if (!isOpen) return;
    const defs = stateManager.getChannelDefs();
    setChannels(defs);
    setFormError('');

    if (initialCalc) {
      setCalcName(initialCalc.name);
      const exists = defs.some((c) => c.slug === initialCalc.target_slug);
      if (exists) {
        setIsNewChannel(false);
        setTargetSlug(initialCalc.target_slug);
      } else {
        setIsNewChannel(true);
        setTargetSlug(NEW_CHANNEL_OPTION);
        setNewChannelName(initialCalc.target_label || initialCalc.name);
        setNewChannelUnit('');
      }
      const entries = Object.entries(initialCalc.inputs || {});
      if (entries.length > 0) {
        setVarRows(entries.map(([letter, column]) => ({ letter, column })));
      } else {
        setVarRows([{ letter: 'A', column: rawColumns[0] ?? '' }]);
      }
      setFormula(initialCalc.formula || '');
    } else {
      const firstNonSystem = defs.find((c) => c.type !== 'system') ?? defs[0];
      setIsNewChannel(false);
      setTargetSlug(firstNonSystem?.slug ?? NEW_CHANNEL_OPTION);
      if (!firstNonSystem) {
        setIsNewChannel(true);
      }
      setNewChannelName('');
      setNewChannelUnit('');
      setCalcName('');
      setVarRows([{ letter: 'A', column: rawColumns[0] ?? '' }]);
      setFormula('');
    }
  }, [isOpen, initialCalc, rawColumns]);

  const varLetters = useMemo(() => varRows.map((r) => r.letter), [varRows]);

  useEffect(() => {
    if (!isOpen) return;
    const trimmed = formula.trim();
    if (!trimmed) {
      setValidation({ status: 'idle', message: '' });
      return;
    }

    let cancelled = false;
    setValidation({ status: 'checking', message: 'Validating formula…' });
    const timer = window.setTimeout(async () => {
      try {
        const res = await telemetryClient.validateFormula(trimmed, varLetters);
        if (cancelled) return;
        setValidation({
          status: res.valid ? 'valid' : 'invalid',
          message: res.message || (res.valid ? 'Formula is valid' : 'Invalid formula'),
        });
      } catch (err) {
        if (cancelled) return;
        setValidation({
          status: 'invalid',
          message: err instanceof Error ? err.message : 'Validation failed',
        });
      }
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [isOpen, formula, varLetters]);

  if (!isOpen) return null;

  const handleTargetChange = (value: string) => {
    setTargetSlug(value);
    setIsNewChannel(value === NEW_CHANNEL_OPTION);
    setFormError('');
  };

  const handleAddVar = () => {
    setVarRows((prev) => [
      ...prev,
      { letter: nextVarLetter(prev), column: rawColumns[0] ?? '' },
    ]);
  };

  const handleRemoveVar = (index: number) => {
    if (varRows.length <= 1) return;
    setVarRows((prev) => prev.filter((_, i) => i !== index));
  };

  const handleVarColumnChange = (index: number, column: string) => {
    setVarRows((prev) => prev.map((row, i) => (i === index ? { ...row, column } : row)));
  };

  const handleSave = async () => {
    setFormError('');
    let resolvedSlug = targetSlug;
    let resolvedLabel = '';

    if (isNewChannel || targetSlug === NEW_CHANNEL_OPTION) {
      const cleanName = newChannelName.trim();
      if (!cleanName) {
        setFormError('Enter a name for the new target channel.');
        return;
      }
      const existingSlugs = channels.map((c) => c.slug);
      resolvedSlug = generateUniqueSlug(cleanName, existingSlugs);
      const newDef: ChannelDef = {
        label: cleanName,
        slug: resolvedSlug,
        type: 'custom',
        unit: newChannelUnit.trim(),
      };
      await stateManager.saveChannelDefs([...channels, newDef]);
      resolvedLabel = formatChannelDisplay(newDef.label, newDef.unit);
    } else {
      const ch = channels.find((c) => c.slug === targetSlug);
      if (!ch) {
        setFormError('Select a valid target global channel.');
        return;
      }
      resolvedLabel = formatChannelDisplay(ch.label, ch.unit);
    }

    const finalName = calcName.trim() || resolvedLabel;
    const duplicateName = existingNames.some(
      (n) =>
        n.toLowerCase() === finalName.toLowerCase() &&
        (!initialCalc || initialCalc.name.toLowerCase() !== finalName.toLowerCase()),
    );
    if (duplicateName) {
      setFormError(`A local calculation named "${finalName}" already exists.`);
      return;
    }

    if (varRows.some((r) => !r.column)) {
      setFormError('All variable rows must map to a raw file column.');
      return;
    }

    if (!formula.trim()) {
      setFormError('Enter a formula expression.');
      return;
    }

    if (validation.status === 'invalid') {
      setFormError(validation.message || 'Fix formula errors before saving.');
      return;
    }

    const inputs: Record<string, string> = {};
    for (const row of varRows) {
      inputs[row.letter] = row.column;
    }

    onSave({
      name: finalName,
      target_slug: resolvedSlug,
      target_label: resolvedLabel,
      formula: formula.trim(),
      inputs,
    });
  };

  return (
    <div style={overlayStyle} role="dialog" aria-modal="true" aria-label="Local Calculated Channel">
      <div style={modalStyle}>
        <div style={headerStyle}>
          <h3 style={titleStyle}>
            {initialCalc ? 'Edit Local Calculated Channel' : 'Add Local Calculated Channel'}
          </h3>
          <button type="button" onClick={onClose} style={iconBtnStyle} aria-label="Close">
            <X size={16} />
          </button>
        </div>

        <div style={bodyStyle}>
          <div style={fieldGroupStyle}>
            <label style={labelStyle}>Target Global Channel</label>
            <select
              value={targetSlug}
              onChange={(e) => handleTargetChange(e.target.value)}
              style={inputStyle}
            >
              {channels.map((ch) => (
                <option key={ch.slug} value={ch.slug}>
                  {formatChannelDisplay(ch.label, ch.unit)} ({ch.slug})
                </option>
              ))}
              <option value={NEW_CHANNEL_OPTION}>+ New Channel...</option>
            </select>
          </div>

          {isNewChannel && (
            <div style={inlineNewBoxStyle}>
              <div style={{ flex: 2 }}>
                <label style={labelStyle}>New Channel Name</label>
                <input
                  type="text"
                  value={newChannelName}
                  onChange={(e) => setNewChannelName(e.target.value)}
                  placeholder="e.g. Wheel Slip"
                  style={inputStyle}
                />
              </div>
              <div style={{ flex: 1 }}>
                <label style={labelStyle}>Unit</label>
                <input
                  type="text"
                  value={newChannelUnit}
                  onChange={(e) => setNewChannelUnit(e.target.value)}
                  placeholder="e.g. km/h"
                  style={inputStyle}
                />
              </div>
            </div>
          )}

          <div style={fieldGroupStyle}>
            <label style={labelStyle}>Calculation Name (optional)</label>
            <input
              type="text"
              value={calcName}
              onChange={(e) => setCalcName(e.target.value)}
              placeholder="Defaults to target channel name"
              style={inputStyle}
            />
          </div>

          <div style={fieldGroupStyle}>
            <div style={rowBetweenStyle}>
              <label style={labelStyle}>Input Variables (Raw File Columns)</label>
              <button type="button" onClick={handleAddVar} style={smallBtnStyle}>
                <Plus size={13} /> Add Variable
              </button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {varRows.map((row, idx) => (
                <div key={row.letter} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={varBadgeStyle}>{row.letter}</span>
                  <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>=</span>
                  <select
                    value={row.column}
                    onChange={(e) => handleVarColumnChange(idx, e.target.value)}
                    style={{ ...inputStyle, flex: 1 }}
                  >
                    {rawColumns.length === 0 && <option value="">No columns available</option>}
                    {rawColumns.map((col) => (
                      <option key={col} value={col}>
                        {col}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={() => handleRemoveVar(idx)}
                    disabled={varRows.length <= 1}
                    style={{
                      ...iconBtnStyle,
                      opacity: varRows.length <= 1 ? 0.35 : 1,
                      cursor: varRows.length <= 1 ? 'not-allowed' : 'pointer',
                    }}
                    aria-label={`Remove variable ${row.letter}`}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div style={fieldGroupStyle}>
            <label style={labelStyle}>Formula</label>
            <input
              type="text"
              value={formula}
              onChange={(e) => setFormula(e.target.value)}
              placeholder="e.g. (A + B) / 2"
              style={{ ...inputStyle, fontFamily: 'monospace' }}
            />
            <div style={hintStyle}>
              Functions: <code>sqrt, abs, sin, cos, tan, arctan2, clip, min, max, pow, log, exp, pi</code>
            </div>
            {validation.status !== 'idle' && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  fontSize: 12,
                  marginTop: 4,
                  color:
                    validation.status === 'valid'
                      ? 'var(--accent)'
                      : validation.status === 'invalid'
                        ? 'var(--danger)'
                        : 'var(--text-muted)',
                }}
              >
                {validation.status === 'valid' && <CheckCircle2 size={14} />}
                {validation.status === 'invalid' && <AlertCircle size={14} />}
                <span>{validation.message}</span>
              </div>
            )}
          </div>

          {formError && <div style={errorBoxStyle}>{formError}</div>}
        </div>

        <div style={footerStyle}>
          <button type="button" onClick={onClose} style={secondaryBtnStyle}>
            Cancel
          </button>
          <button type="button" onClick={handleSave} style={primaryBtnStyle}>
            Save Calculation
          </button>
        </div>
      </div>
    </div>
  );
};

const overlayStyle: React.CSSProperties = {
  position: 'fixed',
  inset: 0,
  backgroundColor: 'rgba(0, 0, 0, 0.6)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 1100,
  padding: 16,
};

const modalStyle: React.CSSProperties = {
  width: '100%',
  maxWidth: 520,
  backgroundColor: 'var(--bg-panel)',
  border: '1px solid var(--border-strong)',
  borderRadius: 8,
  boxShadow: '0 16px 40px rgba(0, 0, 0, 0.45)',
  display: 'flex',
  flexDirection: 'column',
  maxHeight: '90vh',
};

const headerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '12px 16px',
  borderBottom: '1px solid var(--border-subtle)',
};

const titleStyle: React.CSSProperties = {
  margin: 0,
  fontSize: 15,
  fontWeight: 600,
  color: 'var(--text-strong)',
};

const bodyStyle: React.CSSProperties = {
  padding: 16,
  overflowY: 'auto',
  display: 'flex',
  flexDirection: 'column',
  gap: 14,
};

const footerStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'flex-end',
  gap: 8,
  padding: '12px 16px',
  borderTop: '1px solid var(--border-subtle)',
};

const fieldGroupStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 6,
};

const labelStyle: React.CSSProperties = {
  fontSize: 12,
  fontWeight: 500,
  color: 'var(--text-muted)',
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '7px 10px',
  fontSize: 13,
  backgroundColor: 'var(--bg-input)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-subtle)',
  borderRadius: 5,
  boxSizing: 'border-box',
};

const inlineNewBoxStyle: React.CSSProperties = {
  display: 'flex',
  gap: 10,
  padding: 10,
  backgroundColor: 'var(--bg-surface)',
  border: '1px solid var(--border-subtle)',
  borderRadius: 6,
};

const rowBetweenStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
};

const varBadgeStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 26,
  height: 26,
  borderRadius: 4,
  backgroundColor: 'var(--bg-elevated)',
  border: '1px solid var(--border-strong)',
  color: 'var(--accent)',
  fontWeight: 700,
  fontSize: 12,
  fontFamily: 'monospace',
};

const hintStyle: React.CSSProperties = {
  fontSize: 11,
  color: 'var(--text-muted)',
};

const errorBoxStyle: React.CSSProperties = {
  padding: '8px 10px',
  fontSize: 12,
  color: 'var(--danger)',
  backgroundColor: 'var(--danger-bg)',
  border: '1px solid var(--danger)',
  borderRadius: 5,
};

const iconBtnStyle: React.CSSProperties = {
  background: 'transparent',
  border: 'none',
  color: 'var(--text-muted)',
  cursor: 'pointer',
  padding: 4,
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  borderRadius: 4,
};

const smallBtnStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 4,
  padding: '4px 8px',
  fontSize: 12,
  backgroundColor: 'var(--bg-button)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-subtle)',
  borderRadius: 4,
  cursor: 'pointer',
};

const secondaryBtnStyle: React.CSSProperties = {
  padding: '7px 14px',
  fontSize: 13,
  backgroundColor: 'var(--bg-button)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-subtle)',
  borderRadius: 5,
  cursor: 'pointer',
};

const primaryBtnStyle: React.CSSProperties = {
  padding: '7px 14px',
  fontSize: 13,
  fontWeight: 600,
  backgroundColor: 'var(--accent)',
  color: 'var(--accent-text)',
  border: '1px solid var(--accent-border)',
  borderRadius: 5,
  cursor: 'pointer',
};

import React, { useEffect, useMemo, useState } from 'react';
import { AlertCircle, CheckCircle2, Plus, Trash2, X } from 'lucide-react';
import { formatChannelDisplay, generateUniqueSlug } from '@/state/stateManager';
import { ChannelDef } from '@/types/telemetry';
import { telemetryClient } from '@/workers/telemetryClient';

export interface GlobalCalcModalProps {
  isOpen: boolean;
  availableChannels: ChannelDef[];
  initialChannel?: ChannelDef | null;
  onSave: (channel: ChannelDef) => void;
  onClose: () => void;
}

interface VarRow {
  letter: string;
  slug: string;
}

function nextVarLetter(rows: VarRow[]): string {
  const used = new Set(rows.map((r) => r.letter));
  for (let i = 0; i < 26; i += 1) {
    const ch = String.fromCharCode(65 + i);
    if (!used.has(ch)) return ch;
  }
  return `V${rows.length + 1}`;
}

export const GlobalCalcModal: React.FC<GlobalCalcModalProps> = ({
  isOpen,
  availableChannels,
  initialChannel,
  onSave,
  onClose,
}) => {
  const [name, setName] = useState('');
  const [unit, setUnit] = useState('');
  const [varRows, setVarRows] = useState<VarRow[]>([]);
  const [formula, setFormula] = useState('');
  const [validation, setValidation] = useState<{
    status: 'idle' | 'checking' | 'valid' | 'invalid';
    message: string;
  }>({ status: 'idle', message: '' });
  const [formError, setFormError] = useState('');

  const selectableChannels = useMemo(
    () =>
      availableChannels.filter(
        (ch) => !initialChannel || ch.slug !== initialChannel.slug,
      ),
    [availableChannels, initialChannel],
  );

  useEffect(() => {
    if (!isOpen) return;
    setFormError('');

    if (initialChannel) {
      setName(initialChannel.label);
      setUnit(initialChannel.unit || '');
      const entries = Object.entries(initialChannel.inputs || {});
      if (entries.length > 0) {
        setVarRows(entries.map(([letter, slug]) => ({ letter, slug })));
      } else {
        setVarRows([{ letter: 'A', slug: selectableChannels[0]?.slug ?? '' }]);
      }
      setFormula(initialChannel.formula || '');
    } else {
      setName('');
      setUnit('');
      setVarRows([{ letter: 'A', slug: selectableChannels[0]?.slug ?? '' }]);
      setFormula('');
    }
  }, [isOpen, initialChannel, selectableChannels]);

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

  const handleAddVar = () => {
    setVarRows((prev) => [
      ...prev,
      { letter: nextVarLetter(prev), slug: selectableChannels[0]?.slug ?? '' },
    ]);
  };

  const handleRemoveVar = (index: number) => {
    if (varRows.length <= 1) return;
    setVarRows((prev) => prev.filter((_, i) => i !== index));
  };

  const handleVarSlugChange = (index: number, slug: string) => {
    setVarRows((prev) => prev.map((row, i) => (i === index ? { ...row, slug } : row)));
  };

  const handleSave = () => {
    setFormError('');
    const cleanName = name.trim();
    if (!cleanName) {
      setFormError('Enter a channel name.');
      return;
    }

    if (varRows.some((r) => !r.slug)) {
      setFormError('All variable rows must map to a global channel.');
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
      inputs[row.letter] = row.slug;
    }

    const slug = initialChannel
      ? initialChannel.slug
      : generateUniqueSlug(
          cleanName,
          availableChannels.map((c) => c.slug),
        );

    onSave({
      label: cleanName,
      slug,
      type: 'calculated',
      unit: unit.trim(),
      formula: formula.trim(),
      inputs,
    });
  };

  return (
    <div style={overlayStyle} role="dialog" aria-modal="true" aria-label="Global Calculated Channel">
      <div style={modalStyle}>
        <div style={headerStyle}>
          <h3 style={titleStyle}>
            {initialChannel ? 'Edit Global Calculated Channel' : 'New Global Calculated Channel'}
          </h3>
          <button type="button" onClick={onClose} style={iconBtnStyle} aria-label="Close">
            <X size={16} />
          </button>
        </div>

        <div style={bodyStyle}>
          <div style={{ display: 'flex', gap: 10 }}>
            <div style={{ ...fieldGroupStyle, flex: 2 }}>
              <label style={labelStyle}>Channel Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Power"
                style={inputStyle}
              />
            </div>
            <div style={{ ...fieldGroupStyle, flex: 1 }}>
              <label style={labelStyle}>Unit</label>
              <input
                type="text"
                value={unit}
                onChange={(e) => setUnit(e.target.value)}
                placeholder="e.g. kW"
                style={inputStyle}
              />
            </div>
          </div>

          <div style={fieldGroupStyle}>
            <div style={rowBetweenStyle}>
              <label style={labelStyle}>Input Variables (Global Channels)</label>
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
                    value={row.slug}
                    onChange={(e) => handleVarSlugChange(idx, e.target.value)}
                    style={{ ...inputStyle, flex: 1 }}
                  >
                    {selectableChannels.length === 0 && (
                      <option value="">No channels available</option>
                    )}
                    {selectableChannels.map((ch) => (
                      <option key={ch.slug} value={ch.slug}>
                        {formatChannelDisplay(ch.label, ch.unit)} ({ch.slug})
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
              placeholder="e.g. A * B / 1000"
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
            Save Channel
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

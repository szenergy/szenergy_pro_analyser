import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Check,
  Edit2,
  Plus,
  RotateCcw,
  Save,
  Trash2,
  X,
} from 'lucide-react';
import { LocalCalcModal } from '@/components/LocalCalcModal';
import {
  formatChannelDisplay,
  generateUniqueSlug,
  stateManager,
} from '@/state/stateManager';
import {
  ChannelDef,
  DEFAULT_GAP_DIST_THRESHOLD,
  DEFAULT_GAP_TIME_THRESHOLD,
  FilePreview,
  LocalCalcDef,
  PresetDef,
  STD_CH_LAP_DIST_SLUG,
  STD_CH_LAP_NUM_SLUG,
  STD_CH_LAP_TIME_SLUG,
} from '@/types/telemetry';

export interface ImportWizardSubmitResult {
  mapping: Record<string, string>;
  localCalculatedChannels: LocalCalcDef[];
  gapTimeThreshold: number;
  gapDistThreshold: number;
  presetSlug: string | null;
  presetName: string | null;
  rememberForFile: boolean;
}

export interface ImportWizardModalProps {
  isOpen: boolean;
  mode: 'import' | 'edit';
  fileName: string;
  fileSignature: string;
  preview: FilePreview;
  initialPresetSlug: string | null;
  initialMapping: Record<string, string>;
  initialLocalCalcs: LocalCalcDef[];
  initialGapTime: number | null;
  initialGapDist: number | null;
  initialRemember: boolean;
  onSubmit: (result: ImportWizardSubmitResult) => Promise<void> | void;
  onCancel: () => void;
}

const SKIP_VALUE = '';
const NEW_CHANNEL_VALUE = '__new_channel__';

interface PendingNewChannel {
  label: string;
  unit: string;
}

export const ImportWizardModal: React.FC<ImportWizardModalProps> = ({
  isOpen,
  mode,
  fileName,
  fileSignature,
  preview,
  initialPresetSlug,
  initialMapping,
  initialLocalCalcs,
  initialGapTime,
  initialGapDist,
  initialRemember,
  onSubmit,
  onCancel,
}) => {
  const [presets, setPresets] = useState<PresetDef[]>([]);
  const [channels, setChannels] = useState<ChannelDef[]>([]);
  const [selectedPresetSlug, setSelectedPresetSlug] = useState<string | null>(null);
  const [presetNameInput, setPresetNameInput] = useState('');
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [pendingNewChannels, setPendingNewChannels] = useState<
    Record<string, PendingNewChannel>
  >({});
  const [localCalcs, setLocalCalcs] = useState<LocalCalcDef[]>([]);
  const [gapTime, setGapTime] = useState<string>(String(DEFAULT_GAP_TIME_THRESHOLD));
  const [gapDist, setGapDist] = useState<string>(String(DEFAULT_GAP_DIST_THRESHOLD));
  const [rememberForFile, setRememberForFile] = useState(true);

  const [saveChoiceOpen, setSaveChoiceOpen] = useState(false);
  const [localCalcModalOpen, setLocalCalcModalOpen] = useState(false);
  const [editingCalcIndex, setEditingCalcIndex] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [statusMsg, setStatusMsg] = useState('');

  useEffect(() => {
    if (!isOpen) return;
    const loadedPresets = stateManager.loadPresets();
    const loadedChannels = stateManager.getChannelDefs();
    setPresets(loadedPresets);
    setChannels(loadedChannels);
    setSelectedPresetSlug(initialPresetSlug);
    const matchedPreset = initialPresetSlug
      ? loadedPresets.find((p) => p.slug === initialPresetSlug)
      : undefined;
    setPresetNameInput(matchedPreset?.name ?? '');
    setMapping({ ...initialMapping });
    setPendingNewChannels({});
    setLocalCalcs(initialLocalCalcs.map((c) => ({ ...c, inputs: { ...c.inputs } })));
    setGapTime(String(initialGapTime ?? DEFAULT_GAP_TIME_THRESHOLD));
    setGapDist(String(initialGapDist ?? DEFAULT_GAP_DIST_THRESHOLD));
    setRememberForFile(initialRemember);
    setSaveChoiceOpen(false);
    setLocalCalcModalOpen(false);
    setEditingCalcIndex(null);
    setSubmitting(false);
    setErrorMsg('');
    setStatusMsg('');
  }, [
    isOpen,
    initialPresetSlug,
    initialMapping,
    initialLocalCalcs,
    initialGapTime,
    initialGapDist,
    initialRemember,
  ]);

  const selectedPreset = useMemo(
    () =>
      selectedPresetSlug
        ? presets.find((p) => p.slug === selectedPresetSlug) ?? null
        : null,
    [presets, selectedPresetSlug],
  );

  const matchStats = useMemo(() => {
    if (!selectedPreset) return null;
    return stateManager.getPresetMatchStats(selectedPreset.slug, preview.columns);
  }, [selectedPreset, preview.columns]);

  const rawColumnSet = useMemo(() => new Set(preview.columns), [preview.columns]);

  const duplicateTargets = useMemo(() => {
    const counts = new Map<string, number>();
    for (const col of preview.columns) {
      const target = mapping[col];
      if (!target || target === NEW_CHANNEL_VALUE) continue;
      counts.set(target, (counts.get(target) ?? 0) + 1);
    }
    const dups = new Set<string>();
    for (const [slug, count] of counts.entries()) {
      if (count > 1) dups.add(slug);
    }
    return dups;
  }, [mapping, preview.columns]);

  const mappedSlugs = useMemo(() => {
    const set = new Set<string>();
    for (const col of preview.columns) {
      const target = mapping[col];
      if (target && target !== NEW_CHANNEL_VALUE) {
        set.add(target);
      }
    }
    for (const calc of localCalcs) {
      if (calc.target_slug) set.add(calc.target_slug);
    }
    return set;
  }, [mapping, preview.columns, localCalcs]);

  const lapNumMissing = !mappedSlugs.has(STD_CH_LAP_NUM_SLUG);

  if (!isOpen) return null;

  const applyPresetToWizard = (preset: PresetDef | null) => {
    if (!preset) {
      setSelectedPresetSlug(null);
      setPresetNameInput('');
      setMapping({});
      setPendingNewChannels({});
      setLocalCalcs([]);
      setGapTime(String(DEFAULT_GAP_TIME_THRESHOLD));
      setGapDist(String(DEFAULT_GAP_DIST_THRESHOLD));
      return;
    }
    setSelectedPresetSlug(preset.slug);
    setPresetNameInput(preset.name);
    const nextMap: Record<string, string> = {};
    for (const col of preview.columns) {
      if (preset.mapping[col]) {
        nextMap[col] = preset.mapping[col];
      }
    }
    setMapping(nextMap);
    setPendingNewChannels({});
    setLocalCalcs(
      (preset.local_calculated_channels || []).map((c) => ({
        ...c,
        inputs: { ...c.inputs },
      })),
    );
    setGapTime(String(preset.gap_time_threshold ?? DEFAULT_GAP_TIME_THRESHOLD));
    setGapDist(String(preset.gap_dist_threshold ?? DEFAULT_GAP_DIST_THRESHOLD));
  };

  const handlePresetSelect = (slug: string) => {
    setErrorMsg('');
    setStatusMsg('');
    if (!slug) {
      applyPresetToWizard(null);
      return;
    }
    const found = presets.find((p) => p.slug === slug) ?? null;
    applyPresetToWizard(found);
  };

  const handleLoadPreset = () => {
    if (!selectedPreset) return;
    applyPresetToWizard(selectedPreset);
    setStatusMsg(`Reloaded preset "${selectedPreset.name}".`);
  };

  const buildCleanMapping = (): Record<string, string> => {
    const clean: Record<string, string> = {};
    for (const col of preview.columns) {
      const target = mapping[col];
      if (target && target !== NEW_CHANNEL_VALUE) {
        clean[col] = target;
      }
    }
    return clean;
  };

  const persistPreset = async (targetSlug: string | null, name: string) => {
    const cleanName = name.trim();
    const parsedGapTime = Number(gapTime);
    const parsedGapDist = Number(gapDist);

    const savedSlug = await stateManager.savePreset(cleanName, buildCleanMapping(), {
      slug: targetSlug,
      localCalculatedChannels: localCalcs,
      gapTimeThreshold: Number.isFinite(parsedGapTime)
        ? parsedGapTime
        : DEFAULT_GAP_TIME_THRESHOLD,
      gapDistThreshold: Number.isFinite(parsedGapDist)
        ? parsedGapDist
        : DEFAULT_GAP_DIST_THRESHOLD,
    });
    const refreshed = stateManager.loadPresets();
    setPresets(refreshed);
    setSelectedPresetSlug(savedSlug);
    setPresetNameInput(cleanName);
    setSaveChoiceOpen(false);
    setStatusMsg(`Saved preset "${cleanName}".`);
  };

  const handleSavePresetClick = () => {
    setErrorMsg('');
    setStatusMsg('');
    const cleanName = presetNameInput.trim();
    if (!cleanName) {
      setErrorMsg('Enter a preset name before saving.');
      return;
    }
    if (selectedPreset && selectedPreset.name !== cleanName) {
      setSaveChoiceOpen(true);
      return;
    }
    void persistPreset(selectedPreset ? selectedPreset.slug : null, cleanName);
  };

  const handleMappingChange = (rawCol: string, value: string) => {
    setMapping((prev) => {
      const next = { ...prev };
      if (!value) {
        delete next[rawCol];
      } else {
        next[rawCol] = value;
      }
      return next;
    });
    if (value === NEW_CHANNEL_VALUE) {
      setPendingNewChannels((prev) => ({
        ...prev,
        [rawCol]: prev[rawCol] ?? { label: rawCol, unit: '' },
      }));
    } else {
      setPendingNewChannels((prev) => {
        if (!(rawCol in prev)) return prev;
        const next = { ...prev };
        delete next[rawCol];
        return next;
      });
    }
  };

  const handleSaveLocalCalc = (calc: LocalCalcDef) => {
    setLocalCalcs((prev) => {
      if (editingCalcIndex !== null && editingCalcIndex >= 0 && editingCalcIndex < prev.length) {
        return prev.map((item, idx) => (idx === editingCalcIndex ? calc : item));
      }
      return [...prev, calc];
    });
    setChannels(stateManager.getChannelDefs());
    setLocalCalcModalOpen(false);
    setEditingCalcIndex(null);
  };

  const handleSubmit = async () => {
    setErrorMsg('');
    setStatusMsg('');

    if (duplicateTargets.size > 0) {
      setErrorMsg('Resolve duplicate target channel mappings before continuing.');
      return;
    }

    const finalMapping = buildCleanMapping();
    const newDefsToCreate: ChannelDef[] = [];
    const existingSlugs = new Set(channels.map((c) => c.slug));

    for (const col of preview.columns) {
      if (mapping[col] === NEW_CHANNEL_VALUE) {
        const pending = pendingNewChannels[col];
        const label = pending?.label.trim() || col;
        const slug = generateUniqueSlug(label, existingSlugs);
        existingSlugs.add(slug);
        newDefsToCreate.push({
          label,
          slug,
          type: 'custom',
          unit: pending?.unit.trim() || '',
        });
        finalMapping[col] = slug;
      }
    }

    if (newDefsToCreate.length > 0) {
      await stateManager.saveChannelDefs([...stateManager.getChannelDefs(), ...newDefsToCreate]);
      setChannels(stateManager.getChannelDefs());
    }

    const allMappedSlugs = new Set<string>(Object.values(finalMapping));
    for (const calc of localCalcs) {
      allMappedSlugs.add(calc.target_slug);
    }

    if (
      !allMappedSlugs.has(STD_CH_LAP_TIME_SLUG) &&
      !allMappedSlugs.has(STD_CH_LAP_DIST_SLUG)
    ) {
      setErrorMsg('Map at least Lap Time or Lap Distance to import this session.');
      return;
    }

    const parsedGapTime = Number(gapTime);
    const parsedGapDist = Number(gapDist);
    const finalGapTime =
      Number.isFinite(parsedGapTime) && parsedGapTime > 0
        ? parsedGapTime
        : DEFAULT_GAP_TIME_THRESHOLD;
    const finalGapDist =
      Number.isFinite(parsedGapDist) && parsedGapDist > 0
        ? parsedGapDist
        : DEFAULT_GAP_DIST_THRESHOLD;

    if (rememberForFile) {
      stateManager.saveFileMappingConfig(fileSignature, {
        preset_slug: selectedPresetSlug,
        mapping: finalMapping,
        local_calculated_channels: localCalcs,
        gap_time_threshold: finalGapTime,
        gap_dist_threshold: finalGapDist,
      });
    } else {
      stateManager.removeFileMappingConfig(fileSignature);
    }

    setSubmitting(true);
    try {
      await onSubmit({
        mapping: finalMapping,
        localCalculatedChannels: localCalcs,
        gapTimeThreshold: finalGapTime,
        gapDistThreshold: finalGapDist,
        presetSlug: selectedPresetSlug,
        presetName: selectedPreset?.name ?? null,
        rememberForFile,
      });
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : 'Failed to process session.');
      setSubmitting(false);
    }
  };

  return (
    <div style={overlayStyle} role="dialog" aria-modal="true" aria-label="Import Wizard">
      <div style={modalStyle}>
        <div style={headerStyle}>
          <div>
            <h3 style={titleStyle}>
              {mode === 'edit' ? `Manage Session - ${fileName}` : `Import Log File - ${fileName}`}
            </h3>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
              {preview.columns.length} columns detected
            </div>
          </div>
          <button type="button" onClick={onCancel} style={iconBtnStyle} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div style={bodyStyle}>
          {/* Preset Bar */}
          <div style={sectionBoxStyle}>
            <div style={presetBarStyle}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1, minWidth: 160 }}>
                <label style={labelStyle}>Preset</label>
                <select
                  value={selectedPresetSlug ?? ''}
                  onChange={(e) => handlePresetSelect(e.target.value)}
                  style={inputStyle}
                >
                  <option value="">None</option>
                  {presets.map((p) => (
                    <option key={p.slug} value={p.slug}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1, minWidth: 160 }}>
                <label style={labelStyle}>Preset Name</label>
                <input
                  type="text"
                  value={presetNameInput}
                  onChange={(e) => setPresetNameInput(e.target.value)}
                  placeholder="Enter name to save preset"
                  style={inputStyle}
                />
              </div>

              <div style={{ display: 'flex', alignItems: 'flex-end', gap: 6 }}>
                <button
                  type="button"
                  onClick={handleLoadPreset}
                  disabled={!selectedPreset}
                  style={{
                    ...secondaryBtnStyle,
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 5,
                    opacity: selectedPreset ? 1 : 0.45,
                    cursor: selectedPreset ? 'pointer' : 'not-allowed',
                  }}
                >
                  <RotateCcw size={13} /> Load Preset
                </button>
                <button
                  type="button"
                  onClick={handleSavePresetClick}
                  style={{
                    ...secondaryBtnStyle,
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 5,
                  }}
                >
                  <Save size={13} /> Save Preset
                </button>
              </div>
            </div>

            {saveChoiceOpen && selectedPreset && (
              <div style={choiceBannerStyle}>
                <span style={{ fontSize: 12, color: 'var(--text-primary)' }}>
                  Preset renamed from <strong>{selectedPreset.name}</strong> to{' '}
                  <strong>{presetNameInput.trim()}</strong>:
                </span>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button
                    type="button"
                    onClick={() => persistPreset(selectedPreset.slug, presetNameInput)}
                    style={smallPrimaryBtnStyle}
                  >
                    Update Existing
                  </button>
                  <button
                    type="button"
                    onClick={() => persistPreset(null, presetNameInput)}
                    style={smallBtnStyle}
                  >
                    Create New
                  </button>
                  <button
                    type="button"
                    onClick={() => setSaveChoiceOpen(false)}
                    style={smallBtnStyle}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {matchStats && (
              <div style={matchStatsStyle}>
                <span style={badgeStyle}>Matched: {matchStats.matched_count}</span>
                <span
                  style={{
                    ...badgeStyle,
                    color:
                      matchStats.missing_in_file_count > 0
                        ? 'var(--warning)'
                        : 'var(--text-muted)',
                  }}
                >
                  {matchStats.missing_in_file_count > 0 && '⚠ '}
                  Missing from file: {matchStats.missing_in_file_count}
                </span>
                <span style={badgeStyle}>Unmapped in file: {matchStats.unmapped_in_file_count}</span>
                {matchStats.missing_channels.length > 0 && (
                  <span style={{ fontSize: 11, color: 'var(--warning)' }}>
                    ⚠ Missing preset columns: {matchStats.missing_channels.join(', ')}
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Mapping Table */}
          <div style={sectionBoxStyle}>
            <div style={sectionTitleStyle}>Channel Mapping</div>
            <div style={tableWrapStyle}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={thStyle}>Raw Column</th>
                    <th style={thStyle}>Sample Values</th>
                    <th style={thStyle}>Target Channel</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.columns.map((col, colIdx) => {
                    const samples = preview.rows
                      .slice(0, 4)
                      .map((r) => r[colIdx] ?? '')
                      .filter((v) => v !== '');
                    const currentTarget = mapping[col] ?? SKIP_VALUE;
                    const isDup =
                      currentTarget !== SKIP_VALUE &&
                      currentTarget !== NEW_CHANNEL_VALUE &&
                      duplicateTargets.has(currentTarget);
                    const pendingNew = pendingNewChannels[col];

                    return (
                      <tr key={col} style={trStyle}>
                        <td style={tdStyle}>
                          <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{col}</span>
                        </td>
                        <td style={{ ...tdStyle, color: 'var(--text-muted)', fontSize: 12 }}>
                          {samples.length > 0 ? samples.join(', ') : '—'}
                        </td>
                        <td style={tdStyle}>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                              <select
                                value={currentTarget}
                                onChange={(e) => handleMappingChange(col, e.target.value)}
                                style={{
                                  ...inputStyle,
                                  borderColor: isDup
                                    ? 'var(--danger)'
                                    : 'var(--border-subtle)',
                                }}
                              >
                                <option value={SKIP_VALUE}>-- Skip --</option>
                                {channels.map((ch) => (
                                  <option key={ch.slug} value={ch.slug}>
                                    {formatChannelDisplay(ch.label, ch.unit)}
                                  </option>
                                ))}
                                <option value={NEW_CHANNEL_VALUE}>+ New Channel...</option>
                              </select>
                              {isDup && (
                                <span
                                  title="Duplicate target channel"
                                  style={{ color: 'var(--danger)', fontSize: 12, whiteSpace: 'nowrap' }}
                                >
                                  ⚠ Duplicate
                                </span>
                              )}
                            </div>

                            {currentTarget === NEW_CHANNEL_VALUE && pendingNew && (
                              <div style={{ display: 'flex', gap: 6 }}>
                                <input
                                  type="text"
                                  value={pendingNew.label}
                                  onChange={(e) =>
                                    setPendingNewChannels((prev) => ({
                                      ...prev,
                                      [col]: { ...pendingNew, label: e.target.value },
                                    }))
                                  }
                                  placeholder="Channel name"
                                  style={{ ...inputStyle, flex: 2, padding: '4px 8px', fontSize: 12 }}
                                />
                                <input
                                  type="text"
                                  value={pendingNew.unit}
                                  onChange={(e) =>
                                    setPendingNewChannels((prev) => ({
                                      ...prev,
                                      [col]: { ...pendingNew, unit: e.target.value },
                                    }))
                                  }
                                  placeholder="Unit"
                                  style={{ ...inputStyle, flex: 1, padding: '4px 8px', fontSize: 12 }}
                                />
                              </div>
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

          {/* Local Calculated Channels */}
          <div style={sectionBoxStyle}>
            <div style={rowBetweenStyle}>
              <div style={sectionTitleStyle}>Local Calculated Channels</div>
              <button
                type="button"
                onClick={() => {
                  setEditingCalcIndex(null);
                  setLocalCalcModalOpen(true);
                }}
                style={smallBtnStyle}
              >
                <Plus size={13} /> Add Calculated Channel
              </button>
            </div>
            {localCalcs.length === 0 ? (
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                No local calculated channels defined for this file.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {localCalcs.map((calc, idx) => {
                  const missingInputs = Object.values(calc.inputs || {}).filter(
                    (col) => !rawColumnSet.has(col),
                  );
                  return (
                    <div key={`${calc.name}-${idx}`} style={calcItemStyle}>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <span style={{ fontWeight: 600, fontSize: 13 }}>{calc.name}</span>
                          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                            → {calc.target_label || calc.target_slug}
                          </span>
                          {missingInputs.length > 0 && (
                            <span style={{ fontSize: 11, color: 'var(--warning)' }}>
                              ⚠ Missing input: {missingInputs.join(', ')}
                            </span>
                          )}
                        </div>
                        <code style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                          {calc.formula}
                        </code>
                      </div>
                      <div style={{ display: 'flex', gap: 4 }}>
                        <button
                          type="button"
                          onClick={() => {
                            setEditingCalcIndex(idx);
                            setLocalCalcModalOpen(true);
                          }}
                          style={iconBtnStyle}
                          aria-label={`Edit ${calc.name}`}
                        >
                          <Edit2 size={14} />
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            setLocalCalcs((prev) => prev.filter((_, i) => i !== idx))
                          }
                          style={iconBtnStyle}
                          aria-label={`Remove ${calc.name}`}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Data Gap Thresholds */}
          <div style={sectionBoxStyle}>
            <div style={sectionTitleStyle}>Data Rate / Gap Thresholds</div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: 160 }}>
                <label style={labelStyle}>Max Time Gap (s)</label>
                <input
                  type="number"
                  step="0.1"
                  min="0.01"
                  value={gapTime}
                  onChange={(e) => setGapTime(e.target.value)}
                  style={inputStyle}
                />
              </div>
              <div style={{ flex: 1, minWidth: 160 }}>
                <label style={labelStyle}>Max Distance Gap (m)</label>
                <input
                  type="number"
                  step="1"
                  min="0.1"
                  value={gapDist}
                  onChange={(e) => setGapDist(e.target.value)}
                  style={inputStyle}
                />
              </div>
            </div>
          </div>

          {lapNumMissing && (
            <div style={warningBannerStyle}>
              <AlertTriangle size={15} />
              <span>
                <strong>Lap Number</strong> is unmapped — the entire log will be imported as Lap 1.
              </span>
            </div>
          )}

          {statusMsg && (
            <div style={statusBannerStyle}>
              <Check size={14} />
              <span>{statusMsg}</span>
            </div>
          )}

          {errorMsg && <div style={errorBoxStyle}>{errorMsg}</div>}
        </div>

        <div style={footerStyle}>
          <label
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              fontSize: 13,
              color: 'var(--text-primary)',
              cursor: 'pointer',
            }}
          >
            <input
              type="checkbox"
              checked={rememberForFile}
              onChange={(e) => setRememberForFile(e.target.checked)}
            />
            Remember for this file
          </label>

          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" onClick={onCancel} style={secondaryBtnStyle}>
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={submitting}
              style={{
                ...primaryBtnStyle,
                opacity: submitting ? 0.6 : 1,
                cursor: submitting ? 'wait' : 'pointer',
              }}
            >
              {submitting
                ? 'Processing…'
                : mode === 'edit'
                  ? 'Apply Changes'
                  : 'Import Data'}
            </button>
          </div>
        </div>
      </div>

      <LocalCalcModal
        isOpen={localCalcModalOpen}
        rawColumns={preview.columns}
        existingNames={localCalcs.map((c) => c.name)}
        initialCalc={editingCalcIndex !== null ? localCalcs[editingCalcIndex] : null}
        onSave={handleSaveLocalCalc}
        onClose={() => {
          setLocalCalcModalOpen(false);
          setEditingCalcIndex(null);
        }}
      />
    </div>
  );
};

const overlayStyle: React.CSSProperties = {
  position: 'fixed',
  inset: 0,
  backgroundColor: 'rgba(0, 0, 0, 0.65)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 1000,
  padding: 16,
};

const modalStyle: React.CSSProperties = {
  width: '100%',
  maxWidth: 820,
  backgroundColor: 'var(--bg-panel)',
  border: '1px solid var(--border-strong)',
  borderRadius: 8,
  boxShadow: '0 20px 50px rgba(0, 0, 0, 0.5)',
  display: 'flex',
  flexDirection: 'column',
  maxHeight: '92vh',
};

const headerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '14px 18px',
  borderBottom: '1px solid var(--border-subtle)',
};

const titleStyle: React.CSSProperties = {
  margin: 0,
  fontSize: 16,
  fontWeight: 600,
  color: 'var(--text-strong)',
};

const bodyStyle: React.CSSProperties = {
  padding: 18,
  overflowY: 'auto',
  display: 'flex',
  flexDirection: 'column',
  gap: 14,
};

const footerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 12,
  padding: '12px 18px',
  borderTop: '1px solid var(--border-subtle)',
};

const sectionBoxStyle: React.CSSProperties = {
  backgroundColor: 'var(--bg-surface)',
  border: '1px solid var(--border-subtle)',
  borderRadius: 6,
  padding: 12,
  display: 'flex',
  flexDirection: 'column',
  gap: 10,
};

const sectionTitleStyle: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 600,
  color: 'var(--text-strong)',
};

const presetBarStyle: React.CSSProperties = {
  display: 'flex',
  gap: 10,
  flexWrap: 'wrap',
  alignItems: 'flex-end',
};

const choiceBannerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  flexWrap: 'wrap',
  gap: 8,
  padding: '8px 10px',
  backgroundColor: 'var(--bg-elevated)',
  border: '1px solid var(--accent-border)',
  borderRadius: 5,
};

const matchStatsStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  flexWrap: 'wrap',
  gap: 8,
};

const badgeStyle: React.CSSProperties = {
  fontSize: 11,
  padding: '2px 8px',
  borderRadius: 999,
  backgroundColor: 'var(--badge-bg)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-subtle)',
};

const tableWrapStyle: React.CSSProperties = {
  maxHeight: 280,
  overflowY: 'auto',
  border: '1px solid var(--border-subtle)',
  borderRadius: 5,
};

const tableStyle: React.CSSProperties = {
  width: '100%',
  borderCollapse: 'collapse',
  fontSize: 13,
};

const thStyle: React.CSSProperties = {
  textAlign: 'left',
  padding: '8px 10px',
  fontSize: 12,
  fontWeight: 600,
  color: 'var(--text-muted)',
  backgroundColor: 'var(--bg-elevated)',
  borderBottom: '1px solid var(--border-subtle)',
  position: 'sticky',
  top: 0,
};

const trStyle: React.CSSProperties = {
  borderBottom: '1px solid var(--border-subtle)',
};

const tdStyle: React.CSSProperties = {
  padding: '7px 10px',
  verticalAlign: 'middle',
};

const calcItemStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '8px 10px',
  backgroundColor: 'var(--bg-elevated)',
  border: '1px solid var(--border-subtle)',
  borderRadius: 5,
};

const rowBetweenStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
};

const labelStyle: React.CSSProperties = {
  fontSize: 12,
  fontWeight: 500,
  color: 'var(--text-muted)',
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '6px 9px',
  fontSize: 13,
  backgroundColor: 'var(--bg-input)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-subtle)',
  borderRadius: 5,
  boxSizing: 'border-box',
};

const warningBannerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  padding: '8px 10px',
  fontSize: 12,
  color: 'var(--warning)',
  backgroundColor: 'var(--bg-elevated)',
  border: '1px solid var(--warning)',
  borderRadius: 5,
};

const statusBannerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  padding: '8px 10px',
  fontSize: 12,
  color: 'var(--accent)',
  backgroundColor: 'var(--accent-subtle)',
  border: '1px solid var(--accent-border)',
  borderRadius: 5,
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
  padding: '4px 9px',
  fontSize: 12,
  backgroundColor: 'var(--bg-button)',
  color: 'var(--text-primary)',
  border: '1px solid var(--border-subtle)',
  borderRadius: 4,
  cursor: 'pointer',
};

const smallPrimaryBtnStyle: React.CSSProperties = {
  padding: '4px 9px',
  fontSize: 12,
  fontWeight: 600,
  backgroundColor: 'var(--accent)',
  color: 'var(--accent-text)',
  border: '1px solid var(--accent-border)',
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
  padding: '7px 16px',
  fontSize: 13,
  fontWeight: 600,
  backgroundColor: 'var(--accent)',
  color: 'var(--accent-text)',
  border: '1px solid var(--accent-border)',
  borderRadius: 5,
};

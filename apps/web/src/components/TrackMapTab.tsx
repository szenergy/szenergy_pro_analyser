import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RotateCw, Settings } from 'lucide-react';
import {
  buildTrackMapGeometry,
  renderTrackMapCanvas,
  TrackMapCursorPoint,
  TrackMapGeometry,
} from '@/plot/trackMapRenderer';
import { stateManager } from '@/state/stateManager';

export interface TrackMapTabProps {
  isDark: boolean;
  cursorPoints: TrackMapCursorPoint[];
  selectedMapSlug: string | null;
  mapRefreshVersion: number;
  onSelectMap: (slug: string | null) => void;
  onOpenMapManager: () => void;
}

export const TrackMapTab: React.FC<TrackMapTabProps> = ({
  isDark,
  cursorPoints,
  selectedMapSlug,
  mapRefreshVersion,
  onSelectMap,
  onOpenMapManager,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const maps = useMemo(() => {
    void mapRefreshVersion;
    return stateManager.loadMaps();
  }, [mapRefreshVersion]);

  const selectedMap = useMemo(() => {
    if (!selectedMapSlug) return null;
    return maps.find((m) => m.slug === selectedMapSlug) ?? null;
  }, [maps, selectedMapSlug]);

  const geom: TrackMapGeometry | null = useMemo(() => {
    if (!selectedMap) return null;
    return buildTrackMapGeometry(selectedMap.x, selectedMap.y, selectedMap.distance);
  }, [selectedMap]);

  const [angle, setAngle] = useState<number>(() => selectedMap?.rotation ?? 0);

  // Keep local rotation slider synchronized when selected map or maps list refreshes
  useEffect(() => {
    setAngle(selectedMap?.rotation ?? 0);
  }, [selectedMap?.slug, selectedMap?.rotation, mapRefreshVersion]);

  // Debounced persistence of map rotation (300ms)
  const pendingSaveRef = useRef<{
    slug: string;
    angle: number;
    timer: number;
  } | null>(null);

  const flushPendingRotationSave = useCallback(() => {
    const pending = pendingSaveRef.current;
    if (!pending) return;
    window.clearTimeout(pending.timer);
    pendingSaveRef.current = null;
    void stateManager.saveMapRotation(pending.slug, pending.angle);
  }, []);

  // Flush pending save before switching maps or unmounting
  useEffect(() => {
    return () => {
      flushPendingRotationSave();
    };
  }, [selectedMapSlug, flushPendingRotationSave]);

  const trackColor = selectedMap?.color || (isDark ? '#FFC815' : '#D9A700');

  const renderParamsRef = useRef({
    geom,
    angle,
    trackColor,
    cursorPoints,
    isDark,
  });
  renderParamsRef.current = {
    geom,
    angle,
    trackColor,
    cursorPoints,
    isDark,
  };

  const drawCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const p = renderParamsRef.current;
    renderTrackMapCanvas(canvas, p.geom, p.angle, p.trackColor, p.cursorPoints, p.isDark);
  }, []);

  // Redraw immediately when cursorPoints, isDark, angle, trackColor, or geom changes
  useEffect(() => {
    drawCanvas();
  }, [geom, angle, trackColor, cursorPoints, isDark, drawCanvas]);

  // Auto-resize canvas via ResizeObserver
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const observer = new ResizeObserver(() => {
      drawCanvas();
    });
    observer.observe(canvas);
    return () => {
      observer.disconnect();
    };
  }, [drawCanvas]);

  const handleSelectChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const next = e.target.value;
    onSelectMap(next ? next : null);
  };

  const handleRotationChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const nextAngle = Number(e.target.value);
    setAngle(nextAngle);

    if (!selectedMap) return;
    const targetSlug = selectedMap.slug;

    if (pendingSaveRef.current) {
      window.clearTimeout(pendingSaveRef.current.timer);
      if (pendingSaveRef.current.slug !== targetSlug) {
        void stateManager.saveMapRotation(
          pendingSaveRef.current.slug,
          pendingSaveRef.current.angle,
        );
      }
    }

    const timer = window.setTimeout(() => {
      pendingSaveRef.current = null;
      void stateManager.saveMapRotation(targetSlug, nextAngle);
    }, 300);

    pendingSaveRef.current = { slug: targetSlug, angle: nextAngle, timer };
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        minHeight: 0,
        padding: '8px',
        gap: '8px',
        background: 'var(--bg-panel)',
      }}
    >
      {/* Map Selector + Settings */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
        <select
          aria-label="Select track map"
          value={selectedMap ? selectedMap.slug : ''}
          onChange={handleSelectChange}
          style={{
            flex: 1,
            minWidth: 0,
            height: '28px',
            padding: '0 8px',
            borderRadius: '4px',
            border: '1px solid var(--border-strong)',
            background: 'var(--bg-input)',
            color: 'var(--text-primary)',
            fontSize: '12px',
          }}
        >
          <option value="">-- No Track Map --</option>
          {maps.map((m) => (
            <option key={m.slug} value={m.slug}>
              {m.name}
            </option>
          ))}
        </select>

        <button
          type="button"
          onClick={onOpenMapManager}
          title="Manage Track Maps"
          aria-label="Manage Track Maps"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '28px',
            height: '28px',
            padding: 0,
            borderRadius: '4px',
            border: '1px solid var(--border-strong)',
            background: 'var(--bg-button)',
            color: 'var(--text-primary)',
            cursor: 'pointer',
            flexShrink: 0,
          }}
        >
          <Settings size={14} />
        </button>
      </div>

      {/* Track Map Canvas */}
      <div
        style={{
          flex: 1,
          minHeight: '110px',
          position: 'relative',
          borderRadius: '6px',
          border: '1px solid var(--border-subtle)',
          background: 'var(--bg-canvas)',
          overflow: 'hidden',
        }}
      >
        <canvas
          ref={canvasRef}
          style={{
            width: '100%',
            height: '100%',
            display: 'block',
          }}
        />
      </div>

      {/* Rotation Slider */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          flexShrink: 0,
          padding: '2px 2px 0',
        }}
      >
        <span
          title="Map Rotation"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '4px',
            fontSize: '11px',
            color: 'var(--text-muted)',
            flexShrink: 0,
          }}
        >
          <RotateCw size={13} />
          <span>Rot</span>
        </span>

        <input
          type="range"
          min={-180}
          max={180}
          step={1}
          value={angle}
          disabled={!selectedMap}
          onChange={handleRotationChange}
          aria-label="Track map rotation degrees"
          style={{
            flex: 1,
            minWidth: 0,
            accentColor: 'var(--accent)',
            cursor: selectedMap ? 'pointer' : 'not-allowed',
          }}
        />

        <span
          className="tabular-nums"
          style={{
            width: '38px',
            textAlign: 'right',
            fontSize: '11px',
            color: selectedMap ? 'var(--text-primary)' : 'var(--text-muted)',
            flexShrink: 0,
          }}
        >
          {Math.round(angle)}°
        </span>
      </div>
    </div>
  );
};

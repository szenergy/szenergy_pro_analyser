/**
 * Pure Canvas2D Track Map renderer mirroring old_python_app/ui/track_map_tab.py
 * and old_python_app/core/map_parser.py start-line geometry.
 */

export interface TrackMapCursorPoint {
  distance: number;
  color: string;
}

export interface TrackMapGeometry {
  x: Float64Array;
  y: Float64Array;
  dist: Float64Array;
  centroidX: number;
  centroidY: number;
  distMin: number;
  distMax: number;
  distSpan: number;
}

export function buildTrackMapGeometry(
  rawX: number[] | Float64Array,
  rawY: number[] | Float64Array,
  rawDist?: number[] | Float64Array | null
): TrackMapGeometry | null {
  const n = Math.min(rawX.length, rawY.length);
  if (n === 0) return null;

  const x = Float64Array.from(rawX.slice(0, n));
  const y = Float64Array.from(rawY.slice(0, n));
  let dist: Float64Array;

  if (rawDist && rawDist.length >= n) {
    dist = Float64Array.from(rawDist.slice(0, n));
  } else {
    dist = new Float64Array(n);
    let acc = 0;
    dist[0] = 0;
    for (let i = 1; i < n; i++) {
      const dx = x[i] - x[i - 1];
      const dy = y[i] - y[i - 1];
      acc += Math.hypot(dx, dy);
      dist[i] = acc;
    }
  }

  let sumX = 0;
  let sumY = 0;
  let distMin = Infinity;
  let distMax = -Infinity;
  for (let i = 0; i < n; i++) {
    sumX += x[i];
    sumY += y[i];
    if (dist[i] < distMin) distMin = dist[i];
    if (dist[i] > distMax) distMax = dist[i];
  }

  return {
    x,
    y,
    dist,
    centroidX: sumX / n,
    centroidY: sumY / n,
    distMin,
    distMax,
    distSpan: distMax - distMin,
  };
}

function interpPolyline(distArr: Float64Array, valArr: Float64Array, targetD: number): number {
  const n = distArr.length;
  if (n === 0) return 0;
  if (n === 1 || targetD <= distArr[0]) return valArr[0];
  if (targetD >= distArr[n - 1]) return valArr[n - 1];

  // Binary search assuming monotonic cumulative distance
  let lo = 0;
  let hi = n - 1;
  while (lo + 1 < hi) {
    const mid = (lo + hi) >> 1;
    if (distArr[mid] <= targetD) {
      lo = mid;
    } else {
      hi = mid;
    }
  }
  const d0 = distArr[lo];
  const d1 = distArr[hi];
  const span = d1 - d0;
  if (span <= 1e-12) return valArr[lo];
  const t = (targetD - d0) / span;
  return valArr[lo] + t * (valArr[hi] - valArr[lo]);
}

function computeStartLine(
  x: Float64Array,
  y: Float64Array,
  cx: number,
  cy: number,
  cosTheta: number,
  sinTheta: number
): [number, number, number, number] | null {
  const n = x.length;
  if (n < 2) return null;

  const x0 = x[0];
  const y0 = y[0];
  let dx = 1;
  let dy = 0;
  for (let i = 1; i < n; i++) {
    const ddx = x[i] - x0;
    const ddy = y[i] - y0;
    if (ddx * ddx + ddy * ddy > 1e-8) {
      dx = ddx;
      dy = ddy;
      break;
    }
  }
  const len = Math.hypot(dx, dy);
  const tx = len > 0 ? dx / len : 1;
  const ty = len > 0 ? dy / len : 0;
  const nx = -ty;
  const ny = tx;

  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (let i = 0; i < n; i++) {
    if (x[i] < minX) minX = x[i];
    if (x[i] > maxX) maxX = x[i];
    if (y[i] < minY) minY = y[i];
    if (y[i] > maxY) maxY = y[i];
  }
  const trackSpan = Math.max(maxX - minX, maxY - minY);
  const halfWidth = Math.max(0.03 * trackSpan, 1.0);

  const p1x = x0 - halfWidth * nx - cx;
  const p1y = y0 - halfWidth * ny - cy;
  const p2x = x0 + halfWidth * nx - cx;
  const p2y = y0 + halfWidth * ny - cy;

  return [
    p1x * cosTheta - p1y * sinTheta + cx,
    p1x * sinTheta + p1y * cosTheta + cy,
    p2x * cosTheta - p2y * sinTheta + cx,
    p2x * sinTheta + p2y * cosTheta + cy,
  ];
}

export function renderTrackMapCanvas(
  canvas: HTMLCanvasElement,
  geom: TrackMapGeometry | null,
  angleDeg: number,
  trackColor: string,
  cursorPoints: TrackMapCursorPoint[],
  isDark: boolean
) {
  const rect = canvas.getBoundingClientRect();
  const w = Math.max(1, Math.round(rect.width));
  const h = Math.max(1, Math.round(rect.height));
  const dpr = window.devicePixelRatio || 1;
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }

  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  ctx.save();
  ctx.scale(dpr, dpr);
  ctx.fillStyle = isDark ? '#191B1F' : '#FFFFFF';
  ctx.fillRect(0, 0, w, h);

  if (!geom || geom.x.length === 0) {
    ctx.fillStyle = '#808080';
    ctx.font = '12px system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('No track map selected', w / 2, h / 2);
    ctx.restore();
    return;
  }

  const rad = (angleDeg * Math.PI) / 180;
  const cosTheta = Math.cos(rad);
  const sinTheta = Math.sin(rad);
  const { x, y, dist, centroidX: cx, centroidY: cy, distMin, distMax, distSpan } = geom;
  const n = x.length;

  const rotX = new Float64Array(n);
  const rotY = new Float64Array(n);
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;

  for (let i = 0; i < n; i++) {
    const ox = x[i] - cx;
    const oy = y[i] - cy;
    const rx = ox * cosTheta - oy * sinTheta + cx;
    const ry = ox * sinTheta + oy * cosTheta + cy;
    rotX[i] = rx;
    rotY[i] = ry;
    if (rx < minX) minX = rx;
    if (rx > maxX) maxX = rx;
    if (ry < minY) minY = ry;
    if (ry > maxY) maxY = ry;
  }

  const pad = 16;
  const spanX = Math.max(1e-6, maxX - minX);
  const spanY = Math.max(1e-6, maxY - minY);
  const availW = Math.max(10, w - pad * 2);
  const availH = Math.max(10, h - pad * 2);
  const scale = Math.min(availW / spanX, availH / spanY);
  const offsetX = pad + (availW - spanX * scale) * 0.5;
  const offsetY = pad + (availH - spanY * scale) * 0.5;

  const toCanvasX = (vx: number) => offsetX + (vx - minX) * scale;
  const toCanvasY = (vy: number) => h - (offsetY + (vy - minY) * scale);

  // Draw track polyline
  ctx.beginPath();
  ctx.strokeStyle = trackColor || (isDark ? '#FFC815' : '#D9A700');
  ctx.lineWidth = 3.5;
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  ctx.moveTo(toCanvasX(rotX[0]), toCanvasY(rotY[0]));
  for (let i = 1; i < n; i++) {
    ctx.lineTo(toCanvasX(rotX[i]), toCanvasY(rotY[i]));
  }
  ctx.stroke();

  // Draw start/finish line
  const sl = computeStartLine(x, y, cx, cy, cosTheta, sinTheta);
  if (sl) {
    ctx.beginPath();
    ctx.strokeStyle = isDark ? '#FF1744' : '#D50000';
    ctx.lineWidth = 3.5;
    ctx.moveTo(toCanvasX(sl[0]), toCanvasY(sl[1]));
    ctx.lineTo(toCanvasX(sl[2]), toCanvasY(sl[3]));
    ctx.stroke();
  }

  // Draw live cursor tracking dots
  const borderCol = isDark ? '#FFFFFF' : '#000000';
  for (const pt of cursorPoints) {
    let targetD = distMin;
    if (distSpan > 0) {
      if (pt.distance < distMin) {
        targetD = distMin;
      } else if (pt.distance > distMax) {
        targetD = distMin + ((pt.distance - distMin) % distSpan);
      } else {
        targetD = pt.distance;
      }
    }
    const ix = interpPolyline(dist, x, targetD);
    const iy = interpPolyline(dist, y, targetD);
    const ox = ix - cx;
    const oy = iy - cy;
    const rx = ox * cosTheta - oy * sinTheta + cx;
    const ry = ox * sinTheta + oy * cosTheta + cy;

    const px = toCanvasX(rx);
    const py = toCanvasY(ry);

    ctx.beginPath();
    ctx.arc(px, py, 6.5, 0, Math.PI * 2);
    ctx.fillStyle = pt.color;
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = borderCol;
    ctx.stroke();
  }

  ctx.restore();
}

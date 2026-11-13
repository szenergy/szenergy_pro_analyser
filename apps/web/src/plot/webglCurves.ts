/**
 * WebGL2 instanced anti-aliased curve + tracking-dot renderer for stacked telemetry plots.
 * Uses relative-to-origin Float32 coordinates (subtracting view center in Float64)
 * so deep zoom levels never suffer Float32 precision jitter.
 */

export interface CurveRenderInput {
  /** Interleaved relative positions [dx0, dy0, dx1, dy1, ...] in Float32, or separate x/y Float64Arrays */
  x: Float64Array;
  y: Float64Array;
  color: [number, number, number, number];
  lineWidth: number;
}

export interface DotRenderInput {
  x: number;
  y: number;
  fillColor: [number, number, number, number];
  borderColor: [number, number, number, number];
  radiusPx: number;
}

export interface ViewportRect {
  /** CSS pixels relative to canvas top-left */
  left: number;
  top: number;
  width: number;
  height: number;
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
}

export function hexToRgba(hex: string, alpha = 1.0): [number, number, number, number] {
  const clean = hex.replace('#', '');
  if (clean.length === 6) {
    const r = parseInt(clean.slice(0, 2), 16) / 255;
    const g = parseInt(clean.slice(2, 4), 16) / 255;
    const b = parseInt(clean.slice(4, 6), 16) / 255;
    return [r, g, b, alpha];
  }
  return [1, 1, 1, alpha];
}

const LINE_VERT_SRC = `#version 300 es
precision highp float;

// Unit quad corner: a_corner.x in [0, 1] along segment, a_corner.y in [-1, 1] perpendicular
layout(location = 0) in vec2 a_corner;
// Segment endpoints relative to (u_xOrigin, u_yOrigin)
layout(location = 1) in vec2 a_p0;
layout(location = 2) in vec2 a_p1;

uniform vec2 u_scale;       // (2.0 / spanX, 2.0 / spanY) in relative view units -> [-1, 1]
uniform vec2 u_viewportPx;  // (widthPx, heightPx) of this plot's scissor rect
uniform float u_halfWidth;  // half stroke width in CSS px
uniform float u_feather;    // AA feather in CSS px

out float v_edgeDist;
out float v_halfWidth;

void main() {
  // Skip NaN / Inf endpoints by collapsing quad off-screen
  bool bad0 = isnan(a_p0.x) || isnan(a_p0.y) || isinf(a_p0.x) || isinf(a_p0.y);
  bool bad1 = isnan(a_p1.x) || isnan(a_p1.y) || isinf(a_p1.x) || isinf(a_p1.y);
  if (bad0 || bad1) {
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
    v_edgeDist = 0.0;
    v_halfWidth = u_halfWidth;
    return;
  }

  // Convert relative data coordinates to plot-local pixel coordinates
  vec2 p0Px = (a_p0 * u_scale * 0.5 + 0.5) * u_viewportPx;
  vec2 p1Px = (a_p1 * u_scale * 0.5 + 0.5) * u_viewportPx;

  vec2 delta = p1Px - p0Px;
  float segLen = length(delta);
  vec2 dir = segLen > 1e-5 ? delta / segLen : vec2(1.0, 0.0);
  vec2 normal = vec2(-dir.y, dir.x);

  float expand = u_halfWidth + u_feather;
  // Slightly extend caps by halfWidth * 0.4 to avoid hairline miter cracks on sharp bends
  float along = a_corner.x * segLen + (a_corner.x - 0.5) * (u_halfWidth * 0.6);
  vec2 posPx = p0Px + dir * along + normal * (a_corner.y * expand);

  vec2 ndc = (posPx / u_viewportPx) * 2.0 - 1.0;
  gl_Position = vec4(ndc, 0.0, 1.0);

  v_edgeDist = a_corner.y * expand;
  v_halfWidth = u_halfWidth;
}
`;

const LINE_FRAG_SRC = `#version 300 es
precision highp float;

uniform vec4 u_color;
uniform float u_feather;

in float v_edgeDist;
in float v_halfWidth;

out vec4 outColor;

void main() {
  float d = abs(v_edgeDist);
  float alpha = u_feather > 0.01
    ? 1.0 - smoothstep(v_halfWidth - u_feather * 0.5, v_halfWidth + u_feather * 0.5, d)
    : step(d, v_halfWidth);
  if (alpha <= 0.001) discard;
  outColor = vec4(u_color.rgb, u_color.a * alpha);
}
`;

const DOT_VERT_SRC = `#version 300 es
precision highp float;

layout(location = 0) in vec2 a_quad; // [-1, 1] x [-1, 1]

uniform vec2 u_centerPx;
uniform float u_radiusPx;
uniform vec2 u_viewportPx;

out vec2 v_localPx;

void main() {
  float r = u_radiusPx + 1.5;
  vec2 posPx = u_centerPx + a_quad * r;
  vec2 ndc = (posPx / u_viewportPx) * 2.0 - 1.0;
  gl_Position = vec4(ndc, 0.0, 1.0);
  v_localPx = a_quad * r;
}
`;

const DOT_FRAG_SRC = `#version 300 es
precision highp float;

uniform vec4 u_fillColor;
uniform vec4 u_borderColor;
uniform float u_radiusPx;

in vec2 v_localPx;
out vec4 outColor;

void main() {
  float dist = length(v_localPx);
  float outerAlpha = 1.0 - smoothstep(u_radiusPx + 0.25, u_radiusPx + 1.15, dist);
  if (outerAlpha <= 0.001) discard;
  float borderMix = smoothstep(u_radiusPx - 1.5, u_radiusPx - 0.5, dist);
  vec4 col = mix(u_fillColor, u_borderColor, borderMix);
  outColor = vec4(col.rgb, col.a * outerAlpha);
}
`;

function compileShader(gl: WebGL2RenderingContext, type: number, src: string): WebGLShader {
  const shader = gl.createShader(type);
  if (!shader) throw new Error('Failed to create WebGL shader');
  gl.shaderSource(shader, src);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const info = gl.getShaderInfoLog(shader) || 'Unknown shader compile error';
    gl.deleteShader(shader);
    throw new Error(info);
  }
  return shader;
}

function linkProgram(gl: WebGL2RenderingContext, vertSrc: string, fragSrc: string): WebGLProgram {
  const vs = compileShader(gl, gl.VERTEX_SHADER, vertSrc);
  const fs = compileShader(gl, gl.FRAGMENT_SHADER, fragSrc);
  const prog = gl.createProgram();
  if (!prog) throw new Error('Failed to create WebGL program');
  gl.attachShader(prog, vs);
  gl.attachShader(prog, fs);
  gl.linkProgram(prog);
  gl.deleteShader(vs);
  gl.deleteShader(fs);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
    const info = gl.getProgramInfoLog(prog) || 'Unknown link error';
    gl.deleteProgram(prog);
    throw new Error(info);
  }
  return prog;
}

export class WebGLCurveRenderer {
  private gl: WebGL2RenderingContext;
  private lineProgram: WebGLProgram;
  private dotProgram: WebGLProgram;
  private lineVao: WebGLVertexArrayObject;
  private dotVao: WebGLVertexArrayObject;
  private quadVbo: WebGLBuffer;
  private dotQuadVbo: WebGLBuffer;
  private instanceVbo: WebGLBuffer;
  private instanceCapacityBytes = 0;
  private scratchBuf = new Float32Array(0);

  // Uniform locations
  private uScale: WebGLUniformLocation | null;
  private uViewportPx: WebGLUniformLocation | null;
  private uHalfWidth: WebGLUniformLocation | null;
  private uFeather: WebGLUniformLocation | null;
  private uColor: WebGLUniformLocation | null;

  private uDotCenterPx: WebGLUniformLocation | null;
  private uDotRadiusPx: WebGLUniformLocation | null;
  private uDotViewportPx: WebGLUniformLocation | null;
  private uDotFillColor: WebGLUniformLocation | null;
  private uDotBorderColor: WebGLUniformLocation | null;

  constructor(canvas: HTMLCanvasElement) {
    const gl = canvas.getContext('webgl2', {
      alpha: true,
      antialias: false,
      depth: false,
      stencil: false,
      preserveDrawingBuffer: false,
      powerPreference: 'high-performance',
    });
    if (!gl) {
      throw new Error('WebGL2 is not supported in this browser.');
    }
    this.gl = gl;

    this.lineProgram = linkProgram(gl, LINE_VERT_SRC, LINE_FRAG_SRC);
    this.dotProgram = linkProgram(gl, DOT_VERT_SRC, DOT_FRAG_SRC);

    this.uScale = gl.getUniformLocation(this.lineProgram, 'u_scale');
    this.uViewportPx = gl.getUniformLocation(this.lineProgram, 'u_viewportPx');
    this.uHalfWidth = gl.getUniformLocation(this.lineProgram, 'u_halfWidth');
    this.uFeather = gl.getUniformLocation(this.lineProgram, 'u_feather');
    this.uColor = gl.getUniformLocation(this.lineProgram, 'u_color');

    this.uDotCenterPx = gl.getUniformLocation(this.dotProgram, 'u_centerPx');
    this.uDotRadiusPx = gl.getUniformLocation(this.dotProgram, 'u_radiusPx');
    this.uDotViewportPx = gl.getUniformLocation(this.dotProgram, 'u_viewportPx');
    this.uDotFillColor = gl.getUniformLocation(this.dotProgram, 'u_fillColor');
    this.uDotBorderColor = gl.getUniformLocation(this.dotProgram, 'u_borderColor');

    // Line VAO
    this.lineVao = gl.createVertexArray()!;
    gl.bindVertexArray(this.lineVao);

    this.quadVbo = gl.createBuffer()!;
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quadVbo);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([
        0, -1,
        1, -1,
        1, 1,
        0, -1,
        1, 1,
        0, 1,
      ]),
      gl.STATIC_DRAW
    );
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 8, 0);

    // Instance buffer: [p0x, p0y, p1x, p1y] = 16 bytes per segment
    // Packed as 2 * f32 per vertex with stride=8: p0 at offset 0, p1 at offset 8!
    this.instanceVbo = gl.createBuffer()!;
    gl.bindBuffer(gl.ARRAY_BUFFER, this.instanceVbo);
    gl.enableVertexAttribArray(1);
    gl.vertexAttribPointer(1, 2, gl.FLOAT, false, 8, 0);
    gl.vertexAttribDivisor(1, 1);
    gl.enableVertexAttribArray(2);
    gl.vertexAttribPointer(2, 2, gl.FLOAT, false, 8, 8);
    gl.vertexAttribDivisor(2, 1);

    // Dot VAO
    this.dotVao = gl.createVertexArray()!;
    gl.bindVertexArray(this.dotVao);
    this.dotQuadVbo = gl.createBuffer()!;
    gl.bindBuffer(gl.ARRAY_BUFFER, this.dotQuadVbo);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([
        -1, -1,
        1, -1,
        1, 1,
        -1, -1,
        1, 1,
        -1, 1,
      ]),
      gl.STATIC_DRAW
    );
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 8, 0);

    gl.bindVertexArray(null);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
  }

  public beginFrame(widthCss: number, heightCss: number, dpr: number, clearColor: [number, number, number, number]) {
    const gl = this.gl;
    const w = Math.max(1, Math.round(widthCss * dpr));
    const h = Math.max(1, Math.round(heightCss * dpr));
    if (gl.canvas.width !== w || gl.canvas.height !== h) {
      gl.canvas.width = w;
      gl.canvas.height = h;
    }
    gl.disable(gl.SCISSOR_TEST);
    gl.viewport(0, 0, w, h);
    gl.clearColor(clearColor[0], clearColor[1], clearColor[2], clearColor[3]);
    gl.clear(gl.COLOR_BUFFER_BIT);
  }

  public drawPlot(
    rect: ViewportRect,
    canvasHeightCss: number,
    dpr: number,
    curves: CurveRenderInput[],
    dots: DotRenderInput[],
    antialias: boolean
  ) {
    const gl = this.gl;
    if (rect.width <= 1 || rect.height <= 1) return;

    const sx = Math.round(rect.left * dpr);
    const sy = Math.round((canvasHeightCss - (rect.top + rect.height)) * dpr);
    const sw = Math.max(1, Math.round(rect.width * dpr));
    const sh = Math.max(1, Math.round(rect.height * dpr));

    gl.enable(gl.SCISSOR_TEST);
    gl.scissor(sx, sy, sw, sh);
    gl.viewport(sx, sy, sw, sh);

    const spanX = rect.xMax - rect.xMin;
    const spanY = rect.yMax - rect.yMin;
    if (spanX <= 0 || spanY <= 0 || !Number.isFinite(spanX) || !Number.isFinite(spanY)) {
      return;
    }

    const xOrigin = (rect.xMin + rect.xMax) * 0.5;
    const yOrigin = (rect.yMin + rect.yMax) * 0.5;
    const scaleX = 2.0 / spanX;
    const scaleY = 2.0 / spanY;
    const feather = antialias ? 1.15 : 0.0;

    gl.useProgram(this.lineProgram);
    gl.bindVertexArray(this.lineVao);
    gl.uniform2f(this.uScale, scaleX, scaleY);
    gl.uniform2f(this.uViewportPx, rect.width, rect.height);
    gl.uniform1f(this.uFeather, feather);

    for (const curve of curves) {
      const n = Math.min(curve.x.length, curve.y.length);
      if (n < 2) continue;

      const neededFloats = n * 2;
      if (this.scratchBuf.length < neededFloats) {
        this.scratchBuf = new Float32Array(Math.max(neededFloats, this.scratchBuf.length * 2 || 4096));
      }

      const xArr = curve.x;
      const yArr = curve.y;
      const buf = this.scratchBuf;
      for (let i = 0; i < n; i++) {
        buf[i * 2] = xArr[i] - xOrigin;
        buf[i * 2 + 1] = yArr[i] - yOrigin;
      }

      const byteLen = neededFloats * 4;
      gl.bindBuffer(gl.ARRAY_BUFFER, this.instanceVbo);
      if (byteLen > this.instanceCapacityBytes) {
        this.instanceCapacityBytes = Math.max(byteLen, this.instanceCapacityBytes * 2 || 65536);
        gl.bufferData(gl.ARRAY_BUFFER, this.instanceCapacityBytes, gl.DYNAMIC_DRAW);
      }
      gl.bufferSubData(gl.ARRAY_BUFFER, 0, buf.subarray(0, neededFloats));

      gl.uniform1f(this.uHalfWidth, curve.lineWidth * 0.5);
      gl.uniform4f(this.uColor, curve.color[0], curve.color[1], curve.color[2], curve.color[3]);
      gl.drawArraysInstanced(gl.TRIANGLES, 0, 6, n - 1);
    }

    if (dots.length > 0) {
      gl.useProgram(this.dotProgram);
      gl.bindVertexArray(this.dotVao);
      gl.uniform2f(this.uDotViewportPx, rect.width, rect.height);

      for (const dot of dots) {
        if (!Number.isFinite(dot.x) || !Number.isFinite(dot.y)) continue;
        const cx = ((dot.x - rect.xMin) / spanX) * rect.width;
        const cy = ((dot.y - rect.yMin) / spanY) * rect.height;
        gl.uniform2f(this.uDotCenterPx, cx, cy);
        gl.uniform1f(this.uDotRadiusPx, dot.radiusPx);
        gl.uniform4f(this.uDotFillColor, dot.fillColor[0], dot.fillColor[1], dot.fillColor[2], dot.fillColor[3]);
        gl.uniform4f(this.uDotBorderColor, dot.borderColor[0], dot.borderColor[1], dot.borderColor[2], dot.borderColor[3]);
        gl.drawArrays(gl.TRIANGLES, 0, 6);
      }
    }

    gl.bindVertexArray(null);
  }

  public dispose() {
    const gl = this.gl;
    gl.deleteBuffer(this.quadVbo);
    gl.deleteBuffer(this.dotQuadVbo);
    gl.deleteBuffer(this.instanceVbo);
    gl.deleteVertexArray(this.lineVao);
    gl.deleteVertexArray(this.dotVao);
    gl.deleteProgram(this.lineProgram);
    gl.deleteProgram(this.dotProgram);
  }
}

/**
 * Pixel-style chart renderer for card chart specs (see API.md "Card").
 * Draws on a canvas so "Download chart (PNG)" works offline.
 * Chunky bars with ink outlines, square markers, dashed grid, no smoothing.
 *
 *   drawChart(canvas, { type: 'bar', title, x_label, y_label, labels, values });
 *   drawChart(canvas, { type: 'heatmap', title, labels, matrix });   // matrix[i][j] = r, or null
 */

const SERIES = ['--leaf', '--pink', '--blue', '--orange', '--yellow', '--red'];
const HEIGHT = 240;      // the usual canvas height; taller when x labels have to be angled
const MAX_ANGLED = 14;   // characters kept on an angled x label
const LINE_GAP = 34;     // least pixels between two labelled ticks on a line chart (dates stay readable)
let H = HEIGHT;          // height of the chart being drawn right now
const measure = document.createElement('canvas').getContext('2d');

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function theme() {
  return {
    bg: cssVar('--surface') || '#fffaf0',
    ink: cssVar('--text') || '#2b1d14',
    muted: cssVar('--text-muted') || '#5c3b26',
    grid: cssVar('--surface-2') || '#e3d3b0',
    outline: '#2b1d14',
    colors: SERIES.map(cssVar),
    font: '12px ui-monospace, Consolas, monospace',
    titleFont: 'bold 13px ui-monospace, Consolas, monospace',
    charW: 7.2,
  };
}

/** A "nice" axis: [max, step] with round numbers. */
function niceScale(maxValue, ticks = 5) {
  if (!(maxValue > 0)) return [1, 0.2];
  const rough = maxValue / ticks;
  const pow = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map(m => m * pow).find(s => s >= rough) ?? 10 * pow;
  return [Math.ceil(maxValue / step) * step, step];
}

function fmt(n) {
  if (Math.abs(n) >= 1e6) return `${+(n / 1e6).toFixed(1)}M`;
  if (Math.abs(n) >= 1e3) return `${+(n / 1e3).toFixed(1)}k`;
  return String(+n.toFixed(2));
}

function fit(text, maxChars) {
  const s = String(text);
  return s.length > maxChars ? `${s.slice(0, Math.max(1, maxChars - 1))}~` : s;
}

/** Draw `spec` into `canvas`, sized to its container width. */
export function drawChart(canvas, spec) {
  const t = theme();
  const width = Math.max(260, Math.floor(canvas.parentElement?.clientWidth || 480));
  const plan = xPlan(spec, t, width);
  H = HEIGHT + plan.extra;
  const dpr = Math.max(1, Math.round(window.devicePixelRatio || 1));
  canvas.width = width * dpr;
  canvas.height = H * dpr;
  canvas.style.width = `${width}px`;
  canvas.style.height = `${H}px`;
  canvas.setAttribute('role', 'img');
  canvas.setAttribute('aria-label', describe(spec));

  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.imageSmoothingEnabled = false;
  ctx.fillStyle = t.bg;
  ctx.fillRect(0, 0, width, H);

  ctx.fillStyle = t.ink;
  ctx.font = t.titleFont;
  ctx.textBaseline = 'top';
  ctx.fillText(fit(spec.title ?? '', Math.floor((width - 24) / (t.charW + 1))), 12, 10);

  const draw = { bar: drawBars, hist: drawBars, hbar: drawHBars, line: drawLine, scatter: drawScatter, box: drawBox, heatmap: drawHeatmap }[spec.type];
  if (draw) draw(ctx, spec, t, width, plan);
  else {
    ctx.font = t.font;
    ctx.fillText(`(chart type "${spec.type}" not supported yet)`, 12, H / 2);
  }
}

/** Short text alternative for screen readers. */
function describe(spec) {
  const kind = { bar: 'Bar chart', hist: 'Histogram', hbar: 'Bar chart', line: 'Line chart', scatter: 'Scatter plot', box: 'Box plot', heatmap: 'Correlation heatmap' }[spec.type] ?? 'Chart';
  if (spec.type === 'heatmap') return `${kind}: ${spec.title ?? ''}. Columns: ${(spec.labels ?? []).join(', ')}. Correlation does not prove causation.`;
  if (spec.type === 'box') return `${kind}: ${spec.x_label ?? ''}. Median ${spec.median}, quartiles ${spec.q1} to ${spec.q3}, ${spec.outliers?.length ?? 0} outliers.`;
  if (spec.type === 'scatter') return `${kind}: ${spec.title ?? ''}, ${spec.points?.length ?? 0} points.`;
  const pairs = (spec.labels ?? []).slice(0, 8).map((l, i) => `${l} ${fmt(spec.values?.[i] ?? 0)}`).join(', ');
  return `${kind}: ${spec.title ?? ''}. ${pairs}`;
}

// ------------------------------------------------------------------ pieces

function plotArea(width, left = 52, bottom = 40) {
  return { x0: left, y0: 48, x1: width - 16, y1: H - bottom };  // y0 leaves room for title + y label
}

/**
 * How to write the x labels: flat if they fit under their bars, otherwise at 45 degrees (long words
 * and dates like "2025-10" fit that way), with `extra` pixels of canvas height to hold them.
 */
function xPlan(spec, t, width) {
  const flat = { angle: 0, extra: 0, every: 1 };
  if (spec.type === 'heatmap') return heatPlan(spec, t, width);
  if (!['bar', 'hist', 'line'].includes(spec.type)) return flat;
  const labels = (spec.labels ?? []).map(String);
  const line = spec.type === 'line';
  const slot = (width - 16 - 52) / Math.max(1, labels.length);
  measure.font = t.font;
  const widest = text => labels.reduce((m, l) => Math.max(m, measure.measureText(text(l)).width), 0);
  if (widest(l => l) <= slot - 6) return { ...flat, ticks: line };
  const bottom = 34 + Math.ceil(widest(l => fit(l, MAX_ANGLED)) * Math.SQRT1_2);   // labels + gap + x title
  // A line chart is a time axis: label every few points (spaced LINE_GAP apart) rather than crowd every one.
  const pitch = (width - 16 - 52 - 20) / Math.max(1, labels.length - 1);
  const every = line ? Math.max(1, Math.ceil(LINE_GAP / pitch)) : Math.max(1, Math.ceil(18 / slot));
  return { angle: -Math.PI / 4, extra: bottom - 40, every, ticks: line };
}

/** The x labels under the axis: `x(i)` is where label i belongs. Angled labels end at their tick. */
function xLabels(ctx, a, t, labels, x, plan) {
  ctx.font = t.font;
  ctx.fillStyle = t.ink;
  const last = labels.length - 1;
  labels.forEach((label, i) => {
    // line charts also label the final point when there is room, so the axis shows where the data ends
    const showLast = plan.ticks && i === last && i % plan.every >= plan.every / 2;
    if (i % plan.every && !showLast) return;
    if (plan.ticks) {                                   // a small tick joins each label to its point
      ctx.fillStyle = t.ink;
      ctx.fillRect(Math.round(x(i)) - 1, a.y1 + 2, 2, 4);
    }
    if (!plan.angle) {
      ctx.fillStyle = t.ink;
      ctx.textBaseline = 'top';
      ctx.textAlign = 'center';
      ctx.fillText(String(label), Math.round(x(i)), a.y1 + 8);
      return;
    }
    ctx.save();
    ctx.translate(Math.round(x(i)), a.y1 + 8);
    ctx.rotate(plan.angle);
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'right';
    ctx.fillText(fit(label, MAX_ANGLED), 0, 0);
    ctx.restore();
  });
  ctx.textAlign = 'left';
}

function gridY(ctx, a, t, max, step) {
  ctx.font = t.font;
  ctx.textBaseline = 'middle';
  ctx.textAlign = 'right';
  for (let v = 0; v <= max + step / 2; v += step) {
    const y = Math.round(a.y1 - (v / max) * (a.y1 - a.y0)) + 0.5;
    ctx.strokeStyle = t.grid;
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath(); ctx.moveTo(a.x0, y); ctx.lineTo(a.x1, y); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = t.muted;
    ctx.fillText(fmt(v), a.x0 - 6, y);
  }
  ctx.textAlign = 'left';
}

function axes(ctx, a, t, spec) {
  ctx.fillStyle = t.ink;
  ctx.fillRect(a.x0 - 2, a.y0, 2, a.y1 - a.y0 + 2);   // y axis
  ctx.fillRect(a.x0 - 2, a.y1, a.x1 - a.x0 + 2, 2);   // x axis
  ctx.font = t.font;
  ctx.fillStyle = t.muted;
  ctx.textBaseline = 'alphabetic';
  if (spec.y_label) ctx.fillText(fit(spec.y_label, 30), a.x0 - 2, a.y0 - 12);
  if (spec.x_label) {
    ctx.textAlign = 'center';
    ctx.fillText(fit(spec.x_label, 40), (a.x0 + a.x1) / 2, H - 6);
    ctx.textAlign = 'left';
  }
}

function block(ctx, x, y, w, h, color, t) {
  x = Math.round(x); y = Math.round(y); w = Math.round(w); h = Math.round(h);
  if (w <= 0 || h <= 0) return;
  ctx.fillStyle = t.outline;
  ctx.fillRect(x, y, w, h);
  if (w > 4 && h > 4) {
    ctx.fillStyle = color;
    ctx.fillRect(x + 2, y + 2, w - 4, h - 4);
    // 2px highlight on the left edge, the pixel-art way
    ctx.fillStyle = 'rgba(255,255,255,0.25)';
    ctx.fillRect(x + 2, y + 2, 2, h - 4);
  }
}

function drawBars(ctx, spec, t, width, plan) {
  const labels = spec.labels ?? [];
  const values = (spec.values ?? []).map(Number);
  const a = plotArea(width, 52, 40 + plan.extra);
  const [max, step] = niceScale(Math.max(...values, 0));
  gridY(ctx, a, t, max, step);
  const n = Math.max(1, values.length);
  const slot = (a.x1 - a.x0) / n;
  const gap = spec.type === 'hist' ? 2 : Math.max(4, slot * 0.28);

  values.forEach((v, i) => {
    const h = (v / max) * (a.y1 - a.y0);
    const x = a.x0 + i * slot + gap / 2;
    const color = spec.type === 'hist' ? t.colors[0] : t.colors[i % t.colors.length];
    block(ctx, x, a.y1 - h, slot - gap, h, color, t);
  });
  xLabels(ctx, a, t, labels, i => a.x0 + i * slot + slot / 2, plan);
  axes(ctx, a, t, spec);
}

function drawHBars(ctx, spec, t, width) {
  const labels = (spec.labels ?? []).map(String);
  const values = (spec.values ?? []).map(Number);
  const labelChars = Math.min(16, Math.max(4, ...labels.map(l => l.length)));
  const a = plotArea(width, 16 + labelChars * t.charW);
  a.y1 = H - 40;                                       // room for the value ticks and the x title
  const [max, step] = niceScale(Math.max(...values, 0), 4);
  const n = Math.max(1, values.length);
  const slot = (a.y1 - a.y0) / n;
  const gap = Math.max(4, slot * 0.25);

  // vertical grid + value ticks along the bottom
  ctx.font = t.font;
  for (let v = 0; v <= max + step / 2; v += step) {
    const x = Math.round(a.x0 + (v / max) * (a.x1 - a.x0)) + 0.5;
    ctx.strokeStyle = t.grid; ctx.lineWidth = 1; ctx.setLineDash([4, 4]);
    ctx.beginPath(); ctx.moveTo(x, a.y0); ctx.lineTo(x, a.y1); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = t.muted; ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    ctx.fillText(fmt(v), x, a.y1 + 8);
  }
  values.forEach((v, i) => {
    const w = (v / max) * (a.x1 - a.x0);
    const y = a.y0 + i * slot + gap / 2;
    block(ctx, a.x0, y, w, slot - gap, t.colors[i % t.colors.length], t);
    ctx.fillStyle = t.ink; ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    ctx.fillText(fit(labels[i] ?? '', labelChars), a.x0 - 8, Math.round(y + (slot - gap) / 2));
  });
  ctx.textAlign = 'left';
  ctx.fillStyle = t.ink;
  ctx.fillRect(a.x0 - 2, a.y0, 2, a.y1 - a.y0 + 2);
  ctx.fillRect(a.x0 - 2, a.y1, a.x1 - a.x0 + 2, 2);
  if (spec.x_label) {
    ctx.fillStyle = t.muted;
    ctx.textBaseline = 'alphabetic';
    ctx.textAlign = 'center';
    ctx.fillText(fit(spec.x_label, 40), (a.x0 + a.x1) / 2, H - 6);
    ctx.textAlign = 'left';
  }
}

function drawLine(ctx, spec, t, width, plan) {
  const labels = spec.labels ?? [];
  const values = (spec.values ?? []).map(Number);
  const a = plotArea(width, 52, 40 + plan.extra);
  const [max, step] = niceScale(Math.max(...values, 0));
  gridY(ctx, a, t, max, step);
  const n = Math.max(2, values.length);
  const px = i => Math.round(a.x0 + 10 + (i / (n - 1)) * (a.x1 - a.x0 - 20));
  const py = v => Math.round(a.y1 - (v / max) * (a.y1 - a.y0));

  ctx.strokeStyle = t.colors[2];
  ctx.lineWidth = 3;
  ctx.lineCap = 'square';
  ctx.lineJoin = 'miter';
  ctx.beginPath();
  values.forEach((v, i) => (i ? ctx.lineTo(px(i), py(v)) : ctx.moveTo(px(i), py(v))));
  ctx.stroke();
  values.forEach((v, i) => block(ctx, px(i) - 5, py(v) - 5, 10, 10, t.colors[1], t));

  xLabels(ctx, a, t, labels, px, plan);
  axes(ctx, a, t, spec);
}

function drawScatter(ctx, spec, t, width) {
  const pts = (spec.points ?? []).map(([x, y]) => [Number(x), Number(y)])
    .filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y));
  const a = plotArea(width);
  if (!pts.length) return axes(ctx, a, t, spec);
  const range = (values) => {
    let lo = Math.min(...values), hi = Math.max(...values);
    if (lo === hi) { lo -= 1; hi += 1; }
    return [lo, hi];
  };
  const [xmin, xmax] = range(pts.map(p => p[0]));
  const [ymin, ymax] = range(pts.map(p => p[1]));
  const px = x => a.x0 + (x - xmin) / (xmax - xmin) * (a.x1 - a.x0);
  const py = y => a.y1 - (y - ymin) / (ymax - ymin) * (a.y1 - a.y0);
  ctx.font = t.font;
  ctx.fillStyle = t.muted;
  ctx.textBaseline = 'top';
  ctx.textAlign = 'center';
  for (let i = 0; i <= 4; i++) {
    const x = xmin + (xmax - xmin) * i / 4;
    ctx.fillText(fmt(x), Math.round(px(x)), a.y1 + 8);
  }
  ctx.textBaseline = 'middle';
  ctx.textAlign = 'right';
  for (let i = 0; i <= 4; i++) {
    const y = ymin + (ymax - ymin) * i / 4;
    ctx.fillText(fmt(y), a.x0 - 6, Math.round(py(y)));
  }
  ctx.textAlign = 'left';
  for (const [x, y] of pts) {
    block(ctx, px(x) - 4, py(y) - 4, 9, 9, t.colors[0], t);
  }
  axes(ctx, a, t, spec);
}

// ------------------------------------------------------------------ box plot

function drawBox(ctx, spec, t, width) {
  const values = [spec.min, spec.q1, spec.median, spec.q3, spec.max, ...(spec.outliers ?? [])]
    .map(Number).filter(Number.isFinite);
  const a = plotArea(width, 62, 54);
  if (values.length < 5) return axes(ctx, a, t, spec);
  let lo = Math.min(...values), hi = Math.max(...values);
  if (lo === hi) { lo -= 1; hi += 1; }
  const pad = (hi - lo) * 0.08;
  lo -= pad; hi += pad;
  const py = v => a.y1 - (v - lo) / (hi - lo) * (a.y1 - a.y0);
  const mid = Math.round((a.x0 + a.x1) / 2);
  const half = Math.min(52, (a.x1 - a.x0) / 5);
  ctx.font = t.font;
  ctx.fillStyle = t.muted;
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let i = 0; i <= 4; i++) {
    const v = lo + (hi - lo) * i / 4;
    ctx.fillText(fmt(v), a.x0 - 6, py(v));
  }
  ctx.strokeStyle = t.outline;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(mid, py(spec.min)); ctx.lineTo(mid, py(spec.max));
  for (const v of [spec.min, spec.max]) {
    ctx.moveTo(mid - half / 2, py(v)); ctx.lineTo(mid + half / 2, py(v));
  }
  ctx.stroke();
  const top = py(spec.q3), bottom = py(spec.q1);
  ctx.fillStyle = t.colors[0] || t.grid;
  ctx.fillRect(mid - half, top, half * 2, Math.max(1, bottom - top));
  ctx.strokeRect(mid - half, top, half * 2, Math.max(1, bottom - top));
  ctx.beginPath(); ctx.moveTo(mid - half, py(spec.median));
  ctx.lineTo(mid + half, py(spec.median)); ctx.stroke();
  ctx.fillStyle = t.colors[5] || t.ink;
  for (const v of spec.outliers ?? []) {
    if (!Number.isFinite(Number(v))) continue;
    ctx.beginPath(); ctx.arc(mid, py(Number(v)), 3, 0, Math.PI * 2); ctx.fill();
  }
  ctx.fillStyle = t.ink;
  ctx.textAlign = 'center'; ctx.textBaseline = 'top';
  ctx.fillText(fit(spec.x_label ?? '', 30), mid, a.y1 + 10);
}

// ------------------------------------------------------------------ heatmap

const HEAT_FALLBACK = { bg: '#fffaf0', blue: '#4a6fa5', red: '#c8473d' };

function rgb(css, fallback) {
  const m = /^#([0-9a-f]{6})$/i.exec(String(css).trim()) ?? /^#([0-9a-f]{6})$/i.exec(fallback);
  return [0, 2, 4].map(i => parseInt(m[1].slice(i, i + 2), 16));
}

/** Pale at r = 0, blue towards -1, red towards +1 (the theme's own blue and red; the pale end is the card background). */
function heatColor(r, t) {
  const from = rgb(t.bg, HEAT_FALLBACK.bg);
  const to = rgb(r < 0 ? t.colors[2] : t.colors[5], r < 0 ? HEAT_FALLBACK.blue : HEAT_FALLBACK.red);
  const k = Math.min(1, Math.abs(r));
  const c = from.map((v, i) => Math.round(v + (to[i] - v) * k));
  const light = (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) / 255 > 0.5;
  return { fill: `rgb(${c.join(',')})`, text: light ? '#2b1d14' : '#fffaf0' };
}

/** Sizes for the heatmap: square cells that fit the width, and the canvas height they need. */
function heatPlan(spec, t, width) {
  const labels = (spec.labels ?? []).map(String);
  const n = Math.max(1, labels.length);
  measure.font = t.font;
  const rowChars = Math.min(MAX_ANGLED, Math.max(4, ...labels.map(l => l.length)));
  const left = 20 + rowChars * t.charW;
  const cell = Math.max(10, Math.min(44, Math.floor((width - left - 16) / n)));
  const colLabels = Math.ceil(Math.max(...labels.map(l => measure.measureText(fit(l, MAX_ANGLED)).width), 0) * Math.SQRT1_2) + 10;
  const top = 36;
  const needed = top + cell * n + colLabels + 64;       // grid + column labels + colour legend + caption
  return { angle: 0, every: 1, extra: Math.max(0, needed - HEIGHT), heat: { n, left, cell, top, colLabels, rowChars } };
}

function drawHeatmap(ctx, spec, t, width, plan) {
  const { n, left, cell, top, colLabels, rowChars } = plan.heat;
  const labels = (spec.labels ?? []).map(String);
  const matrix = spec.matrix ?? [];
  const gridW = cell * n;
  const x0 = left + Math.max(0, Math.floor((width - left - 16 - gridW) / 2));
  const showValues = cell >= 34;

  ctx.font = showValues ? '10px ui-monospace, Consolas, monospace' : t.font;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  let missing = false;
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      const r = matrix[i]?.[j];
      const x = x0 + j * cell, y = top + i * cell;
      if (typeof r !== 'number' || !Number.isFinite(r)) {       // no r for this pair (constant column, too few shared rows)
        missing = true;
        ctx.fillStyle = t.grid;
        ctx.fillRect(x, y, cell - 1, cell - 1);
        ctx.fillStyle = t.muted;
        ctx.fillText('-', x + cell / 2, y + cell / 2);
        continue;
      }
      const c = heatColor(r, t);
      ctx.fillStyle = c.fill;
      ctx.fillRect(x, y, cell - 1, cell - 1);
      if (showValues) {
        ctx.fillStyle = c.text;
        ctx.fillText((Math.round(r * 100) / 100 + 0).toFixed(2), x + (cell - 1) / 2, y + (cell - 1) / 2);   // + 0: no "-0.00"
      }
    }
  }
  ctx.fillStyle = t.outline;                                    // ink frame, like the other charts' axes
  ctx.fillRect(x0 - 2, top - 2, gridW + 2, 2);
  ctx.fillRect(x0 - 2, top - 2, 2, cell * n + 2);

  ctx.font = t.font;
  ctx.fillStyle = t.ink;
  ctx.textAlign = 'right';
  labels.forEach((l, i) => ctx.fillText(fit(l, rowChars), x0 - 8, top + i * cell + (cell - 1) / 2));
  labels.forEach((l, j) => {                                    // column names at 45 degrees, ending under their column
    ctx.save();
    ctx.translate(x0 + j * cell + (cell - 1) / 2, top + cell * n + 8);
    ctx.rotate(-Math.PI / 4);
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'right';
    ctx.fillText(fit(l, MAX_ANGLED), 0, 0);
    ctx.restore();
  });

  // legend: -1 .. 0 .. +1 on the same scale as the cells
  const ly = top + cell * n + colLabels + 10;
  const lw = Math.min(gridW, 200), lx = x0 + Math.floor((gridW - lw) / 2);
  const steps = 40;
  for (let k = 0; k < steps; k++) {
    ctx.fillStyle = heatColor(-1 + (2 * (k + 0.5)) / steps, t).fill;
    ctx.fillRect(Math.round(lx + (k * lw) / steps), ly, Math.ceil(lw / steps), 10);
  }
  ctx.fillStyle = t.outline;
  ctx.fillRect(lx - 1, ly - 1, lw + 2, 1);
  ctx.fillRect(lx - 1, ly + 10, lw + 2, 1);
  ctx.fillStyle = t.muted;
  ctx.textBaseline = 'top';
  ctx.textAlign = 'left';   ctx.fillText('-1', lx, ly + 14);
  ctx.textAlign = 'center'; ctx.fillText('0', lx + lw / 2, ly + 14);
  ctx.textAlign = 'right';  ctx.fillText('+1', lx + lw, ly + 14);
  if (missing) {
    ctx.textAlign = 'left';
    ctx.fillText('- = no r', Math.min(lx + lw + 10, width - 70), ly - 1);
  }
  ctx.textAlign = 'left';
  ctx.fillText(fit('Correlation does not prove causation.', Math.floor((width - 24) / t.charW)), 12, H - 18);
}
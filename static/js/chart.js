/**
 * Pixel-style chart renderer for card chart specs (see API.md "Card").
 * Draws on a canvas so "Download chart (PNG)" works offline.
 * Chunky bars with ink outlines, square markers, dashed grid, no smoothing.
 *
 *   drawChart(canvas, { type: 'bar', title, x_label, y_label, labels, values });
 */

const SERIES = ['--leaf', '--pink', '--blue', '--orange', '--yellow', '--red'];
const HEIGHT = 240;

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function theme() {
  const fallback = document.documentElement.classList.contains('font-fallback');
  return {
    bg: cssVar('--surface') || '#fffaf0',
    ink: cssVar('--text') || '#2b1d14',
    muted: cssVar('--text-muted') || '#5c3b26',
    grid: cssVar('--surface-2') || '#e3d3b0',
    outline: '#2b1d14',
    colors: SERIES.map(cssVar),
    font: fallback ? '12px ui-monospace, Consolas, monospace' : '8px PressStart, monospace',
    titleFont: fallback ? 'bold 13px ui-monospace, Consolas, monospace' : '9px PressStart, monospace',
    charW: fallback ? 7.2 : 8,
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
  const dpr = Math.max(1, Math.round(window.devicePixelRatio || 1));
  canvas.width = width * dpr;
  canvas.height = HEIGHT * dpr;
  canvas.style.width = `${width}px`;
  canvas.style.height = `${HEIGHT}px`;
  canvas.setAttribute('role', 'img');
  canvas.setAttribute('aria-label', describe(spec));

  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.imageSmoothingEnabled = false;
  ctx.fillStyle = t.bg;
  ctx.fillRect(0, 0, width, HEIGHT);

  ctx.fillStyle = t.ink;
  ctx.font = t.titleFont;
  ctx.textBaseline = 'top';
  ctx.fillText(fit(spec.title ?? '', Math.floor((width - 24) / (t.charW + 1))), 12, 10);

  const draw = { bar: drawBars, hist: drawBars, hbar: drawHBars, line: drawLine, scatter: drawScatter }[spec.type];
  if (draw) draw(ctx, spec, t, width);
  else {
    ctx.font = t.font;
    ctx.fillText(`(chart type "${spec.type}" not supported yet)`, 12, HEIGHT / 2);
  }
}

/** Short text alternative for screen readers. */
function describe(spec) {
  const kind = { bar: 'Bar chart', hist: 'Histogram', hbar: 'Bar chart', line: 'Line chart', scatter: 'Scatter plot' }[spec.type] ?? 'Chart';
  if (spec.type === 'scatter') return `${kind}: ${spec.title ?? ''}, ${spec.points?.length ?? 0} points.`;
  const pairs = (spec.labels ?? []).slice(0, 8).map((l, i) => `${l} ${fmt(spec.values?.[i] ?? 0)}`).join(', ');
  return `${kind}: ${spec.title ?? ''}. ${pairs}`;
}

// ------------------------------------------------------------------ pieces

function plotArea(width, left = 52) {
  return { x0: left, y0: 48, x1: width - 16, y1: HEIGHT - 40 };  // y0 leaves room for title + y label
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
    ctx.textAlign = 'right';
    ctx.fillText(fit(spec.x_label, 30), a.x1, HEIGHT - 6);
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

function drawBars(ctx, spec, t, width) {
  const labels = spec.labels ?? [];
  const values = (spec.values ?? []).map(Number);
  const a = plotArea(width);
  const [max, step] = niceScale(Math.max(...values, 0));
  gridY(ctx, a, t, max, step);
  const n = Math.max(1, values.length);
  const slot = (a.x1 - a.x0) / n;
  const gap = spec.type === 'hist' ? 2 : Math.max(4, slot * 0.28);
  const maxChars = Math.max(2, Math.floor(slot / t.charW));
  const every = Math.ceil((t.charW * 4) / slot);       // skip labels if crowded

  values.forEach((v, i) => {
    const h = (v / max) * (a.y1 - a.y0);
    const x = a.x0 + i * slot + gap / 2;
    const color = spec.type === 'hist' ? t.colors[0] : t.colors[i % t.colors.length];
    block(ctx, x, a.y1 - h, slot - gap, h, color, t);
    if (i % every === 0) {
      ctx.font = t.font;
      ctx.fillStyle = t.ink;
      ctx.textBaseline = 'top';
      ctx.textAlign = 'center';
      ctx.fillText(fit(labels[i] ?? '', maxChars * every), Math.round(a.x0 + i * slot + slot / 2), a.y1 + 8);
      ctx.textAlign = 'left';
    }
  });
  axes(ctx, a, t, { ...spec, x_label: null });
}

function drawHBars(ctx, spec, t, width) {
  const labels = (spec.labels ?? []).map(String);
  const values = (spec.values ?? []).map(Number);
  const labelChars = Math.min(16, Math.max(4, ...labels.map(l => l.length)));
  const a = plotArea(width, 16 + labelChars * t.charW);
  a.y1 = HEIGHT - 30;
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
}

function drawLine(ctx, spec, t, width) {
  const labels = spec.labels ?? [];
  const values = (spec.values ?? []).map(Number);
  const a = plotArea(width);
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

  const every = Math.ceil((t.charW * 4) / ((a.x1 - a.x0) / n));
  ctx.font = t.font; ctx.fillStyle = t.ink; ctx.textBaseline = 'top'; ctx.textAlign = 'center';
  labels.forEach((l, i) => i % every === 0 && ctx.fillText(fit(l, 4), px(i), a.y1 + 8));
  ctx.textAlign = 'left';
  axes(ctx, a, t, { ...spec, x_label: null });
}

function drawScatter(ctx, spec, t, width) {
  const pts = (spec.points ?? []).map(([x, y]) => [Number(x), Number(y)]);
  const a = plotArea(width);
  const [ymax, ystep] = niceScale(Math.max(...pts.map(p => p[1]), 0));
  const [xmax, xstep] = niceScale(Math.max(...pts.map(p => p[0]), 0));
  gridY(ctx, a, t, ymax, ystep);
  ctx.font = t.font; ctx.fillStyle = t.muted; ctx.textBaseline = 'top'; ctx.textAlign = 'center';
  for (let v = 0; v <= xmax + xstep / 2; v += xstep) {
    ctx.fillText(fmt(v), Math.round(a.x0 + (v / xmax) * (a.x1 - a.x0)), a.y1 + 8);
  }
  ctx.textAlign = 'left';
  for (const [x, y] of pts) {
    if (y < 0 || x < 0) continue;
    block(ctx, a.x0 + (x / xmax) * (a.x1 - a.x0) - 4, a.y1 - (y / ymax) * (a.y1 - a.y0) - 4, 9, 9, t.colors[0], t);
  }
  axes(ctx, a, t, spec);
}

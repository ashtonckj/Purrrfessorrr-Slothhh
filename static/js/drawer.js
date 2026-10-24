/**
 * Results drawer: slides in over the office and shows one cat's cards as
 * accordion "dropdowns" (chart, data preview, code, downloads).
 * Opened by the `drawer:open { cat }` bus event (cat click or Results button).
 */
import { CAT_ICONS, CAT_IDS, DRAWER, NAMES, ROLES } from '../copy.js';
import * as api from './api.js';
import { on } from './bus.js';
import { drawChart } from './chart.js';
import { copyButton, renderCode } from './codebox.js';
import { createSprite } from './sprites.js';
import { el, icon, prefersReducedMotion } from './ui.js';

const TABLE_ROWS = 10;   // rows a table shows before "show more"
const MORE_ROWS = 50;    // rows each "show more" adds

const state = {
  jobId: null,
  done: false,
  results: {},     // cat -> cards
  errors: {},      // cat -> message
  cat: null,
  opener: null,    // element to refocus on close
};

let drawer, avatarSlot, titleEl, roleEl, body, tabs, zipLink, nbLink, lockNote;

export function initDrawer(container) {
  avatarSlot = el('span', { class: 'drawer__avatar' });
  titleEl = el('h2', { class: 'drawer__title', id: 'drawer-title' });
  roleEl = el('p', { class: 'drawer__role' });
  body = el('div', { class: 'drawer__body' });
  tabs = el('nav', { class: 'drawer__tabs', 'aria-label': 'Cats' },
    CAT_IDS.map(cat => el('button', {
      type: 'button', class: 'drawer__tab', 'data-cat': cat, 'aria-label': DRAWER.switchTo(NAMES[cat]),
      title: NAMES[cat], onclick: () => show(cat),
    }, createSprite(CAT_ICONS[cat], { scale: 2 }))));

  zipLink = el('a', { class: 'btn btn--primary', 'aria-disabled': 'true' }, icon('download'), DRAWER.downloadZip);
  nbLink = el('a', { class: 'btn', 'aria-disabled': 'true' }, icon('download'), DRAWER.exportNotebook);
  lockNote = el('span', { class: 'drawer__lock', text: DRAWER.exportsLocked });

  drawer = el('aside', { class: 'drawer', hidden: true, role: 'dialog', 'aria-modal': 'false',
    'aria-labelledby': 'drawer-title' },
    el('div', { class: 'px-frame drawer__frame' },
      el('div', { class: 'drawer__fill px-fill' },
        el('header', { class: 'drawer__head' },
          avatarSlot,
          el('div', { class: 'drawer__who' }, titleEl, roleEl),
          el('button', { type: 'button', class: 'btn btn--icon', 'aria-label': DRAWER.close, title: DRAWER.close,
            onclick: close }, icon('close'))),
        tabs,
        body,
        el('footer', { class: 'drawer__foot' }, lockNote, nbLink, zipLink))));
  container.append(drawer);

  drawer.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
  on('drawer:open', ({ cat }) => open(cat));
  on('job:start', ({ jobId }) => {
    Object.assign(state, { jobId, done: false, results: {}, errors: {} });
    setExports();
    if (!drawer.hidden) show(state.cat);
  });
  on('job:result', ({ cat, cards }) => {
    state.results[cat] = cards;
    if (!drawer.hidden && state.cat === cat) show(cat);
  });
  on('card:update', ({ cat, card }) => {     // the chat re-drew a chart: swap it in, by id
    const cards = state.results[cat];
    if (!cards) return;
    const i = cards.findIndex(c => c.id === card.id);
    if (i >= 0) cards[i] = card; else cards.unshift(card);
    if (!drawer.hidden && state.cat === cat) show(cat);
  });
  on('job:error', ({ cat, message }) => {
    if (!cat) return;
    state.errors[cat] = message;
    if (!drawer.hidden && state.cat === cat) show(cat);
  });
  on('job:done', () => { state.done = true; setExports(); });
  setExports();
}

// ------------------------------------------------------------ open / close

function open(cat) {
  state.opener = document.activeElement;
  drawer.hidden = false;
  drawer.classList.remove('is-open');
  void drawer.offsetWidth;            // restart the slide-in
  drawer.classList.add('is-open');
  show(cat);
  drawer.querySelector('.drawer__head .btn').focus();
}

function close() {
  drawer.classList.remove('is-open');
  const finish = () => {
    drawer.hidden = true;
    state.opener?.focus?.();
  };
  if (prefersReducedMotion()) finish();
  else setTimeout(finish, 240);
}

function setExports() {
  const ready = Boolean(state.jobId && state.done);
  for (const [link, kind] of [[zipLink, 'zip'], [nbLink, 'notebook']]) {
    if (ready) {
      link.href = api.exportUrl(state.jobId, kind);
      link.setAttribute('download', '');
      link.removeAttribute('aria-disabled');
    } else {
      link.removeAttribute('href');
      link.setAttribute('aria-disabled', 'true');
    }
  }
  lockNote.hidden = ready;
}

// ------------------------------------------------------------------- view

async function show(cat) {
  state.cat = cat;
  avatarSlot.replaceChildren(createSprite(`avatar_${cat}`, { scale: 1, alt: '' }));
  titleEl.textContent = NAMES[cat];
  roleEl.textContent = ROLES[cat];
  tabs.querySelectorAll('.drawer__tab').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.cat === cat)));

  let cards = state.results[cat];
  // Not seen on the stream (e.g. page reloaded mid-job)? Ask the API.
  if (!cards && state.jobId && !state.errors[cat]) {
    try {
      const res = await api.getResults(state.jobId, cat);
      if (res.ready) cards = state.results[cat] = res.cards;
    } catch { /* fall through to the empty state */ }
    if (state.cat !== cat) return;    // user switched cats meanwhile
  }

  body.replaceChildren();
  body.scrollTop = 0;
  if (state.errors[cat]) return body.append(emptyState(cat, DRAWER.empty.error(state.errors[cat]), 'error'));
  if (!state.jobId) return body.append(emptyState(cat, DRAWER.empty.noJob, 'idle'));
  if (!cards) return body.append(emptyState(cat, DRAWER.empty.working, 'work'));
  if (!cards.length) return body.append(emptyState(cat, DRAWER.empty.none, 'done'));

  cards.forEach((card, i) => body.append(renderCard(cat, card, i === 0)));
}

function emptyState(cat, text, mood) {
  return el('div', { class: 'drawer__empty' },
    createSprite(`${cat}_${mood}`, { scale: 3, alt: NAMES[cat] }),
    el('p', { text }));
}

// ------------------------------------------------------------------- card

export function renderCard(cat, card, openByDefault) {
  const details = el('details', { class: 'card px-fill' });
  details.open = openByDefault;

  const summary = el('summary', { class: 'card__head' },
    el('span', { class: 'card__title', text: card.title }),
    card.severity ? el('span', { class: `tag tag--${card.severity}`, text: DRAWER.severity[card.severity] ?? card.severity,
      title: DRAWER.severityHelp[card.severity] }) : null,
    el('span', { class: 'card__chevron' }, icon('chevron', { scale: 1 })));

  const content = el('div', { class: 'card__body' });
  if (card.description) content.append(el('p', { class: 'card__desc', text: card.description }));

  let canvas = null;
  if (card.chart) {
    canvas = el('canvas', { class: 'card__canvas' });
    content.append(el('div', { class: 'card__chart' }, canvas));
  }
  if (card.id === 'artist-scatter' && card.chart?.type === 'scatter' && card.scatter_columns?.length) {
    const columns = card.scatter_columns;
    const selector = (axis, selected) => el('select', { 'aria-label': `Scatter ${axis} column` },
      columns.map(name => el('option', { value: name, text: name, selected: name === selected })));
    const x = selector('X', card.chart.x_label);
    const y = selector('Y', card.chart.y_label);
    const message = el('p', { role: 'alert', 'aria-live': 'polite' });
    const controls = el('div', { class: 'card__scatter-controls' },
      el('label', {}, 'X ', x), el('label', {}, 'Y ', y), message);
    const change = async () => {
      const previousX = card.chart.x_label, previousY = card.chart.y_label;
      x.disabled = y.disabled = true;
      message.textContent = '';
      try {
        if (x.value === y.value) throw new Error('Choose two different columns for X and Y');
        if (!state.jobId) throw new Error('No active analysis');
        const result = await api.redrawScatter(state.jobId, x.value, y.value);
        const cards = state.results[cat];
        const index = cards?.findIndex(item => item.id === card.id) ?? -1;
        if (index >= 0) cards[index] = result.card;
        // Replace just this card so the selected pair's code, table and PNG export update together.
        const replacement = renderCard(cat, result.card, details.open);
        details.parentElement.replaceWith(replacement);
      } catch (error) {
        message.textContent = error.message || 'Could not redraw scatter plot';
        x.value = previousX;
        y.value = previousY;
        x.disabled = y.disabled = false;
      }
    };
    x.addEventListener('change', change);
    y.addEventListener('change', change);
    content.append(controls);
  }
  if (card.table?.columns?.length) content.append(renderTable(card.table));

  let code = null;
  if (card.code?.python || card.code?.r) {
    code = renderCode(card.code, cat === 'coder');
    content.append(code.node);
  }

  const actions = el('div', { class: 'card__actions' });
  if (code) {
    actions.append(copyButton(code.current));
  }
  if (canvas) {
    actions.append(el('button', { type: 'button', class: 'btn', onclick: () => downloadCanvas(canvas, `${card.id}.png`) },
      icon('download', { scale: 1 }), DRAWER.downloadChart));
  }
  if (card.table?.columns?.length) {
    actions.append(el('button', { type: 'button', class: 'btn', onclick: () => downloadCsv(card.table, `${card.id}.csv`) },
      icon('download', { scale: 1 }), DRAWER.downloadData));
  }
  if (actions.childElementCount) content.append(actions);

  details.append(summary, content);
  // Charts need a laid-out width: draw when opened (and again on reopen, to pick up theme changes).
  if (canvas) {
    const paint = () => details.open && drawChart(canvas, card.chart);
    details.addEventListener('toggle', paint);
    requestAnimationFrame(paint);
  }
  return el('div', { class: 'px-frame card__frame' }, details);
}

const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });
const present = v => v != null && v !== '';

/** The number a cell starts with ("1,200-2,300" -> 1200, "2025-10" -> 2025), or NaN. */
function lead(v) {
  const m = String(v).replace(/(\d),(?=\d{3}\b)/g, '$1').match(/^-?\d+(\.\d+)?/);
  return m ? Number(m[0]) : NaN;
}

/** Rows ordered by one column: numbers as numbers, labels by their leading number, then text. Blanks last. */
function sortRows(rows, col, dir) {
  return rows.slice().sort((x, y) => {
    const a = x[col], b = y[col];
    if (!present(a) || !present(b)) return present(b) - present(a);
    const [la, lb] = [lead(a), lead(b)];
    const cmp = typeof a === 'number' && typeof b === 'number' ? a - b
      : la !== lb && Number.isFinite(la) && Number.isFinite(lb) ? la - lb : collator.compare(String(a), String(b));
    return dir === 'asc' ? cmp : -cmp;
  });
}

function renderTable(table) {
  let shown = TABLE_ROWS;
  const sort = { col: 0, dir: 'asc' };       // starts sorted by the first column, ascending
  const wrap = el('div', { class: 'card__table-wrap' });
  // Click a column: ascending, then descending, then the order the cat wrote them in.
  const sortBy = i => {
    if (sort.col !== i) Object.assign(sort, { col: i, dir: 'asc' });
    else if (sort.dir === 'asc') sort.dir = 'desc';
    else Object.assign(sort, { col: null, dir: 'asc' });
  };
  const paint = () => {
    const ordered = sort.col == null ? table.rows : sortRows(table.rows, sort.col, sort.dir);
    const rows = ordered.slice(0, shown);
    const left = table.rows.length - rows.length;
    wrap.replaceChildren(
      el('table', { class: 'card__table' },
        el('caption', { text: DRAWER.rowsShown(rows.length, table.rows.length) }),
        el('thead', {}, el('tr', {}, table.columns.map((c, i) => el('th', { scope: 'col',
          'aria-sort': sort.col === i ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none' },
          el('button', { type: 'button', class: 'card__sort', title: DRAWER.sortBy(String(c)),
            onclick: () => { sortBy(i); paint(); } },
          String(c), el('span', { class: 'card__arrow', 'aria-hidden': 'true',
            text: sort.col === i ? (sort.dir === 'asc' ? '▲' : '▼') : '' })))))),
        el('tbody', {}, rows.map(r => el('tr', {}, r.map(v => el('td', { text: v == null ? '' : String(v) })))))),
      ...(left ? [el('button', { type: 'button', class: 'btn card__more',
        onclick: () => { shown += MORE_ROWS; paint(); } }, DRAWER.moreRows(Math.min(MORE_ROWS, left)))] : []));
  };
  paint();
  return wrap;
}

// ---------------------------------------------------------------- actions

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = el('a', { href: url, download: filename });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function downloadCanvas(canvas, filename) {
  canvas.toBlob(blob => blob && saveBlob(blob, filename), 'image/png');
}

function csvCell(v) {
  const s = v == null ? '' : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function downloadCsv(table, filename) {
  const lines = [table.columns, ...table.rows].map(r => r.map(csvCell).join(','));
  saveBlob(new Blob([lines.join('\n') + '\n'], { type: 'text/csv' }), filename);
}

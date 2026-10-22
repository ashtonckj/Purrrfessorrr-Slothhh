/**
 * Results drawer: slides in over the office and shows one cat's cards as
 * accordion "dropdowns" (chart, data preview, code, downloads).
 * Opened by the `drawer:open { cat }` bus event (cat click or Results button).
 */
import { CAT_ICONS, DRAWER, NAMES, ROLES } from '../copy.js';
import * as api from './api.js';
import { emit, on } from './bus.js';
import { drawChart } from './chart.js';
import { createSprite } from './sprites.js';
import { highlight } from './syntax.js';
import { el, icon, prefersReducedMotion } from './ui.js';

const CAT_IDS = ['detective', 'artist', 'scribe', 'coder', 'janitor'];
const PREVIEW_ROWS = 5;

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

function renderCard(cat, card, openByDefault) {
  const details = el('details', { class: 'card px-fill' });
  details.open = openByDefault;

  const summary = el('summary', { class: 'card__head' },
    el('span', { class: 'card__title', text: card.title }),
    card.severity ? el('span', { class: `tag tag--${card.severity}`, text: DRAWER.severity[card.severity] ?? card.severity }) : null,
    el('span', { class: 'card__chevron' }, icon('chevron', { scale: 1 })));

  const content = el('div', { class: 'card__body' });
  if (card.description) content.append(el('p', { class: 'card__desc', text: card.description }));

  let canvas = null;
  if (card.chart) {
    canvas = el('canvas', { class: 'card__canvas' });
    content.append(el('div', { class: 'card__chart' }, canvas));
  }
  if (card.table?.columns?.length) content.append(renderTable(card.table));

  let code = null;
  if (card.code?.python || card.code?.r) {
    code = renderCode(card.code, cat === 'coder');
    content.append(code.node);
  }

  const actions = el('div', { class: 'card__actions' });
  if (code) {
    const copyBtn = el('button', { type: 'button', class: 'btn' }, icon('copy', { scale: 1 }), el('span', { text: DRAWER.copyCode }));
    copyBtn.addEventListener('click', () => copyCode(copyBtn, code.current()));
    actions.append(copyBtn);
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

function renderTable(table) {
  const rows = table.rows.slice(0, PREVIEW_ROWS);
  return el('div', { class: 'card__table-wrap' },
    el('table', { class: 'card__table' },
      el('caption', { text: DRAWER.preview(Math.min(PREVIEW_ROWS, table.rows.length)) + ` / ${table.rows.length}` }),
      el('thead', {}, el('tr', {}, table.columns.map(c => el('th', { scope: 'col', text: String(c) })))),
      el('tbody', {}, rows.map(r => el('tr', {}, r.map(v => el('td', { text: v == null ? '' : String(v) })))))));
}

/** Code block with a Python / R toggle. R without code shows a disabled "soon" tab. */
function renderCode(code, openByDefault) {
  let lang = code.python ? 'python' : 'r';
  const pre = el('pre', { class: 'code__pre', tabindex: '0' });
  const codeEl = el('code', {});
  pre.append(codeEl);
  const paint = () => {
    codeEl.innerHTML = highlight(code[lang] ?? '', lang);
    codeEl.className = `lang-${lang}`;
    for (const b of toggle.querySelectorAll('button')) b.setAttribute('aria-pressed', String(b.dataset.lang === lang));
  };

  const tab = (id, label) => {
    const available = Boolean(code[id]);
    return el('button', { type: 'button', class: 'code__tab', 'data-lang': id, disabled: !available,
      onclick: () => { lang = id; paint(); } },
      label, available ? null : el('span', { class: 'tag', text: DRAWER.soon }));
  };
  const toggle = el('div', { class: 'code__toggle', role: 'group', 'aria-label': 'Language' },
    tab('python', DRAWER.python), tab('r', DRAWER.r));

  const inner = el('div', { class: 'code' }, toggle, pre);
  paint();

  // Coder Cat shows code up front; other cats tuck it away.
  const node = openByDefault ? inner
    : el('details', { class: 'code__more' }, el('summary', { text: DRAWER.showCode }), inner);
  return { node, current: () => code[lang] ?? '' };
}

// ---------------------------------------------------------------- actions

async function copyCode(btn, text) {
  const label = btn.querySelector('span:last-child');
  let ok = true;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // Fallback for browsers that block the async clipboard API.
    const ta = el('textarea', { style: { position: 'fixed', opacity: '0' } }, text);
    document.body.append(ta);
    ta.select();
    ok = document.execCommand('copy');
    ta.remove();
  }
  label.textContent = ok ? DRAWER.copied : DRAWER.copyFailed;
  btn.querySelector('.sprite')?.replaceWith(icon(ok ? 'check' : 'warning', { scale: 1 }));
  if (ok) emit('sound', { name: 'copy' });
  setTimeout(() => {
    label.textContent = DRAWER.copyCode;
    btn.querySelector('.sprite')?.replaceWith(icon('copy', { scale: 1 }));
  }, 1600);
}

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

/**
 * Chat panel: rendering only (bubbles, typing dots, input, drag & drop).
 * The conversation logic lives in flow.js.
 */
import { CAT_IDS, NAMES, STATUS, UI } from '../copy.js';
import { createSprite } from './sprites.js';
import { el, icon, formatBytes, formatNumber, moodFor, prefersReducedMotion, sleep, timeNow } from './ui.js';

let root, log, field, statusEl, fileInput;
let lastSender = null;

/**
 * @param {HTMLElement} container  the .chat section
 * @param {{ onSend: (text: string) => void, onFiles: (files: File[]) => void }} handlers
 */
export function initChat(container, { onSend, onFiles }) {
  root = container;
  statusEl = el('span', { class: 'chat__status', 'data-status': 'online', text: STATUS.online });
  log = el('div', { class: 'chat__log', id: 'chat-log', role: 'log', 'aria-live': 'polite', 'aria-label': 'Messages' });
  field = el('input', {
    class: 'chat__field', type: 'text', autocomplete: 'off', maxlength: '4000',
    placeholder: UI.inputPlaceholder, 'aria-label': 'Message to the sloth',
  });
  fileInput = el('input', { type: 'file', accept: '.csv,.tsv,.xlsx', class: 'sr-only', tabindex: '-1', 'aria-hidden': 'true' });

  const form = el('form', { class: 'chat__input' },
    el('button', { type: 'button', class: 'btn btn--icon', 'aria-label': UI.attach, title: UI.attach,
      onclick: () => fileInput.click() }, icon('paperclip')),
    field,
    el('button', { type: 'submit', class: 'btn btn--icon btn--primary', 'aria-label': UI.send, title: UI.send },
      icon('send')),
    fileInput,
  );
  form.addEventListener('submit', e => {
    e.preventDefault();
    const text = field.value.trim();
    if (!text) return;
    field.value = '';
    onSend(text);
  });
  fileInput.addEventListener('change', () => {
    if (fileInput.files.length) onFiles([...fileInput.files]);
    fileInput.value = '';
  });

  const drop = el('div', { class: 'chat__drop', hidden: true, 'aria-hidden': 'true' },
    icon('upload', { scale: 4 }), el('span', { text: UI.drop }), el('small', { text: UI.dropHint }));

  root.append(el('div', { class: 'px-frame chat__frame', style: { height: '100%' } },
    el('div', { class: 'chat__fill px-fill' },
      el('header', { class: 'chat__header' },
        createSprite('avatar_sloth', { scale: 1, alt: NAMES.sloth }),
        el('div', { class: 'chat__who' }, el('h2', { class: 'chat__name', text: NAMES.sloth }), statusEl)),
      log,
      form)),
    drop);

  setupDragDrop(drop, onFiles);
  log.append(el('div', { class: 'day-sep', text: UI.today }));
}

function setupDragDrop(drop, onFiles) {
  let depth = 0; // dragenter/leave fire for every child; count them
  const hasFiles = e => [...(e.dataTransfer?.types ?? [])].includes('Files');
  const show = v => { drop.hidden = !v; root.classList.toggle('is-dragging', v); };

  root.addEventListener('dragenter', e => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    depth += 1;
    show(true);
  });
  root.addEventListener('dragover', e => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  });
  root.addEventListener('dragleave', e => {
    if (!hasFiles(e)) return;
    depth = Math.max(0, depth - 1);
    if (depth === 0) show(false);
  });
  root.addEventListener('drop', e => {
    if (!hasFiles(e)) return;
    e.preventDefault();
    depth = 0;
    show(false);
    const files = [...e.dataTransfer.files];
    if (files.length) onFiles(files);
  });
  // Dropping a file anywhere else would make the browser navigate to it.
  window.addEventListener('dragover', e => e.preventDefault());
  window.addEventListener('drop', e => e.preventDefault());
}

function scrollToEnd() {
  log.scrollTo({ top: log.scrollHeight, behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
}

/**
 * Add a message.
 * @param {object} m
 * @param {'sloth'|'user'|'detective'|'artist'|'scribe'|'coder'|'janitor'} m.from
 * @param {string} [m.text]
 * @param {string} [m.icon]     manifest id shown after the text (cats)
 * @param {Node[]} [m.extra]    extra nodes inside the bubble
 * @param {{label: string, icon?: string, onClick: () => void}[]} [m.actions]
 */
export function addMessage({ from, text = '', icon: iconId, extra = [], actions = [] }) {
  const out = from === 'user';
  const isCat = CAT_IDS.includes(from);
  const cont = lastSender === from;
  lastSender = from;

  const textEl = el('p', { class: 'msg__text' }, text);
  if (iconId) textEl.append(createSprite(iconId, { scale: 1 }));

  const body = el('div', { class: 'bubble__body' },
    out ? null : el('span', { class: 'msg__name', text: NAMES[from] ?? from }),
    text ? textEl : null,
    ...extra,
    actions.length ? el('div', { class: 'msg__actions' }, actions.map(a =>
      el('button', { type: 'button', class: 'btn', onclick: a.onClick }, a.icon ? icon(a.icon, { scale: 1 }) : null, a.label))) : null,
    el('div', { class: 'msg__meta' }, el('span', { class: 'msg__time', text: timeNow() })),
  );

  const msg = el('div', {
    class: `msg ${out ? 'msg--out' : 'msg--in'} ${isCat ? 'msg--cat' : ''} msg--${from} ${cont ? 'msg--cont' : ''}`,
  },
    el('span', { class: 'msg__avatar' }, createSprite(`avatar_${from}`, { scale: 1, alt: NAMES[from] ?? from })),
    el('div', { class: 'bubble px-frame' }, body),
  );
  log.append(msg);
  scrollToEnd();
  return msg;
}

/** Show the sender's typing dots for `ms`, then remove them. */
export async function showTyping(from, ms) {
  const prevSender = lastSender;
  const msg = addMessage({ from, extra: [el('div', { class: 'typing', 'aria-label': `${NAMES[from]} is typing` },
    el('span'), el('span'), el('span'))] });
  msg.classList.add('msg--typing');
  msg.querySelector('.msg__meta').remove();
  const prevStatus = statusEl.dataset.status;
  if (from === 'sloth') setStatus('typing');
  await sleep(ms);
  msg.remove();
  lastSender = prevSender;
  if (from === 'sloth') setStatus(prevStatus);
}

/** File bubble (user side) with live upload progress. */
export function addFileMessage(file) {
  const info = el('span', { class: 'file-card__info', text: `${formatBytes(file.size)} · ${UI.uploading(0)}` });
  const fill = el('span');
  const bar = el('div', { class: 'file-card__bar', role: 'progressbar', 'aria-valuemin': '0', 'aria-valuemax': '100',
    'aria-label': `Uploading ${file.name}` }, fill);
  const card = el('div', { class: 'file-card' },
    icon('file', { scale: 2, alt: 'file' }),
    el('span', { class: 'file-card__name', text: file.name }),
    info, bar);
  addMessage({ from: 'user', extra: [card] });

  return {
    setProgress(pct) {
      fill.style.setProperty('--pct', `${pct}%`);
      bar.setAttribute('aria-valuenow', String(pct));
      info.textContent = pct < 100 ? `${formatBytes(file.size)} · ${UI.uploading(pct)}` : `${formatBytes(file.size)} · ${UI.counting}`;
    },
    setInfo({ size_bytes, rows, cols }) {
      bar.remove();
      info.textContent = UI.fileInfo({ size: formatBytes(size_bytes), rows: formatNumber(rows), cols });
    },
    setError(text) {
      bar.remove();
      info.textContent = text;
      card.querySelector('.sprite')?.replaceWith(icon('warning', { scale: 2, alt: 'error' }));
    },
  };
}

/** Health meter node for the sloth's verdict bubble. */
export function healthMeter(score) {
  const color = { happy: 'var(--leaf)', grumpy: 'var(--red)', idle: 'var(--yellow)' }[moodFor(score)];
  const on = Math.round(score / 10);
  return el('div', { class: 'health', role: 'meter', 'aria-valuemin': '0', 'aria-valuemax': '100',
    'aria-valuenow': String(score), 'aria-label': UI.health },
    el('div', { class: 'health__meter', style: { '--meter': color } },
      Array.from({ length: 10 }, (_, i) => el('span', { class: i < on ? 'on' : '' }))),
    el('span', { class: 'health__score', text: `${score}/100` }));
}

export function setStatus(key) {
  statusEl.dataset.status = key;
  statusEl.textContent = STATUS[key] ?? key;
}

export function setBusy(busy) {
  field.placeholder = busy ? UI.inputPlaceholderBusy : UI.inputPlaceholder;
}

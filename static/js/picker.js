/**
 * Upload dialog: preview the first rows, pick the columns to analyse, an
 * optional target, and rows to leave out ("exclude rows where <column> is <value>").
 */
import { PICKER } from '../copy.js';
import { previewRows } from './api.js';
import { el, icon } from './ui.js';

const FIRST_PAGE = 30;   // rows fetched when a rule changes
const NEXT_PAGE = 100;   // rows per "show more"

/**
 * @param {{ file_id: string, filename: string, rows: number, columns: string[], preview: string[][] }} info  the /api/upload response
 * @returns {Promise<{ columns: number[], target: number|null, exclude: {column: number, value: string}[] } | null>}
 *          null when the user cancels
 */
export function pickColumns(info) {
  const cols = info.columns;
  const checks = cols.map((name, i) => el('input', { type: 'checkbox', checked: true, value: String(i) }));
  const target = el('select', { class: 'picker__select', 'aria-label': PICKER.target });
  const rules = el('div', { class: 'picker__rules' });
  const preview = el('div', { class: 'card__table-wrap picker__preview' });
  // The rows shown. Without rules these are the upload's first rows; with rules the server filters the
  // whole file, so the preview never hides rows that are only beyond the first few.
  const view = { rows: info.preview, flags: info.preview.map(() => false), cursor: info.preview.length,
    done: info.rows <= info.preview.length, busy: false, failed: false };
  let ticket = 0;      // a newer request makes older answers stale
  let timer;
  const start = el('button', { type: 'submit', class: 'btn btn--primary', value: 'start' }, PICKER.start);
  const showExcluded = el('input', { type: 'checkbox', checked: true });
  const showLabel = el('label', { class: 'picker__col', hidden: true }, showExcluded, el('span', { text: PICKER.showExcluded }));

  const chosen = () => checks.filter(c => c.checked).map(c => Number(c.value));
  const ruleList = () => [...rules.children].map(r => ({
    column: Number(r.querySelector('select').value), value: r.querySelector('input').value.trim(),
  }));

  function paintTarget() {
    const keep = target.value;
    target.replaceChildren(el('option', { value: '', text: PICKER.noTarget }),
      ...chosen().map(i => el('option', { value: String(i), text: cols[i] })));
    target.value = chosen().includes(Number(keep)) && keep !== '' ? keep : '';
  }

  function paintPreview() {
    const keep = chosen();
    const struck = view.flags.filter(Boolean).length;
    showLabel.hidden = ruleList().length === 0;
    preview.replaceChildren(el('table', { class: 'card__table' },
      el('caption', { text: view.failed ? PICKER.previewFailed : PICKER.preview(view.rows.length, struck, view.done) }),
      el('thead', {}, el('tr', {}, keep.map(i => el('th', { scope: 'col', text: cols[i] })))),
      el('tbody', {}, view.rows.map((row, n) => el('tr', { class: view.flags[n] ? 'is-excluded' : '' },
        keep.map(i => el('td', { text: row[i] ?? '' })))))),
      // replaceChildren() would print a null as the text "null", so leave the button out entirely
      ...(view.done ? [] : [el('button', { type: 'button', class: 'btn picker__more', disabled: view.busy,
        onclick: () => showMore() }, view.busy ? PICKER.loading : PICKER.more)]));
    start.disabled = keep.length === 0;
  }

  const query = (cursor, limit) => previewRows({ file_id: info.file_id, exclude: ruleList(),
    show_excluded: showExcluded.checked, cursor, limit });

  /** Rules or the show-excluded box changed: start the preview over from the top of the file. */
  async function reloadPreview() {
    const mine = ++ticket;
    if (ruleList().length === 0) {
      Object.assign(view, { rows: info.preview, flags: info.preview.map(() => false), cursor: info.preview.length,
        done: info.rows <= info.preview.length, busy: false, failed: false });
      return paintPreview();
    }
    view.busy = true;
    paintPreview();
    try {
      const page = await query(0, FIRST_PAGE);
      if (mine !== ticket) return;
      Object.assign(view, { rows: page.rows, flags: page.excluded, cursor: page.next, done: page.done, failed: false });
    } catch {
      if (mine !== ticket) return;
      view.failed = true;
    }
    view.busy = false;
    paintPreview();
  }
  const reloadSoon = () => { clearTimeout(timer); timer = setTimeout(reloadPreview, 250); };

  async function showMore() {
    const mine = ticket;
    view.busy = true;
    paintPreview();
    try {
      const page = await query(view.cursor, NEXT_PAGE);
      if (mine !== ticket) return;
      view.rows = view.rows.concat(page.rows);
      view.flags = view.flags.concat(page.excluded);
      Object.assign(view, { cursor: page.next, done: page.done, failed: false });
    } catch {
      if (mine !== ticket) return;
      view.failed = true;
    }
    view.busy = false;
    paintPreview();
  }

  function addRule() {
    const column = el('select', { class: 'picker__select', 'aria-label': PICKER.ruleColumn },
      cols.map((name, i) => el('option', { value: String(i), text: name })));
    const value = el('input', { type: 'text', class: 'picker__value', maxlength: '1000',
      placeholder: PICKER.ruleValue, 'aria-label': PICKER.ruleValue });
    const row = el('div', { class: 'picker__rule' }, el('span', { text: PICKER.ruleLead }), column,
      el('span', { text: PICKER.ruleIs }), value,
      el('button', { type: 'button', class: 'btn btn--icon', 'aria-label': PICKER.ruleRemove, title: PICKER.ruleRemove,
        onclick: () => { row.remove(); reloadPreview(); } }, icon('close', { scale: 1 })));
    column.addEventListener('change', reloadPreview);
    value.addEventListener('input', reloadSoon);
    rules.append(row);
    value.focus();
  }

  const setAll = on => { checks.forEach(c => { c.checked = on; }); paintTarget(); paintPreview(); };
  checks.forEach(c => c.addEventListener('change', () => { paintTarget(); paintPreview(); }));
  showExcluded.addEventListener('change', reloadPreview);

  const form = el('form', { method: 'dialog', class: 'picker__fill px-fill' },
    el('h2', { id: 'picker-title', text: PICKER.title(info.filename) }),
    el('fieldset', { class: 'picker__group' },
      el('legend', { text: PICKER.columns(cols.length) }),
      el('div', { class: 'picker__bulk' },
        el('button', { type: 'button', class: 'btn', onclick: () => setAll(true) }, PICKER.all),
        el('button', { type: 'button', class: 'btn', onclick: () => setAll(false) }, PICKER.none)),
      el('div', { class: 'picker__cols' }, cols.map((name, i) => el('label', { class: 'picker__col', title: name },
        checks[i], el('span', { text: name }))))),
    el('label', { class: 'picker__group picker__target' }, el('span', { text: PICKER.target }), target),
    el('fieldset', { class: 'picker__group' },
      el('legend', { text: PICKER.rows }),
      rules,
      el('button', { type: 'button', class: 'btn', onclick: addRule }, PICKER.addRule),
      showLabel),
    preview,
    el('div', { class: 'settings__foot' },
      el('button', { type: 'button', class: 'btn', onclick: () => dialog.close('') }, PICKER.cancel),
      start));

  const dialog = el('dialog', { class: 'settings picker', 'aria-labelledby': 'picker-title' },
    el('div', { class: 'px-frame' }, form));
  paintTarget();
  paintPreview();
  document.body.append(dialog);
  dialog.showModal();

  return new Promise(resolve => {
    dialog.addEventListener('close', () => {
      const ok = dialog.returnValue === 'start';
      ticket += 1;
      clearTimeout(timer);
      dialog.remove();
      resolve(ok ? {
        columns: chosen(),
        target: target.value === '' ? null : Number(target.value),
        exclude: ruleList(),
      } : null);
    });
  });
}

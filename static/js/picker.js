/**
 * Upload dialog: preview the first rows, pick the columns to analyse, an
 * optional target, and rows to leave out ("exclude rows where <column> is <value>").
 */
import { PICKER } from '../copy.js';
import { el, icon } from './ui.js';

const NUMBER = /^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/;
/** Same text, or the same number (0 equals 0.0). Mirrors _matcher in backend/engines/local.py. */
const same = (cell, value) => cell === value || (NUMBER.test(cell) && NUMBER.test(value) && Number(cell) === Number(value));

/**
 * @param {{ filename: string, columns: string[], preview: string[][] }} info  the /api/upload response
 * @returns {Promise<{ columns: number[], target: number|null, exclude: {column: number, value: string}[] } | null>}
 *          null when the user cancels
 */
export function pickColumns(info) {
  const cols = info.columns;
  const checks = cols.map((name, i) => el('input', { type: 'checkbox', checked: true, value: String(i) }));
  const target = el('select', { class: 'picker__select', 'aria-label': PICKER.target });
  const rules = el('div', { class: 'picker__rules' });
  const preview = el('div', { class: 'card__table-wrap picker__preview' });
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
    const active = ruleList();
    const excluded = row => active.some(r => same(row[r.column] ?? '', r.value));
    const struck = info.preview.filter(excluded).length;
    const rows = showExcluded.checked ? info.preview : info.preview.filter(row => !excluded(row));
    showLabel.hidden = active.length === 0;
    preview.replaceChildren(el('table', { class: 'card__table' },
      el('caption', { text: PICKER.preview(rows.length, struck, showExcluded.checked) }),
      el('thead', {}, el('tr', {}, keep.map(i => el('th', { scope: 'col', text: cols[i] })))),
      el('tbody', {}, rows.map(row => el('tr', { class: excluded(row) ? 'is-excluded' : '' },
        keep.map(i => el('td', { text: row[i] ?? '' })))))));
    start.disabled = keep.length === 0;
  }

  function addRule() {
    const column = el('select', { class: 'picker__select', 'aria-label': PICKER.ruleColumn },
      cols.map((name, i) => el('option', { value: String(i), text: name })));
    const value = el('input', { type: 'text', class: 'picker__value', maxlength: '1000',
      placeholder: PICKER.ruleValue, 'aria-label': PICKER.ruleValue });
    const row = el('div', { class: 'picker__rule' }, el('span', { text: PICKER.ruleLead }), column,
      el('span', { text: PICKER.ruleIs }), value,
      el('button', { type: 'button', class: 'btn btn--icon', 'aria-label': PICKER.ruleRemove, title: PICKER.ruleRemove,
        onclick: () => { row.remove(); paintPreview(); } }, icon('close', { scale: 1 })));
    column.addEventListener('change', paintPreview);
    value.addEventListener('input', paintPreview);
    rules.append(row);
    value.focus();
  }

  const setAll = on => { checks.forEach(c => { c.checked = on; }); paintTarget(); paintPreview(); };
  checks.forEach(c => c.addEventListener('change', () => { paintTarget(); paintPreview(); }));
  showExcluded.addEventListener('change', paintPreview);

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
      dialog.remove();
      resolve(ok ? {
        columns: chosen(),
        target: target.value === '' ? null : Number(target.value),
        exclude: ruleList(),
      } : null);
    });
  });
}

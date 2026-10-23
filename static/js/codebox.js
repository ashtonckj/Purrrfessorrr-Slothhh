/**
 * Code box with a Python / R toggle, syntax colours and a copy button.
 * Shared by the results drawer and the chat, so code looks the same in both.
 */
import { DRAWER } from '../copy.js';
import { emit } from './bus.js';
import { highlight } from './syntax.js';
import { el, icon } from './ui.js';

/** Code block with a Python / R toggle. R without code shows a disabled "soon" tab. */
export function renderCode(code, openByDefault) {
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

/** "Copy code" button for whatever `getText()` returns when clicked. */
export function copyButton(getText) {
  const btn = el('button', { type: 'button', class: 'btn' }, icon('copy', { scale: 1 }), el('span', { text: DRAWER.copyCode }));
  btn.addEventListener('click', () => copyCode(btn, getText()));
  return btn;
}

/** A code box plus its copy button, for a chat bubble. */
export function codeBlock(code) {
  const box = renderCode(code, true);
  return el('div', { class: 'msg__codebox' }, box.node, el('div', { class: 'card__actions' }, copyButton(box.current)));
}

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

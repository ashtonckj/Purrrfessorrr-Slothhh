/**
 * Top bar (name, sloth icon, theme + settings buttons) and the settings dialog.
 */
import { APP_NAME, UI } from '../copy.js';
import { SAMPLE_URL } from './api.js';
import { createSprite, setSprite } from './sprites.js';
import { el, icon } from './ui.js';

const THEME_KEY = 'slothhh.theme';

function storedTheme() {
  try { return localStorage.getItem(THEME_KEY); } catch { return null; }
}

function storeTheme(theme) {
  try { localStorage.setItem(THEME_KEY, theme); } catch { /* private mode: fine */ }
}

export function applyTheme(theme) {
  if (theme === 'night') document.documentElement.dataset.theme = 'night';
  else delete document.documentElement.dataset.theme;
}

export function initHeader(container, config) {
  let theme = storedTheme() ?? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'night' : 'day');
  applyTheme(theme);

  const themeBtn = el('button', { type: 'button', class: 'btn btn--icon' });
  const paintThemeBtn = () => {
    const night = theme === 'night';
    themeBtn.replaceChildren(icon(night ? 'sun' : 'moon'));
    themeBtn.setAttribute('aria-label', night ? UI.toggleDay : UI.toggleNight);
    themeBtn.title = night ? UI.toggleDay : UI.toggleNight;
  };
  themeBtn.addEventListener('click', () => {
    theme = theme === 'night' ? 'day' : 'night';
    applyTheme(theme);
    storeTheme(theme);
    paintThemeBtn();
  });
  paintThemeBtn();

  const dialog = buildSettings(config);
  const settingsBtn = el('button', { type: 'button', class: 'btn btn--icon', 'aria-label': UI.settings, title: UI.settings,
    'aria-haspopup': 'dialog', onclick: () => dialog.showModal() }, icon('gear'));

  container.append(el('div', { class: 'px-frame', style: { width: '100%' } },
    el('div', { class: 'topbar__fill px-fill' },
      createSprite('sloth_idle', { scale: 1, alt: '' }),
      el('div', {},
        el('h1', { text: APP_NAME }),
        el('div', { class: 'topbar__sub', text: UI.tagline })),
      el('div', { class: 'topbar__actions' }, themeBtn, settingsBtn))));
  document.body.append(dialog);
}

function buildSettings(config) {
  const row = (label, value) => el('div', { class: 'settings__row' }, el('dt', { text: label }), el('dd', {}, value));
  const dialog = el('dialog', { class: 'settings', 'aria-labelledby': 'settings-title' });
  const close = el('button', { type: 'button', class: 'btn btn--primary', onclick: () => dialog.close() }, UI.close);

  dialog.append(el('div', { class: 'px-frame' },
    el('div', { class: 'settings__fill px-fill' },
      el('h2', { id: 'settings-title', text: UI.settingsTitle }),
      el('dl', { style: { margin: 0, display: 'grid', gap: '12px' } },
        row(UI.model, el('code', { text: config?.model_name ?? '?' })),
        row(UI.mode, el('span', { class: 'tag', text: config?.mock_mode ? UI.modeMock : UI.modeReal })),
        row(UI.sample, el('a', { href: SAMPLE_URL, download: 'cafe_sales_sample.csv' }, icon('download', { scale: 1 }), ' ', UI.sampleLink))),
      el('div', { class: 'settings__foot' }, close))));
  // click on the backdrop closes
  dialog.addEventListener('click', e => { if (e.target === dialog) dialog.close(); });
  return dialog;
}

/** Keep the little header sloth in sync with the big one (called from main). */
export function setHeaderSloth(mood) {
  const s = document.querySelector('.topbar__fill > .sprite');
  if (s) setSprite(s, `sloth_${mood}`);
}

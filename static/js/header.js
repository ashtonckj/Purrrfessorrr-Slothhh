/**
 * Top bar (name, sloth icon, theme + settings buttons) and the settings dialog.
 */
import { APP_NAME, UI } from '../copy.js';
import { SAMPLE_URL } from './api.js';
import { isSoundOn, onSoundChange, setSoundOn } from './sound.js';
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

  // Theme and sound live in the settings dialog.
  const themeBtn = el('button', { type: 'button', class: 'btn' });
  const paintThemeBtn = () => {
    const night = theme === 'night';
    themeBtn.replaceChildren(icon(night ? 'sun' : 'moon', { scale: 1 }), night ? UI.toggleDay : UI.toggleNight);
  };
  themeBtn.addEventListener('click', () => {
    theme = theme === 'night' ? 'day' : 'night';
    applyTheme(theme);
    storeTheme(theme);
    paintThemeBtn();
  });
  paintThemeBtn();

  // Sound: off by default (see sound.js)
  const soundBtn = el('button', { type: 'button', class: 'btn', onclick: () => setSoundOn(!isSoundOn()) });
  const paintSoundBtn = on_ => {
    soundBtn.replaceChildren(icon(on_ ? 'sound_on' : 'sound_off', { scale: 1 }), on_ ? UI.soundIsOn : UI.soundIsOff);
    soundBtn.setAttribute('aria-pressed', String(on_));
  };
  onSoundChange(paintSoundBtn);
  paintSoundBtn(isSoundOn());

  const dialog = buildSettings(config, themeBtn, soundBtn);
  const settingsBtn = el('button', { type: 'button', class: 'btn btn--icon', 'aria-label': UI.settings, title: UI.settings,
    'aria-haspopup': 'dialog', onclick: () => dialog.showModal() }, icon('gear'));

  container.append(el('div', { class: 'px-frame', style: { width: '100%' } },
    el('div', { class: 'topbar__fill px-fill' },
      createSprite('sloth_idle', { scale: 1, alt: '' }),
      el('div', {},
        el('h1', { text: APP_NAME }),
        el('div', { class: 'topbar__sub', text: UI.tagline })),
      el('div', { class: 'topbar__actions' }, settingsBtn))));
  document.body.append(dialog);
}

function buildSettings(config, themeBtn, soundBtn) {
  const row = (label, value) => el('div', { class: 'settings__row' }, el('dt', { text: label }), el('dd', {}, value));
  const dialog = el('dialog', { class: 'settings', 'aria-labelledby': 'settings-title' });
  const close = el('button', { type: 'button', class: 'btn btn--primary', onclick: () => dialog.close() }, UI.close);

  dialog.append(el('div', { class: 'px-frame' },
    el('div', { class: 'settings__fill px-fill' },
      el('h2', { id: 'settings-title', text: UI.settingsTitle }),
      el('dl', { style: { margin: 0, display: 'grid', gap: '12px' } },
        row(UI.theme, themeBtn),
        row(UI.soundToggle, soundBtn),
        row(UI.engine, el('span', { class: 'tag', text: UI.engines[config?.engine] ?? config?.engine ?? '?' })),
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

// Entry point: load sprites + config, then start each module.
import { getConfig } from './api.js';
import { on } from './bus.js';
import { initFlow, greet } from './flow.js';
import { initHeader, setHeaderSloth } from './header.js';
import { loadSprites } from './sprites.js';
import { UI } from '../copy.js';
import { el } from './ui.js';

async function detectFont() {
  // Without the bundled pixel font, bump sizes so monospace stays readable.
  try { await document.fonts.load('11px PressStart'); } catch { /* ignore */ }
  if (!document.fonts.check('11px PressStart')) document.documentElement.classList.add('font-fallback');
}

async function main() {
  const [config] = await Promise.all([getConfig().catch(() => null), loadSprites(), detectFont()]);

  initHeader(document.getElementById('topbar'), config);
  initFlow(config);

  // Office scene arrives in step 4; placeholder for now.
  document.getElementById('office').append(el('div', { class: 'px-frame', style: { height: '100%' } },
    el('div', { class: 'office__fill px-fill' }, UI.officeSoon)));

  // The header sloth mirrors the sloth's mood (talk returns to the previous mood).
  let mood = 'sleep';
  setHeaderSloth(mood);
  let talkTimer;
  on('sloth:mood', ({ mood: m }) => {
    if (m === 'talk') {
      setHeaderSloth('talk');
      clearTimeout(talkTimer);
      talkTimer = setTimeout(() => setHeaderSloth(mood), 1800);
    } else {
      mood = m;
      clearTimeout(talkTimer);
      setHeaderSloth(m);
    }
  });

  greet();
}

main();

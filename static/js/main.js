// Entry point: load sprites + config, then start each module.
import { getConfig } from './api.js';
import { on } from './bus.js';
import { initFlow, greet } from './flow.js';
import { initHeader, setHeaderSloth } from './header.js';
import { followSlothMood } from './mood.js';
import { initOffice } from './office.js';
import { loadSprites } from './sprites.js';

async function detectFont() {
  // Without the bundled pixel font, bump sizes so monospace stays readable.
  try { await document.fonts.load('11px PressStart'); } catch { /* ignore */ }
  if (!document.fonts.check('11px PressStart')) document.documentElement.classList.add('font-fallback');
}

async function main() {
  const [config] = await Promise.all([getConfig().catch(() => null), loadSprites(), detectFont()]);

  initHeader(document.getElementById('topbar'), config);
  initFlow(config);

  initOffice(document.getElementById('office'));
  followSlothMood(setHeaderSloth);

  // The results drawer arrives in step 5.
  on('drawer:open', ({ cat }) => console.info('[drawer] open', cat));

  greet();
}

main();

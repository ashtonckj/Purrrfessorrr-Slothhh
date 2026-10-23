// Entry point: load sprites + config, then start each module.
import { getConfig } from './api.js';
import { initDrawer } from './drawer.js';
import { initFlow, greet } from './flow.js';
import { initHeader, setHeaderSloth } from './header.js';
import { followSlothMood } from './mood.js';
import { initOffice } from './office.js';
import { initSound } from './sound.js';
import { loadSprites } from './sprites.js';

async function main() {
  const [config] = await Promise.all([getConfig().catch(() => null), loadSprites(), initSound()]);

  initHeader(document.getElementById('topbar'), config);
  initFlow(config);

  initOffice(document.getElementById('office'));
  followSlothMood(setHeaderSloth);

  initDrawer(document.getElementById('office'));

  greet();
}

main();

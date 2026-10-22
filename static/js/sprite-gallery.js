// Sprite gallery: renders every manifest entry with the sprite engine.
import { loadSprites, createSprite, reducedMotion } from './sprites.js';

const GROUP_TITLES = { sloth: 'Professor Slothhh', cats: 'Cats', props: 'Props', avatars: 'Avatars', ui: 'UI icons' };
const state = { scale: 3, paused: false, missing: false };
let manifest;

function render() {
  const root = document.getElementById('gallery');
  root.textContent = '';
  const groups = {};
  for (const [id, info] of Object.entries(manifest.sprites)) (groups[info.group ?? 'other'] ??= []).push([id, info]);

  for (const [group, items] of Object.entries(groups)) {
    const h = document.createElement('h2');
    h.textContent = `${GROUP_TITLES[group] ?? group} (${items.length})`;
    const grid = document.createElement('div');
    grid.className = 'grid';
    // Icons and avatars are small; give them a bit more zoom so details are visible.
    const scale = group === 'ui' ? state.scale + 1 : group === 'avatars' ? Math.max(1, state.scale - 1) : state.scale;
    for (const [id, info] of items) {
      const card = document.createElement('figure');
      card.className = 'card';
      card.style.margin = '0';
      const stage = document.createElement('div');
      stage.className = 'stage';
      stage.append(createSprite(id, { scale, alt: `${info.label} (${id})`, paused: state.paused, placeholder: state.missing }));
      const meta = document.createElement('figcaption');
      meta.className = 'meta';
      meta.innerHTML = `<b></b><br>${info.frameWidth}x${info.frameHeight} · ${info.frameCount}f · ${info.fps}fps`;
      meta.querySelector('b').textContent = id;
      meta.title = info.file;
      card.append(stage, meta);
      grid.append(card);
    }
    root.append(h, grid);
  }
}

function buildControls() {
  const box = document.getElementById('scales');
  for (const s of [1, 2, 3, 4]) {
    const b = document.createElement('button');
    b.textContent = `${s}x`;
    b.setAttribute('aria-pressed', String(s === state.scale));
    b.addEventListener('click', () => {
      state.scale = s;
      box.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
      render();
    });
    box.append(b, ' ');
  }
  document.getElementById('paused').addEventListener('change', e => { state.paused = e.target.checked; render(); });
  document.getElementById('missing').addEventListener('change', e => { state.missing = e.target.checked; render(); });
  const motion = document.getElementById('motion');
  const showMotion = () => { motion.textContent = reducedMotion.matches ? '(reduced motion is on: animations frozen)' : ''; };
  reducedMotion.addEventListener('change', showMotion);
  showMotion();
}

manifest = await loadSprites();
buildControls();
render();

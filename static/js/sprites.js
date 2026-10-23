/**
 * Sprite engine.
 *
 * Reads assets/manifest.json, preloads every sheet, and turns sprite ids into
 * elements animated with CSS steps(). Sheets are horizontal strips of equal
 * frames; the manifest says how big a frame is, how many there are and the fps.
 * Replace any PNG with your own art: if the numbers in the manifest match, no
 * code changes are needed.
 *
 * Missing PNG or manifest entry -> a coloured pixel block with the sprite's
 * name, so the UI never breaks.
 *
 *   await loadSprites();
 *   const cat = createSprite('detective_idle', { scale: 2 });
 *   setSprite(cat, 'detective_work');
 */

const ASSET_ROOT = 'assets/';
const status = new Map(); // id -> 'ok' | 'missing'
let manifest = { sprites: {} };

export const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

/** Fetch the manifest and preload all sheets. Never throws. */
export async function loadSprites(url = `${ASSET_ROOT}manifest.json`) {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    manifest = await res.json();
  } catch (err) {
    console.warn('[sprites] no manifest, everything will be placeholder blocks:', err);
    manifest = { sprites: {} };
  }
  await Promise.all(Object.entries(manifest.sprites).map(([id, info]) => preload(id, info)));
  return manifest;
}

function preload(id, info) {
  return new Promise(resolve => {
    const img = new Image();
    img.onload = () => {
      status.set(id, 'ok');
      const expected = info.frameWidth * info.frameCount;
      if (img.naturalWidth !== expected || img.naturalHeight !== info.frameHeight) {
        console.warn(`[sprites] ${info.file} is ${img.naturalWidth}x${img.naturalHeight}, ` +
          `manifest expects ${expected}x${info.frameHeight} (${info.frameCount} frames of ` +
          `${info.frameWidth}x${info.frameHeight}). Update manifest.json.`);
      }
      resolve();
    };
    img.onerror = () => {
      status.set(id, 'missing');
      console.warn(`[sprites] missing ${info.file}, using a placeholder block`);
      resolve();
    };
    img.src = ASSET_ROOT + info.file;
  });
}

/** Manifest record for an id (or undefined). */
export function spriteInfo(id) {
  return manifest.sprites[id];
}

/**
 * Create a sprite element.
 * @param {string} id        manifest id, e.g. 'sloth_idle'
 * @param {object} opts
 * @param {number} opts.scale     integer multiple (rounded, min 1)
 * @param {string} opts.alt       accessible label; omit for decorative sprites
 * @param {boolean} opts.paused   show frame 0 only
 * @param {string} opts.className extra classes
 * @param {boolean} opts.placeholder force the missing-art block (for previews)
 */
export function createSprite(id, { scale = 2, alt = '', paused = false, className = '', placeholder = false } = {}) {
  const el = document.createElement('span');
  el.className = `sprite ${className}`.trim();
  if (alt) {
    el.setAttribute('role', 'img');
    el.setAttribute('aria-label', alt);
  } else {
    el.setAttribute('aria-hidden', 'true');
  }
  el.dataset.scale = String(toScale(scale));
  if (paused) el.dataset.paused = '';
  if (placeholder) el.dataset.placeholder = '';
  setSprite(el, id);
  return el;
}

/** Swap the sheet shown by a sprite element (e.g. idle -> work). Same id is a no-op. */
export function setSprite(el, id, { force = false } = {}) {
  if (!force && el.dataset.sprite === id) return el;
  el.dataset.sprite = id;
  const scale = Number(el.dataset.scale) || 1;
  const info = spriteInfo(id);
  const w = (info?.frameWidth ?? 32) * scale;
  const h = (info?.frameHeight ?? 32) * scale;

  el.style.setProperty('--w', `${w}px`);
  el.style.setProperty('--h', `${h}px`);
  el.textContent = '';

  if (!info || status.get(id) !== 'ok' || 'placeholder' in el.dataset) {
    el.classList.add('sprite--missing');
    el.classList.remove('sprite--anim');
    el.style.backgroundImage = '';
    el.style.setProperty('--fallback', info?.color ?? '#9a948c');
    const label = document.createElement('span');
    label.className = 'sprite__label';
    label.textContent = info?.label ?? id;
    el.append(label);
    return el;
  }

  el.classList.remove('sprite--missing');
  const frames = info.frameCount;
  el.style.backgroundImage = `url("${ASSET_ROOT}${info.file}")`;
  el.style.setProperty('--sheet-w', `${w * frames}px`);
  el.style.setProperty('--frames', frames);
  el.style.setProperty('--dur', `${frames / Math.max(0.1, info.fps)}s`);
  const animate = frames > 1 && !('paused' in el.dataset);
  el.classList.toggle('sprite--anim', animate);
  if (animate) restartAnimation(el);
  return el;
}

/** Change the integer scale of an existing sprite. */
export function setScale(el, scale) {
  el.dataset.scale = String(toScale(scale));
  return setSprite(el, el.dataset.sprite, { force: true });
}

function toScale(scale) {
  return Math.max(1, Math.round(Number(scale) || 1));
}

// Restart so a newly swapped sheet starts at frame 0.
function restartAnimation(el) {
  el.style.animation = 'none';
  void el.offsetWidth; // force reflow
  el.style.animation = '';
}

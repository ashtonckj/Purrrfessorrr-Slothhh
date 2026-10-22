/**
 * Sound hooks. OFF by default; the speaker button in the header turns it on
 * (and the choice is remembered in this browser).
 *
 * Anything can request a sound with emit('sound', { name }). Names used now:
 *   pop (sloth message), drop (file received), paper (paper lands),
 *   done (cat finished), copy (code copied), error (cat gave up)
 *
 * Real files: list them in assets/audio/sounds.json ("pop": "pop.ogg").
 * Names without a file play a tiny generated chiptune blip, so nothing is
 * ever fetched from the network. "music" (if listed) loops quietly.
 */
import { on } from './bus.js';

const KEY = 'slothhh.sound';
const MIN_GAP_MS = 70;           // don't machine-gun the same sound

// built-in blips: [frequency Hz, duration s] notes played in a row
const BLIPS = {
  pop: [[660, 0.05], [880, 0.06]],
  drop: [[330, 0.07], [440, 0.07], [660, 0.1]],
  paper: [[1200, 0.025]],
  done: [[523, 0.07], [659, 0.07], [784, 0.12]],
  copy: [[988, 0.05], [1319, 0.07]],
  error: [[392, 0.1], [262, 0.18]],
};

let enabled = false;
let files = {};
let ctx = null;
let music = null;
const lastPlayed = {};
const listeners = new Set();

function readPref() {
  try { return localStorage.getItem(KEY) === 'on'; } catch { return false; }
}

function writePref(on_) {
  try { localStorage.setItem(KEY, on_ ? 'on' : 'off'); } catch { /* private mode */ }
}

export async function initSound() {
  try {
    const res = await fetch('assets/audio/sounds.json');
    if (res.ok) files = (await res.json()).files ?? {};
  } catch { /* no sound list: blips only */ }
  enabled = readPref();
  on('sound', ({ name }) => play(name));
  // Remembered "on" from last time: audio can only start after the first click/key.
  const unlock = () => {
    if (enabled && !ctx) {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      startMusic();
    }
  };
  window.addEventListener('pointerdown', unlock, { once: true });
  window.addEventListener('keydown', unlock, { once: true });
}

export function isSoundOn() {
  return enabled;
}

/** Turn sound on/off. Call from a click handler (browsers need a user gesture). */
export function setSoundOn(value) {
  enabled = value;
  writePref(value);
  if (value) {
    ctx ??= new (window.AudioContext || window.webkitAudioContext)();
    ctx.resume?.();
    startMusic();
    play('pop');
  } else {
    music?.pause();
  }
  listeners.forEach(fn => fn(enabled));
}

export function onSoundChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function play(name) {
  if (!enabled) return;
  const now = performance.now();
  if (now - (lastPlayed[name] ?? 0) < MIN_GAP_MS) return;
  lastPlayed[name] = now;

  if (files[name]) {
    const a = new Audio(`assets/audio/${files[name]}`);
    a.volume = 0.5;
    a.play().catch(() => {});
    return;
  }
  blip(BLIPS[name]);
}

function blip(notes) {
  if (!notes || !ctx) return;
  let t = ctx.currentTime;
  for (const [freq, dur] of notes) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'square';
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.06, t);
    gain.gain.setValueAtTime(0, t + dur);   // hard cut: chiptune, not a fade
    osc.connect(gain).connect(ctx.destination);
    osc.start(t);
    osc.stop(t + dur + 0.01);
    t += dur;
  }
}

function startMusic() {
  if (!files.music) return;
  music ??= Object.assign(new Audio(`assets/audio/${files.music}`), { loop: true, volume: 0.2 });
  music.play().catch(() => {});
}

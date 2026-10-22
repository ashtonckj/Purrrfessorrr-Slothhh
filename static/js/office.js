/**
 * The office scene: Professor Slothhh's desk, five cat desks, progress bars
 * and flying papers. Driven entirely by bus events (see bus.js), so it does
 * not care whether the data comes from the mock or the real engine.
 */
import { NAMES, OFFICE, ROLES } from '../copy.js';
import { emit, on } from './bus.js';
import { followSlothMood } from './mood.js';
import { createSprite, setScale, setSprite } from './sprites.js';
import { el, prefersReducedMotion, say } from './ui.js';

const CAT_IDS = ['detective', 'artist', 'scribe', 'coder', 'janitor'];
const SEGMENTS = 20;
const MAX_PAPERS = 30;
const ROWS_PER_PAPER = 1000;

let room;
let scale = 2;               // cats and props
let bossScale = 3;           // the sloth's corner
const sprites = [];          // [{ el, boss }] every sprite, for rescaling
const stations = {};         // cat -> station state + nodes
const boss = {};             // sloth nodes

function sprite(id, opts = {}, isBoss = false) {
  const s = createSprite(id, { scale: isBoss ? bossScale : scale, ...opts });
  sprites.push({ el: s, boss: isBoss });
  return s;
}

export function initOffice(container) {
  room = el('div', { class: 'room px-fill' });
  container.append(el('div', { class: 'px-frame office__frame' }, room));

  buildBoss();
  const list = el('ul', { class: 'stations', 'aria-label': 'Cat desks' });
  for (const cat of CAT_IDS) list.append(buildStation(cat));
  room.append(list);

  new ResizeObserver(fitScale).observe(room);
  fitScale();

  followSlothMood(setSlothMood);
  on('job:start', onStart);
  on('job:delegated', onDelegated);
  on('job:progress', onProgress);
  on('job:result', ({ cat }) => setCatState(cat, 'done'));
  on('job:error', ({ cat, message }) => cat && setCatState(cat, 'error', message));
  on('job:done', onDone);
}

// ------------------------------------------------------------------ build

function buildBoss() {
  boss.sloth = sprite('sloth_sleep', { alt: NAMES.sloth }, true);
  boss.zzz = sprite('zzz', {}, true);
  boss.zzzWrap = el('span', { class: 'boss__zzz' }, boss.zzz);
  boss.speechText = el('span', { class: 'speech__text' });
  boss.speechScore = el('span', { class: 'speech__score', hidden: true });
  boss.speech = el('div', { class: 'speech px-frame', role: 'status', 'aria-live': 'polite' },
    el('div', { class: 'speech__fill' }, boss.speechText, boss.speechScore));
  boss.stack = sprite('paper_stack');  // drawn at cat scale: it's a prop, not the boss
  boss.stackWrap = el('span', { class: 'boss__stack', hidden: true }, boss.stack);
  boss.capped = el('div', { class: 'capped-note', hidden: true });

  // wall decorations (purely visual)
  room.append(el('div', { class: 'decor decor--chart', 'aria-hidden': 'true' },
    ...[3, 5, 4, 7, 6].map(h => el('span', { style: { height: `${h * 6}px` } }))));
  room.append(el('div', { class: 'decor decor--sign', 'aria-hidden': 'true' }, OFFICE.sign));

  room.append(el('div', { class: 'boss' },
    el('span', { class: 'boss__branch' }, sprite('branch', {}, true)),
    el('div', { class: 'boss__stage' }, boss.sloth, boss.zzzWrap, boss.speech),
    el('div', { class: 'boss__desk' }, sprite('desk_sloth', {}, true), boss.stackWrap, boss.capped)));
  speak(say(OFFICE.bubble.idle));
}

function buildStation(cat) {
  const catSprite = sprite(`${cat}_idle`, { alt: NAMES[cat] });
  const catBtn = el('button', { type: 'button', class: 'station__cat', title: `${NAMES[cat]}: ${ROLES[cat]}`,
    onclick: () => emit('drawer:open', { cat }) }, catSprite);
  const pile = el('div', { class: 'pile', 'aria-hidden': 'true' });
  const segs = Array.from({ length: SEGMENTS }, () => el('span', { class: 'pbar__seg' }));
  const track = el('div', { class: 'pbar__track', role: 'progressbar', 'aria-valuemin': '0', 'aria-valuemax': '100',
    'aria-valuenow': '0', 'aria-label': `${NAMES[cat]} progress` }, segs);
  const runner = sprite('progress_cat_run');
  const runnerWrap = el('span', { class: 'pbar__runner', hidden: true }, runner);
  const msg = el('div', { class: 'station__msg', text: '' });
  const results = el('button', { type: 'button', class: 'btn', disabled: true,
    onclick: () => emit('drawer:open', { cat }) }, 'Results');

  const li = el('li', { class: 'station', 'data-state': 'idle', 'data-cat': cat },
    catBtn,
    el('div', { class: 'station__desk' }, sprite('desk'), pile, el('span', { class: 'plate', text: OFFICE.plates[cat] })),
    el('div', { class: 'pbar' }, track, runnerWrap),
    msg,
    results);

  stations[cat] = { li, catBtn, catSprite, pile, segs, track, runner, runnerWrap, msg, results,
    state: 'idle', percent: 0, papers: 0, landed: 0 };
  updateLabel(cat);
  return li;
}

// ------------------------------------------------------------------ scale

/**
 * Pick the biggest integer scales that fit: five desks across for the cats,
 * then whatever height is left for the sloth (up to two steps bigger).
 */
function fitScale() {
  const w = room.clientWidth - 24 - 4 * 8;
  const h = room.clientHeight;
  // rough height budget in px: boss = (branch + sloth + desk) art px, station = (cat + desk) art px + bars/buttons
  const fits = (s, b) => 54 * b + 46 * s + 160 <= h;
  let s = Math.max(1, Math.min(4, Math.floor(w / (5 * 48))));
  while (s > 1 && !fits(s, s + 1)) s -= 1;
  let b = s + 2;
  while (b > s && !fits(s, b)) b -= 1;
  if (s === scale && b === bossScale && room.style.getPropertyValue('--s')) return;
  scale = s;
  bossScale = b;
  room.style.setProperty('--s', String(s));
  room.style.setProperty('--ss', String(b));
  for (const { el: sp, boss: isBoss } of sprites) setScale(sp, isBoss ? b : s);
}

// ------------------------------------------------------------------ sloth

function setSlothMood(mood) {
  setSprite(boss.sloth, `sloth_${mood}`);
  boss.zzzWrap.hidden = mood !== 'sleep';
}

function speak(text, score = null, mood = 'idle') {
  boss.speechText.textContent = text;
  boss.speechScore.hidden = score == null;
  if (score != null) {
    boss.speechScore.textContent = say(OFFICE.bubble.health, { score });
    boss.speechScore.dataset.mood = mood;
  }
}

// ------------------------------------------------------------- job events

function onStart({ file }) {
  for (const cat of CAT_IDS) resetStation(cat);
  const total = Math.max(1, Math.ceil(file.rows / ROWS_PER_PAPER));
  boss.stackWrap.hidden = false;
  boss.capped.hidden = total <= MAX_PAPERS;
  boss.capped.textContent = say(OFFICE.capped, { total });
  speak(say(OFFICE.bubble.start));
  for (const cat of CAT_IDS) stations[cat].msg.textContent = OFFICE.waiting;
}

function resetStation(cat) {
  const st = stations[cat];
  Object.assign(st, { state: 'idle', percent: 0, papers: 0, landed: 0 });
  st.li.dataset.state = 'idle';
  setSprite(st.catSprite, `${cat}_idle`);
  st.pile.replaceChildren();
  st.segs.forEach(s => s.classList.remove('on'));
  st.track.setAttribute('aria-valuenow', '0');
  st.runnerWrap.hidden = true;
  st.msg.textContent = '';
  st.results.disabled = true;
  updateLabel(cat);
}

let flightsPending = 0;

function onDelegated({ cat, paper_count: count }) {
  const st = stations[cat];
  st.papers = count;
  st.msg.textContent = OFFICE.ready;
  const order = CAT_IDS.indexOf(cat);
  for (let i = 0; i < count; i++) {
    flightsPending += 1;
    // round-robin: every desk gets its first paper before anyone gets a second
    flyPaper(cat, (i * CAT_IDS.length + order) * 90).then(() => {
      st.landed += 1;
      renderPile(cat);
      flightsPending -= 1;
      if (flightsPending === 0) boss.stackWrap.hidden = true;
    });
  }
}

/** Animate one paper from the sloth's stack to a cat's desk. Resolves on landing. */
function flyPaper(cat, delay) {
  const from = boss.stack.getBoundingClientRect();
  const to = stations[cat].pile.getBoundingClientRect();
  const origin = room.getBoundingClientRect();
  if (prefersReducedMotion() || !from.width) return new Promise(r => setTimeout(r, delay / 4));

  const paper = createSprite('paper', { scale });
  const flyer = el('span', { class: 'flyer' }, paper);
  const x0 = from.left - origin.left + from.width / 2 - 8 * scale;
  const y0 = from.top - origin.top;
  const x1 = to.left - origin.left;
  const y1 = to.top - origin.top;
  const peak = Math.min(y0, y1) - 40 * scale;

  room.append(flyer);
  const anim = flyer.animate([
    { transform: `translate(${x0}px, ${y0}px)` },
    { transform: `translate(${(x0 + x1) / 2}px, ${peak}px)`, offset: 0.45 },
    { transform: `translate(${x1}px, ${y1}px)` },
  ], { duration: 750, delay, easing: 'steps(10, end)', fill: 'both' });
  return anim.finished.then(() => flyer.remove(), () => flyer.remove());
}

/** Papers left on a desk: the pile shrinks as the cat works through it. */
function renderPile(cat) {
  const st = stations[cat];
  const left = st.state === 'done' ? 0 : Math.ceil(st.papers * (1 - st.percent / 100));
  const show = Math.min(st.landed, left);
  while (st.pile.childElementCount > show) st.pile.lastElementChild.remove();
  while (st.pile.childElementCount < show) {
    const i = st.pile.childElementCount + 1;
    const p = createSprite('paper', { scale, paused: true });
    p.style.setProperty('--i', String(i));
    st.pile.append(p);
  }
}

function onProgress({ cat, percent, message }) {
  const st = stations[cat];
  if (st.state === 'done' || st.state === 'error') return;
  st.percent = percent;
  if (st.state === 'idle') setCatState(cat, 'work');
  const on = Math.floor((percent / 100) * SEGMENTS);
  st.segs.forEach((s, i) => s.classList.toggle('on', i < on));
  st.track.setAttribute('aria-valuenow', String(percent));
  st.runnerWrap.hidden = false;
  st.runnerWrap.style.setProperty('--p', String(percent / 100));
  if (message) st.msg.textContent = message;
  renderPile(cat);
  updateLabel(cat);
  if (Object.values(stations).every(s => s.state !== 'idle')) speak(OFFICE.bubble.working);
}

function setCatState(cat, state, message) {
  const st = stations[cat];
  st.state = state;
  st.li.dataset.state = state;
  setSprite(st.catSprite, `${cat}_${state}`);
  if (state === 'done') {
    st.percent = 100;
    st.segs.forEach(s => s.classList.add('on'));
    st.track.setAttribute('aria-valuenow', '100');
    st.runnerWrap.hidden = false;
    st.runnerWrap.style.setProperty('--p', '1');
    setSprite(st.runner, 'progress_cat_sit');
    st.results.disabled = false;
    st.msg.replaceChildren(createSprite('icon_check', { scale: 1, alt: '' }), ' ', OFFICE.done);
    renderPile(cat);
  } else if (state === 'error') {
    st.runnerWrap.hidden = true;
    st.msg.replaceChildren(createSprite('icon_warning', { scale: 1, alt: '' }), ' ', message || OFFICE.error);
  } else if (state === 'work') {
    setSprite(st.runner, 'progress_cat_run');
  }
  updateLabel(cat);
}

function onDone({ health_score: score }) {
  boss.stackWrap.hidden = true;
  if (score == null) return;
  const mood = score > 80 ? 'happy' : score < 40 ? 'grumpy' : 'idle';
  speak(say(OFFICE.bubble.mood, { score }), score, mood);
}

function updateLabel(cat) {
  const st = stations[cat];
  st.catBtn.setAttribute('aria-label', say(OFFICE.catLabel, {
    name: NAMES[cat], role: ROLES[cat], state: OFFICE.states[st.state],
    percent: st.state === 'work' ? st.percent : null,
  }));
}

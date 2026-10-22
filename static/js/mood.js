// Follow the sloth's mood from the bus. 'talk' is temporary: it falls back
// to the last lasting mood after a moment.
import { on } from './bus.js';

const TALK_MS = 1800;

/** Call `apply(mood)` now and on every change. Returns an unsubscribe function. */
export function followSlothMood(apply, initial = 'sleep') {
  let mood = initial;
  let talkTimer;
  apply(mood);
  return on('sloth:mood', ({ mood: next }) => {
    clearTimeout(talkTimer);
    if (next === 'talk') {
      apply('talk');
      talkTimer = setTimeout(() => apply(mood), TALK_MS);
    } else {
      mood = next;
      apply(mood);
    }
  });
}

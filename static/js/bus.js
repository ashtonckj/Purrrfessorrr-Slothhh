/**
 * Tiny app-wide event bus so modules don't import each other.
 *
 * Events used:
 *   job:start      { jobId, file }
 *   job:delegated  { cat, paper_count }
 *   job:progress   { cat, percent, message }
 *   job:result     { cat, cards }
 *   job:error      { cat, message }
 *   job:done       { health_score }
 *   sloth:mood     { mood: 'idle' | 'sleep' | 'talk' | 'happy' | 'grumpy' }
 *   drawer:open    { cat }
 *   sound          { name }          (hook for step 6, muted by default)
 */

const target = new EventTarget();

export function emit(type, detail = {}) {
  target.dispatchEvent(new CustomEvent(type, { detail }));
}

export function on(type, handler) {
  const fn = e => handler(e.detail);
  target.addEventListener(type, fn);
  return () => target.removeEventListener(type, fn);
}

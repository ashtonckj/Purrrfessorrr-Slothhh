// Small DOM and formatting helpers shared by the UI modules.
import { createSprite } from './sprites.js';

/** Create an element: el('div', { class: 'x', text: 'hi' }, child1, child2) */
export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'text') node.textContent = v;
    else if (k === 'style') Object.assign(node.style, v);
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else if (k in node && typeof v !== 'string') node[k] = v;
    else node.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) if (c != null && c !== false) node.append(c);
  return node;
}

/** A pixel icon sprite (16x16 at `scale`). */
export function icon(name, { scale = 2, alt = '' } = {}) {
  return createSprite(`icon_${name}`, { scale, alt, className: 'icon' });
}

/** Resolve a copy entry (string | string[] | fn) to one string. */
export function say(entry, values = {}) {
  let v = typeof entry === 'function' ? entry(values) : entry;
  if (Array.isArray(v)) v = v[Math.floor(Math.random() * v.length)];
  return String(v ?? '');
}

export function formatBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 ** 2).toFixed(1)} MB`;
}

export const formatNumber = n => Number(n).toLocaleString('en-US');

export function timeNow() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export const sleep = ms => new Promise(r => setTimeout(r, ms));

export const prefersReducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

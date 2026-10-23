#!/usr/bin/env node
/**
 * Check every sprite PNG against static/assets/manifest.json.
 *
 *   node scripts/check-image-sizes.js            # checks static/assets
 *   node scripts/check-image-sizes.js some/dir   # checks another assets folder (with its own manifest.json)
 *
 * A sheet is a horizontal strip of equal frames, so a PNG must be exactly
 * (frameWidth x frameCount) wide and frameHeight tall. For each PNG that is not,
 * this prints the numbers to put in manifest.json instead. Exits with 1 if anything is off.
 * No dependencies: the size is read from the PNG header.
 */
'use strict';

const fs = require('fs');
const path = require('path');

const assets = path.resolve(process.argv[2] || path.join(__dirname, '..', 'static', 'assets'));
const manifestPath = path.join(assets, 'manifest.json');
const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

/** { width, height } from the IHDR chunk, or null if the file is not a PNG. */
function pngSize(file) {
  const fd = fs.openSync(file, 'r');
  const head = Buffer.alloc(24);
  try { fs.readSync(fd, head, 0, 24, 0); } finally { fs.closeSync(fd); }
  if (!head.subarray(0, 8).equals(PNG_SIGNATURE) || head.toString('ascii', 12, 16) !== 'IHDR') return null;
  return { width: head.readUInt32BE(16), height: head.readUInt32BE(20) };
}

/** What to write in the manifest so `size` splits into equal frames. */
function suggest(info, { width, height }) {
  const frames = info.frameCount;
  if (width % frames === 0) {
    return { frameWidth: width / frames, frameHeight: height, frameCount: frames };
  }
  if (width % height === 0) {  // can't keep the frame count: assume square frames
    return { frameWidth: height, frameHeight: height, frameCount: width / height };
  }
  return null;
}

function listPngs(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return listPngs(full);
    return entry.name.toLowerCase().endsWith('.png') ? [full] : [];
  });
}

function main() {
  if (!fs.existsSync(manifestPath)) {
    console.error(`no manifest at ${manifestPath}`);
    return 2;
  }
  const sprites = JSON.parse(fs.readFileSync(manifestPath, 'utf8')).sprites || {};
  const problems = [];
  let ok = 0;

  for (const [id, info] of Object.entries(sprites)) {
    const file = path.join(assets, info.file);
    const want = `${info.frameWidth * info.frameCount}x${info.frameHeight}`
      + ` (${info.frameCount} frame${info.frameCount === 1 ? '' : 's'} of ${info.frameWidth}x${info.frameHeight})`;
    if (!fs.existsSync(file)) {
      problems.push(`${id}: ${info.file} is missing (manifest expects ${want})`);
      continue;
    }
    const size = pngSize(file);
    if (!size) {
      problems.push(`${id}: ${info.file} is not a PNG`);
      continue;
    }
    if (size.width === info.frameWidth * info.frameCount && size.height === info.frameHeight) {
      ok += 1;
      continue;
    }
    const fix = suggest(info, size);
    let line = `${id}: ${info.file} is ${size.width}x${size.height}, manifest expects ${want}`;
    if (fix) {
      line += `\n    put in manifest.json: "frameWidth": ${fix.frameWidth}, "frameHeight": ${fix.frameHeight}, "frameCount": ${fix.frameCount}`;
      const grow = fix.frameWidth / info.frameWidth;
      if (grow !== 1) line += `\n    note: it will show ${+grow.toFixed(2)}x ${grow > 1 ? 'bigger' : 'smaller'} on screen (sprites scale by whole pixels; see ASSETS.md)`;
    } else {
      line += `\n    ${size.width}px can't be cut into ${info.frameCount} equal frames: make every frame the same width`;
    }
    problems.push(line);
  }

  const listed = new Set(Object.values(sprites).map(info => path.join(assets, info.file)));
  const unlisted = listPngs(assets).filter(file => !listed.has(file));

  console.log(`checked ${Object.keys(sprites).length} sprites in ${path.relative(process.cwd(), manifestPath) || manifestPath}: ${ok} ok, ${problems.length} to fix`);
  for (const line of problems) console.log(`\n- ${line}`);
  if (unlisted.length) {
    console.log(`\n${unlisted.length} PNG${unlisted.length === 1 ? ' is' : 's are'} not in the manifest (the app ignores them):`);
    for (const file of unlisted) console.log(`  ${path.relative(assets, file).split(path.sep).join('/')}`);
  }
  return problems.length ? 1 : 0;
}

process.exitCode = main();

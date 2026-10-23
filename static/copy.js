/**
 * All UI copy lives here. Edit freely.
 *
 * Strings can be:
 *   - a plain string
 *   - an array of strings (one is picked at random)
 *   - a function taking values and returning a string or an array
 * Use say(entry, values) from js/ui.js to resolve any of them.
 *
 * Sloth: lazy, sleepy, gentle; short lowercase sentences with "..." and the
 * occasional stretched word. Cats: eager, slightly overworked, a little punny.
 */

export const APP_NAME = 'Purrfessorrr Slothhh';

export const NAMES = {
  sloth: 'Prof. Slothhh',
  user: 'You',
  detective: 'Detective Cat',
  artist: 'Artist Cat',
  scribe: 'Scribe Cat',
  coder: 'Coder Cat',
  janitor: 'Janitor Cat',
};

export const ROLES = {
  detective: 'data quality: outliers, duplicates, type problems',
  artist: 'chart selection and rendering',
  scribe: 'plain-english explanations and docs',
  coder: 'python code snippets',
  janitor: 'preprocessing and cleaning',
};

/** Icon shown next to each cat's chat messages (manifest ids). */
export const CAT_ICONS = {
  detective: 'icon_magnifier',
  artist: 'icon_brush',
  scribe: 'icon_quill',
  coder: 'icon_laptop',
  janitor: 'icon_broom',
};

export const UI = {
  tagline: 'a very lazy data science office',
  settings: 'Settings',
  settingsTitle: 'settings',
  model: 'model',
  mode: 'mode',
  modeMock: 'mock (pretend cats)',
  modeReal: 'real',
  sample: 'sample csv',
  sampleLink: 'download sample',
  soundToggle: 'Sound effects',
  soundIsOn: 'sound: on (click to mute)',
  soundIsOff: 'sound: off (click for blips)',
  close: 'close',
  toggleNight: 'Switch to night mode',
  toggleDay: 'Switch to day mode',
  attach: 'Attach a CSV file',
  send: 'Send message',
  inputPlaceholder: 'type to the sloth... or drop a csv',
  inputPlaceholderBusy: 'the cats are working... chat anyway',
  drop: "drop it like it's hot... slowly",
  dropHint: '.csv  .tsv  .xlsx',
  results: 'Results',
  uploading: pct => `uploading... ${pct}%`,
  counting: 'counting rows...',
  fileInfo: ({ size, rows, cols }) => `${size} · ${rows} rows · ${cols} cols`,
  health: 'data health',
  today: 'today',
};

export const STATUS = {
  online: 'online',
  typing: 'typing... slowly',
  delegating: 'delegating...',
  napping: 'napping...',
};

export const SLOTH = {
  greeting: [
    "oh... hi...\ni'm professor slothhh... i run this office...\nby not running anywhere...",
    "hello... welcome to my office...\ni'm professor slothhh... i delegate things...\nprofessionally...",
  ],
  greeting2: [
    'drop a csv in the chat... or press the paperclip...\nthe cats will do the work... i will supervise... with my eyes closed...',
    'give me a csv... i give it to the cats...\nthat is the whole job... it is a great job...',
  ],
  received: ({ name, rows }) => [
    `oh... ${name}...\n${rows} rows... that's... a lot of rows...`,
    `mmh... ${name}... ${rows} rows...\ni'm tired just reading the number...`,
    `a csv... with ${rows} rows... okaaay...`,
  ],
  receivedTiny: ({ name, rows }) => [
    `${name}... only ${rows} rows... cute... i could almost do this myself... almost...`,
  ],
  delegate: [
    'cats... work... i will supervise... from here...',
    'okaaay... passing the jobs to the cats...\nwake me when it is done...',
    'time to delegate... my favourite sport...',
  ],
  papers: ({ papers }) => `${papers} piles of papers... every row is in there... the cats get all of it...`,
  again: [
    'another file... okaaay... cats... again...',
    'more work... not for me though...',
  ],
  health: ({ score }) => {
    if (score > 80) return [`data health: ${score}... nice and tidy... i approve... lazily...`];
    if (score < 40) return [`data health: ${score}...\nugh... it's a mess... the janitor cat has notes...`];
    return [`data health: ${score}...\nnot bad... not great... very... average... like my naps...`];
  },
  allDone: 'everyone is done... click a cat or a results button to see what they found...',
  catError: ({ cat }) => `the ${cat} cat... had a little accident... the others are fine...`,
  wrongType: ({ name }) => [`${name}...? i only eat csv... tsv... and xlsx... sometimes...`],
  tooBig: ({ max }) => `that file is heavier than me... over ${max} MB... please... a smaller one...`,
  uploadFailed: ({ reason }) => `the upload fell over... ${reason}...`,
  connectionLost: 'i lost the cats... the connection dropped... try the file again...',
  chatFailed: 'mmh... i fell asleep mid-thought... try again...',
  busy: 'one file at a time... please... i am only one sloth...',
};

export const CATS = {
  done: {
    detective: ({ cards }) => `case closed! ${lower(cards[0]?.title ?? 'nothing suspicious')}.`,
    artist: ({ cards }) => `${cards.length} charts, pawsitively framed.`,
    scribe: () => 'wrote it all down, in plain english.',
    coder: ({ cards }) => `${cards.length} snippets ready to copy. no bugs. probably.`,
    janitor: ({ cards }) => `${lower(cards[0]?.title ?? 'all clean')}, swept up.`,
  },
  error: ({ message }) => `oops... ${message}`,
};

/** The office scene (left column). */
export const OFFICE = {
  plates: { detective: 'DETECTIVE', artist: 'ARTIST', scribe: 'SCRIBE', coder: 'CODER', janitor: 'JANITOR' },
  bubble: {
    idle: ['drop a csv... in the chat...', 'resting my eyes... not asleep...'],
    start: ['papers... go...', 'okaaay... delegating...'],
    working: 'zzz...',
    health: ({ score }) => `health: ${score}/100`,
    mood: ({ score }) => (score > 80 ? 'tidy... nice...' : score < 40 ? 'ugh... messy...' : 'meh... okay...'),
  },
  sign: 'NAP\nMORE',
  waiting: 'waiting for papers...',
  ready: 'papers received',
  done: 'done!',
  error: 'confused...',
  catLabel: ({ name, role, state, percent }) => `${name}, ${role}. ${state}${percent != null ? `, ${percent}%` : ''}. Open results.`,
  states: { idle: 'idle', work: 'working', done: 'done', error: 'error' },
};

/** The results drawer. */
export const DRAWER = {
  label: 'Results',
  close: 'Close results',
  switchTo: name => `Show ${name}'s results`,
  copyCode: 'Copy code',
  copied: 'Copied!',
  copyFailed: 'Copy failed',
  downloadChart: 'Download chart (PNG)',
  downloadData: 'Download data (CSV)',
  downloadZip: 'Download everything (.zip)',
  exportNotebook: 'Export notebook (.ipynb)',
  python: 'Python',
  r: 'R',
  soon: 'soon',
  showCode: 'show code',
  preview: n => `first ${n} rows`,
  severity: { ok: 'ok', warn: 'check', bad: 'fix me' },
  empty: {
    noJob: 'no papers yet... drop a csv in the chat and this cat gets to work.',
    working: 'still working on it... pawsitively almost done.',
    error: message => `this cat had an accident: ${message}`,
    none: 'nothing to report. suspiciously quiet.',
  },
  exportsLocked: 'exports unlock when every cat is done',
};

function lower(s) {
  return s.charAt(0).toLowerCase() + s.slice(1);
}

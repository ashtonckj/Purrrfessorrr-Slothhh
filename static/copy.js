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
  theme: 'theme',
  themeDay: 'day',
  themeNight: 'night',
  sound: 'sound',
  soundOff: 'off',
  soundOn: 'on',
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
  officeSoon: 'the office is being built (step 4)... the cats are on a coffee break',
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
  papers: ({ papers }) => `${papers} papers... one for each of you... roughly...`,
  papersCapped: ({ total }) => `that's ${total} lots of papers... i only gave them the first 30... the rest is... a problem for later...`,
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
  start: {
    detective: ['on the case, boss!', 'magnifier: ready. let me sniff this out.'],
    artist: ['ooh, a blank canvas!', 'sharpening my pencils!'],
    scribe: ['taking notes... purrfectly.', 'quill inked, ready to write.'],
    coder: ['booting up my brain.', 'import pandas as pd. on it!'],
    janitor: ['broom out, sleeves up!', 'time to tidy up this mess.'],
  },
  done: {
    detective: ({ cards }) => `case closed! ${lower(cards[0]?.title ?? 'nothing suspicious')}.`,
    artist: ({ cards }) => `${cards.length} charts, pawsitively framed.`,
    scribe: () => 'wrote it all down, in plain english.',
    coder: ({ cards }) => `${cards.length} snippets ready to copy. no bugs. probably.`,
    janitor: ({ cards }) => `${lower(cards[0]?.title ?? 'all clean')}, swept up.`,
  },
  error: ({ message }) => `oops... ${message}`,
};

function lower(s) {
  return s.charAt(0).toLowerCase() + s.slice(1);
}

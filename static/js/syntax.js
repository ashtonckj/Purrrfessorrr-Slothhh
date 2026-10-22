/**
 * Tiny local syntax highlighter (no CDN). Good enough for Python and R snippets:
 * comments, strings, numbers, keywords, builtins, constants, function names.
 * Returns escaped HTML with <span class="tok-*"> wrappers.
 */

const KEYWORDS = {
  python: new Set(('and as assert async await break class continue def del elif else except finally for from ' +
    'global if import in is lambda nonlocal not or pass raise return try while with yield').split(' ')),
  r: new Set('if else repeat while function for in next break library require return'.split(' ')),
};

const BUILTINS = {
  python: new Set(('print len range sum min max abs round sorted list dict set tuple str int float bool open ' +
    'enumerate zip map filter isinstance type super').split(' ')),
  r: new Set('c print length sum mean median summary head tail nrow ncol is.na read.csv data.frame'.split(' ')),
};

const CONSTANTS = {
  python: new Set(['True', 'False', 'None']),
  r: new Set(['TRUE', 'FALSE', 'NULL', 'NA', 'Inf', 'NaN']),
};

const TOKEN = new RegExp([
  '(?<comment>#[^\\n]*)',
  '(?<string>[rRbBfFuU]{0,2}(?:"""[\\s\\S]*?"""|\'\'\'[\\s\\S]*?\'\'\'|"(?:\\\\.|[^"\\\\\\n])*"|\'(?:\\\\.|[^\'\\\\\\n])*\'))',
  '(?<number>\\b\\d+(?:\\.\\d+)?(?:[eE][+-]?\\d+)?\\b)',
  '(?<decorator>@[A-Za-z_][\\w.]*)',
  '(?<word>[A-Za-z_][\\w.]*)',
].join('|'), 'g');

const escape = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const span = (cls, text) => `<span class="tok-${cls}">${escape(text)}</span>`;

export function highlight(code, lang = 'python') {
  const kw = KEYWORDS[lang] ?? KEYWORDS.python;
  const bi = BUILTINS[lang] ?? BUILTINS.python;
  const consts = CONSTANTS[lang] ?? CONSTANTS.python;
  let out = '';
  let last = 0;
  let prevWord = '';

  for (const m of code.matchAll(TOKEN)) {
    out += escape(code.slice(last, m.index));
    last = m.index + m[0].length;
    const g = m.groups;
    if (g.comment) out += span('com', g.comment);
    else if (g.string) out += span('str', g.string);
    else if (g.number) out += span('num', g.number);
    else if (g.decorator) out += span('fn', g.decorator);
    else {
      const w = g.word;
      if (prevWord === 'def' || prevWord === 'class') out += span('fn', w);
      else if (kw.has(w)) out += span('kw', w);
      else if (consts.has(w)) out += span('num', w);
      else if (bi.has(w)) out += span('bi', w);
      else out += escape(w);
      prevWord = w;
      continue;
    }
    prevWord = '';
  }
  return out + escape(code.slice(last));
}

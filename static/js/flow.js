/**
 * Conversation flow: upload -> sloth replies -> delegate -> stream cat events.
 * Talks to the server through api.js, renders through chat.js, and
 * broadcasts job events on the bus for the office scene and the drawer.
 */
import * as api from './api.js';
import * as chat from './chat.js';
import { emit } from './bus.js';
import { CAT_ICONS, CATS, NAMES, SLOTH, UI } from '../copy.js';
import { formatNumber, moodFor, prefersReducedMotion, say, sleep } from './ui.js';

const ACCEPTED = ['.csv', '.tsv', '.xlsx'];

const state = {
  config: { max_upload_mb: 200 },
  jobId: null,
  busy: false,      // a file is being uploaded / analysed
  closeStream: null,
  jobs: 0,
};

export function initFlow(config) {
  state.config = config ?? state.config;
  chat.initChat(document.getElementById('chat'), { onSend: handleText, onFiles: handleFiles });
}

// Chat output is serialised so typing dots and messages never interleave.
// Bus events are emitted immediately (the office animates in real time).
let chain = Promise.resolve();
function queue(task) {
  chain = chain.then(task).catch(err => console.error('[flow]', err));
  return chain;
}

/** Sloth "types" (slowly) and then says the line. */
async function slothSays(text, extra = []) {
  emit('sloth:mood', { mood: 'talk' });
  const ms = prefersReducedMotion() ? 250 : Math.min(2600, 900 + text.length * 18);
  await chat.showTyping('sloth', ms);
  chat.addMessage({ from: 'sloth', text, extra });
  emit('sound', { name: 'pop' });
}

export function greet() {
  return queue(async () => {
    await sleep(400);
    await slothSays(say(SLOTH.greeting));
    await slothSays(say(SLOTH.greeting2));
    emit('sloth:mood', { mood: 'sleep' });
  });
}

// ------------------------------------------------------------------- text

function handleText(text) {
  chat.addMessage({ from: 'user', text });
  const reply = api.chat(state.jobId, text).catch(() => ({ from: 'sloth', reply: say(SLOTH.chatFailed) }));
  queue(async () => {
    const [{ from, reply: answer }] = await Promise.all([reply, chat.showTyping('sloth', 1500)]);
    chat.addMessage({ from, text: answer, icon: CAT_ICONS[from] });
  });
}

// ------------------------------------------------------------------ files

async function handleFiles(files) {
  const file = files[0];
  if (state.busy) {
    queue(() => slothSays(say(SLOTH.busy)));
    return;
  }
  const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
  if (!ACCEPTED.includes(ext)) {
    chat.addMessage({ from: 'user', text: file.name });
    queue(() => slothSays(say(SLOTH.wrongType, { name: file.name })));
    return;
  }
  const maxMb = state.config.max_upload_mb;
  if (file.size > maxMb * 1024 * 1024) {
    chat.addMessage({ from: 'user', text: file.name });
    queue(() => slothSays(say(SLOTH.tooBig, { max: maxMb })));
    return;
  }

  state.busy = true;
  chat.setBusy(true);
  try {
    await runFile(file);
  } catch (err) {
    idle();
    emit('sloth:mood', { mood: 'grumpy' });
    queue(() => slothSays(say(SLOTH.uploadFailed, { reason: err.message ?? 'no idea why' })));
  }
}

/** Ready for the next file. */
function idle() {
  state.busy = false;
  chat.setBusy(false);
  chat.setStatus('online');
}

async function runFile(file) {
  const card = chat.addFileMessage(file);
  let info;
  try {
    info = await api.upload(file, pct => card.setProgress(pct));
  } catch (err) {
    card.setError(err.message);
    throw err;
  }
  card.setInfo(info);
  emit('sound', { name: 'drop' });

  const rows = formatNumber(info.rows);
  const first = state.jobs === 0;
  state.jobs += 1;
  await queue(async () => {
    if (!first) await slothSays(say(SLOTH.again));
    else if (info.rows < 1000) await slothSays(say(SLOTH.receivedTiny, { name: info.filename, rows }));
    else await slothSays(say(SLOTH.received, { name: info.filename, rows }));
    await slothSays(say(SLOTH.delegate));
  });

  const { job_id: jobId } = await api.analyze(info.file_id);
  state.jobId = jobId;
  chat.setStatus('delegating');
  emit('job:start', { jobId, file: info });
  listen(jobId);
}

function listen(jobId) {
  state.closeStream?.();
  const delegated = {};

  state.closeStream = api.streamJob(jobId, (type, data) => {
    emit(`job:${type}`, data);
    queue(() => onJobEvent(type, data));
  }, () => queue(async () => {
    idle();
    await slothSays(say(SLOTH.connectionLost));
  }));

  async function onJobEvent(type, data) {
    if (type === 'delegated') {
      delegated[data.cat] = data.paper_count;
      if (Object.keys(delegated).length === 5) {
        const papers = Object.values(delegated).reduce((a, b) => a + b, 0);
        await slothSays(say(SLOTH.papers, { papers }));
        chat.setStatus('napping');
        emit('sloth:mood', { mood: 'sleep' });
      }
    } else if (type === 'result') {
      chat.addMessage({
        from: data.cat,
        text: say(CATS.done[data.cat], { cards: data.cards }),
        icon: CAT_ICONS[data.cat],
        actions: [{ label: UI.results, onClick: () => emit('drawer:open', { cat: data.cat }) }],
      });
      emit('sound', { name: 'done' });
    } else if (type === 'error') {
      if (data.cat) {
        chat.addMessage({ from: data.cat, text: say(CATS.error, { message: data.message }), icon: 'icon_warning' });
        emit('sound', { name: 'error' });
        await slothSays(say(SLOTH.catError, { cat: NAMES[data.cat].split(' ')[0].toLowerCase() }));
      } else {
        await slothSays(data.message);
      }
    } else if (type === 'done') {
      const score = data.health_score;
      if (score != null) {
        const mood = moodFor(score);
        await slothSays(say(SLOTH.health, { score, mood }), [chat.healthMeter(score)]);
        emit('sloth:mood', { mood });
      }
      await slothSays(say(SLOTH.allDone));
      idle();
    }
  }
}

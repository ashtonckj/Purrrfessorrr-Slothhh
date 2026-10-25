/**
 * API client. The only module that knows URLs. Contract: API.md.
 */

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function json(res) {
  if (res.ok) return res.json();
  let detail = res.statusText;
  try { detail = (await res.json()).detail ?? detail; } catch { /* not json */ }
  throw new ApiError(res.status, String(detail));
}

function post(url, body) {
  return fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(json);
}

export const getConfig = () => fetch('/api/config').then(json);

/**
 * Upload a file. Uses XHR (not fetch) so we get upload progress.
 * @param {File} file
 * @param {(pct: number) => void} onProgress
 */
export function upload(file, onProgress = () => {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const fd = new FormData();
    fd.append('file', file, file.name);
    xhr.open('POST', '/api/upload');
    xhr.responseType = 'json';
    xhr.upload.onprogress = e => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100));
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response);
      else reject(new ApiError(xhr.status, xhr.response?.detail ?? xhr.statusText ?? 'upload failed'));
    };
    xhr.onerror = () => reject(new ApiError(0, 'the server is not answering'));
    xhr.send(fd);
  });
}

/** @param {{columns?: number[], target?: number|null, exclude?: {column: number, value: string}[]}} [choice] */
/** A page of the uploaded file with the exclude rules applied (see /api/preview in API.md). */
export const previewRows = body => post('/api/preview', body);

export const analyze = (fileId, choice = {}) => post('/api/analyze', { file_id: fileId, ...choice });

export const chat = (jobId, message) => post('/api/chat', { job_id: jobId, message });

export const redrawScatter = (jobId, x, y) => post(`/api/jobs/${jobId}/scatter`, { x, y });

export const redrawBoxplot = (jobId, column) => post(`/api/jobs/${jobId}/boxplot`, { column });

export const redrawDistribution = (jobId, column) => post(`/api/jobs/${jobId}/distribution`, { column });

export const getResults = (jobId, cat) => fetch(`/api/results/${jobId}/${cat}`).then(json);

export const exportUrl = (jobId, kind) => `/api/export/${jobId}/${kind}`;

export const SAMPLE_URL = '/api/sample.csv';

const EVENT_TYPES = ['delegated', 'progress', 'result', 'error', 'done'];

/**
 * Subscribe to a job's event stream.
 * @param {string} jobId
 * @param {(type: string, data: object) => void} onEvent
 * @param {() => void} onLost  called if the stream dies before `done`
 * @returns {() => void} close function
 */
export function streamJob(jobId, onEvent, onLost = () => {}) {
  const es = new EventSource(`/api/jobs/${jobId}/events`);
  let finished = false;
  for (const type of EVENT_TYPES) {
    es.addEventListener(type, e => {
      // A server "error" event shares its name with EventSource's own connection
      // errors; those carry no data and are handled by onerror below.
      if (e.data == null) return;
      onEvent(type, JSON.parse(e.data));
      if (type === 'done') {
        finished = true;
        es.close();
      }
    });
  }
  // EventSource retries by itself; CLOSED means it gave up (e.g. server restarted).
  es.onerror = () => {
    if (!finished && es.readyState === EventSource.CLOSED) onLost();
  };
  return () => { finished = true; es.close(); };
}

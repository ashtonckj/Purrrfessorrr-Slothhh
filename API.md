# API

Everything is served from `http://127.0.0.1:8765` (port set in `config.env`).
The frontend only talks to these routes; any engine in `backend/engines/`
has to honour this contract.

Interactive docs: `/api/docs`. Developer test page: `/dev.html`.

Cat ids used everywhere: `detective`, `artist`, `scribe`, `coder`, `janitor`.

## Endpoints

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/config` | | `{ engine, max_upload_mb, cats: {id: role} }` |
| POST | `/api/upload` | multipart, field `file` (`.csv`, `.tsv`, `.xlsx`) | `{ file_id, filename, rows, cols, size_bytes, columns: [...], preview: [[...]], warnings: [...] }` (first 8 rows as text). Repeated column names are made unique (`amount`, `amount.1`). `warnings` are plain sentences about the import (renamed columns, rows with more or fewer cells than the header, a file read as Windows-1252 because it is not UTF-8); the upload dialog shows them. |
| POST | `/api/preview` | `{ "file_id": "...", "exclude": [{ "column": 1, "value": "x" }], "show_excluded": true, "cursor": 0, "limit": 100 }` | `{ rows: [[...]], excluded: [bool], next, done }`: the next page of data rows after the first `cursor` rows of the file, with rows matching an exclude rule flagged (or skipped when `show_excluded` is false). Pass `next` back as `cursor`. Used by the upload dialog. |
| POST | `/api/analyze` | `{ "file_id": "...", "columns": [0, 2] or null, "target": 2 or null, "exclude": [{ "column": 1, "value": "x" }] }` | `{ job_id }` (work starts in the background). Columns are indexes into `columns`; omitted = all. `exclude` drops rows whose cell (trimmed text) equals `value`. |
| GET | `/api/jobs/{job_id}/events` | | Server-Sent Events stream, see below |
| GET | `/api/results/{job_id}/{cat}` | | `{ cat, ready, cards: [Card] }` |
| GET | `/api/export/{job_id}/zip` | | `.zip` download (results.json, notebook, per card: README.md, data.csv, chart.json, code.py) |
| GET | `/api/export/{job_id}/notebook` | | `.ipynb` download |
| POST | `/api/chat` | `{ "job_id": "..." or null, "message": "..." }` | `{ replies: [{ from, reply, choices, code, followup }] }`: one reply per question in the message. `from` is `sloth` or the cat id that answered; `choices` are short follow-ups to show as buttons, sent back as the next `message`; `code` is `{ python, r }` for a code box (or null); `followup` is true when the reply answers a question the cat asked. `card` is a card the chat changed (a re-drawn histogram, same shape as in `result` events) or null; the frontend shows it in the bubble and swaps it into the drawer. Short code in `reply` is wrapped in backticks. The engine remembers earlier turns of the same job. |
| POST | `/api/jobs/{job_id}/scatter` | `{ "x": "col", "y": "col" }` | `{ card }`: the artist's scatter card re-drawn for another pair of number columns. |
| POST | `/api/jobs/{job_id}/boxplot` | `{ "column": "col" }` | `{ card }`: the artist's box plot re-drawn for another number column. |
| POST | `/api/jobs/{job_id}/distribution` | `{ "column": "col" }` | `{ card }`: the artist's histogram re-drawn for another number column (keeps the bin count). |
| GET | `/api/sample.csv` | | sample CSV (12,000-ish rows of cafe sales, with mess baked in) |

Errors use FastAPI's default shape: HTTP status + `{ "detail": "message" }`.
`413` file too big, `415` wrong file type, `422` empty file, `404` unknown file/job/cat.

## Event stream

`GET /api/jobs/{job_id}/events` sends standard SSE (`id:`, `event:`, `data:` JSON).

| event | data | when |
|---|---|---|
| `delegated` | `{ cat, paper_count }` | once per cat, right after `/analyze`. Papers on the table = ceil(rows / 1000), capped at 30 (animation only: every row is analysed), split so every cat gets at least 1. |
| `progress` | `{ cat, percent, message }` | many times per cat, 0 to 100. Cats run in parallel. |
| `result` | `{ cat, cards: [Card] }` | when a cat finishes |
| `error` | `{ cat, message }` | a cat gave up (`cat` is `null` if the whole job failed). Other cats keep going. |
| `done` | `{ health_score }` | always last. 0-100; the sloth is happy above 80, grumpy below 40. |

Events are replayable: reconnecting with `Last-Event-ID` resumes, and connecting
late replays from the start. After `done` the server closes the stream and
answers further reconnects with `204` (which makes `EventSource` stop).
Keep-alive comments are sent every 15 s.

There is a 2.5 s pause (times `CAT_SPEED`) between `delegated` and the first
progress, so the UI can fly papers to the desks; the file is read meanwhile.

## Card

```json
{
  "id": "detective-outliers",
  "title": "37 suspicious rows",
  "description": "Plain-text paragraph.",
  "severity": "ok | warn | bad",
  "chart": {
    "type": "bar | hbar | line | hist | scatter | heatmap",
    "title": "...", "x_label": "...", "y_label": "...",
    "labels": ["a", "b"], "values": [1, 2],
    "points": [[x, y], ...]
  },
  "table": { "columns": ["..."], "rows": [["..."]] },
  "code": { "python": "...", "r": "..." }
}
```

Artist cards with header dropdowns carry the options: `scatter_columns` (scatter) or `column_choices` (box plot, distribution). Only `id`, `title` and `description` are required. `chart` is a spec the
frontend draws on a canvas (so "Download chart (PNG)" works offline);
`points` is used by `scatter`, `labels`/`matrix` (square, `matrix[i][j]` = r or `null`) by `heatmap`, `labels`/`values` by the rest. `table` feeds
"Download data (CSV)". Every snippet has a Python and an R version (`r` may be null where there is nothing to say).

## Swapping in another engine

1. Write a class extending `Engine` (`backend/engines/base.py`):
   `async run(job)` emits the events above, `async chat(job, message)` returns
   `(who, text)`.
2. Return it from `get_engine()` in `backend/engines/__init__.py`.
3. Exports, uploads, the event stream and the frontend need no changes.
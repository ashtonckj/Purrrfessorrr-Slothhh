# Purrfessorrr Slothhh

A local-first, pixel-art helper for data scientists. Drop a CSV into the chat;
Professor Slothhh (a very lazy sloth) delegates the work to five cats, and each
cat reports back with findings, charts, explanations, code and cleaning steps.

> The sloth typed "Purrfessor Sloth" and left his finger on the keys too long.

Everything runs on your machine; the app makes no external network requests.
The cats read **every row** of your file and report real statistics (missing
values, IQR outliers, duplicates, type problems, distributions, correlations),
using only the Python standard library. Another engine (e.g. pandas +
Ollama/Gemma) can be plugged in without touching the frontend (see [API.md](API.md)).

| Cat | Job |
|---|---|
| Detective Cat | data quality: outliers, duplicates, type problems |
| Artist Cat | chart selection and rendering |
| Scribe Cat | plain-English explanations and documentation |
| Coder Cat | Python code snippets |
| Janitor Cat | preprocessing and cleaning (missing values, encoding) |

## Install and run

You need **Python 3.10 or newer**. A desktop browser at least 1100 px wide works best.

### Windows

1. Install Python from [python.org](https://www.python.org/downloads/) and tick **"Add python.exe to PATH"** in the installer.
2. Double-click **`run.bat`** (or run it from a terminal in this folder).

The first run creates a `.venv` folder and installs the requirements (needs
internet once, takes about a minute). Then it starts the app and opens
**http://127.0.0.1:8765** in your browser. Close the window (or press Ctrl+C) to stop.

To do it by hand:

```bat
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

### macOS / Linux

```bash
./run.sh
```

If it says "permission denied", run `chmod +x run.sh` once, or start it with `sh run.sh`.
By hand:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

### Options

`python app.py --port 9000` uses another port. `python app.py --no-browser` doesn't open a tab.

## Using it

1. Drag a `.csv`, `.tsv` or `.xlsx` onto the chat (or click the paperclip).
   No data at hand? Settings (gear icon) > **download sample**.
   A dialog previews the first rows: untick columns to skip, pick a **target**
   (the column you want to predict), and add rules like "exclude rows where
   store is Campus". Then press **start the cats**.
2. The sloth replies, then papers fly to the five desks: one paper per 1,000
   rows, capped at 30 on screen (the cats still read every row).
3. Watch the progress bars. When a cat finishes, click it (or its **Results**
   button) to open the results drawer: charts, data previews, code, downloads.
4. When everyone is done the sloth shows a **data health score** (0-100):
   happy above 80, grumpy below 40. The drawer can then export everything as a
   `.zip` or a Jupyter notebook.
5. Chat any time. Ask about outliers, duplicates, missing values, charts,
   correlations, code, or a column by name ("tell me about customer age"): the
   sloth passes the question to the cat whose job it is, and that cat answers
   from the results. Cats remember the last topic, so "and total?" or "is it
   missing anywhere?" work as follow-ups, and when a question is vague (a
   partial column name, an average with no column) the cat asks you to confirm,
   with tap-to-answer buttons.

Top-right buttons: sound (off by default), day/night theme, settings.

## Pixel font (optional, recommended)

The UI is designed for **Press Start 2P** (SIL Open Font License). It isn't
bundled yet; without it the app falls back to a monospace font at larger sizes.

1. Download `PressStart2P-Regular.ttf` from
   <https://fonts.google.com/specimen/Press+Start+2P> (or from the
   [google/fonts repo](https://github.com/google/fonts/tree/main/ofl/pressstart2p)).
2. Put it at `static/assets/fonts/PressStart2P-Regular.ttf` (exact name).
3. Reload the page.

## Configuration

Edit **`config.env`** (environment variables with the same name override it):

| Setting | Default | Meaning |
|---|---|---|
| `HOST`, `PORT` | `127.0.0.1`, `8765` | Where the server listens (localhost only). |
| `OPEN_BROWSER` | `true` | Open a browser tab on start. |
| `MAX_UPLOAD_MB` | `200` | Upload size limit. |
| `UPLOAD_DIR` | `data/uploads` | Where uploads are stored (git-ignored). |
| `CAT_SPEED` | `1.0` | Cat animation multiplier (`0.3` = fast demo). The numbers are real either way. |

## Customising

- **Text and jokes:** all UI copy is in [`static/copy.js`](static/copy.js). The cats'
  progress lines and chat voices are in [`backend/engines/lines.py`](backend/engines/lines.py).
- **Art:** replace any PNG and keep `static/assets/manifest.json` in sync. See
  [ASSETS.md](ASSETS.md). The sprite gallery at **/sprites.html** previews everything.
- **Sounds:** off by default. Drop files in `static/assets/audio/` and list them in
  `sounds.json` (e.g. `"pop": "pop.ogg"`, `"music": "music.ogg"`); unlisted sounds
  use tiny built-in chiptune blips.
- **Colours:** `static/css/palette.css` (same palette as the placeholder art).

## Developer pages

- **/dev.html**: a bare test page that runs upload > analyze > event stream without the pixel UI.
- **/sprites.html**: sprite gallery (zoom, pause, missing-file preview).
- **/api/docs**: interactive API docs (FastAPI).

## Project layout

```
app.py                  start here: serves the API and the static frontend
config.env              settings (port, upload limit, ...)
backend/
  api.py                HTTP routes (the frontend contract, see API.md)
  jobs.py               job registry + replayable event log for SSE
  files.py              upload storage, row/column counting
  exporters.py          .zip and .ipynb exports
  sample_data.py        the sample CSV
  engines/
    base.py             Engine interface
    local.py            the cats: real statistics over every row
    lines.py            the cats' progress lines and chat voices
static/
  index.html, copy.js
  css/                  palette, base app, chat, office, drawer, sprites
  js/
    main.js             entry point
    api.js              API client (the only file that knows URLs)
    bus.js              tiny event bus between modules
    flow.js             conversation flow: upload > sloth > delegate > events
    chat.js             chat panel rendering, drag & drop
    office.js           office scene: sloth, desks, bars, flying papers
    drawer.js           results drawer: cards, downloads
    picker.js           upload dialog: columns, target, row filter
    chart.js            pixel charts on canvas
    syntax.js           tiny syntax highlighter
    sprites.js          sprite engine (reads the manifest)
    sound.js            sound hooks (muted by default)
    header.js, mood.js, ui.js
  assets/               sprites, avatars, ui icons, fonts, audio, manifest.json
tools/
  generate_placeholders.py   draws the placeholder pixel art + manifest
tests/                  python -m unittest discover tests
```

## Troubleshooting

- **"Python was not found"** (Windows): reinstall Python with "Add to PATH" ticked,
  or disable the Microsoft Store alias under *Settings > Apps > App execution aliases*.
- **Port already in use:** `python app.py --port 9000`, or change `PORT` in `config.env`.
- **The page looks squashed:** the layout targets windows at least 1100 px wide.
- **Text looks like a normal monospace font:** the pixel font isn't installed (see above).

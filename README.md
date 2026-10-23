# Purrfessorrr Slothhh

A local-first, pixel-art helper for data scientists. Drop a CSV into the chat;
Professor Slothhh (a very lazy sloth) delegates the work to five cats, and each
cat reports back with findings, charts, explanations, code and cleaning steps.

> The sloth typed "Purrfessor Sloth" and left his finger on the keys too long.

Everything runs on your machine; the app makes no external network requests.
The cats read **every row** of your file and report real statistics (missing
values, IQR outliers, duplicates, type problems, distributions, correlations),
using only the Python standard library. Optionally, **Gemma 3 (4B)** running in
[Ollama](https://ollama.com) on the same computer helps the chat explain things
and read unusual questions. Gemma is not bundled: install it separately (below),
or skip it and the chat uses its built-in rules.

| Cat | Job |
|---|---|
| Detective Cat | data quality: outliers, duplicates, type problems |
| Artist Cat | chart selection and rendering |
| Scribe Cat | plain-English explanations and documentation |
| Coder Cat | Python and R code snippets |
| Janitor Cat | preprocessing and cleaning (missing values, encoding) |

## How it fits together

```
browser (static/)  --HTTP + SSE-->  FastAPI (backend/api.py)  -->  engine (backend/engines/)
                                                                     |  analysis: plain Python over every row
                                                                     |  chat: rules first, then Gemma
                                                                     +--HTTP-->  Ollama on 127.0.0.1:11434 (gemma3:4b)
```

- **Analysis is deterministic.** On upload, `analyse()` profiles every column and the five cats
  turn the facts into cards (charts, tables, Python and R code). No language model is involved,
  so the same file always gets the same report. The checks are listed in [EDA.md](EDA.md).
- **The chat picks a path for each message** (`GemmaEngine._answer` in `backend/engines/gemma.py`):
  1. *Sure things go to the rules:* chart edits ("use 30 bins", "undo"), a named statistic ("highest
     traffic_volume"), "do I need matplotlib?" (answered from the generated code's real imports).
     Messages are cleaned up first (`thank youuu` -> `thank you`, `avrage totl` -> `average total`).
  2. *Discussions go to Gemma:* why / explain questions, advice ("best", "make sense", "limitations",
     "useful") and machine-learning words (LSTM, forecasting, random forest, ...). Gemma gets the
     file's facts (size, target and task, time span, column summaries, correlations, the cards, what
     the code imports and how the baseline splits the data) and the last three turns, never the rows.
  3. *Everything else goes to the rules.* If they cannot really answer, a follow-up to the last
     discussion ("does it need a GPU?") goes back to Gemma; otherwise Gemma reads the message as a
     JSON tool request that the backend checks against the file. Lookups are answered and say how
     the message was read ("reading that as 'what is the lowest temp?'"), chart changes ask first,
     and vague messages ("is it ok?") get a question back instead of a guess.
- **Numbers about your file always come from Python.** In Gemma's answers, any sentence about the
  file (its columns, rows, missing values, scores, ...) whose numbers are not in Python's facts is
  removed, with a note. General numbers ("hold out the last 20%") are fine.
- **Fallback:** if Ollama is not running, the rules answer what they can; questions only the model
  can answer get a plain "that needs my language model" instead of an unrelated reply.

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

### Gemma and Ollama (optional)

The app works without them; with them, the chat can explain concepts and code. Gemma 3 4B needs
about 3.5 GB of disk and 4 GB of free memory (graphics memory if you have a GPU; it also runs on a CPU,
slowly). On a weaker computer use `gemma3:1b` (1 GB) by setting `OLLAMA_MODEL=gemma3:1b`: it explains
less accurately and misreads more questions.

1. **Install Ollama**
   - Windows: download the installer from <https://ollama.com/download>, or `winget install Ollama.Ollama`.
   - macOS: download the app from <https://ollama.com/download>, or `brew install ollama`.
   - Linux: `curl -fsSL https://ollama.com/install.sh | sh`
2. **Download the model** (once): `ollama pull gemma3:4b`
3. **Check it:**
   ```bash
   ollama list                          # gemma3:4b should be listed
   ollama run gemma3:4b "Say hi in five words"
   curl http://127.0.0.1:11434/api/tags # the HTTP API the app uses
   ```
4. **Keep Ollama running.** The Windows and macOS apps start it in the background (tray / menu bar
   icon). On Linux the installer sets up a service; otherwise run `ollama serve` in a terminal.
5. **Start the app** as usual (`run.bat`, `./run.sh`). The terminal prints `gemma: gemma3:4b is loaded`,
   or what is missing. Settings (gear icon) shows the engine.

The app loads the model in the background at start-up, so the first answer after a reboot can
take up to a minute; after that, answers take a few seconds. It never downloads the model.

To turn Gemma off, set `ENGINE=local` in `config.env`.

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
   with tap-to-answer buttons. You can also ask what is inside: "what holidays
   are there?" (lists a column's values with counts), "what columns are there?",
   "show me some rows", "how many Labor Day". Questions about the generated
   code are answered from the code itself ("what seed does it use?", "which
   libraries?", "what model?", "show me the code to load the data"), the cards can
   be asked about ("what does the histogram show?"), and the sloth also handles
   greetings, "how is the health score calculated?", "are you an AI?" (no: the
   cats just count) and "say that again". Typos and stretched words are fine
   ("thank youuu", "whats the avrage totl"), and vague questions get a
   question back ("what about the other column?" -> "which one did you mean?").
6. **Change the histogram from the chat:** "use 30 bins", "more bins", "show the
   distribution of rating", "change the title to Daily sales and the x label to
   Units", "undo", "regenerate the Python code with these settings". The chart is
   re-drawn from its spec and its Python and R code are rebuilt; the rest of the
   analysis is not re-run and your file is never changed. Other chart kinds
   (box plots, ...) can't be changed from the chat yet.
7. **With Gemma on**, also ask why and how: "why do I need pandas?", "why did you
   recommend this cleaning method?", "what's the difference between mean and
   median?", "explain that again".

The top-right gear opens settings: day/night theme, sound effects (off by default) and a sample CSV.

Text uses your system's monospace font (`ui-monospace`: Cascadia Mono or
Consolas on Windows), so there is nothing to download.

## Configuration

Edit **`config.env`** (environment variables with the same name override it):

| Setting | Default | Meaning |
|---|---|---|
| `HOST`, `PORT` | `127.0.0.1`, `8765` | Where the server listens (localhost only). |
| `OPEN_BROWSER` | `true` | Open a browser tab on start. |
| `MAX_UPLOAD_MB` | `200` | Upload size limit. |
| `UPLOAD_DIR` | `data/uploads` | Where uploads are stored (git-ignored). |
| `CAT_SPEED` | `1.0` | Cat animation multiplier (`0.3` = fast demo). The numbers are real either way. |
| `ENGINE` | `local` (`gemma` in the shipped `config.env`) | `gemma` adds Gemma to the chat; `local` is rules only. |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Where Ollama listens. Must be this computer (`127.0.0.1`, `localhost` or `::1`): the prompts describe your data. |
| `OLLAMA_MODEL` | `gemma3:4b` | Any model you have pulled, e.g. `gemma3:1b` (smaller and faster, weaker answers). |
| `OLLAMA_TIMEOUT` | `45` | Seconds to wait for one answer before the rules answer instead. |

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
- `node scripts/check-image-sizes.js`: checks every sprite PNG against `manifest.json` after art changes.

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
    local.py            the cats: real statistics over every row, and the chat routing
    gemma.py            Gemma via Ollama: explanations, checked tool requests, fallback
    rcode.py            the R versions of the cats' code snippets
    talk.py             chat helpers: small talk, code questions, finding a card
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
scripts/
  check-image-sizes.js       PNG sizes vs manifest.json (node, no packages)
EDA.md                  the baseline analysis: every check, when it runs, how
tests/                  python -m unittest discover tests
```

## Tests

```bash
.venv/Scripts/python -m unittest discover tests
```

(On macOS / Linux: `.venv/bin/python`.) The R tests run the generated R with `Rscript` and are
skipped without R. One Gemma test asks the real model a question and is skipped when Ollama with
the configured model is not running; the other Gemma tests use a stand-in, so the suite needs no model.
The real-model tests only check that an answer arrives from the right cat on the right subject:
a model's wording changes, so they cannot prove an answer is correct.

## Licences

**Gemma** is not included in this project and is not redistributed by it: Ollama downloads it to
your computer, and using it means accepting Google's [Gemma Terms of Use](https://ai.google.dev/gemma/terms)
and [Prohibited Use Policy](https://ai.google.dev/gemma/prohibited_use_policy). If you ever ship the
model with the app, you must pass those terms on to your users. **Ollama** is MIT-licensed.

## Troubleshooting

- **"Python was not found"** (Windows): reinstall Python with "Add to PATH" ticked,
  or disable the Microsoft Store alias under *Settings > Apps > App execution aliases*.
- **Port already in use:** `python app.py --port 9000`, or change `PORT` in `config.env`.
- **The page looks squashed:** the layout targets windows at least 1100 px wide.
- **Text looks like a normal monospace font:** the pixel font isn't installed (see above).
- **"ollama is not running"** in the chat: start the Ollama app (or `ollama serve`), then ask again
  (the app retries after 30 seconds). Check with `curl http://127.0.0.1:11434/api/tags`.
- **"ollama has no gemma3:4b model":** run `ollama pull gemma3:4b`, and make sure `OLLAMA_MODEL`
  matches a name in `ollama list`.
- **"took more than 45 s":** the model was still loading (first answer after a reboot) or the
  computer is busy. Ask again, or raise `OLLAMA_TIMEOUT`.
- **Out of memory / "model requires more system memory":** close other programs, or stay with
  switch to `OLLAMA_MODEL=gemma3:1b` (bigger Gemma models need more). `ENGINE=local` works with no model at all.
- **"i left out a sentence that quoted a number about your file":** Gemma said something about your
  file with a number Python never computed, so that sentence was removed. Working as intended.
- **Gemma's advice sounds confident but wrong:** a small local model can misjudge things that have
  no number to check (it once called six years of hourly data "short"). Treat its suggestions as
  ideas to test; the cards and statistics are the facts.

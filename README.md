<div align="center">

<img src="images/sloth.png" alt="Purrrfessorrr Slothhh logo: a muscular pixel-art sloth" width="180" height="180">

# Purrrfessorrr Slothhh

**Upload a dataset. A lazy sloth delegates. Five cats do the actual work.**

[![Hacktoberfest 2026](https://img.shields.io/badge/Hacktoberfest-2026-orange?labelColor=383838&style=for-the-badge)](https://hacktoberfest.com/)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&labelColor=383838&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?labelColor=383838&style=for-the-badge&logo=fastapi&logoColor=white)
![Local-first](https://img.shields.io/badge/Privacy-Local--first-6A8563?labelColor=383838&style=for-the-badge)
![Gemma 3](https://img.shields.io/badge/AI-Gemma%203%20(optional)-836F9C?labelColor=383838&style=for-the-badge)

[Quick start](#quick-start) · [The team](#the-team) · [How it works](#how-it-works) · [Contribute](CONTRIBUTING.md)

<!-- SCREENSHOT: add a wide shot at docs/images/hero.png (the office, the sloth, the cats at work) and uncomment:
![The pixel-art office](docs/images/hero.png)
-->

</div>

---

## Why this exists

Every exploratory analysis starts the same way: check for nulls, hunt duplicates, plot a few histograms, copy-paste the same boilerplate. It's necessary, and it's rarely the interesting part.

**Purrrfessorrr Slothhh** turns that routine into a tiny office. Drop in a CSV, TSV, or XLSX, pick what matters, and Professor Slothhh hands the job to five specialist cats. Open their desks to see real statistics, charts, plain-English explanations, and code you can reuse.

The sloth is lazy. The analysis isn't.

## What you get

- 🔎 **Data quality checks:** missing values, duplicates, type problems, IQR outliers.
- 📊 **Charts and summaries** generated from your actual data.
- 🧹 **Cleaning suggestions** for missing values and preprocessing.
- 💻 **Python and R snippets** attached to each analysis card.
- 💬 **Chat** about any column, chart, or outlier.
- 📦 **Export** everything as a ZIP or a Jupyter notebook.

You control the scope: choose columns, set a prediction target, and exclude rows before anything runs.

> **The numbers are never made up.** All statistics come from deterministic Python routines. The optional Gemma model only explains results; it never computes them, and it sees a summary of findings, not your raw rows.

## 🐈 Meet the team

| Character | Job |
| :-- | :-- |
| **Professor Slothhh** | Greets you, delegates, keeps the office running |
| **Detective Cat** | Data quality: duplicates, outliers, suspicious types |
| **Artist Cat** | Charts that make patterns obvious |
| **Scribe Cat** | Plain-language summaries of what was found |
| **Coder Cat** | Reusable Python and R |
| **Janitor Cat** | Cleaning and missing-value strategies |

<!-- SCREENSHOT: add docs/images/cats.png (a cropped lineup of the cats at their desks) -->

## Quick start

You need Python 3.10+, a desktop browser (best at 1100px wide or more), and internet access for the first dependency install.

**Windows**

```powershell
git clone https://github.com/ashtonckj/Purrrfessorrr-Slothhh.git
cd Purrrfessorrr-Slothhh
.\run.bat
```

**macOS / Linux**

```bash
git clone https://github.com/ashtonckj/Purrrfessorrr-Slothhh.git
cd Purrrfessorrr-Slothhh
chmod +x run.sh
./run.sh
```

Open **http://127.0.0.1:8765** if your browser doesn't launch on its own.

<details>
<summary>Manual installation</summary>

```bash
python -m venv .venv
```

**Windows:**

```powershell
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

**macOS / Linux:**

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

</details>

### Optional: richer chat with Gemma 3

Without a model, the app still runs the full analysis and answers common questions with built-in rules. To unlock open-ended explanations:

1. Install [Ollama](https://ollama.com/download).
2. Run `ollama pull gemma3:4b`.
3. Keep Ollama running and start the app as usual.
4. Check engine status in the app's settings.

Defaults live in `config.env` (`ENGINE=gemma`, `OLLAMA_MODEL=gemma3:4b`). Set `ENGINE=local` for rules-only chat, or use `gemma3:1b` on low-memory machines (faster, less capable).

Model weights are not bundled. Ollama downloads them separately under [Google's Gemma terms](https://ai.google.dev/gemma/terms).

## Using it

1. **Upload** a `.csv`, `.tsv`, or `.xlsx` by dragging it into the chat. Sample data is available in settings.
2. **Customize** columns, target, and row exclusions after previewing.
3. **Watch** the cats work through their tasks.
4. **Explore** results in the drawer: charts, previews, quality findings, code.
5. **Ask** questions, such as:
   - *Which columns have missing values?*
   - *Tell me about the outliers.*
   - *What does this histogram show?*
   - *Which libraries does the generated code use?*
6. **Export** as a ZIP or notebook.

Open-ended questions work best with Gemma enabled; without it, the app says so and falls back to its rules.

<!-- SCREENSHOT: add docs/images/results.png (a chart next to its code in the results drawer) -->

## How it works

```text
Browser (pixel-art UI, vanilla JS)
   │  HTTP + Server-Sent Events
   ▼
FastAPI server (backend/api.py)
   ├── uploads, previews, jobs, exports
   ├── deterministic EDA (backend/engines/local.py)
   │     statistics, charts, cleaning insights, code
   └── chat routing (backend/engines/gemma.py)
         ├── rule-based answers and validated operations
         └── optional Ollama → Gemma 3 on localhost
```

Files are analyzed on your machine. More detail in [EDA.md](EDA.md), [API.md](API.md), and [ASSETS.md](ASSETS.md).

## Contributing

Bug fixes, docs, accessibility improvements, new charts, and pixel art are all welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md).

## Built by

Made for **Hacktoberfest 2026, Open-Source AI Challenge, Week 3: "Slow and Steady"** by
[@ashtonckj](https://github.com/ashtonckj), [@fionakhl](https://github.com/fionakhl), and [@JocelynKoh3](https://github.com/JocelynKoh3).

## 📜 License and acknowledgements

See [LICENSE](LICENSE). Third-party code, fonts, art, and model weights may carry their own terms. Ollama is a separate project.

## 🎨 Credits & Acknowledgements

This project wouldn't feel quite the same without its charming collection of pixel art illustrations! ✨

Special thanks to the talented artists and creative communities whose artwork helped shape the application's visual identity.

Visual assets were sourced from Freepik, Dreamstime, Vecteezy, Pixel Art Maker, Pinterest, and other online resources.

**🖼️ [View Full Asset Credits & Attribution](./ASSETS.md)**

All third-party artwork belongs to its respective copyright holders and is subject to its own licensing terms.

Made with ☕, creativity, and a little pixel magic. 💛

---

<div align="center">

**Less boilerplate. More curiosity. A few more cat naps.** 🦥💤

⭐ If this project made your data science day a little easier, consider starring the repository!

</div>
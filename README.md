<div align="center">

# 🦥 Purrrfessorrr Slothhh 🐱

### Your data is complicated. Your study buddies don't have to be.

**A cozy, pixel-art, local-first data science assistant powered by five hardworking cats, one sleepy sloth, and optional open-weight AI.**

[![Hacktoberfest 2026](https://img.shields.io/badge/Hacktoberfest-2026-orange?style=for-the-badge)](https://hacktoberfest.com/)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Local-first](https://img.shields.io/badge/Privacy-Local--first-7D9D75?style=for-the-badge)
![Gemma 3](https://img.shields.io/badge/AI-Gemma%203%20(optional)-B8A2D6?style=for-the-badge)

[**Get started**](#-quick-start) · [**Meet the cats**](#-meet-the-team) · [**How it works**](#-under-the-hood) · [**Contribute**](CONTRIBUTING.md)

<!-- SCREENSHOT: Add a wide screenshot at docs/images/hero.png and uncomment the next line. -->
<!-- ![The pixel-art office, Professor Slothhh, and five specialist cats](docs/images/hero.png) -->

</div>

---

## ✨ The idea

Exploratory data analysis can mean repetitive checks, chart-building, cleaning decisions, and writing boilerplate code before you even reach the interesting questions.

**Purrrfessorrr Slothhh** turns that workflow into a little pixel-art office. Upload a dataset, choose what to analyze, and watch Professor Slothhh delegate the work to five specialist cats. Open their results to inspect actual statistics, visualizations, explanations, and reusable code.

The sloth may be lazy. **The analysis isn't.**

## 🌟 Highlights

- 📂 **Upload CSV, TSV, or XLSX** and preview your data before starting.
- 🎛️ **Customize the analysis** by selecting columns, a prediction target, and row-exclusion rules.
- 🔎 **Explore data quality** including missing values, duplicates, type issues, and IQR outliers.
- 📊 **Inspect visualizations and summaries** produced from the dataset.
- 🧹 **Review preprocessing suggestions** from the Janitor Cat.
- 💻 **Get Python and R snippets** alongside relevant analysis cards.
- 💬 **Ask follow-up questions** in the chat, with optional local Gemma 3 assistance.
- 📦 **Export results** as a ZIP archive or Jupyter notebook.
- 🔐 **Keep processing local**; no hosted LLM API is required.

> **Accuracy by design:** Core exploratory analysis is computed by deterministic Python routines. Gemma is an optional language layer for explanations and more flexible conversation—not the source of statistical results.

## 🐈 Meet the team

| Character | Specialty | What they help with |
| :-- | :-- | :-- |
| 🦥 **Professor Slothhh** | Delegation | Welcomes you, routes work, and keeps the office moving. |
| 🕵️ **Detective Cat** | Data quality | Finds duplicates, outliers, and suspicious types. |
| 🎨 **Artist Cat** | Visualization | Builds charts to make patterns easier to spot. |
| 📝 **Scribe Cat** | Explanation | Summarizes findings in approachable language. |
| 💻 **Coder Cat** | Reusable code | Supplies Python and R examples. |
| 🧽 **Janitor Cat** | Cleaning | Suggests preprocessing and missing-value handling. |

<!-- SCREENSHOT: Add docs/images/cats.png: a cropped lineup of the five cats and their desks. -->

## 🚀 Quick start

**Requirements:** Python **3.10+**, a modern desktop browser (best at **1100px+**), and an internet connection for the initial Python dependency installation. Ollama is **optional**.

### Windows

Clone the repository and run `run.bat`:

```powershell
git clone https://github.com/ashtonckj/Purrrfessorrr-Slothhh.git
cd Purrrfessorrr-Slothhh
.\run.bat
```

### macOS / Linux

```bash
git clone https://github.com/ashtonckj/Purrrfessorrr-Slothhh.git
cd Purrrfessorrr-Slothhh
chmod +x run.sh
./run.sh
```

Then open **http://127.0.0.1:8765** if the browser does not open automatically.

<details>
<summary><strong>Manual installation</strong></summary>

Create a virtual environment, install dependencies, and start the server:

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

### 🧠 Optional: run Gemma 3 locally

Without a model, the app still performs its deterministic analysis and supports rule-based chat. To enable richer explanations:

1. Install [Ollama](https://ollama.com/download).
2. Download the model: `ollama pull gemma3:4b`.
3. Ensure Ollama is running; then start the app normally.
4. Check the engine status in the app's settings.

The default configuration uses `ENGINE=gemma` and `OLLAMA_MODEL=gemma3:4b` in `config.env`. For rules-only chat, set `ENGINE=local`. A smaller model, `gemma3:1b`, is an option for lower-memory machines, though its responses may be less capable.

> Gemma model weights are **not bundled** with this repository. They are downloaded separately through Ollama and subject to Google's Gemma terms.

## 🎮 How to use

1. **Upload:** Drag a `.csv`, `.tsv`, or `.xlsx` file into the chat, or use the attachment control. You can also download sample data from settings.
2. **Customize:** Preview the dataset, choose columns, optionally select a target, and configure row exclusions.
3. **Start the cats:** Watch each specialist process their part of the workflow.
4. **Explore:** Open the results drawer for charts, data previews, quality findings, and code.
5. **Ask:** Chat about a column, an outlier, a chart, or the generated code.
6. **Export:** Download the analysis as a ZIP or Jupyter notebook.

<!-- SCREENSHOT: Add docs/images/upload-dialog.png showing column/target/exclusion choices. -->
<!-- SCREENSHOT: Add docs/images/results.png showing a chart and its code in the results drawer. -->

### 💬 Things to ask

```text
What columns are in my dataset?
Which columns have missing values?
Tell me about the outliers.
What does this histogram show?
Which libraries does the generated code use?
Can you explain why this chart is useful?
```

Some conversational questions require the optional Gemma model; without it, the app uses its built-in rules and explains when a model is needed.

## 🏗️ Under the hood

```text
Browser: pixel-art UI (static/)
           │ HTTP + Server-Sent Events
           ▼
FastAPI server (backend/api.py)
           │
           ├── Uploads, previews, jobs, and exports
           │
           ├── Deterministic EDA (backend/engines/local.py)
           │      └── Statistics, charts, cleaning insights, code
           │
           └── Chat routing (backend/engines/gemma.py)
                  ├── Rule-based answers and validated operations
                  └── Optional Ollama → Gemma 3 on localhost
```

The app uses **FastAPI**, **vanilla JavaScript**, and **Python**. Uploaded files are analyzed locally; the core statistical pipeline does not depend on the language model. Gemma receives a structured summary of computed findings for explanation rather than raw dataset rows.

For implementation details, see [EDA.md](EDA.md), [API.md](API.md), and [ASSETS.md](ASSETS.md).

## 📁 Project map

```text
Purrrfessorrr-Slothhh/
├── app.py                    # Application entry point
├── backend/
│   ├── api.py                # FastAPI routes
│   ├── engines/              # Local analysis, Gemma, chat, code
│   ├── files.py              # File handling
│   └── exporters.py          # Download/export logic
├── static/                   # Frontend, pixel art, scripts
├── tests/                    # Automated tests
├── tools/                    # Asset generation utilities
├── config.env                # Local configuration
├── requirements.txt
├── EDA.md                    # Statistical methods
├── API.md                    # Backend API reference
└── ASSETS.md                 # Pixel-art asset guide
```

## 🧪 Testing

With dependencies installed, run:

```bash
python -m unittest discover tests
```

Some optional integration tests require R or a running Ollama model; tests designed for those tools may be skipped when unavailable.

## 🤝 Contributing

Bug fixes, documentation improvements, accessibility work, new charts, and pixel-art contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

## 👥 The humans behind the cats

Built for **Hacktoberfest 2026 — Open-Source AI Challenge, Week 3: Slow and Steady** by:

- [@ashtonckj](https://github.com/ashtonckj)
- [@fionakhl](https://github.com/fionakhl)
- [@JocelynKoh3](https://github.com/JocelynKoh3)

## 📜 License and acknowledgements

See [LICENSE](LICENSE) for the project's license **once the team has agreed to and added it**. Third-party code, fonts, art, and model weights may have their own terms. Gemma is provided separately under [Google's Gemma terms](https://ai.google.dev/gemma/terms); Ollama is a separate project.

---

<div align="center">

**Less boilerplate. More curiosity. A few more cat naps.** 🦥💤

⭐ If this project made your data science day a little easier, consider starring the repository!

</div>

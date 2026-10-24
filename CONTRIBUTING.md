# 🤝 Contributing to Purrrfessorrr Slothhh

Thanks for helping the cats make data science friendlier! Contributions of all sizes are welcome.

## Before you start

- Check existing issues and pull requests to avoid duplicate work.
- For a larger change, open an issue describing your approach first.
- Be respectful and constructive in discussions and reviews.
- Do not upload private datasets, credentials, or secrets in issues or pull requests.

## Ways to help

- Fix bugs and improve error messages.
- Add tests for tricky CSV/TSV/XLSX inputs.
- Improve charts, keyboard accessibility, and responsive layouts.
- Clarify documentation or add reproducible examples.
- Improve or contribute original pixel art, with clear asset licensing.

## Local setup

```bash
git clone https://github.com/ashtonckj/Purrrfessorrr-Slothhh.git
cd Purrrfessorrr-Slothhh
python -m venv .venv
```

On Windows, run `.venv\Scripts\python -m pip install -r requirements.txt`; on macOS/Linux run `.venv/bin/python -m pip install -r requirements.txt`. Start the app with `run.bat` or `./run.sh` as appropriate. Ollama is optional for most development.

## Pull request workflow

1. Fork the repository and create a descriptive branch, e.g. `fix/upload-preview`.
2. Make a focused change and include tests where practical.
3. Run `python -m unittest discover tests` (using your virtual environment's Python if needed).
4. Update `README.md`, `EDA.md`, `API.md`, or `ASSETS.md` if your change affects documented behavior.
5. Open a pull request explaining what changed, why, and how you tested it. Add before/after screenshots for UI changes.

## Project conventions

- Keep computed dataset statistics in deterministic Python code; do not rely on LLM-generated numerical claims.
- Preserve local-first behavior and avoid introducing cloud data transmission without explicit discussion.
- Keep frontend changes compatible with the existing vanilla-JavaScript structure.
- If modifying sprites, follow `ASSETS.md` and check asset dimensions/manifest entries.
- Do not commit generated uploads, local logs, environment secrets, or virtual environments.

## Reporting bugs

Include your operating system, Python version, steps to reproduce, expected versus actual behavior, and relevant non-sensitive logs. A small synthetic dataset is ideal for data-dependent bugs.

## Community

Please be kind and assume good intent. Maintainers may request changes before merging, and hackathon timelines can affect review speed.

Thanks for contributing! 🐱

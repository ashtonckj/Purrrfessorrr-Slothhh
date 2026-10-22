#!/usr/bin/env sh
# Purrfessorrr Slothhh - macOS / Linux launcher.
# Creates .venv on first run, installs requirements, starts the app (opens your browser).
set -e
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
command -v "$PY" >/dev/null 2>&1 || { echo "python3 not found. Install Python 3.10+."; exit 1; }

if [ ! -x .venv/bin/python ]; then
  echo "Creating virtual environment..."
  "$PY" -m venv .venv
fi

echo "Installing requirements (first run takes a minute)..."
.venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt

exec .venv/bin/python app.py "$@"

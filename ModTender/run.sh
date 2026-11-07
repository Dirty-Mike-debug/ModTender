#!/usr/bin/env sh
# Start ModTender from source on Linux (or macOS). The first run sets up its own Python environment.
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "Setting up ModTender (first run only)..."
  python3 -m venv .venv || { echo "Install Python 3.10+ and python3-venv first."; exit 1; }
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -r requirements.txt || exit 1
fi
exec .venv/bin/python main.py "$@"

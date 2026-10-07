#!/bin/bash
# Mac: double-click to open Combo Manager. (Linux: use combo-manager.sh, which is the same.)
cd "$(dirname "$0")" || exit 1
VENV="$HOME/.combo-scheduler-python"          # private Python for the scheduler, outside the synced folder

has_tk() { "$1" -c "import tkinter; tkinter.Tcl()" >/dev/null 2>&1; }   # can this Python show windows?

# A private Python made earlier from a Python without tkinter (e.g. Homebrew's) can't show the window: start over.
if [ -x "$VENV/bin/python" ] && ! has_tk "$VENV/bin/python"; then
  echo "The scheduler's Python can't show windows (no tkinter): setting it up again..."
  rm -rf "$VENV"
fi
if [ ! -x "$VENV/bin/python" ]; then
  # The python.org installer's Python first (it always has tkinter), then any other python3.
  PY=""
  for p in /Library/Frameworks/Python.framework/Versions/3.*/bin/python3 /usr/local/bin/python3 $(which -a python3 2>/dev/null); do
    if [ -x "$p" ] && has_tk "$p"; then PY="$p"; break; fi
  done
  if [ -z "$PY" ]; then
    echo "No Python 3 that can show windows was found. Install Python from https://www.python.org/downloads/"
    echo "(the macOS installer; Homebrew's Python lacks tkinter), then double-click this again."
    read -r -p "Press Enter to close."; exit 1
  fi
  echo "First run: setting up Python for the scheduler (only once), from $PY ..."
  if ! "$PY" -m venv "$VENV"; then
    echo "Couldn't set up Python."
    read -r -p "Press Enter to close."; exit 1
  fi
fi
"$VENV/bin/python" app/scheduler_app.py

#!/bin/bash
# Linux: double-click (choose "Run") or run ./make-schedule.sh to open the Combo Scheduler window.
cd "$(dirname "$0")" || exit 1
VENV="$HOME/.combo-scheduler-python"          # private Python for the scheduler, outside the synced folder

has_tk() { "$1" -c "import tkinter; tkinter.Tcl()" >/dev/null 2>&1; }   # can this Python show windows?

# A private Python made earlier from a Python without tkinter can't show the window: start over.
if [ -x "$VENV/bin/python" ] && ! has_tk "$VENV/bin/python"; then
  echo "The scheduler's Python can't show windows (no tkinter): setting it up again..."
  rm -rf "$VENV"
fi
if [ ! -x "$VENV/bin/python" ]; then
  PY=""
  for p in $(which -a python3 2>/dev/null); do
    if has_tk "$p"; then PY="$p"; break; fi
  done
  if [ -z "$PY" ]; then
    echo "No Python 3 that can show windows was found. On Linux: sudo apt install python3 python3-tk python3-venv"
    read -r -p "Press Enter to close."; exit 1
  fi
  echo "First run: setting up Python for the scheduler (only once), from $PY ..."
  if ! "$PY" -m venv "$VENV"; then
    echo "Couldn't set up Python. On Linux: sudo apt install python3-venv python3-tk"
    read -r -p "Press Enter to close."; exit 1
  fi
fi
"$VENV/bin/python" app/scheduler_app.py

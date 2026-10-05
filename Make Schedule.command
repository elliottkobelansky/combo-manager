#!/bin/bash
# Mac: double-click to open the Combo Scheduler window. (Linux: use make-schedule.sh, which is the same.)
cd "$(dirname "$0")" || exit 1
VENV="$HOME/.combo-scheduler-python"          # private Python for the scheduler, outside the synced folder
if [ ! -x "$VENV/bin/python" ]; then
  if ! command -v python3 >/dev/null; then
    echo "Python 3 isn't installed. Get it from https://www.python.org/downloads/ and double-click this again."
    read -r -p "Press Enter to close."; exit 1
  fi
  echo "First run: setting up Python for the scheduler (only once)..."
  if ! python3 -m venv "$VENV"; then
    echo "Couldn't set up Python. On Linux: sudo apt install python3-venv python3-tk"
    read -r -p "Press Enter to close."; exit 1
  fi
fi
"$VENV/bin/python" app/scheduler_app.py
